# Ownership tracker

**Goal:** the owner can defend every module in an interview (`CLAUDE.md` → Ownership rules).

How to read and update this file:
- **Implemented by** comes from git history. Every module so far was written by Claude (AI). No row is overstated.
- **Owner's role** records what the owner did: *spec* (wrote the behaviour/test cases), *design* (decided the approach), *review* (passed the review gate), *defended* (answered the "Defend the PR" questions).
- **Can explain** starts at `not yet`. It moves to `partly` or `yes` only after the owner answers that module's questions in `docs/learning/defense-questions.md` (or a "Defend the PR" check) without hints. Claude updates it after the check; the owner can always downgrade it.

_Baseline set 2026-11-25 (mentor review): 32 modules, 0 owner-written. Owner contributions so far are two designs, both typed by Claude._

## API layer (`app/api/`)

| Module | What it does | Introduced | Implemented by | Owner's role | Can explain |
|---|---|---|---|---|---|
| `api/routes/health.py` | `/health/live` and `/health/ready` | #3 (1.1), #8 (1.6) | Claude | — | not yet |
| `api/schemas/health.py` | Liveness and readiness response models | #3 (1.1) | Claude | — | not yet |
| `api/routes/me.py` | `GET /v1/me` | #10 (2.1) | Claude | — | not yet |
| `api/schemas/me.py` | `/v1/me` response model | #10 (2.1) | Claude | — | not yet |
| `api/dependencies/auth.py` | `ApiKey` header → `TenantContext`; 401/403 | #10 (2.1) | Claude | — | not yet |
| `api/dependencies/db.py` | One database session per request | #7 (1.5) | Claude | — | not yet |
| `api/middleware/request_context.py` | Request ID, contextvars, access log | #5 (1.3) | Claude | — | not yet |

## Core (`app/core/`, `app/main.py`, `app/cli.py`)

| Module | What it does | Introduced | Implemented by | Owner's role | Can explain |
|---|---|---|---|---|---|
| `main.py` | App factory, clients, lifespan | #3 (1.1) | Claude | — | not yet |
| `core/config.py` | Typed fail-fast settings (`NEXUS_*`) | #4 (1.2) | Claude | — | not yet |
| `core/logging.py` | structlog pipeline, redaction | #5 (1.3) | Claude | — | not yet |
| `core/ids.py` | UUIDv7 generation | #7 (1.5) | Claude | — | not yet |
| `core/readiness.py` | Concurrent dependency checks with timeouts | #8 (1.6) | Claude | — | not yet |
| `core/redis.py` | Redis client factory | #8 (1.6) | Claude | — | not yet |
| `core/tenancy.py` | `TenantContext` | #10 (2.1) | Claude | — | not yet |
| `cli.py` | Operator CLI: tenants, keys, `extract` | #10 (2.1), #12 (W1) | Claude | — | not yet |

## Auth (`app/auth/`)

| Module | What it does | Introduced | Implemented by | Owner's role | Can explain |
|---|---|---|---|---|---|
| `auth/api_keys.py` | Key format, SHA-256 hashing, header parsing | #10 (2.1) | Claude | — | not yet |
| `auth/service.py` | Create tenant; issue / revoke / look up keys | #10 (2.1) | Claude | — | not yet |

## Database (`app/db/`)

| Module | What it does | Introduced | Implemented by | Owner's role | Can explain |
|---|---|---|---|---|---|
| `db/base.py` | Declarative base, constraint naming convention | #7 (1.5) | Claude | — | not yet |
| `db/session.py` | Engine (pool) and session factories | #7 (1.5) | Claude | — | not yet |
| `db/migrations.py` | Expected Alembic head for readiness | #8 (1.6) | Claude | — | not yet |
| `db/models/tenant.py` | `tenants` table | #7 (1.5) | Claude | — | not yet |
| `db/models/api_key.py` | `api_keys` table | #10 (2.1) | Claude | — | not yet |
| `db/models/ingestion.py` | Batches, documents, versions, jobs, job events; composite FKs; partial unique indexes | #11 (2.2) | Claude | — | not yet |

## Ingestion (`app/ingestion/`)

| Module | What it does | Introduced | Implemented by | Owner's role | Can explain |
|---|---|---|---|---|---|
| `ingestion/state.py` | Job state machine (allowed transitions) | #11 (2.2) | Claude | — | not yet |
| `ingestion/jobs.py` (except below) | CAS transitions, claims, leases, fencing | #11 (2.2) | Claude | Lesson only (2.2a–c) | not yet |
| ↳ `retry_dead_letter()` | Operator requeue of dead-lettered jobs | #11 (2.2) | Claude (typed) | **design**: expected `DEAD_LETTER` → `QUEUED`, no attempt fence | **yes** |
| `ingestion/extraction/models.py` | `PageText`, `ExtractedDocument`, `ExtractionError` | #12 (W1) | Claude | — | not yet |
| `ingestion/extraction/pdf.py` | pypdf extraction, encrypted/corrupt handling | #12 (W1) | Claude | — | not yet |
| `ingestion/extraction/text.py` | TXT decoding, form feeds as pages | #12 (W1) | Claude | — | not yet |
| `ingestion/extraction/cleaning.py` (except below) | Unicode, hyphenation, whitespace | #12 (W1) | Claude | — | not yet |
| ↳ `find_repeated_lines()` | Header/footer detection | #12 (W1) | Claude (typed) | **spec**: repetition across pages + 4 test cases (refinements by Claude) | not yet |
| `ingestion/extraction/pipeline.py` | Extract → clean → guard; `NO_TEXT_LAYER` | #12 (W1) | Claude | — | not yet |

## Storage (`app/storage/`)

| Module | What it does | Introduced | Implemented by | Owner's role | Can explain |
|---|---|---|---|---|---|
| `storage/s3.py` | boto3 client, `ensure_bucket` | #8 (1.6) | Claude | — | not yet |
| `storage/bootstrap.py` | One-off bucket creation job | #8 (1.6) | Claude | — | not yet |

## Summary

| Status | Modules |
|---|---|
| Owner can explain (`yes`) | 1 function (`retry_dead_letter`) |
| `partly` | 0 |
| `not yet` | 32 modules |
| Owner-specified or owner-designed | 2 functions |
