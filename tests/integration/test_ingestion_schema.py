"""Rules the database itself enforces for ingestion tables (docs/database-design.md)."""

from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import Document, DocumentVersion, IngestionJob, IngestionJobEvent
from tests.integration.factories import (
    make_batch,
    make_document,
    make_job,
    make_job_chain,
    make_tenant,
    make_version,
)

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


async def expect_violation(
    session_factory: Factory,
    constraint: str,
    act: Callable[[AsyncSession], Awaitable[object]],
) -> None:
    async with session_factory() as session:
        with pytest.raises(IntegrityError, match=constraint):
            await act(session)
            await session.flush()


# ------------------------------------------------------------- tenant isolation


async def test_version_cannot_point_at_another_tenants_document(session_factory: Factory) -> None:
    async with session_factory() as session:
        acme, globex = await make_tenant(session), await make_tenant(session)
        acme_doc = await make_document(session, acme.id)
        await session.commit()

    await expect_violation(
        session_factory,
        "fk_document_versions_document",
        lambda s: make_version(s, globex.id, acme_doc.id),  # Globex row, Acme document
    )


async def test_job_cannot_point_at_another_tenants_version(session_factory: Factory) -> None:
    async with session_factory() as session:
        acme, globex = await make_tenant(session), await make_tenant(session)
        doc = await make_document(session, acme.id)
        version = await make_version(session, acme.id, doc.id)
        await session.commit()

    await expect_violation(
        session_factory, "fk_ingestion_jobs_version", lambda s: make_job(s, globex.id, version.id)
    )


async def test_job_cannot_use_another_tenants_batch(session_factory: Factory) -> None:
    async with session_factory() as session:
        acme, globex = await make_tenant(session), await make_tenant(session)
        doc = await make_document(session, acme.id)
        version = await make_version(session, acme.id, doc.id)
        globex_batch = await make_batch(session, globex.id)
        await session.commit()

    await expect_violation(
        session_factory,
        "fk_ingestion_jobs_batch",
        lambda s: make_job(s, acme.id, version.id, batch_id=globex_batch.id),
    )


async def test_current_version_must_belong_to_the_same_tenant(session_factory: Factory) -> None:
    async with session_factory() as session:
        acme, globex = await make_tenant(session), await make_tenant(session)
        acme_doc = await make_document(session, acme.id)
        globex_doc = await make_document(session, globex.id)
        globex_version = await make_version(session, globex.id, globex_doc.id)
        await session.commit()

    async def point_acme_doc_at_globex_version(s: AsyncSession) -> None:
        await s.execute(
            update(Document)
            .where(Document.id == acme_doc.id)
            .values(current_version_id=globex_version.id)
        )

    await expect_violation(
        session_factory, "fk_documents_current_version", point_acme_doc_at_globex_version
    )


# ------------------------------------------------------------- dedupe and identity


async def test_same_bytes_twice_in_a_tenant_is_rejected(session_factory: Factory) -> None:
    async with session_factory() as session:
        tenant = await make_tenant(session)
        doc_a = await make_document(session, tenant.id)
        doc_b = await make_document(session, tenant.id)
        await make_version(session, tenant.id, doc_a.id, content=b"same bytes")
        await session.commit()

    await expect_violation(
        session_factory,
        "uq_document_versions_tenant_checksum_live",
        lambda s: make_version(s, tenant.id, doc_b.id, content=b"same bytes"),
    )


async def test_same_bytes_in_different_tenants_is_fine(session_factory: Factory) -> None:
    async with session_factory() as session:
        for _ in range(2):
            tenant = await make_tenant(session)
            doc = await make_document(session, tenant.id)
            await make_version(session, tenant.id, doc.id, content=b"same bytes")
        await session.commit()


async def test_failed_versions_dont_block_a_reupload(session_factory: Factory) -> None:
    async with session_factory() as session:
        tenant = await make_tenant(session)
        doc = await make_document(session, tenant.id)
        await make_version(session, tenant.id, doc.id, content=b"retry me", status="FAILED")
        await make_version(session, tenant.id, doc.id, content=b"retry me", version_number=2)
        await session.commit()


async def test_external_id_is_unique_among_live_documents(session_factory: Factory) -> None:
    async with session_factory() as session:
        tenant = await make_tenant(session)
        first = await make_document(session, tenant.id, external_id="hr/policy")
        await session.commit()

    await expect_violation(
        session_factory,
        "uq_documents_tenant_external_id_live",
        lambda s: make_document(s, tenant.id, external_id="hr/policy"),
    )

    # After deletion the identifier is free again.
    async with session_factory() as session:
        await session.execute(
            update(Document).where(Document.id == first.id).values(deleted_at=func.now())
        )
        await make_document(session, tenant.id, external_id="hr/policy")
        await session.commit()


# ------------------------------------------------------------- jobs


async def test_only_one_active_job_per_version(session_factory: Factory) -> None:
    async with session_factory() as session:
        job = await make_job_chain(session)
        await session.commit()

    await expect_violation(
        session_factory,
        "uq_ingestion_jobs_one_active_per_version",
        lambda s: make_job(s, job.tenant_id, job.document_version_id),
    )

    # Once the first job is finished, a new run (e.g. re-index) is allowed.
    async with session_factory() as session:
        await session.execute(
            update(IngestionJob).where(IngestionJob.id == job.id).values(status="COMPLETED")
        )
        await make_job(session, job.tenant_id, job.document_version_id)
        await session.commit()


@pytest.mark.parametrize(
    "table,column,value,constraint",
    [
        ("ingestion_jobs", "status", "DONE", "ck_ingestion_jobs_status"),
        ("ingestion_jobs", "checkpoint", "index", "ck_ingestion_jobs_checkpoint"),
        ("document_versions", "status", "LIVE", "ck_document_versions_status"),
        ("documents", "status", "GONE", "ck_documents_status"),
    ],
)
async def test_status_columns_reject_unknown_values(
    session_factory: Factory, table: str, column: str, value: str, constraint: str
) -> None:
    async with session_factory() as session:
        await make_job_chain(session)
        await session.commit()

    async def set_bad_value(s: AsyncSession) -> None:
        # table/column come from the fixed parametrize list above, not from input.
        await s.execute(text(f"UPDATE {table} SET {column} = :v"), {"v": value})  # noqa: S608

    await expect_violation(session_factory, constraint, set_bad_value)


async def test_deleting_a_tenant_removes_all_its_ingestion_rows(session_factory: Factory) -> None:
    async with session_factory() as session:
        job = await make_job_chain(session)
        session.add(
            IngestionJobEvent(
                tenant_id=job.tenant_id, job_id=job.id, to_status="PENDING", attempt=0
            )
        )
        await session.commit()
        await session.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": job.tenant_id})
        await session.commit()

        for model in (Document, DocumentVersion, IngestionJob, IngestionJobEvent):
            assert await session.scalar(select(func.count()).select_from(model)) == 0, model
