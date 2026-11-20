# ADR-0001: Modular monolith with separate process roles

- **Status:** Accepted (2026-11-20)
- **Date:** 2026-11-20

## Context
The platform has two very different workloads. **Request handling** (uploads, status, streaming queries) is latency-sensitive and I/O-bound. **Document processing** is slow, CPU- and provider-bound, and bursty (1,000 documents at once). These must not interfere. The specification also asks for a "separate query service" while warning against unnecessary microservices.

## Decision
One Python package and one container image, run as separate **process roles**: `api`, `worker-extract`, `worker-embed`, `worker-maint`. Ingestion and query code are separate modules with no imports between them. The query routes can be deployed as their own `query-api` role (same image, different router set) when measurements show upload and query traffic interfering.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Single process (API does processing in background threads) | Simplest | Processing starves the API; can't scale independently; lost work on restart |
| **Modular monolith + process roles** | Workload isolation, independent scaling, one codebase, in-process calls | Discipline needed to keep module boundaries clean |
| Microservices (ingestion, query, worker, auth as separate services) | Independent deploys and team ownership | Network hops, distributed consistency, N deploy pipelines, all before there's any need |

## Consequences
- Scaling is per role via replica count and concurrency settings.
- Module boundaries are enforced by convention and reviewed. An import-linter rule can be added in Phase 1 if needed.
- Revisit if independent teams, independent release cadences, or measured contention appear.
