# NexusRAG — Requirements

> Status: **Proposed (Phase 0)**. Open questions are listed at the end. Nothing here is final until the project owner approves it.

## 1. What we are building

NexusRAG is a multi-tenant document intelligence backend. Tenants upload large batches of documents (500–1,000+ per batch). The platform processes them asynchronously on horizontally scalable workers, indexes them for hybrid (semantic + keyword) retrieval, and answers natural-language questions with streamed, cited answers grounded only in documents the caller is authorized to see.

The engineering interest is not "chat with a PDF". It is in the parts a production system needs and a demo skips:

- a durable ingestion pipeline that survives crashes, duplicate deliveries, and provider rate limits without corrupting state or duplicating vectors;
- strict tenant isolation enforced in the backend, never by the LLM;
- measured, not claimed, retrieval quality and throughput.

## 2. Functional requirements

### FR-1 Ingestion
| ID | Requirement |
|---|---|
| FR-1.1 | Upload documents individually or as a named **batch** (target: 1,000 documents per batch). |
| FR-1.2 | Accept PDF, DOCX, TXT and HTML. Validate type by content (magic bytes), not by extension or `Content-Type`. |
| FR-1.3 | Enforce per-file size limits and per-request file-count limits. Reject encrypted or corrupt files with a clear reason. |
| FR-1.4 | Compute a SHA-256 checksum while streaming the upload. Detect duplicate content within a tenant. |
| FR-1.5 | Register each document and create an ingestion job before acknowledging the upload (HTTP 202). |
| FR-1.6 | Process jobs asynchronously: extract → clean → chunk → extract metadata → embed → index. |
| FR-1.7 | Expose job, document and batch status, including per-document failure reasons. |
| FR-1.8 | **Versioning**: re-uploading a document with the same identity but different content creates a new version. The previous version stays searchable until the new one is fully indexed. |
| FR-1.9 | **Deletion**: deleting a document removes it from retrieval immediately and asynchronously removes its chunks, vectors and stored objects. |
| FR-1.10 | Manually retry dead-lettered jobs, cancel queued jobs, and re-index documents. |

### FR-2 Retrieval
| ID | Requirement |
|---|---|
| FR-2.1 | Semantic (vector) search over chunk embeddings. |
| FR-2.2 | Keyword (full-text) search over chunk text. |
| FR-2.3 | Hybrid retrieval that fuses both result lists (Reciprocal Rank Fusion by default). |
| FR-2.4 | Metadata filters: document IDs, MIME type, tags, upload date range. |
| FR-2.5 | Optional reranking of fused candidates. |
| FR-2.6 | Context assembly within a token budget, with source attribution for every chunk. |
| FR-2.7 | A retrieval-only endpoint for debugging and evaluation. |

### FR-3 Generation
| ID | Requirement |
|---|---|
| FR-3.1 | Answer questions using only the retrieved context, with citations to documents and pages. |
| FR-3.2 | Stream responses using Server-Sent Events. |
| FR-3.3 | Support OpenAI, Anthropic and AWS Bedrock behind one provider interface. Make the model configurable per request within an allow-list. |
| FR-3.4 | Persist multi-turn conversations and use history to resolve follow-up questions. |
| FR-3.5 | Return "insufficient evidence" instead of answering when retrieval finds nothing relevant. |
| FR-3.6 | Return structured output (answer + citations as JSON) for non-streaming calls. |

### FR-4 Tenancy and access
| ID | Requirement |
|---|---|
| FR-4.1 | Tenants, users and memberships with roles (`owner`, `admin`, `member`, `viewer`). |
| FR-4.2 | Authenticate interactive users with JWT bearer tokens and machine clients with API keys. |
| FR-4.3 | Scope every read and write to the caller's tenant. The tenant is derived from the credential, never from the request body. |
| FR-4.4 | Document-level access restriction (groups). *Proposed as a Phase 5 stretch goal; see open questions.* |

### FR-5 Evaluation and operations
| ID | Requirement |
|---|---|
| FR-5.1 | A versioned evaluation dataset (questions, reference answers, relevant source chunks). |
| FR-5.2 | Evaluation runs that compute retrieval metrics (Recall@K, Precision@K, MRR) and generation metrics (faithfulness, answer relevance, citation correctness), stored with the exact configuration used. |
| FR-5.3 | Prometheus metrics, Grafana dashboards and structured JSON logs with correlation IDs. |
| FR-5.4 | Liveness and readiness health endpoints for API and workers. |

## 3. Non-functional requirements

These are **targets to be verified by measurement in Phase 7**, not claims.

| ID | Category | Target |
|---|---|---|
| NFR-1 | Ingestion throughput | A 1,000-document batch (reference corpus: ~10 pages per document) completes with zero lost documents. Throughput is reported as documents/min and chunks/min per worker count. |
| NFR-2 | Ingestion correctness | Zero duplicate chunks or vectors under duplicate deliveries, retries and worker crashes, verified by tests. |
| NFR-3 | Query latency | Initial targets, to be revised after the first benchmark: retrieval (excluding the LLM) p95 < 300 ms; time to first token p95 < 2.5 s; full answer p95 < 10 s. |
| NFR-4 | Availability (local) | Killing any single worker or restarting Redis loses no jobs. Jobs complete after recovery. |
| NFR-5 | Availability (AWS) | No single API or worker task is a single point of failure. Managed data stores use multi-AZ options where the budget allows. Real HA is claimed only for what has been failure-tested. |
| NFR-6 | Security | No cross-tenant data access through any API path (verified by dedicated tests). No secrets in code, images or logs. |
| NFR-7 | Scalability | API and workers scale independently. Worker count and concurrency are configuration, not code changes. |
| NFR-8 | Resource safety | Workers never load a whole large file into memory at once. Bounded memory per worker process. |
| NFR-9 | Provider safety | Ingestion never exceeds the configured embedding-provider rate limits (requests/min and tokens/min), even with many workers. |
| NFR-10 | Observability | Every request and job is traceable end-to-end by correlation ID. Core metrics are listed in the system design. |
| NFR-11 | Portability | Vector store, object store, LLM provider and embedding provider sit behind interfaces. Local development needs only Docker Compose. |
| NFR-12 | Cost visibility | Embedding and LLM token usage is recorded per tenant, so cost per 1,000 documents and per query can be reported. |

## 4. Missing requirements and assumptions

The specification leaves these open. Each has a proposed assumption that the design relies on. **Please confirm or correct them.**

| # | Gap | Proposed assumption |
|---|---|---|
| A-1 | **What makes two uploads "the same document" for versioning?** Checksums detect identical *content*, not a new version of the same document. | Clients may send an optional `external_id` (for example a path or a CMS ID). Same tenant + same `external_id` + different content = new version. No `external_id` means always a new document. Same tenant + same checksum = duplicate (the existing document is returned, with no new job). |
| A-2 | Scanned PDFs / OCR | **No OCR** initially. PDFs without a text layer fail with the error code `NO_TEXT_LAYER`. OCR can be added later as an extractor. |
| A-3 | Tables, images, charts inside documents | Text only. Tables are extracted as plain text where the extractor supports it. |
| A-4 | Language | English first (Postgres FTS uses the `english` configuration). The configuration is stored per tenant so it can change later. |
| A-5 | Document size distribution | Reference corpus: median ~10 pages, max 50 MB / 1,000 pages per file. Limits are configurable. |
| A-6 | Number of tenants | Tens of tenants, not thousands. This affects the Qdrant collection strategy (see ADR-0008). |
| A-7 | Identity provider | NexusRAG issues its own JWTs (email + password, argon2 hashing) and API keys. Integration with an external IdP (Cognito / Auth0 / Keycloak) is deferred but not precluded. |
| A-8 | Frontend | API-only plus OpenAPI/Swagger UI. A minimal demo UI is optional in Phase 9. |
| A-9 | Tenant fairness | One tenant's 1,000-document batch should not starve another tenant's single upload. Handled with per-tenant in-flight limits (Phase 5). |
| A-10 | Retention and erasure | Deletion is a hard delete of the stored object, chunks and vectors, with a tombstone row kept for audit. Conversations that cited a deleted document keep the citation snapshot but mark it unavailable. |
| A-11 | Embedding model | One embedding model per deployment at a time (default: OpenAI `text-embedding-3-small`, 1,536 dimensions, to be confirmed in Phase 3). Changing the model means a new vector collection and a re-index. |
| A-12 | Cost limits | Per-tenant monthly token budgets are out of scope initially. Usage is recorded so budgets can be added. |
| A-13 | Data sources | Ingestion is upload-based. Connectors that pull from S3 buckets or RDBMS tables (shown in the reference diagram) are out of scope until after Phase 9. |

## 5. Scope relative to the reference architecture diagram

The reference diagram contains components the written specification either omits or argues against. The proposal is to **build the specification first and treat the extra diagram components as later extensions**. ADR-0009 has the full reasoning.

| Diagram component | Proposal | Reason |
|---|---|---|
| Kubernetes, Helm | Defer; use **ECS** (Phase 8) | The specification says not to introduce Kubernetes without a justified need. ECS covers API and worker scaling. |
| Terraform | **Adopt** in Phase 8 | Infrastructure as code is missing from the specification, and Terraform works for ECS too. |
| Neo4j + graph extraction (GraphRAG) | Defer (optional Phase 10) | LLM-based entity extraction costs roughly one LLM call per chunk, which is expensive at 1,000 documents. Adopt it only if evaluation shows multi-hop questions failing. |
| Multi-sub-agents / planner | Defer | The specification excludes agentic orchestration from the core pipeline unless a stateful workflow needs it. |
| Ray Serve + vLLM on GPU clusters | Defer | Self-hosted models need GPUs, which drive up cost. vLLM exposes an OpenAI-compatible API, so it can later be added as a provider with little code. |
| Caching layer | Phase 7, measured | Query-embedding cache first. Answer caching only with tenant- and permission-aware cache keys. |
| Alerting | Phase 6 | Grafana alerting on the same Prometheus metrics. |
| Amazon S3 / RDBMS as data sources | See A-13 | — |

## 6. Open questions for the project owner

1. Do you approve the scoping in section 5 (specification first, diagram extras deferred)?
2. Is assumption A-1 (`external_id` defines document identity) acceptable?
3. Is document-level access control (FR-4.4) a hard requirement, or a stretch goal after tenant isolation?
4. Do you want a separately deployed query service from day one, or a modular monolith that can be split later? (Recommendation: split later; see ADR-0001.)
5. Should reranking use a hosted API (Cohere / Bedrock rerank) or a local cross-encoder? A local model adds roughly 1–2 GB of PyTorch to the image. (Recommendation: decide in Phase 4 using evaluation data.)
