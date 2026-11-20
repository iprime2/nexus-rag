# NexusRAG — System Design Document

> **Status: Proposed. Awaiting owner approval (Phase 0).**
> This is the entry point. It summarizes the design and the cross-cutting concerns, and links to the detailed documents.

| Document | Contents |
|---|---|
| [requirements.md](requirements.md) | Functional and non-functional requirements, assumptions, open questions, scope vs the reference diagram |
| [architecture.md](architecture.md) | Process roles, component diagram, sync/async paths, infrastructure roles, deployment views, repository structure |
| [ingestion-workflow.md](ingestion-workflow.md) | Pipeline stages, job state machine, retries, idempotency, backpressure, 1,000-document batch handling |
| [retrieval-workflow.md](retrieval-workflow.md) | Hybrid retrieval, fusion, reranking, context assembly, generation, citations, prompt injection |
| [database-design.md](database-design.md) | Schema, ER diagram, constraints, transaction boundaries |
| [api-specification.md](api-specification.md) | REST + SSE contract |
| [testing-strategy.md](testing-strategy.md) | Test layers and the failure-scenario test matrix |
| [adr/](adr/) | Architecture Decision Records |

## 1. The project in one paragraph

NexusRAG is a multi-tenant backend that turns large, messy document collections into a question-answering service whose answers can be verified. The interesting engineering is in the guarantees, not the chat: an upload of 1,000 files finishes with every document either indexed exactly once or failed with a reason, even if workers crash, Redis restarts, or the embedding provider rate-limits. A query only ever sees the caller's tenant's current documents, enforced by database constraints and code paths the LLM can't influence. And every quality or performance claim is backed by a reproducible evaluation or benchmark.

## 2. Key decisions at a glance

| # | Decision | One-line reason | ADR |
|---|---|---|---|
| 1 | Modular monolith, one image, separate **process roles** (api, extract worker, embed worker, maintenance) | Workload isolation without distributed-system overhead | [0001](adr/0001-modular-monolith-with-process-roles.md) |
| 2 | **Celery + Redis** broker, at-least-once delivery | Mature, routing per queue, familiar Redis. Weaknesses covered by Postgres-backed state. | [0002](adr/0002-celery-with-redis-broker.md) |
| 3 | **Qdrant** for vectors; **chunk text only in Postgres** | Filtered ANN + tenant indexing; a single source of truth for text | [0003](adr/0003-qdrant-for-vectors-postgres-for-text.md) |
| 4 | **Postgres is the source of truth for job state**; a sweeper reconciles the broker | No committed job lost to broker failure | [0004](adr/0004-postgres-as-job-state-source-of-truth.md) |
| 5 | **S3 API everywhere** (MinIO locally) | One code path, dev/prod parity | [0005](adr/0005-s3-compatible-object-storage.md) |
| 6 | **Hybrid retrieval** = Postgres FTS + Qdrant, fused with **RRF** | Catches exact terms embeddings miss, with no extra infrastructure | [0006](adr/0006-hybrid-retrieval-postgres-fts-rrf.md) |
| 7 | **Native LLM provider adapters** behind a protocol; LangChain only where it saves real work | Readability, debuggability, provider-specific capabilities | [0007](adr/0007-native-llm-provider-abstraction.md) |
| 8 | **Shared Qdrant collection with a mandatory tenant filter** + composite FKs in Postgres + hydration re-check | Isolation enforced in three independent places | [0008](adr/0008-tenant-isolation-strategy.md) |
| 9 | Build the written spec first; **defer K8s, Neo4j/GraphRAG, agents and self-hosted LLMs** from the reference diagram | Each needs evidence that justifies its cost | [0009](adr/0009-scope-relative-to-reference-diagram.md) |
| 10 | **Two-stage worker pipeline** (extract queue / embed queue), chunks in Postgres as the checkpoint | Separate CPU vs I/O scaling; retries don't redo extraction | [0010](adr/0010-two-stage-worker-pipeline.md) |

## 3. Technology comparisons you asked about

Each ADR has the full reasoning. Short versions:

### Celery vs alternatives
Celery wins on maturity, queue routing, time limits, process recycling and operational tooling (Flower, a large body of documented failure modes). Its known weak spots with Redis (ETA tasks held in worker memory, visibility-timeout redelivery, no global rate limit) are **designed around**: retries are scheduled via Postgres, tasks are idempotent with CAS + fencing, and the rate limiter is a Redis token bucket. **Dramatiq** is cleaner but has a smaller ecosystem. **arq** is async-native but minimal. **Temporal** gives durable workflows out of the box and is the strongest alternative technically, but it adds a cluster to run and a programming model to learn, which is a lot for this scope. It is worth revisiting if pipelines become long multi-step workflows.

### Redis vs AWS SQS
| | Redis (as broker) | SQS |
|---|---|---|
| Durability | Depends on persistence (AOF). A restart can lose messages. | Managed, replicated, durable |
| Redelivery | Visibility timeout per transport | Visibility timeout per message, extendable |
| DLQ | Not native (we implement `DEAD_LETTER` in Postgres) | Native redrive policy |
| Local development | Trivial | Needs LocalStack or a real AWS account |
| Celery support | First-class | Supported, with fewer features (no remote control, polling latency) |
| Other uses | Also rate limiting and caching | Queue only |

**Decision:** Redis for Phases 1–7. Because Postgres holds job state and the sweeper recovers lost messages, Redis's weaker durability costs *latency of recovery*, not *lost work*. Evaluate SQS in Phase 8 as a configuration change of the Celery transport. Production Redis must use `maxmemory-policy noeviction` for the broker; an evicting cache policy on a broker silently drops tasks. That is why **broker and cache use separate Redis instances in production**.

### Qdrant vs pgvector
At this project's scale (tens to hundreds of thousands of vectors) **pgvector would work**, and it has real advantages: one database, transactional consistency between metadata and vectors, simpler operations. Qdrant is chosen because:
- filters are applied during HNSW traversal, with tenant-optimized payload indexes, so recall stays high when a tenant owns a small slice of the collection;
- native sparse vectors are a future path to single-engine hybrid search;
- quantization, snapshots, sharding and replication are available when the scale grows;
- it forces us to solve the **dual-store consistency** problem properly (deterministic IDs, hydration as authority, cleanup reconciliation), which is a real enterprise concern worth demonstrating.

The `VectorStore` protocol keeps pgvector available as an alternative implementation. A small pgvector-vs-Qdrant benchmark is a good Phase 7 extension.

### MinIO vs local storage vs S3
Local filesystem storage is a different code path from production. It also breaks as soon as workers run in separate containers (they'd need a shared volume) and skips S3 semantics (multipart, presigned URLs, eventual consistency of listings). MinIO speaks the S3 API, so development exercises the **same boto3 code** as production with only `endpoint_url` changed. Note: MinIO's community distribution and licensing changed in 2025. Phase 1 will pin a working image or switch to another S3-compatible server (e.g. SeaweedFS, LocalStack). The application depends only on the S3 API.

### Worker concurrency (Python-specific)
Coming from Node.js: Node handles concurrency with one event loop and is weak at CPU-bound work. Python has the **GIL** (Global Interpreter Lock): only one thread executes Python bytecode at a time per process. So:
- **CPU-bound extraction** (PDF parsing, cleaning, chunking) needs **processes**: Celery `prefork` pool, concurrency ≈ CPU cores per container.
- **I/O-bound embedding** spends most of its time waiting on HTTP. Threads or higher prefork concurrency work fine, because waiting releases the GIL. Start with prefork at a higher concurrency for simplicity. Benchmark a `threads` pool in Phase 7.
- **The API** is async (FastAPI on an event loop, much like Node). The rule is the same as in Node: never block the loop. Blocking libraries run in a threadpool.

### Embedding batching and provider rate limits
Batch per document by **both** item count (≤ 256 inputs) and token total (well under the provider's per-request limit). Token counts are computed at chunking time and stored, so batches and rate-limit reservations are exact, not estimated. A Redis token bucket shared by all workers enforces requests/min and tokens/min, and a provider `429` triggers a shared cooldown. Cross-document batching (packing small documents into one request) is a Phase 7 optimization, to be done only if measurements show per-request overhead matters.

### Idempotency and retry behavior
Summarized in [ingestion-workflow.md §4–5](ingestion-workflow.md#4-failure-handling-and-retries). The four building blocks:
1. unique constraints (duplicates resolved by the DB, not by check-then-insert);
2. CAS state transitions with leases;
3. attempt-number fencing;
4. deterministic chunk and point IDs.

Retries use full-jitter exponential backoff. Throttling and outages don't consume a document's retry budget; crashes do.

### Multi-tenant retrieval security
Three independent layers, so no single bug leaks data:
1. **Request layer:** tenant comes only from the verified credential.
2. **Index layer:** `VectorStore.search()` and the FTS repository cannot be called without a `TenantContext`; the tenant filter is added inside them, not by callers.
3. **Authority layer:** hydration from Postgres re-checks tenant, document status and current version. Composite foreign keys make cross-tenant links impossible to store.

The LLM is never part of an authorization decision.

## 4. Error-handling strategy

| Layer | Strategy |
|---|---|
| Domain / services | Raise typed exceptions (`DocumentNotFound`, `InvalidTransition`, `DuplicateDocument`, `QuotaExceeded`, `DependencyUnavailable`). Services never import FastAPI. |
| API | One exception-handler module maps domain exceptions to RFC 9457 problem responses. Unknown exceptions → `500` with a request ID; the stack trace is logged, never returned. |
| Workers | Exceptions are classified as permanent / transient / throttled / crash (see ingestion §4). The classification decides the next state. |
| External calls | Every call has a timeout. Retries happen only at one layer (avoiding retry multiplication: if SDK, task and sweeper all retried, one failure would become 3 × 3 × 3 attempts). The official SDKs' built-in retries are configured deliberately, not left at defaults. |
| Data integrity | The database constraints in database-design.md are the last line of defense. A violated constraint is a bug signal and is logged at error level. |

## 5. Scalability

| Dimension | How it scales | Limit to watch |
|---|---|---|
| API | Stateless replicas behind a load balancer | Postgres connections; SSE connections per replica |
| Extract workers | Add containers; concurrency ≈ cores | CPU; object-storage bandwidth |
| Embed workers | Add containers until the provider TPM limit is saturated | **The provider rate limit is a hard ceiling** |
| Qdrant | Vertical first; sharding and replication when needed | RAM (HNSW graph + payload indexes) |
| PostgreSQL | Vertical + read replica for status queries if needed | Connections (→ PgBouncer), FTS index size |
| Redis | Vertical; tiny working set | Memory if queues grow (bounded by API admission control) |

**No scalability claim will be made without a Phase 7 benchmark** (worker count vs throughput curve, with the bottleneck identified).

## 6. High availability: local resilience vs real HA

| | Local Docker Compose | AWS target (Phase 8) |
|---|---|---|
| What survives | A crashed worker or API container; a Redis restart (via the sweeper) | Loss of a task or an AZ for stateless services; RDS failover; S3 durability |
| Single points of failure | Every data store (one Postgres, one Redis, one Qdrant) | Qdrant unless replicated or managed; Redis unless replicated or SQS is used |
| Claim we can make | "No work is lost when processes crash" (tested) | Only what has been failure-tested on AWS |

Multiple containers on one laptop are **not** high availability, and the documentation will say so.

## 7. Security

| Area | Design |
|---|---|
| Authentication | Short-lived JWT access tokens (15 min) + rotating refresh tokens; argon2id password hashing; API keys hashed (SHA-256), shown once, scoped, revocable |
| Authorization | Role checks via FastAPI dependencies; tenant from credential only; `404` (not `403`) for other tenants' resources |
| Tenant isolation | Three layers (section 3). **Optional Postgres Row-Level Security** as a fourth layer, to be decided in Phase 5: it protects against a forgotten `WHERE`, but needs `SET LOCAL app.tenant_id` per transaction and care with pooled connections. |
| Uploads | Content sniffing; size, count and page limits; DOCX zip-bomb ratio check; filenames sanitized and never used as storage keys (keys are `tenants/{tenant_id}/documents/{document_id}/{version_id}`); no file is ever executed |
| SQL injection | SQLAlchemy bound parameters everywhere; FTS via `websearch_to_tsquery` with bound input |
| Secrets | Environment variables locally (`.env` git-ignored, `.env.example` committed); AWS Secrets Manager in production; settings objects mark secrets as `SecretStr` so they don't print |
| Logging | Structured logs never include document text, prompts, answers, tokens or API keys. Prompt and answer content goes only to the tenant-scoped `messages` table. |
| Prompt injection | Retrieved content is untrusted; no tools in the QA path; authorization outside the LLM (see the retrieval workflow, section 3) |
| Rate limiting | Per user and per tenant (Redis), separate limits for upload and query |
| Supply chain | Locked dependencies (`uv.lock`), `pip-audit` in CI, Dependabot, minimal non-root container image |
| Transport | TLS terminated at the ALB in AWS; internal traffic within the VPC |

## 8. Observability

- **Metrics:** listed in the ingestion and retrieval workflows. System metrics come from exporters (postgres_exporter, redis_exporter, Qdrant's native `/metrics`, cAdvisor). Grafana dashboards: *Ingestion*, *Query*, *Dependencies*, *Cost*.
- **Logs:** JSON via `structlog`, with `request_id`, `tenant_id`, `job_id`, `document_id`, `attempt`, `worker_id` bound as context. The correlation ID travels from HTTP → Celery task headers → provider calls.
- **Traces:** OpenTelemetry (FastAPI, Celery, SQLAlchemy, HTTPX instrumentation) to a local Jaeger/Tempo. One trace covers upload → extract → embed → index.
- **Alerts** (Phase 6): dead-letter rate, queue age > threshold, circuit breaker open, readiness failing, p95 query latency regression.
- **Gotcha to handle in Phase 6:** `prometheus_client` with Celery prefork needs multiprocess mode (`PROMETHEUS_MULTIPROC_DIR`). Otherwise each child process reports separate, partial counters.

## 9. Bottlenecks (predicted, to be verified)

| # | Bottleneck | Why | Mitigation |
|---|---|---|---|
| B1 | Embedding provider TPM / RPM | Hard external limit | Exact token accounting, global bucket, batch sizing; a provider with higher limits; local embedding models (later) |
| B2 | PDF extraction CPU on large or complex PDFs | Python parsing is CPU-heavy | Prefork concurrency = cores; time limits; library choice benchmarked in Phase 2 |
| B3 | Postgres connections | Pools × processes multiply quickly | Small pools; PgBouncer / RDS Proxy |
| B4 | LLM time to first token | Provider latency dominates queries | Streaming; fewer extra LLM calls (condense only when needed); evidence gate skips the LLM entirely |
| B5 | API upload bandwidth for big batches | All bytes flow through the API | Streaming; presigned direct-to-S3 uploads as a Phase 7/8 option |
| B6 | Qdrant memory | HNSW lives in RAM | Scalar quantization; on-disk payload; sizing benchmark |

## 10. Failure scenarios

| Scenario | Expected behavior | Covered by |
|---|---|---|
| Worker killed mid-task | Message redelivered (`acks_late`, `reject_on_worker_lost`) or the lease expires → retry; no duplicates | CAS, fencing, deterministic IDs |
| Same message delivered twice, concurrently | The second CAS fails → no-op | CAS claim |
| Redis restarts and loses queued messages | The sweeper re-enqueues `QUEUED`/`CHUNKED`/`PENDING` jobs from Postgres | Sweeper |
| API crashes after commit, before enqueue | The job stays `PENDING` → the sweeper enqueues it | Sweeper |
| Embedding provider 429 storm | Shared cooldown; jobs park in `RETRY_PENDING` without burning attempts | Token bucket, error classes |
| Embedding provider down for 30 min | Circuit opens; jobs wait; resume automatically | Circuit breaker, wall-clock retry deadline |
| Qdrant unavailable | Ingestion: retries as an outage. Query: keyword-only with `degraded` flag. | Breaker, degradation |
| Postgres connection drop | Pool pre-ping + reconnect; in-flight task fails → retry; API readiness fails, so the load balancer drains it | Pool config, readiness |
| Poison document that crashes the parser | Counts as an attempt → `DEAD_LETTER` after max; doesn't loop forever | Crash classification |
| Duplicate upload, concurrently | One insert wins; the other returns `duplicate` | Unique index |
| Deletion while ingestion is running | Cleanup waits for the lease; hydration hides the document immediately; orphan reconciliation as the backstop | Deletion protocol |
| Partial batch failure | Per-document isolation; batch `completed_with_errors` with listable failures | Per-document jobs |

## 11. Trade-offs we are knowingly making

- **Postgres FTS instead of true BM25.** Simpler, but lower keyword quality on some corpora. Measured, and replaceable.
- **Two stores for chunks (text in Postgres, vectors in Qdrant).** Needs reconciliation logic, but avoids text duplication and gives a single authority.
- **Redis broker before SQS.** Simpler local development; durability gaps covered by the sweeper rather than by the broker.
- **No agentic or graph features in the core.** Smaller scope, deeper quality. Extensions only with evaluation evidence.
- **In-place re-index can briefly mix chunk generations.** Acceptable for an admin operation; a cleaner design is noted.
- **Self-issued JWTs instead of an IdP.** Fewer moving parts. The external IdP path stays open.

## 12. Decisions that need your approval

1. **Scope:** spec first; diagram extras (K8s, Neo4j, agents, Ray/vLLM) deferred (requirements §5, ADR-0009).
2. **Modular monolith** with process roles; query service split later only if measured contention justifies it (ADR-0001).
3. **Two-queue worker pipeline** and the added `CHUNKED` state (ADR-0010).
4. **Chunk text only in Postgres** (database-design D-3).
5. **Shared Qdrant collection** with a mandatory tenant filter instead of collection-per-tenant (ADR-0008).
6. **Document identity via `external_id`** (assumption A-1).
7. **Native provider adapters, minimal LangChain** (ADR-0007).
8. Tooling for Phase 1: **uv, ruff, mypy, pytest, pre-commit**.

Once these are approved, Phase 1 (project foundation) starts. Its plan will be presented separately before any code is written.
