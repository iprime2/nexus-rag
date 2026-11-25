# Defense questions

Interview-style questions about everything merged so far. **Questions only, no answers**: the owner answers them in chat (about 2–3 per session), Claude gives feedback, and a question is ticked with the date only when it was answered **without hints**. When all questions for a module are ticked, its row in [ownership.md](ownership.md) moves to `partly` or `yes`.

**Question types:** **why** (a trade-off), **what if** (a failure), **code** (read real code: explain it, predict the output, find the bug), **alt** (alternatives and when you'd switch). ⭐ = do these first: they cover modules the walking skeleton builds on next.

## Progress

| Section | Answered | Total |
|---|---|---|
| 0. Design (ADRs, PRs #1–#2) | 0 | 9 |
| #3 Project skeleton (1.1) | 0 | 4 |
| #4 Configuration (1.2) | 0 | 4 |
| #5 Logging (1.3) | 0 | 5 |
| #6 Docker (1.4) | 0 | 5 |
| #7 Database (1.5) | 0 | 5 |
| #8 Readiness (1.6) | 0 | 5 |
| #9 CI (1.7) | 0 | 4 |
| #10 API keys (2.1) | 0 | 5 |
| #11 State machine (2.2) | 0 | 6 |
| #12 Extraction (W1) | 0 | 5 |
| #15–#17 Scenario, dataset, evaluation | 0 | 5 |
| **Total** | **0** | **62** |

---

## 0. Design: ADRs and PRs #1–#2

- [ ] ⭐ **(why)** Why a modular monolith with separate process roles instead of microservices? What would make you split the query API into its own service? — *ADR-0001*
- [ ] **(alt)** Celery vs. Temporal vs. arq: why Celery here, and what kind of pipeline would make Temporal the better choice? — *ADR-0002*
- [ ] **(what if)** Redis restarts and loses every queued message. Why does NexusRAG still lose no work? — *ADR-0004*
- [ ] ⭐ **(why)** At this scale pgvector would work. Why Qdrant anyway, and what do you pay for that choice? — *ADR-0003*
- [ ] **(why)** Chunk text lives only in Postgres, vectors only in Qdrant. What does the "hydration" step buy you beyond fetching text? — *ADR-0003*
- [ ] ⭐ **(why)** Name the three independent layers of tenant isolation. Which one catches a bug where the Qdrant filter is forgotten? — *ADR-0008*
- [ ] **(alt)** Shared Qdrant collection with a tenant filter vs. one collection per tenant: when would you switch? — *ADR-0008*
- [ ] **(why)** Why build a walking skeleton (thin end to end first) instead of finishing ingestion completely before retrieval? — *PROJECT_STATUS roadmap*
- [ ] **(why)** What is an ADR for, and why are accepted ADRs never edited (ADR-0011 *refines* ADR-0005 instead)? — *docs/adr*

## #3 Project skeleton (Phase 1.1)

- [ ] **(why)** Why commit `uv.lock` when `pyproject.toml` already lists the dependencies? — *pyproject.toml*
- [ ] **(why)** Why an application factory (`create_app()`) instead of a module-level `app` object? — *main.py*
- [ ] ⭐ **(what if)** If `/health/live` checked Postgres and the database went down, what would the orchestrator do, and why is that worse? — *api/routes/health.py*
- [ ] **(code)** The tests use `httpx.AsyncClient(transport=ASGITransport(app=app))`. Is a real server running? What does the transport actually do? — *tests/conftest.py*

## #4 Configuration (Phase 1.2)

- [ ] **(why)** What does "fail fast" mean for configuration, and why is crashing at startup better than failing on the first request? — *core/config.py*
- [ ] **(code)** `Settings` sets `extra="forbid"`. What happens if `.env` contains `NEXUS_DEUBG=true`? What would happen without it? — *core/config.py*
- [ ] **(why)** Why is `postgres_password` a `SecretStr` and not a `str`? Where would a plain string leak? — *core/config.py*
- [ ] **(code)** Tests build `Settings(_env_file=None, …)`. What bug does `_env_file=None` prevent? — *tests/conftest.py*

## #5 Structured logging (Phase 1.3)

- [ ] **(why)** Why log JSON key/value pairs instead of plain text lines? Give one query you can only run on structured logs. — *core/logging.py*
- [ ] ⭐ **(why)** How does every log line inside a request get the same `request_id` without passing it to every function? What is the Node.js equivalent? — *api/middleware/request_context.py*
- [ ] **(what if)** A client sends `X-Request-ID: abc\nlevel=error fake log line`. What does the middleware do, and what attack does that stop? — *api/middleware/request_context.py*
- [ ] **(code)** Why does the middleware call `clear_contextvars()` at the end of each request? What test proves it matters? — *api/middleware/request_context.py*
- [ ] **(alt)** Why a plain ASGI middleware instead of Starlette's `BaseHTTPMiddleware`? — *api/middleware/request_context.py*

## #6 Docker and Compose (Phase 1.4)

- [ ] **(why)** Why does the Dockerfile copy `pyproject.toml`/`uv.lock` and install dependencies *before* copying `app/`? — *Dockerfile*
- [ ] **(what if)** The container's `CMD` is written in shell form (`CMD uvicorn …`). What happens on `docker stop`? — *Dockerfile*
- [ ] **(why)** Why bind every Compose port to `127.0.0.1`, and why run the API as a non-root user? — *docker-compose.yml, Dockerfile*
- [ ] **(code)** Redis runs with `--appendonly yes --maxmemory-policy noeviction`. What does each flag protect against for a task broker? — *docker-compose.yml*
- [ ] **(what if)** MinIO stopped publishing community images. How did the architecture make the switch to SeaweedFS cheap? — *ADR-0011*

## #7 Database layer (Phase 1.5)

- [ ] **(why)** Engine vs. session: which is created once per process, which per request, and why? — *db/session.py*
- [ ] **(code)** What does `pool_pre_ping=True` do, and which failure does it turn from an error into a non-event? — *db/session.py*
- [ ] ⭐ **(what if)** Two requests create a tenant with slug `acme` at the same moment. Why can't a Python "check, then insert" prevent a duplicate, and what does? — *db/models/tenant.py*
- [ ] **(why)** Why are migrations run by a separate one-off `migrate` job instead of at API startup? — *docker-compose.yml*
- [ ] **(code)** What does `test_migrations_match_the_models` compare, and how was it proven to actually catch drift? — *tests/integration/test_database.py*

## #8 Readiness (Phase 1.6)

- [ ] **(why)** Liveness vs. readiness: what does an orchestrator do when each one fails? — *api/routes/health.py*
- [ ] **(code)** `run_checks` uses `asyncio.gather` with a per-check `wait_for`. With four checks of 0.3 s each, roughly how long does the endpoint take, and why? — *core/readiness.py*
- [ ] **(why)** Why does the response show only the error *type* (e.g. `ConnectionRefusedError`) and not the message? — *core/readiness.py*
- [ ] **(what if)** boto3 is blocking. What happens to all requests on a worker if it's called directly inside `async def`? And why can't `asyncio.wait_for` fully stop a slow `to_thread` call? — *core/readiness.py, storage/s3.py*
- [ ] **(why)** Why does readiness compare the database's Alembic revision with the build's head migration? — *db/migrations.py*

## #9 CI (Phase 1.7)

- [ ] **(why)** Why are third-party Actions pinned to a commit SHA instead of a tag like `@v7`? — *.github/workflows/ci.yml*
- [ ] **(why)** What do `permissions: contents: read` and `persist-credentials: false` protect against? — *.github/workflows/ci.yml*
- [ ] **(alt)** CI starts services with the project's `docker-compose.yml` instead of Actions `services:`. Name one benefit and one cost. — *.github/workflows/ci.yml*
- [ ] **(what if)** A dependency in `pyproject.toml` is bumped without running `uv lock`. Which CI step fails, and why is that desirable? — *.github/workflows/ci.yml*

## #10 API keys and tenant auth (Phase 2.1)

- [ ] ⭐ **(why)** Why can the tenant only come from the credential, never from a header or request body? — *api/dependencies/auth.py*
- [ ] ⭐ **(why)** Why SHA-256 and not bcrypt/argon2 for API keys, when passwords use argon2? — *auth/api_keys.py*
- [ ] **(why)** Why return the *same* 401 for a missing, malformed, unknown or revoked key, but a 403 for a suspended tenant? — *api/dependencies/auth.py*
- [ ] **(code)** `parse_authorization_header` rejects malformed values before any database lookup. Name two reasons that matters. — *auth/api_keys.py*
- [ ] **(what if)** The `api_keys` table leaks. What can an attacker do with it, and what can't they? — *db/models/api_key.py*

## #11 Ingestion schema and job state machine (Phase 2.2)

- [ ] ⭐ **(why)** Why compare-and-set with a fencing token instead of `SELECT` the job, check its status, then `UPDATE`? — *ingestion/jobs.py*
- [ ] ⭐ **(code)** In `claim_job()`, what is returned when another worker already claimed the job, and why does the caller need no error handling? — *ingestion/jobs.py*
- [ ] ⭐ **(what if)** A worker freezes for 10 minutes, its lease expires and another worker takes the job. Walk through what happens when the first worker wakes up and writes. — *ingestion/jobs.py*
- [ ] **(why)** What do composite foreign keys like `(tenant_id, document_id) → documents(tenant_id, id)` guarantee that a normal foreign key doesn't? — *db/models/ingestion.py*
- [ ] **(code)** The "one active job per version" rule is a *partial* unique index. What does "partial" mean here, and what would a normal unique index break? — *db/models/ingestion.py*
- [ ] **(why)** Why is the transition and its audit event written in *one* SQL statement? — *ingestion/jobs.py*

## #12 Extraction, cleaning and guard (W1)

- [ ] ⭐ **(why)** Why keep text per page instead of one long string? — *ingestion/extraction/models.py*
- [ ] ⭐ **(code)** `_edges` caps the edge size at half the page. Which lines count as edges on 1-, 2- and 7-line pages, and which bug did the cap fix? — *ingestion/extraction/cleaning.py*
- [ ] **(what if)** A scanned PDF (only images) is uploaded. What does the pipeline do, and why is it a *permanent* error and not a retry? — *ingestion/extraction/pipeline.py*
- [ ] **(code)** `reader.decrypt("")` was first assumed to raise on a wrong password. What does it actually do, and how did that misreport encrypted PDFs? — *ingestion/extraction/pdf.py*
- [ ] **(alt)** pypdf vs. Docling vs. a vision LLM for extraction: when would you choose each, and how would you decide with evidence? — *ADR-0012*

## #15–#17 Scenario, dataset and evaluation (PRs C–F)

- [ ] **(code)** A golden-set line has `"type": "unanswerable"`, `"answerable": false` and one item in `evidence`. What does `check-golden-set` report, and why is that rule there? — *evaluation/golden_set.py* (review question R1, PR E)
- [ ] **(what if)** You save faa.gov's "Access Denied" page as a `.pdf` and run `--offline --pin`. What happens to that row's checksum, and why is that the right behaviour? — *scripts/fetch_faa_dataset.py* (R2)
- [ ] **(code)** `if (self.type == "unanswerable") == self.answerable: raise …` In plain words, when does it raise? Give one input that passes and one that fails. — *evaluation/golden_set.py* (R3)
- [ ] ⭐ **(why)** Why can't a similarity threshold stop answers from a cancelled revision, and what does? — *docs/learning/06-evaluation-concepts.md*
- [ ] **(why)** Why pin a SHA-256 per dataset file, and why not make the script look like a browser when faa.gov returned 403? — *datasets/faa/manifest.csv*
