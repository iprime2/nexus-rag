# NexusRAG — Project Status

_Last updated: 2026-11-22_

## Current phase
**Phase 2: Document Ingestion**. Plan approved 2026-11-22. Step 2.1 done; step 2.2 next.

## Phase overview
| Phase | Name | Status |
|---|---|---|
| 0 | System design & architecture | ✅ Complete (approved 2026-11-20, PRs #1, #2) |
| 1 | Project foundation | ✅ Complete (PRs #3–#9) |
| 2 | Document ingestion | 🟡 In progress (1/8 steps) |
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
- [ ] 2.2 Ingestion schema + job state machine (documents, versions, batches, jobs, job events; CAS transitions)
- [ ] 2.3 Object storage: `ObjectStore` protocol, streaming upload with SHA-256
- [ ] 2.4 Upload API: batches, documents, cheap validation, registration, dedupe, 202
- [ ] 2.5 Celery workers: claim/lease/heartbeat, enqueue after commit, sweeper
- [ ] 2.6 Extractors (PDF, DOCX, TXT, HTML), deep validation, cleaning
- [ ] 2.7 Chunking → `document_chunks` → `CHUNKED`; job and batch status endpoints
- [ ] 2.8 Failure drills (F1–F3, F5, F9, F12)
- [ ] Learning notes: `docs/learning/02-ingestion-concepts.md` (step 2.1 written)

## Known issues
- The cloud development container can run Docker (started manually), but image builds there need the sandbox proxy's CA mounted as a build secret. This is a sandbox-only workaround, not part of the committed Dockerfile.
- The GitHub default branch may still point at the first pushed branch. Set it to `main` in repository settings.

## Next recommended steps
1. Owner reviews and merges the step 2.1 PR.
2. Owner: set the default branch to `main` and protect it (require both CI checks).
3. Step 2.2: ingestion schema and the job state machine.
