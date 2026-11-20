# ADR-0010: Two-stage worker pipeline

- **Status:** Accepted (2026-11-20)
- **Date:** 2026-11-20

## Context
Extraction and chunking are CPU-bound. Embedding and indexing are I/O-bound and limited by an external rate limit. Embedding is also the most failure-prone stage (429s, outages). If one task did everything, a provider failure would force re-extraction, and one concurrency setting would have to serve two opposite workloads.

## Decision
Two Celery queues and worker roles:
- `ingest.extract`: download, deep validation, extraction, cleaning, chunking, metadata. Persists chunks to Postgres, then sets the job to `CHUNKED` and enqueues the embed stage.
- `ingest.embed`: batched embedding under the global rate limiter, Qdrant upserts, completion transaction.

Persisted chunks are the **checkpoint**. Retries resume from `checkpoint = extract | embed`.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| One task per document | Simplest | Re-extracts on embedding failure; mixed workload under one concurrency setting |
| **Two stages** | Independent scaling; cheap retries; per-stage queue wait time measurable | One extra hand-off and state (`CHUNKED`) |
| Task per stage (5+ queues) / Celery chains | Maximum granularity | Intermediate artifacts everywhere; harder to reason about and test |

## Consequences
- A new job state, `CHUNKED`, is added to the specification's list (see ingestion-workflow §2).
- Benchmarks report extract and embed throughput separately, which makes the bottleneck visible.
