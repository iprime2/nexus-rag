"""CAS transitions, leases and fencing against a real database (docs/ingestion-workflow.md §2)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import IngestionJob, IngestionJobEvent
from app.ingestion.jobs import JobError, claim_job, renew_lease, transition_job
from app.ingestion.state import Checkpoint, InvalidTransitionError, JobStatus
from tests.integration.factories import make_job_chain

pytestmark = pytest.mark.integration

S = JobStatus
Factory = async_sessionmaker[AsyncSession]


async def new_job(session_factory: Factory, status: str = "PENDING") -> uuid.UUID:
    async with session_factory() as session:
        job = await make_job_chain(session, status=status)
        await session.commit()
        return job.id


async def load(session_factory: Factory, job_id: uuid.UUID) -> IngestionJob:
    async with session_factory() as session:
        job = await session.get(IngestionJob, job_id)
        assert job is not None
        return job


async def events(session_factory: Factory, job_id: uuid.UUID) -> list[tuple[str | None, str, int]]:
    async with session_factory() as session:
        rows = await session.execute(
            select(
                IngestionJobEvent.from_status,
                IngestionJobEvent.to_status,
                IngestionJobEvent.attempt,
            )
            .where(IngestionJobEvent.job_id == job_id)
            .order_by(IngestionJobEvent.id)
        )
        return [tuple(row) for row in rows]  # type: ignore[misc]


async def test_full_happy_path_records_every_transition(session_factory: Factory) -> None:
    job_id = await new_job(session_factory)

    async with session_factory() as s:
        assert await transition_job(s, job_id, expected=S.PENDING, target=S.QUEUED)
        claimed = await claim_job(
            s, job_id, expected=S.QUEUED, target=S.EXTRACTING, worker_id="w1", lease_seconds=60
        )
        assert claimed is not None and claimed.attempt == 1
        for current, target in [(S.EXTRACTING, S.CHUNKING), (S.CHUNKING, S.CHUNKED)]:
            assert await transition_job(s, job_id, expected=current, target=target, attempt=1)
        embed = await claim_job(
            s, job_id, expected=S.CHUNKED, target=S.EMBEDDING, worker_id="w2", lease_seconds=60
        )
        assert embed is not None and embed.attempt == 2
        assert await transition_job(s, job_id, expected=S.EMBEDDING, target=S.INDEXING, attempt=2)
        assert await transition_job(s, job_id, expected=S.INDEXING, target=S.COMPLETED, attempt=2)
        await s.commit()

    job = await load(session_factory, job_id)
    assert job.status == "COMPLETED"
    assert job.completed_at is not None and job.queued_at is not None
    assert job.lease_owner is None and job.lease_expires_at is None  # lease released
    assert await events(session_factory, job_id) == [
        ("PENDING", "QUEUED", 0),
        ("QUEUED", "EXTRACTING", 1),
        ("EXTRACTING", "CHUNKING", 1),
        ("CHUNKING", "CHUNKED", 1),
        ("CHUNKED", "EMBEDDING", 2),
        ("EMBEDDING", "INDEXING", 2),
        ("INDEXING", "COMPLETED", 2),
    ]


async def test_wrong_expected_state_changes_nothing(session_factory: Factory) -> None:
    job_id = await new_job(session_factory, status="QUEUED")

    async with session_factory() as s:
        result = await transition_job(s, job_id, expected=S.PENDING, target=S.QUEUED)
        await s.commit()

    assert result is None
    assert (await load(session_factory, job_id)).status == "QUEUED"
    assert await events(session_factory, job_id) == []


async def test_illegal_transition_is_rejected_before_any_sql(session_factory: Factory) -> None:
    job_id = await new_job(session_factory, status="COMPLETED")

    async with session_factory() as s:
        with pytest.raises(InvalidTransitionError):
            await transition_job(s, job_id, expected=S.COMPLETED, target=S.EXTRACTING)


async def test_concurrent_claims_have_exactly_one_winner(session_factory: Factory) -> None:
    """Simulates a duplicate message delivery: 10 workers grab the same job at once."""
    job_id = await new_job(session_factory, status="QUEUED")

    async def worker(n: int) -> int | None:
        async with session_factory() as s:
            result = await claim_job(
                s,
                job_id,
                expected=S.QUEUED,
                target=S.EXTRACTING,
                worker_id=f"w{n}",
                lease_seconds=60,
            )
            await s.commit()
            return result.attempt if result else None

    results = await asyncio.gather(*(worker(n) for n in range(10)))

    assert sorted(r for r in results if r is not None) == [1]
    assert results.count(None) == 9
    assert len(await events(session_factory, job_id)) == 1


async def test_stale_worker_is_fenced_out_after_takeover(session_factory: Factory) -> None:
    """A paused worker whose lease expired must not overwrite the new owner's work."""
    job_id = await new_job(session_factory, status="QUEUED")

    async with session_factory() as s:
        first = await claim_job(
            s, job_id, expected=S.QUEUED, target=S.EXTRACTING, worker_id="slow", lease_seconds=60
        )
        await s.commit()
    assert first is not None and first.attempt == 1

    # The worker freezes; the sweeper sees the expired lease and requeues the job.
    async with session_factory() as s:
        assert await transition_job(
            s,
            job_id,
            expected=S.EXTRACTING,
            target=S.RETRY_PENDING,
            checkpoint=Checkpoint.EXTRACT,
            next_retry_at=datetime.now(UTC),
            worker_id="sweeper",
        )
        assert await transition_job(s, job_id, expected=S.RETRY_PENDING, target=S.QUEUED)
        second = await claim_job(
            s, job_id, expected=S.QUEUED, target=S.EXTRACTING, worker_id="fast", lease_seconds=60
        )
        await s.commit()
    assert second is not None and second.attempt == 2

    # The slow worker wakes up and tries to continue with its old attempt number.
    async with session_factory() as s:
        stale = await transition_job(
            s, job_id, expected=S.EXTRACTING, target=S.CHUNKING, attempt=first.attempt
        )
        renewed = await renew_lease(
            s, job_id, attempt=first.attempt, worker_id="slow", lease_seconds=60
        )
        await s.commit()

    assert stale is None
    assert renewed is False
    job = await load(session_factory, job_id)
    assert (job.status, job.attempt, job.lease_owner) == ("EXTRACTING", 2, "fast")


async def test_heartbeat_extends_the_lease_for_the_owner(session_factory: Factory) -> None:
    job_id = await new_job(session_factory, status="QUEUED")
    async with session_factory() as s:
        claimed = await claim_job(
            s, job_id, expected=S.QUEUED, target=S.EXTRACTING, worker_id="w1", lease_seconds=5
        )
        await s.commit()
    assert claimed is not None
    before = (await load(session_factory, job_id)).lease_expires_at
    assert before is not None

    async with session_factory() as s:
        assert await renew_lease(s, job_id, attempt=1, worker_id="w1", lease_seconds=300)
        assert not await renew_lease(
            s, job_id, attempt=1, worker_id="someone-else", lease_seconds=300
        )
        await s.commit()

    after = (await load(session_factory, job_id)).lease_expires_at
    assert after is not None and after - before > timedelta(seconds=200)


async def test_failure_records_the_error(session_factory: Factory) -> None:
    job_id = await new_job(session_factory, status="QUEUED")
    async with session_factory() as s:
        await claim_job(
            s, job_id, expected=S.QUEUED, target=S.EXTRACTING, worker_id="w1", lease_seconds=60
        )
        result = await transition_job(
            s,
            job_id,
            expected=S.EXTRACTING,
            target=S.FAILED,
            attempt=1,
            error=JobError("NO_TEXT_LAYER", "The PDF has no extractable text.", {"pages": 12}),
        )
        await s.commit()

    assert result is not None
    job = await load(session_factory, job_id)
    assert (job.status, job.error_code, job.error_details) == (
        "FAILED",
        "NO_TEXT_LAYER",
        {"pages": 12},
    )
    assert job.lease_owner is None and job.completed_at is not None


async def test_retry_pending_requires_checkpoint_and_time(session_factory: Factory) -> None:
    job_id = await new_job(session_factory, status="EXTRACTING")
    async with session_factory() as s:
        with pytest.raises(ValueError, match="checkpoint and next_retry_at"):
            await transition_job(s, job_id, expected=S.EXTRACTING, target=S.RETRY_PENDING)


async def test_sweeper_style_multi_state_transition(session_factory: Factory) -> None:
    """One statement can accept several current states, e.g. any expired active stage."""
    job_id = await new_job(session_factory, status="CHUNKING")
    async with session_factory() as s:
        await s.execute(update(IngestionJob).where(IngestionJob.id == job_id).values(attempt=1))
        result = await transition_job(
            s,
            job_id,
            expected={S.EXTRACTING, S.CHUNKING, S.EMBEDDING, S.INDEXING},
            target=S.RETRY_PENDING,
            checkpoint=Checkpoint.EXTRACT,
            next_retry_at=datetime.now(UTC) + timedelta(seconds=30),
        )
        await s.commit()

    assert result is not None and result.from_status is S.CHUNKING
    job = await load(session_factory, job_id)
    assert (job.status, job.checkpoint) == ("RETRY_PENDING", "extract")
