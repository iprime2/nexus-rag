# NexusRAG — API Specification (v1)

> Status: **Proposed (Phase 0)**. This is the contract that FastAPI/Pydantic schemas will implement. The generated OpenAPI document becomes the source of truth once code exists.

## 1. Conventions

| Topic | Convention |
|---|---|
| Base path | `/v1` (URI versioning: simple and visible in logs) |
| Auth | `Authorization: Bearer <JWT>` for users; `Authorization: ApiKey <key>` for machine clients |
| Tenant | **Derived from the credential.** Never accepted in paths or bodies. Users in several tenants select one when logging in (the token is tenant-scoped). |
| IDs | UUIDv7 strings |
| Time | RFC 3339 UTC |
| Pagination | Cursor-based: `?limit=50&cursor=<opaque>` → `{ "items": [...], "next_cursor": "..." }`. Offsets get slow and inconsistent on large, changing tables. |
| Idempotency | `Idempotency-Key` header accepted on `POST` endpoints that create resources. The same key and body within 24 h returns the original response. |
| Errors | RFC 9457 `application/problem+json` (see §8) |
| Correlation | `X-Request-ID` accepted or generated, echoed in responses, propagated to logs, Celery tasks and traces |
| Rate limits | `429` + `Retry-After`. `RateLimit-*` headers on responses. |
| Async operations | `202 Accepted` + a status resource to poll |

## 2. Authentication & tenants

| Method | Path | Role | Description |
|---|---|---|---|
| `POST` | `/v1/auth/token` | — | Email + password + tenant slug → short-lived access token (15 min) + refresh token |
| `POST` | `/v1/auth/refresh` | — | Rotate refresh token → new access token |
| `GET` | `/v1/me` | any | Current user, tenant, role |
| `POST` | `/v1/api-keys` | admin | Create key (plaintext returned **once**) |
| `GET` | `/v1/api-keys` | admin | List (prefix, scopes, last used) |
| `DELETE` | `/v1/api-keys/{id}` | admin | Revoke |
| `POST` | `/v1/tenants/current/members` | owner/admin | Invite or add a member with a role |

Tenant creation is an operator action (a CLI script) in the initial scope.

## 3. Ingestion

### Batches

| Method | Path | Role | Description |
|---|---|---|---|
| `POST` | `/v1/batches` | member+ | Create a batch → `201 {id, name, created_at}` |
| `POST` | `/v1/batches/{batch_id}/documents` | member+ | Multipart upload of up to N files (default 50) into the batch → `202` |
| `GET` | `/v1/batches/{batch_id}` | viewer+ | Progress (below) |
| `GET` | `/v1/batches/{batch_id}/jobs?status=&cursor=` | viewer+ | Per-document job list, filterable (e.g. `status=FAILED`) |
| `POST` | `/v1/batches/{batch_id}/seal` | member+ | Optional: declare that no more uploads are coming, so "complete" is well-defined |

**Upload request** (`multipart/form-data`): repeated `files` parts, plus an optional JSON `metadata` part:
```json
{ "files": { "<filename>": { "external_id": "hr/travel-policy", "title": "Travel Policy", "tags": ["hr"] } } }
```

**Upload response** `202` (per-file outcome; an upload request partially succeeds):
```json
{
  "batch_id": "0192…",
  "results": [
    { "filename": "travel.pdf", "outcome": "accepted",  "document_id": "…", "version_id": "…", "job_id": "…" },
    { "filename": "travel-copy.pdf", "outcome": "duplicate", "document_id": "…", "existing_version_id": "…" },
    { "filename": "notes.exe", "outcome": "rejected", "error": { "code": "UNSUPPORTED_TYPE", "detail": "Detected application/x-dosexec" } }
  ]
}
```

**Batch progress** `200`:
```json
{
  "id": "…", "name": "Q3 contracts", "sealed": true,
  "state": "completed_with_errors",
  "counts": { "total": 1000, "pending": 0, "queued": 0, "processing": 0, "retry_pending": 0,
              "completed": 991, "failed": 6, "dead_letter": 3, "cancelled": 0, "duplicate": 12 },
  "started_at": "…", "completed_at": "…"
}
```
`state` is derived: `in_progress | completed | completed_with_errors`.

### Documents

| Method | Path | Role | Description |
|---|---|---|---|
| `POST` | `/v1/documents` | member+ | Single upload outside a batch (same semantics) → `202` |
| `POST` | `/v1/documents/checksum-lookup` | member+ | Body `{ "sha256": ["…", …] }` (≤ 1,000) → which checksums already exist. Lets incremental-sync clients skip uploading unchanged files. |
| `GET` | `/v1/documents?status=&tag=&cursor=` | viewer+ | List |
| `GET` | `/v1/documents/{id}` | viewer+ | Metadata, current version, latest job status |
| `GET` | `/v1/documents/{id}/versions` | viewer+ | Version history |
| `GET` | `/v1/documents/{id}/download` | viewer+ | `302` to a short-lived presigned URL for the current version |
| `POST` | `/v1/documents/{id}/reindex` | admin | New job for the current version → `202` |
| `DELETE` | `/v1/documents/{id}` | admin | `202`. Immediately hidden from retrieval; async cleanup of vectors, chunks and objects. |

### Jobs

| Method | Path | Role | Description |
|---|---|---|---|
| `GET` | `/v1/jobs/{id}` | viewer+ | Status, attempt, stage timings, error (`code`, `message`; no stack traces) |
| `GET` | `/v1/jobs/{id}/events` | admin | State-transition timeline |
| `POST` | `/v1/jobs/{id}/retry` | admin | `DEAD_LETTER` → `QUEUED` (`409` from any other state) |
| `POST` | `/v1/jobs/{id}/cancel` | member+ | Cancel (immediate or cooperative, see the ingestion workflow) |

### Upload validation errors (`error.code`)
`UNSUPPORTED_TYPE`, `TYPE_MISMATCH` (extension vs content), `FILE_TOO_LARGE`, `TOO_MANY_FILES`, `EMPTY_FILE`, `TENANT_QUOTA_EXCEEDED`. Errors found later by workers (`ENCRYPTED_DOCUMENT`, `CORRUPT_DOCUMENT`, `NO_TEXT_LAYER`, `PAGE_LIMIT_EXCEEDED`, `NO_EXTRACTABLE_TEXT`) appear on the job.

## 4. Query

| Method | Path | Role | Description |
|---|---|---|---|
| `POST` | `/v1/query` | viewer+ | Question answering. Returns JSON, or SSE when `Accept: text/event-stream`. |
| `POST` | `/v1/retrieve` | viewer+ | Retrieval only (no LLM): ranked chunks with scores per retriever. For debugging and evaluation. |

**Request:**
```json
{
  "question": "What is the per-diem limit for international travel?",
  "conversation_id": "…",
  "filters": { "document_ids": ["…"], "tags": ["hr"], "mime_types": ["application/pdf"],
               "uploaded_after": "2026-01-01T00:00:00Z" },
  "retrieval": { "top_k": 8, "use_reranker": true },
  "generation": { "provider": "anthropic", "model": "<allow-listed model id>" }
}
```
All fields except `question` are optional. Defaults come from configuration. `provider`/`model` must be in the allow-list.

**JSON response** `200`:
```json
{
  "answer": "International per-diem is capped at … [S1].",
  "insufficient_evidence": false,
  "citations": [
    { "source_id": "S1", "document_id": "…", "version_id": "…", "title": "Travel Policy 2026",
      "pages": [4, 5], "chunk_ids": ["…"], "quote": "…", "quote_verified": true }
  ],
  "conversation_id": "…", "message_id": "…",
  "usage": { "provider": "anthropic", "model": "<allow-listed model id>", "input_tokens": 4120, "output_tokens": 210 },
  "degraded": [],
  "timings_ms": { "retrieval": 142, "rerank": 210, "ttft": 980, "total": 2650 }
}
```

**SSE stream** (`text/event-stream`):
```text
event: meta
data: {"conversation_id":"…","message_id":"…","degraded":[]}

event: sources
data: {"sources":[{"source_id":"S1","document_id":"…","title":"Travel Policy 2026","pages":[4,5]}]}

event: token
data: {"text":"International per-diem is "}

event: token
data: {"text":"capped at … [S1]."}

event: citations
data: {"citations":[…], "invalid_citations_removed":0}

event: done
data: {"usage":{…},"timings_ms":{…}}
```
On failure mid-stream: `event: error` with a problem object, then the stream closes. A keep-alive comment (`: ping`) is sent every 15 s so proxies don't close idle connections.

**Why SSE and not WebSockets:** the flow is one-directional (server → client) and runs over plain HTTP, which works through ALBs and proxies. It reconnects natively and needs no connection-state management on the server.

## 5. Conversations

| Method | Path | Role | Description |
|---|---|---|---|
| `POST` | `/v1/conversations` | viewer+ | Create (optional title) |
| `GET` | `/v1/conversations?cursor=` | viewer+ | The caller's own conversations |
| `GET` | `/v1/conversations/{id}/messages?cursor=` | owner of conversation | Messages with citation snapshots |
| `DELETE` | `/v1/conversations/{id}` | owner of conversation | Delete |

Conversations are private to the user who created them, even within a tenant.

## 6. Evaluation (admin)

| Method | Path | Description |
|---|---|---|
| `POST` | `/v1/admin/evaluation-runs` | Start a run: `{dataset, dataset_version, config_overrides}` → `202` |
| `GET` | `/v1/admin/evaluation-runs/{id}` | Summary metrics + config + git SHA |
| `GET` | `/v1/admin/evaluation-runs/{id}/results` | Per-question results |

Evaluation will mainly run from a CLI (`python -m app.evaluation run …`). The endpoints are thin wrappers for convenience.

## 7. Operations

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/health/live` | none | Process is up (no dependency checks, so an unhealthy DB doesn't cause restart storms) |
| `GET` | `/health/ready` | none | Can serve: Postgres reachable, migrations current, Redis + Qdrant reachable. Returns per-dependency status. |
| `GET` | `/metrics` | internal network only | Prometheus exposition |

Workers expose liveness via a heartbeat file and Celery `inspect ping`, plus a `/metrics` endpoint on a side port.

## 8. Error format

```json
{
  "type": "https://nexusrag.dev/errors/file-too-large",
  "title": "File too large",
  "status": 413,
  "detail": "contract.pdf is 74 MB; the limit is 50 MB.",
  "code": "FILE_TOO_LARGE",
  "request_id": "…"
}
```

| Status | When |
|---|---|
| 400 | Malformed request |
| 401 | Missing or invalid credential |
| 403 | Authenticated but role insufficient |
| 404 | Resource doesn't exist **or belongs to another tenant**. These are never distinguished, so resource IDs from other tenants can't be probed. |
| 409 | Invalid state transition (e.g. retrying a non-dead-lettered job), idempotency key reused with a different body |
| 413 | File or request too large |
| 415 | Unsupported media type |
| 422 | Validation error (Pydantic) |
| 429 | Rate limit or tenant quota |
| 503 | Dependency unavailable (fail closed) |
