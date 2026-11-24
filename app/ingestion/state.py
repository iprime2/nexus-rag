"""The ingestion job state machine (docs/ingestion-workflow.md §2).

This module is pure: no database, no I/O. It defines the states and the
**only** allowed transitions. Every status change in the system is checked
against ``ALLOWED`` before any SQL runs, so an illegal jump (e.g.
``COMPLETED → EXTRACTING``) is a programming error caught immediately.

            PENDING → QUEUED → EXTRACTING → CHUNKING → CHUNKED
                                                          ↓
            COMPLETED ← INDEXING ← EMBEDDING ←────────────┘
    any active stage → RETRY_PENDING → QUEUED (checkpoint=extract) | CHUNKED (embed)
    any active stage → FAILED (permanent) | DEAD_LETTER (attempts exhausted)
    DEAD_LETTER → QUEUED (manual retry)
    waiting states (PENDING, QUEUED, CHUNKED, RETRY_PENDING) → CANCELLED
"""

from enum import StrEnum


class JobStatus(StrEnum):
    PENDING = "PENDING"  # registered, not yet enqueued
    QUEUED = "QUEUED"  # waiting for an extract worker
    EXTRACTING = "EXTRACTING"
    CHUNKING = "CHUNKING"
    CHUNKED = "CHUNKED"  # chunks persisted, waiting for an embed worker
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"
    COMPLETED = "COMPLETED"
    RETRY_PENDING = "RETRY_PENDING"  # transient failure, waiting for next_retry_at
    FAILED = "FAILED"  # permanent error: retrying is pointless
    DEAD_LETTER = "DEAD_LETTER"  # retryable errors exhausted the attempt budget
    CANCELLED = "CANCELLED"


class Checkpoint(StrEnum):
    """Which stage a RETRY_PENDING job resumes from."""

    EXTRACT = "extract"
    EMBED = "embed"


S = JobStatus

# A worker holds a lease while the job is in one of these.
ACTIVE_STAGES: frozenset[JobStatus] = frozenset({S.EXTRACTING, S.CHUNKING, S.EMBEDDING, S.INDEXING})
# Waiting for someone to pick the job up. Cancellable directly.
WAITING_STATES: frozenset[JobStatus] = frozenset({S.PENDING, S.QUEUED, S.CHUNKED, S.RETRY_PENDING})
# Nothing more will happen (DEAD_LETTER can still be retried manually).
TERMINAL_STATES: frozenset[JobStatus] = frozenset(
    {S.COMPLETED, S.FAILED, S.DEAD_LETTER, S.CANCELLED}
)

_FAILURE_EXITS = {S.RETRY_PENDING, S.FAILED, S.DEAD_LETTER}

ALLOWED: dict[JobStatus, frozenset[JobStatus]] = {
    S.PENDING: frozenset({S.QUEUED, S.CANCELLED}),
    S.QUEUED: frozenset({S.EXTRACTING, S.CANCELLED}),
    S.EXTRACTING: frozenset({S.CHUNKING, *_FAILURE_EXITS, S.CANCELLED}),
    S.CHUNKING: frozenset({S.CHUNKED, *_FAILURE_EXITS, S.CANCELLED}),
    S.CHUNKED: frozenset({S.EMBEDDING, S.CANCELLED}),
    S.EMBEDDING: frozenset({S.INDEXING, *_FAILURE_EXITS, S.CANCELLED}),
    S.INDEXING: frozenset({S.COMPLETED, S.RETRY_PENDING, S.DEAD_LETTER, S.CANCELLED}),
    S.RETRY_PENDING: frozenset({S.QUEUED, S.CHUNKED, S.CANCELLED}),
    S.DEAD_LETTER: frozenset({S.QUEUED}),
    S.COMPLETED: frozenset(),
    S.FAILED: frozenset(),
    S.CANCELLED: frozenset(),
}
# Active stages may move to CANCELLED only cooperatively: the worker sees
# cancel_requested_at at a stage boundary and makes the transition itself.


class InvalidTransitionError(Exception):
    def __init__(self, current: JobStatus, target: JobStatus) -> None:
        super().__init__(f"job cannot go from {current} to {target}")
        self.current = current
        self.target = target


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    return target in ALLOWED[current]


def ensure_transition(current: JobStatus, target: JobStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
