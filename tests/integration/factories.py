"""Small helpers to create valid rows in integration tests."""

import hashlib
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentVersion, IngestionBatch, IngestionJob, Tenant


async def make_tenant(session: AsyncSession, slug: str | None = None) -> Tenant:
    tenant = Tenant(slug=slug or f"t-{uuid.uuid4().hex[:8]}", name="Test tenant")
    session.add(tenant)
    await session.flush()
    return tenant


async def make_document(
    session: AsyncSession, tenant_id: uuid.UUID, external_id: str | None = None
) -> Document:
    document = Document(tenant_id=tenant_id, external_id=external_id, title="Doc")
    session.add(document)
    await session.flush()
    return document


async def make_version(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    document_id: uuid.UUID,
    *,
    content: bytes | None = None,
    version_number: int = 1,
    status: str = "PENDING",
) -> DocumentVersion:
    content = content if content is not None else uuid.uuid4().bytes
    version = DocumentVersion(
        tenant_id=tenant_id,
        document_id=document_id,
        version_number=version_number,
        checksum_sha256=hashlib.sha256(content).digest(),
        size_bytes=len(content),
        mime_type="application/pdf",
        original_filename="doc.pdf",
        storage_key=f"tenants/{tenant_id}/documents/{document_id}/{uuid.uuid4()}",
        status=status,
    )
    session.add(version)
    await session.flush()
    return version


async def make_batch(session: AsyncSession, tenant_id: uuid.UUID) -> IngestionBatch:
    batch = IngestionBatch(tenant_id=tenant_id, name="batch")
    session.add(batch)
    await session.flush()
    return batch


async def make_job(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    version_id: uuid.UUID,
    *,
    status: str = "PENDING",
    batch_id: uuid.UUID | None = None,
) -> IngestionJob:
    job = IngestionJob(
        tenant_id=tenant_id, document_version_id=version_id, status=status, batch_id=batch_id
    )
    session.add(job)
    await session.flush()
    return job


async def make_job_chain(session: AsyncSession, status: str = "PENDING") -> IngestionJob:
    """Tenant → document → version → job, all valid and consistent."""
    tenant = await make_tenant(session)
    document = await make_document(session, tenant.id)
    version = await make_version(session, tenant.id, document.id)
    return await make_job(session, tenant.id, version.id, status=status)
