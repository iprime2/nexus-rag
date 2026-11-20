# NexusRAG — Project Status

_Last updated: 2026-11-20_

## Current phase
**Phase 0: System Design & Architecture**. Design documents drafted. **Awaiting owner approval.**

## Phase overview
| Phase | Name | Status |
|---|---|---|
| 0 | System design & architecture | 🟡 Drafted, in review |
| 1 | Project foundation | ⚪ Not started (blocked on Phase 0 approval) |
| 2 | Document ingestion | ⚪ |
| 3 | Embeddings & vector storage | ⚪ |
| 4 | Retrieval & generation | ⚪ |
| 5 | Reliability & multi-tenancy | ⚪ |
| 6 | Evaluation & observability | ⚪ |
| 7 | Performance & scalability | ⚪ |
| 8 | AWS deployment | ⚪ |
| 9 | Portfolio readiness | ⚪ |

## Phase 0: completed tasks
- [x] Requirements, assumptions, open questions: `docs/requirements.md`
- [x] High-level architecture, sync/async paths, infrastructure roles: `docs/architecture.md`
- [x] Ingestion workflow + job state machine: `docs/ingestion-workflow.md`
- [x] Retrieval workflow: `docs/retrieval-workflow.md`
- [x] Database schema + ER diagram: `docs/database-design.md`
- [x] API contracts: `docs/api-specification.md`
- [x] Error-handling strategy: `docs/system-design.md` §4
- [x] Testing strategy: `docs/testing-strategy.md`
- [x] Mermaid diagrams (in the documents above)
- [x] ADRs 0001–0010 (status: Proposed): `docs/adr/`
- [x] Learning notes for Phase 0: `docs/learning/00-system-design-concepts.md`
- [x] Working agreement incl. teaching mode: `CLAUDE.md`

## Pending (Phase 0)
- [ ] Owner review of the decisions listed in `docs/system-design.md` §12
- [ ] Answers to the open questions in `docs/requirements.md` §6
- [ ] Mark the ADRs `Accepted` / `Rejected`

## Known issues
- The repository's `main` branch was not visible on GitHub when Phase 0 started. These docs live on the working branch and will be rebased onto `main` once it exists.

## Architectural decisions
See `docs/adr/README.md`. All are currently **Proposed**.

## Next recommended steps
1. Owner reviews the design (start with `docs/system-design.md`, then `docs/learning/00-system-design-concepts.md`).
2. Resolve the open questions and approve or adjust the ADRs.
3. Plan Phase 1 (foundation): uv project, FastAPI skeleton with health endpoints, config, structured logging, Docker Compose (Postgres, Redis, Qdrant, MinIO), Alembic, pytest. The plan is presented for approval before any code is written.
