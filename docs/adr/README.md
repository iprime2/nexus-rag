# Architecture Decision Records

An ADR captures one significant decision: the context, the decision, the alternatives and the consequences. ADRs are never rewritten after acceptance. A changed decision gets a new ADR that supersedes the old one, so the history of *why* is preserved.

Status values: `Proposed` → `Accepted` | `Rejected`; later `Superseded by ADR-XXXX`.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-modular-monolith-with-process-roles.md) | Modular monolith with separate process roles | Accepted |
| [0002](0002-celery-with-redis-broker.md) | Celery with a Redis broker | Accepted |
| [0003](0003-qdrant-for-vectors-postgres-for-text.md) | Qdrant for vectors, Postgres for chunk text | Accepted |
| [0004](0004-postgres-as-job-state-source-of-truth.md) | Postgres as the source of truth for job state | Accepted |
| [0005](0005-s3-compatible-object-storage.md) | S3-compatible object storage everywhere | Accepted |
| [0006](0006-hybrid-retrieval-postgres-fts-rrf.md) | Hybrid retrieval with Postgres FTS and RRF | Accepted |
| [0007](0007-native-llm-provider-abstraction.md) | Native LLM provider abstraction | Accepted |
| [0008](0008-tenant-isolation-strategy.md) | Tenant isolation strategy | Accepted |
| [0009](0009-scope-relative-to-reference-diagram.md) | Scope relative to the reference diagram | Accepted |
| [0010](0010-two-stage-worker-pipeline.md) | Two-stage worker pipeline | Accepted |
| [0011](0011-seaweedfs-for-local-object-storage.md) | SeaweedFS as the local S3-compatible store (refines 0005) | Accepted |

Template: [template.md](template.md).
