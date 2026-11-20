# ADR-0006: Hybrid retrieval with Postgres FTS and Reciprocal Rank Fusion

- **Status:** Accepted (2026-11-20)
- **Date:** 2026-11-20

## Context
Dense embeddings capture meaning but miss exact tokens: error codes, SKUs, names, clause numbers. Enterprise questions often hinge on those. A keyword retriever is needed, and its results must be combined with the vector results.

## Decision
- Keyword search via Postgres FTS (`tsvector` generated column + GIN index, `websearch_to_tsquery`, `ts_rank_cd`), filtered by tenant and current version in the same SQL.
- Combine with Qdrant results using **Reciprocal Rank Fusion** (`k = 60`, configurable weights).
- Measure on the evaluation set: semantic-only vs keyword-only vs hybrid.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| **Postgres FTS** | No new infrastructure; text already there; joins with authorization | Not BM25 (no IDF); limited language support |
| Qdrant sparse vectors (BM25/SPLADE) | One engine, one query | Another indexing pipeline; SPLADE needs a model |
| ParadeDB `pg_search` | True BM25 in Postgres | Extension availability (e.g. on RDS) |
| OpenSearch / Elasticsearch | Best-in-class lexical search | A whole cluster to operate |
| Score normalization + weighted sum (instead of RRF) | Can be tuned more finely | Fragile: depends on per-query score distributions |

## Consequences
- Keyword quality may be weaker on some corpora. The evaluation harness will show it, and the alternatives above are the upgrade path.
- The FTS language is fixed per generated column (assumption A-4).
