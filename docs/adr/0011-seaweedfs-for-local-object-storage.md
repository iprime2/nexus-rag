# ADR-0011: SeaweedFS as the local S3-compatible store

- **Status:** Accepted (2026-11-20). The choice was delegated to Phase 1 step 1.4 in the approved Phase 1 plan.
- **Date:** 2026-11-20
- **Refines:** [ADR-0005](0005-s3-compatible-object-storage.md) (which named MinIO as the default, with SeaweedFS/LocalStack as fallbacks)

## Context
ADR-0005 requires an S3-compatible server in local development so the same boto3 code runs locally and on AWS S3. MinIO was the default. In step 1.4 we found that MinIO's community edition stopped publishing Docker images in October 2025, went into maintenance mode, and its repository has since been archived. The last community images get no security fixes.

## Decision
Use **SeaweedFS** (`chrislusf/seaweedfs`, pinned version) as a single all-in-one container (`weed server -s3`). Credentials come from the standard `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` variables. Verified behaviour: correct signature → success, wrong secret → `SignatureDoesNotMatch`, anonymous → `403`, the same as real S3.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Last MinIO image (frozen) | Familiar, zero code change | No security fixes, dead project |
| Third-party MinIO rebuilds / forks | Drop-in | Unclear long-term maintenance and trust |
| **SeaweedFS** | Apache 2.0, mature, actively maintained, single container, S3 auth works via standard env vars | Larger feature surface than we need; different admin tooling from MinIO |
| RustFS | Closest MinIO drop-in, Apache 2.0 | Young project, less proven |
| Garage | Lightweight | AGPLv3; designed for multi-node, awkward as a single dev node |
| LocalStack S3 | Emulates many AWS services | Emulator, not a real store; heavier image |

## Consequences
- No application code changes: the app only depends on the S3 API (`ObjectStore` protocol, ADR-0005).
- Only S3 features we actually use (put/get/delete, multipart, presigned URLs, lifecycle) need to work locally. Integration tests in Phase 2 will verify each one against SeaweedFS.
- Revisit if SeaweedFS's S3 compatibility blocks a feature we need, or if a lighter maintained option becomes standard.
