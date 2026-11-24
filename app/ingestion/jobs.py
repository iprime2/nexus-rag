"""Job state changes as compare-and-set (CAS) statements (docs/ingestion-workflow.md §2).

Every change is **one SQL statement** that:

1. locks the job row and reads its current status (``prev``),
2. updates it only if the status is one of the expected ones and, for
   worker writes, only if ``attempt`` still matches (the *fencing token*),
3. appends the transition to ``ingestion_job_events``.

If another worker got there first (duplicate message delivery, a sweeper, a
cancel), zero rows change and the function returns ``None``. The caller then
simply stops. There is no "check, then update" window for a race to slip in.

Transitions are validated against the state machine (``app.ingestion.state``)
*before* any SQL runs. The caller owns the transaction: commit right after a
transition, so row locks are held for milliseconds, not for a whole task.
"""

import json
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Text

from app.ingestion.state import (
    ACTIVE_STAGES,
    TERMINAL_STATES,
    Checkpoint,
    JobStatus,
    ensure_transition,
)


@dataclass(frozen=True)
class TransitionResult:
    job_id: uuid.UUID
    tenant_id: uuid.UUID
    from_status: JobStatus
    to_status: JobStatus
    attempt: int


@dataclass(frozen=True)
class JobError:
    code: str  # stable, machine-readable, e.g. "NO_TEXT_LAYER"
    message: str  # human-readable, safe to show to the tenant
    details: dict[str, Any] | None = None


def _as_set(states: JobStatus | Collection[JobStatus]) -> frozenset[JobStatus]:
    return frozenset({states}) if isinstance(states, JobStatus) else frozenset(states)


async def _cas(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    expected: frozenset[JobStatus],
    target: JobStatus,
    set_sql: list[str],
    params: dict[str, Any],
    fence_attempt: int | None,
    worker_id: str | None,
    details: dict[str, Any] | None,
) -> TransitionResult | None:
    fence = "AND j.attempt = :fence_attempt" if fence_attempt is not None else ""
    assignments = ", ".join(["status = :target", "updated_at = now()", *set_sql])
    # Only fixed fragments written in this module are interpolated (column names,
    # SQL functions). Every value is a bound parameter, so S608 doesn't apply.
    sql = f"""
        WITH prev AS (
            SELECT id, status FROM ingestion_jobs WHERE id = :job_id FOR UPDATE
        ),
        moved AS (
            UPDATE ingestion_jobs AS j
            SET {assignments}
            FROM prev
            WHERE j.id = prev.id AND prev.status = ANY(:expected) {fence}
            RETURNING j.id, j.tenant_id, j.attempt, prev.status AS from_status
        )
        INSERT INTO ingestion_job_events
            (tenant_id, job_id, from_status, to_status, attempt, worker_id, details)
        SELECT tenant_id, id, from_status, :target, attempt, :worker_id, :details
        FROM moved
        RETURNING job_id, tenant_id, from_status, attempt
    """  # noqa: S608
    statement = text(sql).bindparams(
        bindparam("expected", type_=ARRAY(Text)),
        bindparam("details", type_=JSONB),
    )
    row = (
        await session.execute(
            statement,
            {
                "job_id": job_id,
                "target": target.value,
                "expected": sorted(s.value for s in expected),
                "fence_attempt": fence_attempt,
                "worker_id": worker_id,
                "details": details,
                **params,
            },
        )
    ).one_or_none()
    if row is None:
        return None
    return TransitionResult(
        job_id=row.job_id,
        tenant_id=row.tenant_id,
        from_status=JobStatus(row.from_status),
        to_status=target,
        attempt=row.attempt,
    )


async def claim_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    expected: JobStatus,
    target: JobStatus,
    worker_id: str,
    lease_seconds: float,
) -> TransitionResult | None:
    """A worker takes ownership: waiting state → active stage, new attempt, fresh lease.

    The returned ``attempt`` is the worker's fencing token for every later write.
    """
    ensure_transition(expected, target)
    if target not in ACTIVE_STAGES:
        raise ValueError(f"claim must enter an active stage, not {target}")
    return await _cas(
        session,
        job_id,
        expected=frozenset({expected}),
        target=target,
        set_sql=[
            "attempt = j.attempt + 1",
            "lease_owner = :worker_id",
            "lease_expires_at = now() + make_interval(secs => :lease_seconds)",
            "started_at = coalesce(j.started_at, now())",
        ],
        params={"lease_seconds": lease_seconds},
        fence_attempt=None,
        worker_id=worker_id,
        details=None,
    )


async def transition_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    expected: JobStatus | Collection[JobStatus],
    target: JobStatus,
    attempt: int | None = None,
    worker_id: str | None = None,
    error: JobError | None = None,
    checkpoint: Checkpoint | None = None,
    next_retry_at: datetime | None = None,
    details: dict[str, Any] | None = None,
) -> TransitionResult | None:
    """Move a job between states. Pass ``attempt`` for every write made by a worker.

    ``expected`` may list several states, for transitions that are legal from
    more than one place (e.g. the sweeper moving any expired active stage to
    RETRY_PENDING).
    """
    expected_states = _as_set(expected)
    for state in expected_states:
        ensure_transition(state, target)
    if target is JobStatus.RETRY_PENDING and (checkpoint is None or next_retry_at is None):
        raise ValueError("RETRY_PENDING needs a checkpoint and next_retry_at")

    set_sql: list[str] = []
    params: dict[str, Any] = {}
    if target not in ACTIVE_STAGES:  # leaving an active stage releases the lease
        set_sql += ["lease_owner = NULL", "lease_expires_at = NULL"]
    if target is JobStatus.QUEUED:
        set_sql.append("queued_at = now()")
    if target in TERMINAL_STATES:
        set_sql.append("completed_at = now()")
    if target is JobStatus.RETRY_PENDING:
        set_sql += ["checkpoint = :checkpoint", "next_retry_at = :next_retry_at"]
        params |= {"checkpoint": checkpoint.value if checkpoint else None}
        params |= {"next_retry_at": next_retry_at}
    if error is not None:
        set_sql += [
            "error_code = :error_code",
            "error_message = :error_message",
            "error_details = CAST(:error_details AS jsonb)",
        ]
        params |= {
            "error_code": error.code,
            "error_message": error.message,
            "error_details": json.dumps(error.details) if error.details is not None else None,
        }
    return await _cas(
        session,
        job_id,
        expected=expected_states,
        target=target,
        set_sql=set_sql,
        params=params,
        fence_attempt=attempt,
        worker_id=worker_id,
        details=details,
    )


async def renew_lease(
    session: AsyncSession,
    job_id: uuid.UUID,
    *,
    attempt: int,
    worker_id: str,
    lease_seconds: float,
) -> bool:
    """Heartbeat: extend the lease. False means this worker no longer owns the job: stop."""
    result = await session.execute(
        text("""
            UPDATE ingestion_jobs
            SET lease_expires_at = now() + make_interval(secs => :lease_seconds)
            WHERE id = :job_id AND attempt = :attempt AND lease_owner = :worker_id
              AND status = ANY(:active)
        """).bindparams(bindparam("active", type_=ARRAY(Text))),
        {
            "job_id": job_id,
            "attempt": attempt,
            "worker_id": worker_id,
            "lease_seconds": lease_seconds,
            "active": sorted(s.value for s in ACTIVE_STAGES),
        },
    )
    return bool(result.rowcount)  # type: ignore[attr-defined]
