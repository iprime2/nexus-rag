# NexusRAG — Project Status

_Last updated: 2026-11-20_

## Current phase
**Phase 1: Project Foundation**. Plan approved 2026-11-20. Steps 1.1–1.4 done; step 1.5 next.

## Phase overview
| Phase | Name | Status |
|---|---|---|
| 0 | System design & architecture | ✅ Complete (approved 2026-11-20, PRs #1, #2) |
| 1 | Project foundation | 🟡 In progress (4/7 steps) |
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

## Phase 1: steps (one PR per step, each with teaching notes and tests)
Decisions: Python 3.13 runtime with `requires-python >= 3.12`; S3-compatible store: SeaweedFS (ADR-0011, MinIO is archived); one PR per step; Compose verified on the owner's machine.

- [x] 1.1 Python project skeleton: uv, `pyproject.toml`, ruff, mypy, pytest, pre-commit, minimal FastAPI app + `/health/live`
- [x] 1.2 Configuration: typed settings with pydantic-settings, `.env.example`, fail-fast validation
- [x] 1.3 Structured logging: structlog JSON logs, request-ID middleware, context propagation
- [x] 1.4 Docker: Dockerfile (multi-stage, non-root) + Compose (Postgres, Redis, Qdrant, S3-compatible store, API)
- [ ] 1.5 Database: SQLAlchemy 2 async engine (psycopg 3), session dependency, Alembic with a first `tenants` migration
- [ ] 1.6 Readiness: `/health/ready` checking Postgres, Redis, Qdrant and object storage with timeouts
- [ ] 1.7 CI: GitHub Actions running lint, type checks, unit tests and integration tests (service containers)
- [ ] Learning notes: `docs/learning/01-foundation-concepts.md` (steps 1.1–1.4 written)

## Known issues
- The cloud development container can run Docker (started manually), but image builds there need the sandbox proxy's CA mounted as a build secret. This is a sandbox-only workaround, not part of the committed Dockerfile.
- The GitHub default branch may still point at the first pushed branch. Set it to `main` in repository settings.

## Next recommended steps
1. Owner reviews and merges the step 1.4 PR, and optionally runs `docker compose up -d --build` locally.
2. Step 1.5: SQLAlchemy 2 async engine + Alembic + first `tenants` migration.
