# ADR-0004: Postgres as the source of truth for job state

- **Status:** Accepted (2026-11-20)
- **Date:** 2026-11-20

## Context
Brokers deliver messages; they are not good databases. Redis can lose messages on restart, Celery's result backend isn't queryable by tenant or batch, and a message can be delivered twice. The system must never lose a committed job, never process one twice in parallel, and always be able to answer "what is the state of document X?"

## Decision
- Job state lives in `ingestion_jobs`. The broker message carries only `job_id`.
- State transitions are compare-and-set `UPDATE … WHERE status = :expected RETURNING`.
- Workers hold a **lease** (expiry timestamp, renewed by heartbeat), not a row lock.
- Writes are **fenced** by the attempt number.
- Enqueue happens after commit. A periodic **sweeper** re-enqueues `PENDING`, stale `QUEUED`/`CHUNKED`, due `RETRY_PENDING` and expired-lease jobs. This is a lightweight transactional outbox.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Celery result backend for status | Built-in | Not relational; no batch or tenant queries; lost with Redis |
| Full transactional outbox table + relay process | Exactly the textbook pattern | An extra table and process; the jobs table already serves as the outbox |
| `SELECT … FOR UPDATE SKIP LOCKED` (Postgres as the queue) | No broker at all; strong guarantees | Polling load; contention at high throughput; gives up Celery features. A good learning alternative to benchmark later. |
| **Jobs table + CAS + leases + sweeper** | Broker failures cost latency, not work; full visibility | Sweeper logic to get right and test |

## Consequences
- Duplicate deliveries are no-ops. Lost messages are recovered within one sweeper interval plus the staleness threshold.
- The sweeper is critical and gets dedicated failure tests (F3, F5, F12).
