# NexusRAG — Project Status

_Last updated: 2026-11-20_

## Current phase
**Phase 1: Project Foundation**. Plan proposed, **awaiting owner approval** before any code is written.

## Phase overview
| Phase | Name | Status |
|---|---|---|
| 0 | System design & architecture | ✅ Complete (approved 2026-11-20, PR #1) |
| 1 | Project foundation | 🟡 Plan proposed |
| 2 | Document ingestion | ⚪ |
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

## Phase 1: proposed steps (each step = one small commit with teaching notes and tests)
- [ ] 1.1 Python project skeleton: uv, `pyproject.toml`, ruff, mypy, pytest, pre-commit, minimal FastAPI app + `/health/live`
- [ ] 1.2 Configuration: typed settings with pydantic-settings, `.env.example`, fail-fast validation
- [ ] 1.3 Structured logging: structlog JSON logs, request-ID middleware, context propagation
- [ ] 1.4 Docker: Dockerfile (multi-stage, non-root) + Compose (Postgres, Redis, Qdrant, S3-compatible store, API)
- [ ] 1.5 Database: SQLAlchemy 2 async engine (psycopg 3), session dependency, Alembic with a first `tenants` migration
- [ ] 1.6 Readiness: `/health/ready` checking Postgres, Redis, Qdrant and object storage with timeouts
- [ ] 1.7 CI: GitHub Actions running lint, type checks, unit tests and integration tests (service containers)
- [ ] Learning notes: `docs/learning/01-foundation-concepts.md`

## Known issues
- The cloud development container has no Docker daemon, so Compose can't run there. Integration tests will run against locally installed services or in CI. The owner runs Compose on their own machine.
- The GitHub default branch may still point at the first pushed branch. Set it to `main` in repository settings.

## Next recommended steps
1. Owner approves or adjusts the Phase 1 plan, dependencies and PR granularity.
2. Implement step 1.1.
