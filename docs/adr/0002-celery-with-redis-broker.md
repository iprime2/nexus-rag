# ADR-0002: Celery with a Redis broker

- **Status:** Proposed
- **Date:** 2026-11-20

## Context
Ingestion work must be distributed across horizontally scaled workers, with routing to queues of different kinds (CPU vs I/O), time limits, graceful shutdown and at-least-once delivery. The owner already knows Redis.

## Decision
Celery with Redis as the broker, configured for at-least-once delivery (`acks_late`, `reject_on_worker_lost`, `prefetch_multiplier=1`). Celery's result backend is not used for job state. Retries are scheduled through Postgres (`RETRY_PENDING` + sweeper), not Celery countdowns. Rate limiting uses a Redis token bucket shared by all workers, not Celery's per-worker `rate_limit`.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| **Celery** | Mature; routing, time limits, process recycling; huge knowledge base; Flower | Complex configuration; Redis transport quirks (ETA tasks in memory, visibility-timeout redelivery); per-process rate limits |
| Dramatiq | Simpler, sane defaults | Smaller ecosystem |
| arq | asyncio-native, tiny | Minimal features; Redis only |
| Temporal | Durable workflows, built-in retries and state, excellent visibility | A cluster to operate, a new programming model, heavy for this scope |
| RabbitMQ as broker | Proper acks and redelivery, durable queues | Extra infrastructure; Redis is needed anyway |
| SQS as broker | Managed, durable, native DLQ | Awkward locally; Celery's SQS support is thinner (evaluate in Phase 8) |

## Consequences
- Every task must be idempotent (see ADR-0004 and ingestion-workflow §5).
- Production Redis for the broker uses `noeviction` and AOF, on a separate instance from the cache.
- Revisit if pipelines become long multi-step workflows with human steps (Temporal) or when moving to AWS (SQS).
