# ADR-0005: S3-compatible object storage everywhere

- **Status:** Accepted (2026-11-20)
- **Date:** 2026-11-20

## Context
Original files (up to tens of MB, thousands per batch) must be stored durably and read by any worker. Production will use Amazon S3.

## Decision
Use the S3 API (boto3) behind an `ObjectStore` protocol in every environment. Locally, run an S3-compatible server in Docker Compose (MinIO by default; image and licensing to be confirmed in Phase 1, with SeaweedFS or LocalStack as fallbacks). Keys are `tenants/{tenant_id}/documents/{document_id}/{version_id}`. Uploads stream through S3 multipart.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Local filesystem | Zero setup | A different code path from production; workers in separate containers need a shared volume; no presigned URLs |
| **S3-compatible server locally** | Same code as production; realistic semantics | One more container |
| Files in Postgres (`bytea`/large objects) | Transactional | Database bloat, slow backups, memory pressure |

## Consequences
- Object writes can't join DB transactions, so registration writes the object first and deletes it on failure or duplicate. S3 lifecycle rules clean up orphans.
- Presigned direct uploads stay available as a later optimization (bottleneck B5).
