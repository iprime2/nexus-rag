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
