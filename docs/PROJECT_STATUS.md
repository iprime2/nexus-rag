# NexusRAG — Project Status

_Last updated: 2026-11-25_

## Current phase
**Mentor-review follow-up (PRs A–F), then walking skeleton W2.** Steps 2.1–2.2 and W1 done. Goal: ask questions about your own documents end to end, *then* harden ingestion.

## Mentor review (2026-11-25) and follow-up plan
A senior-FDE mentor reviewed the foundation. Strengths: typed config, structured logging, async DB + Alembic, API-key tenant auth, CAS state machine with fencing, CI, ADRs, docs. Problems, in priority order: (1) ownership gap: all code is AI-written; (2) no AI functionality yet; (3) no evaluation set; (4) no believable customer scenario or real dataset; (5) scope risk against the 15 Feb 2027 portfolio milestone (two more projects follow).

**Owner decisions (2026-11-25):** ~10 hours/week on NexusRAG. Working model: **specify → Claude implements → owner reviews and defends** (the owner doesn't hand-write code); see `CLAUDE.md` → Ownership rules. Hint ladder accepted. The owner reviews in a local editor. Demo dataset: **FAA Advisory Circulars** (US federal works), chosen over the CMS and EU options.

| PR | Scope | Status |
|---|---|---|
| A | Ownership rules in `CLAUDE.md`; `docs/learning/ownership.md` baseline | ✅ #13 |
| B | `docs/learning/defense-questions.md`: 57 questions for PRs #3–#12 + design (ADR) questions | ✅ #14 |
| C | Customer scenario (SkyBridge Regional, fictional) + FAA Advisory Circular dataset: `docs/customer-scenario.md`, `datasets/faa/manifest.csv`, `scripts/fetch_faa_dataset.py` | ✅ #15 |
| D | Portfolio v1 cut line + target dates: ADR-0013 (W2–W3 by 2026-12-06, W4–W5 by 2026-12-13, v1 by 2027-01-17) | ✅ #16 |
| E | `docs/evaluation-plan.md`, `eval/` + golden-set format checker (`check-golden-set`); fetcher `--offline` mode | 🟡 In review |
| F | Housekeeping: complete W1 learning notes; default-branch reminder | ⚪ |

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

Target dates and the v1 cut line: [ADR-0013](adr/0013-portfolio-v1-cut-line.md). Order: W2–W5 → evaluation baseline + tracing → H1, H2 → H4 → AWS + demo. H3 only if the 2026-12-20 checkpoint is on time; H5 after v1.

| Step | What | AI / architecture lesson | Target |
|---|---|---|---|
| W1 ✅ | Text extraction + cleaning (PDF, TXT) as pure pipeline stages; ADR-0012 | Why extraction quality bounds answer quality | done |
| W2 | Token-aware chunking → `document_chunks` (CLI `ingest`) | Chunk size trade-offs, tokens, overlap | 2026-12-06 |
| W3 | Embeddings: `EmbeddingProvider` + OpenAI, batching | What embeddings are; cosine similarity | 2026-12-06 |
| W4 | Qdrant indexing + semantic search (CLI `search`) | Vector databases, HNSW, tenant filters | 2026-12-13 |
| W5 | Grounded answers with citations (CLI `ask`) | Prompting, grounding, hallucination control | 2026-12-13 |
| EV | Evaluation set (30–50 owner-verified questions) + baseline report; Langfuse tracing | Measuring RAG quality; tracing LLM calls | 2026-12-20 |
| H1 | Object storage + upload API (202, dedupe) | Streaming uploads, idempotent registration | 2027-01-03 |
| H2 | Celery workers, leases, sweeper | At-least-once delivery in practice | 2027-01-03 |
| H3 | DOCX/HTML extractors, deep validation | Untrusted input handling | if on time (first cut) |
| H4 | Keyword search + RRF hybrid (reranker deferred, ADR-0013) | Hybrid retrieval, measured against the baseline | 2027-01-10 |
| Q | `POST /v1/query` with streamed answers (SSE) | Streaming LLM output; citations at the end of the stream | 2027-01-10 |
| D1 | One AWS deployment over HTTPS + demo video + README results | Deploying to a customer-like environment; TLS | 2027-01-17 (**v1**) |
| H5 | Failure drills (F1–F3, F5, F9, F12) | Proving reliability | after v1 |

- [ ] Learning notes: `docs/learning/02-ingestion-concepts.md` (steps 2.1–2.2, W1 written)

## Known issues
- The cloud development container can run Docker (started manually), but image builds there need the sandbox proxy's CA mounted as a build secret. This is a sandbox-only workaround, not part of the committed Dockerfile.

## Next recommended steps
1. Owner downloads the 5 FAA PDFs in a browser (faa.gov answers 403 to scripts, also from the owner's Mac) into `data/raw/faa/`, then runs `uv run python -m scripts.fetch_faa_dataset --offline --pin` and verifies the AC statuses. Keep answering ⭐ defense questions (2–3 per session).
2. PR F after E, proposed in chat and approved before implementation.
3. Owner: protect `main` (require both CI checks). The default branch is `main` since 2026-11-25.
4. Then W2 under the new rules: lesson → owner's chunker spec → implementation → review gate → defend.
