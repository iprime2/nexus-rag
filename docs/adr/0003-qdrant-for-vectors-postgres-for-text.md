# ADR-0003: Qdrant for vectors, Postgres for chunk text

- **Status:** Proposed
- **Date:** 2026-11-20

## Context
Semantic retrieval needs approximate nearest-neighbour (ANN) search with tenant and metadata filters. Chunk text is also needed for keyword search, citations and re-embedding. Storing data in two systems creates consistency questions.

## Decision
- **Qdrant** stores one point per chunk: vector + filter payload (`tenant_id`, `document_id`, `document_version_id`, `chunk_index`, `mime_type`, `tags`). No chunk text.
- **Postgres** stores chunk text, metadata and the FTS index, and is the authority on visibility.
- Point ID = chunk ID = `uuid5(version_id:chunk_index)`. Writes are idempotent upserts.
- One collection per embedding model (`chunks__<model>__v<n>`), accessed via a Qdrant alias so a re-embed can switch atomically.
- All access goes through a `VectorStore` protocol so another backend (pgvector) can be added.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| pgvector | One database; transactional consistency; simplest operations; fine at this scale | Filtered HNSW is weaker (iterative scans help but tuning is needed); fewer vector-specific features; scaling ties vector load to the OLTP database |
| **Qdrant** | Filterable HNSW, tenant-optimized payload indexes, sparse vectors, quantization, snapshots, replication | A second store to keep consistent; another service to operate |
| Weaviate / Milvus | Feature-rich | Heavier to run; not needed |
| Text duplicated into the Qdrant payload | One fewer query at search time | 2× text storage; two copies to keep consistent; no authority re-check |

## Consequences
- The query path hydrates chunk text from Postgres by ID (+1 indexed query, ~1–3 ms). That same query re-checks authorization and currency.
- Cleanup and orphan reconciliation are needed (see ingestion-workflow §8).
- Revisit if the hydration round trip shows up as a meaningful share of p95 latency.
