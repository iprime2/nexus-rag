# ADR-0009: Scope relative to the reference architecture diagram

- **Status:** Accepted (2026-11-20)
- **Date:** 2026-11-20

## Context
The reference diagram includes Kubernetes/Helm/Terraform, Neo4j with graph extraction, multi-sub-agents (planner, graph search, vector search), Ray Serve with vLLM on GPU clusters, a caching layer, alerting, and S3/RDBMS data sources. The written specification says to avoid Kubernetes unless justified, keep agentic frameworks out of the core pipeline unless needed, use hosted LLM providers, and use ECS on AWS. Building everything at once would spread effort thin and weaken the depth the portfolio is meant to show.

## Decision
Build the written specification first. Treat diagram-only components as **evidence-gated extensions**:

| Component | When it becomes justified |
|---|---|
| Terraform | Phase 8: adopted (IaC for ECS) |
| Alerting | Phase 6: adopted (Grafana alerting) |
| Caching | Phase 7: query-embedding cache first; answer cache only with permission-aware keys |
| Neo4j / GraphRAG | The evaluation set shows multi-hop or relationship questions failing with hybrid retrieval, **and** the extraction cost per 1,000 documents is acceptable |
| Planner / sub-agents | Questions need multi-step tool use (e.g. combining structured data and documents) that a single retrieval pass can't serve |
| Ray Serve + vLLM | Cost, data residency or latency requirements rule out hosted providers. The OpenAI-compatible adapter path keeps this cheap to add. |
| Kubernetes / Helm | Requirements ECS can't meet (e.g. GPU scheduling for self-hosted models, multi-cloud) |
| S3 / RDBMS connectors | A concrete source-sync use case after Phase 9 |

## Consequences
- Interfaces (pipeline stages, `Retriever`, `LLMProvider`) are designed so these can be added without rewrites.
- The README will show the reference diagram as the *vision* and the implemented architecture separately, so readers aren't misled about what exists.
