"""The job state machine: exhaustive checks over the whole transition table."""

from collections import deque
from itertools import pairwise, product

import pytest

from app.ingestion.state import (
    ACTIVE_STAGES,
    ALLOWED,
    TERMINAL_STATES,
    WAITING_STATES,
    InvalidTransitionError,
    JobStatus,
    can_transition,
    ensure_transition,
)

S = JobStatus


def reachable_from(start: JobStatus) -> set[JobStatus]:
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in ALLOWED[queue.popleft()]:
            if nxt not in seen:
                seen.add(nxt)
                queue.append(nxt)
    return seen


def test_every_state_has_an_entry() -> None:
    assert set(ALLOWED) == set(JobStatus)


def test_state_groups_partition_the_states() -> None:
    assert set(JobStatus) == ACTIVE_STAGES | WAITING_STATES | TERMINAL_STATES
    assert not ACTIVE_STAGES & WAITING_STATES
    assert not ACTIVE_STAGES & TERMINAL_STATES
    assert not WAITING_STATES & TERMINAL_STATES


def test_happy_path_is_allowed() -> None:
    path = [S.PENDING, S.QUEUED, S.EXTRACTING, S.CHUNKING, S.CHUNKED]
    path += [S.EMBEDDING, S.INDEXING, S.COMPLETED]
    for current, target in pairwise(path):
        assert can_transition(current, target), f"{current} -> {target}"


def test_every_state_is_reachable_from_pending() -> None:
    assert reachable_from(S.PENDING) == set(JobStatus)


def test_every_state_can_reach_a_terminal_state() -> None:
    for state in JobStatus:
        assert reachable_from(state) & TERMINAL_STATES, state


def test_completed_failed_and_cancelled_are_final() -> None:
    for state in (S.COMPLETED, S.FAILED, S.CANCELLED):
        assert ALLOWED[state] == frozenset()


def test_dead_letter_can_only_be_manually_requeued() -> None:
    assert ALLOWED[S.DEAD_LETTER] == {S.QUEUED}


def test_retries_resume_at_the_right_stage() -> None:
    assert ALLOWED[S.RETRY_PENDING] == {S.QUEUED, S.CHUNKED, S.CANCELLED}


def test_every_active_stage_can_fail_or_retry() -> None:
    for stage in ACTIVE_STAGES:
        assert {S.RETRY_PENDING, S.DEAD_LETTER} <= ALLOWED[stage], stage


def test_waiting_states_can_be_cancelled_directly() -> None:
    for state in WAITING_STATES:
        assert S.CANCELLED in ALLOWED[state], state


@pytest.mark.parametrize(
    "current,target",
    [
        (S.COMPLETED, S.EXTRACTING),  # no restarting finished jobs
        (S.PENDING, S.EXTRACTING),  # must be enqueued first
        (S.QUEUED, S.CHUNKED),  # can't skip extraction
        (S.CHUNKED, S.COMPLETED),  # can't skip embedding
        (S.FAILED, S.QUEUED),  # permanent failures aren't retried
        (S.INDEXING, S.FAILED),  # indexing only fails transiently
    ],
)
def test_illegal_jumps_are_rejected(current: JobStatus, target: JobStatus) -> None:
    assert not can_transition(current, target)
    with pytest.raises(InvalidTransitionError, match=f"from {current} to {target}"):
        ensure_transition(current, target)


def test_no_self_transitions() -> None:
    for state, target in product(JobStatus, JobStatus):
        if state == target:
            assert not can_transition(state, target), state
