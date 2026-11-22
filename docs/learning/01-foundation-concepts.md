# Phase 1: Foundation Concepts

One section per step. Each has the concepts, how the code works, what breaks if it is done wrong, exercises, and interview questions.

---

## Step 1.1: Python project skeleton

### What a Python project is made of

| File | Node.js equivalent | Purpose |
|---|---|---|
| `pyproject.toml` | `package.json` | Name, version, Python version, dependencies, and settings for every tool (ruff, mypy, pytest) in one place |
| `uv.lock` | `package-lock.json` / `pnpm-lock.yaml` | Exact versions and hashes of *every* package, including transitive ones. **Committed**, so every machine and CI installs identical code. |
| `.python-version` | `.nvmrc` | Which interpreter uv uses (3.13). `requires-python = ">=3.12"` in `pyproject.toml` is the *minimum* the code supports; tests were run on both. |
| `.venv/` | `node_modules/` | The project's isolated environment. Never committed. |
| `[dependency-groups] dev` | `devDependencies` | Test and lint tools that never ship in the production image |

**Why uv?** It replaces pip + virtualenv + pip-tools + pyenv with one fast tool, and gives a real lockfile. **Poetry** is the main alternative (mature, but slower, with its own non-standard config sections). Plain **pip + requirements.txt** has no proper lock of transitive dependencies unless you add pip-tools.

**Why a build backend (hatchling)?** It makes the `app` package *installable*. Once installed into `.venv`, `import app` works from anywhere: tests, Alembic, Celery workers. You don't need `PYTHONPATH` hacks. The `[tool.hatch.build.targets.wheel] packages = ["app"]` line exists because the project name (`nexus-rag`) differs from the import name (`app`).

**`__init__.py` files** mark a directory as a regular package. They can be empty. `app/__init__.py` also holds `__version__`, the single source of the version string used by the API and OpenAPI docs.

### The app factory and ASGI

- **ASGI** (Asynchronous Server Gateway Interface) is the contract between a server (Uvicorn) and an async app (FastAPI). Express apps are called by Node's `http` server in a similar way.
- `create_app()` builds the app; Uvicorn runs it with `--factory`. Benefits:
  1. Importing `app.main` has no side effects (no connections opened at import time).
  2. Each test gets a fresh app, so there is no state leaking between tests.
  3. Later, the factory will choose which routers to mount per process role (ADR-0001: a `query-api` role is the same image with a different router set).
- `async def live()`: FastAPI runs `async def` endpoints on the event loop, like a Node handler. **A blocking call inside one freezes every request on that worker.** Ruff's `ASYNC` rules catch common mistakes (`time.sleep`, blocking `open()` in async code).

### Response models

`LivenessResponse` is a Pydantic model (≈ a NestJS DTO class with `class-validator`, but the type hints *are* the validation). FastAPI uses it to:
1. serialize and validate the response;
2. generate the OpenAPI schema (`/openapi.json`, `/docs`).

`status: Literal["ok"]` documents the exact value and lets mypy reject typos.

### Liveness vs readiness

| | Liveness `/health/live` | Readiness `/health/ready` (step 1.6) |
|---|---|---|
| Question | "Is the process alive?" | "Can it serve traffic right now?" |
| Checks dependencies? | **No** | Yes (DB, Redis, Qdrant, S3) |
| On failure | Orchestrator **restarts** the container | Load balancer **stops sending traffic**; no restart |

**What breaks if liveness checks the database:** Postgres goes down, all API containers fail liveness, the orchestrator restarts all of them in a loop. Restarts can't fix Postgres, but they turn a degraded service into a total outage and slow recovery.

### Tooling choices

- **ruff** (lint + format): replaces flake8, isort, black, pyupgrade and bandit. Rule families enabled: `E/W/F` basics, `I` import order, `B` likely bugs (e.g. mutable default arguments, a classic Python trap), `UP` modern syntax, `SIM`, `ASYNC`, `S` security (bandit), `N` naming, `RUF`.
- **mypy `strict`**: like `"strict": true` in `tsconfig.json`. Every function needs type annotations, `Any` leaks are reported, and so on. Python doesn't check types at runtime, so mypy is the only thing that does.
- **pytest**: plain `assert` statements (pytest rewrites them to show detailed diffs on failure). `asyncio_mode = "auto"` lets `async def test_...` run without decorators. `--strict-markers` turns a typo in a marker name into an error instead of a silently skipped test.
- **pre-commit**: git hooks that run ruff, mypy and hygiene checks before each commit (≈ husky + lint-staged). ruff and mypy run through `uv run`, so the hook versions are the locked versions.

### How the tests work

`tests/conftest.py` defines **fixtures**: `app` (a fresh app) and `client` (an `httpx.AsyncClient` with `ASGITransport`). The transport passes requests straight into the ASGI app, with no network or server. Tests are fast and deterministic, yet every request still goes through real routing, validation and serialization. This is the Python counterpart of `supertest(app.getHttpServer())`.

### Exercises
1. Add a field `service: str = "nexus-rag-api"` to `LivenessResponse`. Run the tests: which one fails, and why is that a *good* failure? Then update the test.
2. Inside `live()`, add `import time; time.sleep(1)` and run `uv run ruff check .`. Read the `ASYNC` warning, explain what it protects against, then remove the line.
3. Delete the return type `-> LivenessResponse` from `live()` and run `uv run mypy`. What does strict mode say?

### Interview questions
- **"Why use an application factory instead of a global `app` object?"** No import-time side effects; isolated test instances; configuration can be chosen per instance (per environment or process role).
- **"What's the difference between liveness and readiness probes, and what goes wrong if you mix them up?"** See the table above. The restart-storm scenario is the answer interviewers want.
- **"Why commit a lockfile? Isn't `pyproject.toml` enough?"** `pyproject.toml` has version *ranges*. Without a lock, two installs on different days can resolve different transitive versions, so "works on my machine" bugs appear and builds aren't reproducible.

---

## Step 1.2: Typed configuration

### The idea
| Principle | How NexusRAG does it | NestJS equivalent |
|---|---|---|
| Config from the environment ([12-factor](https://12factor.net/config)) | `NEXUS_*` env vars, optional `.env` for local development | `ConfigModule.forRoot()` |
| Validate once, at startup | `Settings(BaseSettings)`: type hints are the schema | Joi / zod `validationSchema` |
| **Fail fast** | Bad value → `ValidationError` → the process exits before serving traffic | `validationSchema` throwing on boot |
| One source of truth | `get_settings()` (cached singleton), or inject `Settings` into `create_app()` | `ConfigService` injection |

### How it works (`app/core/config.py`)
- **Precedence:** init kwargs > real env vars > `.env` file > defaults. Production sets real env vars (ECS / Secrets Manager); `.env` is only a local convenience.
- **Type coercion:** `"true"` → `True`, `"staging"` → `Environment.STAGING`. An invalid value is an error, never a silent default.
- **`extra="forbid"`:** a typo in `.env` (`NEXUS_DEUBG`) fails startup instead of being silently ignored. Silently ignored typos are a classic "but I set that flag!" bug.
- **`model_validator`:** cross-field rules (`production` + `debug` is rejected). Each field alone is valid; the combination isn't.
- **`frozen=True`:** settings can't be mutated at runtime, so no hidden global state changes.
- **`SecretStr`** (from step 1.5): prints `**********`; the real value only via `.get_secret_value()`. This keeps secrets out of logs, tracebacks and error pages.

### Testability
Tests build `Settings(_env_file=None, ...)` explicitly and pass it to `create_app(settings)`. **What breaks otherwise:** tests silently read a developer's `.env`, so they pass on one laptop and fail in CI.

### What breaks if done wrong
| Mistake | Consequence | Test |
|---|---|---|
| Reading `os.environ` all over the codebase | Untyped strings, scattered defaults, typos fail at request time | (design rule) |
| Lazy validation | The app boots "healthy" and fails on the first real request | `test_create_app_fails_fast_on_invalid_environment` |
| Ignoring unknown keys | A misspelled flag silently does nothing | `test_unknown_key_in_dotenv_fails_fast` |
| Debug on in production | Stack traces leak internals to users | `test_debug_is_rejected_in_production` |

### Exercises
1. Run `NEXUS_ENVIRONMENT=prod uv run uvicorn app.main:create_app --factory` and read the error. Which part tells you the allowed values?
2. Add `api_title: str = "NexusRAG"` to `Settings`, use it in `create_app`, and set it via `.env`. Which test would you add?

### Interview questions
- **"How do you manage configuration and secrets across environments?"** Env vars validated into a typed object at startup; secrets come from a secret manager into env vars, typed as `SecretStr`; no secrets in code or images.
- **"Why fail fast at startup?"** A misconfigured instance should never pass its readiness check and take traffic. Crashing at deploy time is visible and cheap; failing at request time is neither.

---

## Step 1.3: Structured logging and request IDs

### The idea
| Concept | What it means | Node/NestJS equivalent |
|---|---|---|
| Structured logs | Each line is JSON key/values, so you can query `status_code>=500 AND path=/v1/query` | pino |
| Correlation ID | One `request_id` on every line of one request, and later on its Celery tasks | `nestjs-cls` / pino-http `reqId` |
| `contextvars` | Per-request (per asyncio task) storage, so you don't pass IDs through every function | `AsyncLocalStorage` |
| One pipeline | Library logs (Uvicorn, later SQLAlchemy, Celery) are rendered by the same processors | pino transports |

### How it works
| File | Role |
|---|---|
| `app/core/logging.py` | `configure_logging()`: processors (context merge → level → logger → UTC timestamp → **redaction**) → JSON or console renderer. `ProcessorFormatter` routes stdlib records through the same chain. |
| `app/api/middleware/request_context.py` | Reads or creates `X-Request-ID`, binds it with `bind_contextvars`, echoes it in the response, logs `request.completed` with status and duration, then clears the context. |
| `app/core/config.py` | `NEXUS_LOG_LEVEL`, `NEXUS_LOG_FORMAT` |

**Why plain ASGI middleware instead of `BaseHTTPMiddleware`:** the plain form doesn't buffer or wrap the response stream, which the SSE streaming endpoints need later.

### What breaks if done wrong
| Mistake | Consequence | Test that guards it |
|---|---|---|
| Trusting any incoming `X-Request-ID` | Log injection (a newline forges fake lines), huge values | `test_unsafe_incoming_request_ids_are_replaced` |
| A global variable for the request ID | Concurrent requests overwrite each other's IDs | `test_concurrent_requests_do_not_mix_request_ids` |
| Not clearing the context | The next log line outside a request carries a stale ID | `test_context_is_cleared_after_the_request` |
| Logging a headers dict or config | API keys and tokens in logs, a security incident | `test_sensitive_values_are_redacted_including_nested` |
| Multi-line tracebacks | One error becomes 30 log "events" | `test_exceptions_are_logged_as_one_structured_line` |

Redaction is a **safety net**, not permission to log secrets. Also never log document text, prompts or answers (system-design §7).

### Exercises
1. Run the server with `NEXUS_LOG_FORMAT=json`, call `curl -H "X-Request-ID: my-id" localhost:8000/health/live`, and find your ID in the logs.
2. Add `log.info("live.checked")` inside `live()`. Does it get the `request_id` automatically? Why?

### Interview questions
- **"How do you trace one user request across services?"** Correlation ID created at the edge, bound to context, returned to the client, and propagated in headers and task metadata. Later, OpenTelemetry trace IDs do the same across processes (Phase 6).
- **"How do you keep secrets out of logs?"** Don't log raw objects; type secrets as `SecretStr`; a redaction processor as the last line of defense; tests that check the real output.

---

## Step 1.4: Docker and Docker Compose

### Dockerfile: the ideas
| Technique | What it does | Why it matters |
|---|---|---|
| **Multi-stage build** | `builder` has uv and installs deps; `runtime` gets only Python + the finished `.venv` | Smaller image (235 MB), no build tools for an attacker to use |
| **Dependency layer first** | `uv sync --no-install-project` with only `uv.lock` + `pyproject.toml` mounted, then copy `app/` | Code edits don't re-download dependencies, so rebuilds take seconds. Same trick as `COPY package*.json` before `npm ci`. |
| `--locked` | Build fails if `uv.lock` doesn't match `pyproject.toml` | The image contains exactly what was tested |
| `--no-editable` | `app` is installed into site-packages; the source tree isn't needed at runtime | Runtime stage copies only `.venv` |
| **Non-root user** (uid 10001) | Process runs without root | A compromised process can't own the container |
| **Exec-form `CMD`** | Uvicorn is PID 1 and receives `SIGTERM` directly | Graceful shutdown: in-flight requests finish (measured: stop in 0.6 s) |
| `.dockerignore` | Excludes `.env`, `.git`, `.venv`, tests, docs | **Secrets never enter an image**; smaller, faster build context |
| Pinned image tags | `postgres:18.7-alpine`, not `postgres:latest` | Reproducible builds; upgrades are deliberate |

### Compose: the ideas
| Technique | Where | Why |
|---|---|---|
| Health checks + `depends_on: condition: service_healthy` | every service | The API starts only after the databases accept connections. "Container started" ≠ "service ready". |
| Named volumes | `postgres-data`, `redis-data`, … | Data survives `down`/`up` (verified: rows and keys still there). `down -v` deletes them. |
| Ports bound to `127.0.0.1` | every service | Databases are not exposed to your Wi-Fi network |
| `${VAR:-default}` | credentials, ports | Local defaults that work out of the box, overridable from the shell |
| Redis `--appendonly yes --maxmemory-policy noeviction` | `redis` | Broker safety from ADR-0002: queued tasks survive restarts and are never silently evicted |
| Postgres 18 volume at `/var/lib/postgresql` | `postgres` | The PG 18 image changed its data path; mounting the old `/var/lib/postgresql/data` would silently lose data on recreate |

### MinIO → SeaweedFS
MinIO's community edition stopped publishing images (Oct 2025) and was archived. SeaweedFS replaces it ([ADR-0011](../adr/0011-seaweedfs-for-local-object-storage.md)). The app talks only S3, so nothing else changes. This is the benefit of depending on a **protocol**, not a product.

### Why infrastructure credentials aren't in `.env`
`Settings` rejects unknown keys in `.env` (step 1.2), so `.env` holds only `NEXUS_*` app settings. Local infrastructure credentials are throwaway defaults in `docker-compose.yml`; real environments use Secrets Manager.

### What breaks if done wrong
| Mistake | Consequence |
|---|---|
| `COPY . .` before installing deps | Every code change reinstalls all dependencies |
| Shell-form `CMD uvicorn …` | `sh` is PID 1 and doesn't forward `SIGTERM`; Docker kills the app after 10 s, dropping in-flight requests |
| No `.dockerignore` | `.env` with real keys ends up in an image pushed to a registry |
| `depends_on` without health conditions | API starts before Postgres is ready, so startup errors and restart loops |
| `0.0.0.0` port bindings for databases | Anyone on your network can reach Postgres with the default password |

### Exercises
1. Change one line in `app/main.py` and run `docker compose build api`. Which steps say `CACHED`? Now change `pyproject.toml` and compare.
2. Run `docker compose stop -t 30 api` while `curl` is running in a loop. Read the shutdown logs.

### Interview questions
- **"How do you keep Docker images small and secure?"** Multi-stage builds, slim base, non-root user, `.dockerignore`, pinned versions, no secrets in layers, and a vulnerability scan in CI.
- **"Why might a container ignore `docker stop` and take 10 seconds to die?"** Shell-form `CMD` makes `sh` PID 1, and it doesn't forward signals. Use exec form, or an init like `tini`.
- **"Your dependency (MinIO) was abandoned. What do you do?"** Depend on protocols and interfaces, so you can swap the implementation; record the change in an ADR; verify the replacement with the same behavioural checks.

---

## Step 1.5: Database layer (SQLAlchemy 2 + psycopg 3 + Alembic)

### The pieces
| Piece | Role | TypeORM / NestJS equivalent |
|---|---|---|
| `create_engine()` (`app/db/session.py`) | Owns the **connection pool**; one per process | `DataSource` |
| `AsyncSession` (`get_session` dependency) | One unit of work per request, borrowed from the pool | `EntityManager` / `QueryRunner` |
| `Base` + models (`app/db/`) | Python classes ↔ tables; `Mapped[...]` type hints define columns | `@Entity` classes |
| Alembic (`migrations/`) | Versioned schema changes, `upgrade` / `downgrade` | `typeorm migration:generate/run` |
| psycopg 3 | Postgres driver with both sync and async modes | `pg` |

### Key decisions
| Decision | Why |
|---|---|
| Password is a separate `SecretStr` field, URL built in code | Injected alone from a secret manager; never printed (tested) |
| `pool_pre_ping=True` | Dead connections (DB restart, failover) are replaced before use instead of failing a request |
| Small pool (5 + 5 overflow) | processes × (pool + overflow) must stay below `max_connections` |
| `expire_on_commit=False` | Async sessions can't lazy-load on attribute access after commit |
| Explicit `commit()`, no auto-commit per request | Streaming endpoints mustn't hold a transaction; some operations need several transactions |
| Constraint naming convention | Alembic can find and alter constraints by stable names |
| `text` + `CHECK` instead of Postgres `ENUM` | Changing allowed values is an ordinary migration (D-5) |
| UUIDv7 IDs generated in Python (`app/core/ids.py`) | Exist before INSERT; time-ordered, so B-tree inserts stay fast (D-6) |
| DB URL never in `alembic.ini` | One source of credentials (`Settings`) |
| Migrations as a **separate one-off job** (`migrate` service) | Several API replicas starting at once would otherwise race to migrate |

### Testing strategy here
| Kind | Example | Runs |
|---|---|---|
| Unit (no DB) | password never in `repr`/`str`; pool configured; UUIDv7 format and ordering | `uv run pytest` |
| Integration (real Postgres, fresh DB per run, migrated by Alembic) | unique slug, CHECK constraints, request rollback, migrations down/up | `uv run pytest -m integration` |
| **Schema drift** | `compare_metadata(models, migrated DB) == []` | integration |

The drift test was **proven to fail** by changing `String(63)` to `String(64)` without a migration. It reported `modify_type … VARCHAR(63)`. A test you have never seen fail might not be testing anything.

### What breaks if done wrong
| Mistake | Consequence | Guard |
|---|---|---|
| Model changed, migration forgotten | Production schema differs from code; runtime errors | drift test |
| Migrations run at app startup with N replicas | Concurrent DDL, lock waits, half-applied migrations | `migrate` job |
| One shared session across requests | Data from one request leaks into or blocks another | per-request `get_session` |
| Unique checks done in Python (`SELECT` then `INSERT`) | Race: two requests both pass the check | DB `UNIQUE` constraint (tested) |
| Password in the URL string or `alembic.ini` | Secrets in logs, tracebacks, git | `SecretStr`, URL object, test |

### Exercises
1. Add a nullable `description` column to `Tenant`, run `uv run alembic revision --autogenerate -m "add tenant description"`, read the generated file, then `uv run alembic upgrade head` and `downgrade -1`.
2. Skip the migration in exercise 1 and run `uv run pytest -m integration`. Which test fails, and what does its message say?

### Interview questions
- **"How do you run DB migrations safely in production?"** As a separate job before the new version takes traffic; backwards-compatible changes (expand → migrate data → contract); never at app startup with multiple replicas.
- **"Why enforce constraints in the database if the app validates already?"** Concurrency (check-then-insert races), other writers (scripts, workers), and defense in depth. The database is the last line of defense.
- **"What's a connection pool and how do you size it?"** Reused open connections (opening one costs a TCP + TLS + auth round trip). Size so that all processes' pools fit under `max_connections`; add PgBouncer or RDS Proxy when they don't.

### Q&A: does the database check unique constraints one request at a time?
No. Postgres runs transactions in parallel and only makes them wait when they touch **the same unique key**.

| Time | Transaction A | Transaction B |
|---|---|---|
| t1 | `INSERT slug='acme'` (not committed) | |
| t2 | | `INSERT slug='acme'` → **waits** for A |
| t3 | `COMMIT` | |
| t4 | | ❌ unique violation (had A rolled back, B would succeed) |

- The check is one B-tree index lookup, not a table scan. Inserts of *different* slugs never wait for each other.
- A Python "SELECT then INSERT" check fails here: under MVCC each transaction sees a snapshot without the other's uncommitted row, so both pass the check.
- Use `INSERT … ON CONFLICT DO NOTHING` for "create if missing".
- Try it: two `psql` sessions, `BEGIN; INSERT …` in one, the same `INSERT` in the other (it hangs), then `COMMIT` the first.

---

## Step 1.6: Readiness checks

### Liveness vs readiness, now both implemented
| | `/health/live` | `/health/ready` |
|---|---|---|
| Checks | Nothing | Postgres (and migration version), Redis, Qdrant, S3 bucket |
| Failure | Orchestrator restarts the container | Load balancer stops sending traffic; **no restart** |
| Verified | Stays 200 while Redis is down | 503 while Redis is down → 200 again when it returns |

### Design
| Decision | Why |
|---|---|
| All checks run **concurrently** (`asyncio.gather`) | Response time ≈ slowest check, not the sum (tested: 4×0.3 s checks finish in about 0.3 s) |
| Per-check timeout (`NEXUS_READINESS_TIMEOUT_SECONDS`, 2 s) | A *hanging* dependency is worse than a dead one; frozen Qdrant answered in 2.04 s |
| Response shows only the error **type** | The endpoint is public; messages can include hostnames. Full details go to logs with the request ID. |
| Postgres check compares `alembic_version` with the build's head migration | Code that expects a newer schema must not serve traffic |
| S3 check = `head_bucket` on *our* bucket | Proves endpoint, credentials **and** bucket (tested: missing bucket, wrong secret) |
| boto3 runs via `asyncio.to_thread` | boto3 is blocking; calling it directly would freeze the event loop. A timeout stops *waiting* but can't kill the thread, so boto3 has its own connect/read timeouts. |
| Qdrant checked with plain `httpx` on `/readyz` | The full `qdrant-client` (gRPC, numpy) isn't needed until Phase 3 |
| Clients created once per process, closed in `lifespan` | Connection pools are reused; no leaked sockets on shutdown |
| `storage-init` job creates the bucket | Idempotent local bootstrap; on AWS, Terraform owns the bucket |
| Empty env values mean "unset" (`env_ignore_empty`) | `NEXUS_REDIS_PASSWORD=` must not mean "password is the empty string" |

### What breaks if done wrong
| Mistake | Consequence |
|---|---|
| Dependency checks in liveness | Outage → every container restarts in a loop → slower recovery |
| Sequential checks without timeouts | One hung dependency makes readiness hang; the load balancer's own timeout marks everything unhealthy |
| Returning raw error messages | Leaks internal hostnames and versions to anyone |
| Calling boto3 directly in `async def` | Every request on that worker stalls during a slow S3 call |
| No migration check | New code serves requests against an old schema and fails on new columns |

### Exercises
1. With Compose running, `docker compose pause qdrant`, call `/health/ready`, time it, then `unpause`. Change `NEXUS_READINESS_TIMEOUT_SECONDS` and repeat.
2. Make Postgres "behind": `docker compose exec api alembic downgrade base`. What does readiness report? Fix it with `upgrade head`.

### Interview questions
- **"Design health checks for a service with four dependencies."** Liveness has no dependencies; readiness runs concurrent checks with timeouts, exposes minimal information, and logs details. Readiness gates traffic and never triggers restarts.
- **"How do you call blocking libraries from async Python?"** `asyncio.to_thread` / a thread pool, plus the library's own timeouts, because a thread can't be cancelled from outside.
- **"What does the load balancer do when all instances report not ready?"** It depends on the LB. Many fail *open* (keep routing), so readiness should reflect *this instance's* ability to serve, and alerts must fire separately.

---

## Step 1.7: Continuous integration (GitHub Actions)

### What runs on every PR (`.github/workflows/ci.yml`)
| Job | Steps | Catches |
|---|---|---|
| `quality` | `uv sync --locked` → ruff lint + format → mypy strict → unit tests + coverage → `pip-audit` | Style drift, type errors, logic bugs, known-vulnerable dependencies, lockfile out of sync |
| `integration` | `docker compose up --wait` (real services) → integration tests → **build image + full stack** → `curl /health/live` and `/health/ready` | DB constraints, migrations, drift, outages; broken Dockerfile or Compose file; the app not booting |

### Design choices
| Choice | Why | Alternative |
|---|---|---|
| Reuse `docker-compose.yml` in CI instead of Actions `services:` | One definition of the stack; CI also tests the Compose file. Actions service containers can't override the container command (SeaweedFS needs one). | `services:` blocks (duplicated config) |
| Actions pinned to **commit SHAs** | A tag can be moved or hijacked; a SHA can't (real supply-chain attacks have used moved tags) | `@v7` tags (convenient, mutable) |
| `permissions: contents: read`, `persist-credentials: false` | Least privilege: a compromised step can't push code with the job's token | Default token permissions |
| `concurrency` with `cancel-in-progress` | A new push cancels the obsolete run, saving runner minutes | Every run completes |
| `uv sync --locked` | CI fails if `uv.lock` is out of date with `pyproject.toml` | Silent re-resolution |
| Logs dumped only `if: failure()`; `down -v` with `if: always()` | Debuggable failures, clean runners | — |
| Dependabot (uv, actions, docker) | Updates arrive as PRs that CI tests before merge | Manual upgrades |

### What breaks without CI
| Without | Consequence |
|---|---|
| Automated checks on PRs | "Works on my machine" merges; regressions discovered by users |
| Integration tests in CI | Unit tests pass with mocks while the real database rejects the query |
| A stack smoke test | A Dockerfile typo is found at deploy time, not review time |
| Dependency scanning | Known CVEs ship silently |

### Recommended next (GitHub settings, done by the owner)
Protect `main`: require the `Lint, types, unit tests` and `Integration tests + stack smoke test` checks to pass before merging, and disallow direct pushes.

### Exercises
1. Push a branch with a deliberate type error (e.g. `return 1` from `live()`). Which job fails, on which step?
2. Bump a dependency in `pyproject.toml` without running `uv lock` and push. What does `uv sync --locked` say?

### Interview questions
- **"What belongs in CI for a service like this?"** Fast static checks first, unit tests, then integration tests against real dependencies, an image build, a boot/readiness smoke test, and dependency scanning. Fail fast and keep it under ~10 minutes.
- **"How do you secure a CI pipeline?"** Least-privilege tokens, SHA-pinned actions, no secrets for PRs from forks, secrets scoped to environments, dependency and image scanning.

---

## Phase 1 recap

| Step | You can now explain |
|---|---|
| 1.1 | Python project layout, uv + lockfile, app factory, liveness |
| 1.2 | Typed fail-fast config, `SecretStr`, test isolation from `.env` |
| 1.3 | Structured logs, correlation IDs via contextvars, redaction, log injection |
| 1.4 | Multi-stage non-root images, graceful shutdown, health-gated Compose, ADR for MinIO → SeaweedFS |
| 1.5 | Pools, sessions, migrations as a separate job, DB constraints vs races, schema-drift tests |
| 1.6 | Readiness vs liveness, concurrent checks with timeouts, blocking calls in async code |
| 1.7 | CI pipeline design and supply-chain hygiene |
