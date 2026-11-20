# Architecture Decision Records

An ADR captures one significant decision: the context, the decision, the alternatives and the consequences. ADRs are never rewritten after acceptance. A changed decision gets a new ADR that supersedes the old one, so the history of *why* is preserved.

Status values: `Proposed` → `Accepted` | `Rejected`; later `Superseded by ADR-XXXX`.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-modular-monolith-with-process-roles.md) | Modular monolith with separate process roles | Proposed |
| [0002](0002-celery-with-redis-broker.md) | Celery with a Redis broker | Proposed |
| [0003](0003-qdrant-for-vectors-postgres-for-text.md) | Qdrant for vectors, Postgres for chunk text | Proposed |
| [0004](0004-postgres-as-job-state-source-of-truth.md) | Postgres as the source of truth for job state | Proposed |
| [0005](0005-s3-compatible-object-storage.md) | S3-compatible object storage everywhere | Proposed |
| [0006](0006-hybrid-retrieval-postgres-fts-rrf.md) | Hybrid retrieval with Postgres FTS and RRF | Proposed |
| [0007](0007-native-llm-provider-abstraction.md) | Native LLM provider abstraction | Proposed |
| [0008](0008-tenant-isolation-strategy.md) | Tenant isolation strategy | Proposed |
| [0009](0009-scope-relative-to-reference-diagram.md) | Scope relative to the reference diagram | Proposed |
| [0010](0010-two-stage-worker-pipeline.md) | Two-stage worker pipeline | Proposed |

Template: [template.md](template.md).
