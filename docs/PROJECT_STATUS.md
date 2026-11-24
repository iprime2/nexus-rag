# NexusRAG — Project Status

_Last updated: 2026-11-24_

## Current phase
**Walking skeleton (Phases 2–4 reordered, 2026-11-24)**. Steps 2.1–2.2 and W1 done; next: W2 chunking. Goal: ask questions about your own documents end to end, *then* harden ingestion.

## Phase overview
| Phase | Name | Status |
|---|---|---|
| 0 | System design & architecture | ✅ Complete (approved 2026-11-20, PRs #1, #2) |
| 1 | Project foundation | ✅ Complete (PRs #3–#9) |
| 2 | Document ingestion | 🟡 In progress (2/8 steps) |
| 3 | Embeddings & vector storage | ⚪ |
| 4 | Retrieval & generation | ⚪ |
| 5 | Reliability & multi-tenancy | ⚪ |
| 6 | Evaluation & observability | ⚪ |
| 7 | Performance & scalability | ⚪ |
| 8 | AWS deployment | ⚪ |
| 9 | Portfolio readiness | ⚪ |

## Phase 0: outcome
- All design documents and ADRs 0001–0010 were approved by the owner and are now marked **Accepted**.
- Open question 3 (document-level access control) has no explicit answer yet. It is treated as a **Phase 5 stretch goal** after tenant isolation, as proposed.
- Open question 5 (reranker choice) is deferred to Phase 4, to be decided with evaluation data.

## Phase 1: steps (one PR per step, each with teaching notes and tests)
Decisions: Python 3.13 runtime with `requires-python >= 3.12`; S3-compatible store: SeaweedFS (ADR-0011, MinIO is archived); one PR per step; Compose verified on the owner's machine.

- [x] 1.1 Python project skeleton: uv, `pyproject.toml`, ruff, mypy, pytest, pre-commit, minimal FastAPI app + `/health/live`
- [x] 1.2 Configuration: typed settings with pydantic-settings, `.env.example`, fail-fast validation
- [x] 1.3 Structured logging: structlog JSON logs, request-ID middleware, context propagation
- [x] 1.4 Docker: Dockerfile (multi-stage, non-root) + Compose (Postgres, Redis, Qdrant, S3-compatible store, API)
- [x] 1.5 Database: SQLAlchemy 2 async engine (psycopg 3), session dependency, Alembic with a first `tenants` migration
- [x] 1.6 Readiness: `/health/ready` checking Postgres, Redis, Qdrant and object storage with timeouts
- [x] 1.7 CI: GitHub Actions running lint, type checks, unit tests and integration tests (service containers)
- [x] Learning notes: `docs/learning/01-foundation-concepts.md` (all steps + recap)

## Phase 2: steps (one PR per step)
Decisions (2026-11-22): minimal API-key auth now (users/JWT in Phase 5); `pypdf` for PDFs (license; benchmark in Phase 7); own magic-byte detection and own chunk splitter.

- [x] 2.1 Tenant authentication with API keys (`api_keys`, CLI, `CurrentTenant` dependency, `GET /v1/me`)
- [x] 2.2 Ingestion schema + job state machine (documents, versions, batches, jobs, job events; CAS transitions) + owner exercise: `retry_dead_letter`

### Roadmap change (owner decision, 2026-11-24): walking skeleton first
Build a thin end-to-end RAG path early (synchronous, driven from the CLI), so the AI parts are visible and testable sooner, then harden it with the upload API, Celery and failure drills. Interfaces from the design are kept, so little is rewritten. OpenAI is the first provider for embeddings and answers (owner has a key); the provider abstraction stays.

| Step | What | AI / architecture lesson |
|---|---|---|
| W1 ✅ | Text extraction + cleaning (PDF, TXT) as pure pipeline stages; ADR-0012 | Why extraction quality bounds answer quality |
| W2 | Token-aware chunking → `document_chunks` (CLI `ingest`) | Chunk size trade-offs, tokens, overlap |
| W3 | Embeddings: `EmbeddingProvider` + OpenAI, batching | What embeddings are; cosine similarity |
| W4 | Qdrant indexing + semantic search (CLI `search`) | Vector databases, HNSW, tenant filters |
| W5 | Grounded answers with citations (CLI `ask`) | Prompting, grounding, hallucination control |
| H1 | Object storage + upload API (202, dedupe) | Streaming uploads, idempotent registration |
| H2 | Celery workers, leases, sweeper | At-least-once delivery in practice |
| H3 | DOCX/HTML extractors, deep validation | Untrusted input handling |
| H4 | Keyword search + RRF hybrid, reranking | Hybrid retrieval |
| H5 | Failure drills (F1–F3, F5, F9, F12) | Proving reliability |

- [ ] Learning notes: `docs/learning/02-ingestion-concepts.md` (steps 2.1–2.2, W1 written)

## Known issues
- The cloud development container can run Docker (started manually), but image builds there need the sandbox proxy's CA mounted as a build secret. This is a sandbox-only workaround, not part of the committed Dockerfile.
- The GitHub default branch may still point at the first pushed branch. Set it to `main` in repository settings.

## Next recommended steps
1. Owner reviews the W1 PR (review questions in chat) and merges it.
2. Owner: set the default branch to `main` and protect it (require both CI checks).
3. W2: lesson on chunking, then the owner's spec, then implementation (CLI `ingest`).
