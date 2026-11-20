# Phase 0: Concepts Behind the NexusRAG Design

Read this alongside [system-design.md](../system-design.md). Each section covers one idea that the design depends on. These ideas come up again and again in AI-engineering and FDE interviews, because they are what separates a demo from a system a customer can trust.

---

## 1. RAG in one page

**Problem:** an LLM knows only its training data. It doesn't know your company's documents, and it will confidently make things up.
**RAG (Retrieval-Augmented Generation):** at question time, *find* the relevant passages from your documents and *give them to the model* with instructions to answer only from them.

The pipeline has two halves:
- **Offline (ingestion):** document → text → **chunks** (passages of ~500 tokens) → **embeddings** (vectors, e.g. 1,536 numbers, whose geometric closeness ≈ semantic similarity) → stored in a **vector index**.
- **Online (query):** question → embedding → nearest chunks → prompt (instructions + chunks + question) → answer with citations.

**Why chunk?** Embedding a whole 50-page document into one vector averages away detail, and you can't fit all documents into a prompt. Chunks are the unit of retrieval *and* citation. Chunk size is a trade-off: small chunks are precise but lose context; big chunks keep context but dilute relevance and waste tokens. That's why chunk size is tuned on an evaluation set, not guessed.

**HNSW (how vector search is fast):** comparing a query to every vector is O(N). HNSW builds a layered "small-world" graph in which each vector links to near neighbours, and search hops greedily through the graph. It is *approximate*: much faster, very slightly less exact. **Filtered** search ("only tenant X's vectors") is hard for graph indexes. Naive post-filtering can return almost nothing when a tenant owns 1% of the data. This is one reason we chose Qdrant, which filters *during* graph traversal (ADR-0003).

> **Interview:** *"Why not just use a long-context model and put all documents in the prompt?"*
> Sketch: cost scales with tokens on every query; latency; models attend less reliably to the middle of very long contexts; you still need authorization filtering, and you lose precise citations. Long context complements retrieval (bigger, better-chosen context); it doesn't replace it at 1,000+ documents.

---

## 2. Hybrid search and Reciprocal Rank Fusion

Embeddings capture *meaning* ("vacation" ≈ "annual leave") but are weak at *exact tokens* (`ERR-4012`, "Clause 14.2(b)", a person's name). Keyword search is the opposite. **Hybrid** runs both and merges the results.

**The merging problem:** cosine scores (0–1) and keyword scores (unbounded) can't be added directly. **RRF** ignores scores and uses only **ranks**:

`RRF(d) = Σ 1 / (k + rank_in_list(d))`, with k = 60.

Worked example:

| Chunk | Semantic rank | Keyword rank | RRF score |
|---|---|---|---|
| A | 1 | 3 | 1/61 + 1/63 = **0.0323** |
| C | — | 1 | 1/61 = 0.0164 |
| B | 2 | — | 1/62 = 0.0161 |

A wins because *both* retrievers like it. That's the intuition: agreement between independent signals is strong evidence. `k` dampens the advantage of being ranked first, so one retriever's top hit can't dominate.

> **Try it:** compute RRF for a chunk ranked 10th by both retrievers. Does it beat a chunk ranked 1st by only one? (2/70 = 0.0286 vs 1/61 = 0.0164, so yes.) What does that tell you about RRF's behaviour?

---

## 3. Delivery guarantees: why "exactly once" is a trap

Message brokers can offer:
- **At-most-once:** might lose messages; never duplicates.
- **At-least-once:** never loses (if configured well); **might duplicate.**
- **Exactly-once:** not achievable end-to-end across a broker, a worker and external side effects such as an API call or a vector upsert.

The industry answer is **at-least-once delivery + idempotent processing = "effectively once"**. NexusRAG assumes every task may run twice, even concurrently, and makes that harmless (ingestion-workflow §5).

**Idempotent** means doing the operation twice has the same effect as doing it once. `SET x = 5` is idempotent; `x = x + 1` is not. Our tools:
- **Unique constraints:** let the database reject the duplicate, so you never "check then insert" (that's a race condition).
- **Deterministic IDs:** chunk ID = hash(version, index), so a second upsert overwrites instead of duplicating.
- **Replace, don't append:** on retry, delete the version's chunks and insert again in one transaction.

> **Interview:** *"Your worker crashed after writing to the vector DB but before marking the job done. What happens?"*
> Sketch: the message wasn't acked (acks_late) or the lease expires, so the job is retried. The retry re-upserts the same deterministic point IDs (overwrite, no duplicates), then marks the job complete. The only cost is repeated embedding calls.

---

## 4. Compare-and-set, leases and fencing tokens

**Problem:** two workers receive the same job. How does exactly one of them process it, without holding a database lock for minutes?

1. **Compare-and-set (CAS):** `UPDATE jobs SET status='EXTRACTING' WHERE id=… AND status='QUEUED' RETURNING …`. The database applies it atomically. One worker gets a row back; the other gets nothing and walks away. Same idea as optimistic locking, or a `version` column in an ORM.
2. **Lease:** "I own this until 10:05." The owner renews it with heartbeats. If the owner dies, the lease expires and someone else can take over. Unlike a lock, a lease **frees itself** when its holder disappears.
3. **Fencing token:** leases have a gap. A worker can freeze (long GC pause, network partition), lose its lease, and then wake up and keep writing. So every write carries the attempt number it was given (`WHERE attempt = 3`). Once attempt 4 exists, attempt 3's writes match nothing.

This is the pattern Martin Kleppmann describes in *Designing Data-Intensive Applications* ("How to do distributed locking"). Read it; interviewers love it.

> **Try it (Phase 2):** write a test that claims a job, simulates lease expiry, has a second worker claim it, then lets the first worker try to write. Assert that the write affects 0 rows.

---

## 5. The dual-write problem and the outbox pattern

**Problem:** the API must (1) commit the job row in Postgres and (2) publish a message to Redis. There's no transaction spanning both.
- Publish first, then commit → if the commit fails, a worker processes a job that doesn't exist.
- Commit first, then publish → if the process crashes in between, the job exists but nobody will ever process it.

**Transactional outbox:** write the "intent to publish" into the database *in the same transaction*, then have a relay publish it and retry until it succeeds. In NexusRAG the `ingestion_jobs` row **is** the outbox (status `PENDING`), and the **sweeper** is the relay. The API publishes immediately after commit as a fast path. If that fails, the sweeper picks the job up within a minute (ADR-0004).

The same problem appears with object storage (S3 can't join a DB transaction). Our answer there: write the object first, then commit. If the commit fails, delete the object, with lifecycle rules as a backstop. An orphaned *file* is harmless. A DB row pointing to a *missing* file is not.

> **Interview:** *"How do you keep Postgres and your vector DB consistent?"*
> Sketch: Postgres is the authority; the vector DB is a derived index that may lag. Deterministic IDs make writes idempotent. Every search result is re-validated against Postgres (hydration), so stale vectors are never served, and reconciliation cleans up orphans asynchronously.

---

## 6. Backpressure and rate limiting

**Backpressure:** a slow consumer must be able to slow down a fast producer, otherwise something overflows (memory, queues, a provider's patience).

Layers in NexusRAG, from the outside in: API admission limits → queue as buffer → workers *pull* only what they can process (`prefetch=1`) → global provider rate limiter → circuit breakers.

**Token bucket:** a bucket holds up to N tokens and refills at R per second. Each request takes tokens; if the bucket is empty, you wait. It allows short bursts while enforcing an average rate. We run it **in Redis** (an atomic Lua script) because Celery's rate limit is per worker process. Ten workers would mean ten times the intended rate, and the provider would answer with 429s.

> **Node.js comparison:** like `p-limit` / `bottleneck`, but shared across many machines through Redis.

---

## 7. Retries done right

- **Exponential backoff:** wait 30 s, 60 s, 120 s… so you stop hammering a struggling dependency.
- **Jitter:** randomize the wait. Without it, 1,000 jobs that failed at the same moment retry at the same moment and cause the same failure again (the "thundering herd").
- **Retry budget per cause:** a corrupt PDF will never succeed (permanent error, don't retry). A rate limit is the system's problem, not the document's, so it shouldn't count against the document's attempts.
- **Retry amplification:** if the SDK retries 3×, the task retries 3× and the sweeper retries 3×, one failure becomes 27 calls. Retry at **one** layer deliberately.
- **Circuit breaker:** after repeated failures, stop calling for a while (*open*), then try one probe (*half-open*). This protects the dependency *and* your workers.

> **Interview (FDE flavour):** *"A customer says ingestion 'randomly fails' on big uploads. How do you debug it?"*
> Sketch: look at failure distribution by error class (`error_code`), at queue wait vs processing time per stage, and at 429 rates and circuit-breaker state around the failure times. Check whether failures cluster by document (poison files) or by time (dependency outage). Then explain the fix in the customer's terms.

---

## 8. Multi-tenancy and defense in depth

**Rule:** never rely on one check. NexusRAG enforces tenant isolation in four places: credential → tenant, tenant-aware repositories + composite foreign keys, a mandatory vector-search filter, and re-validation at hydration. A bug in any one layer still doesn't leak data.

**Prompt injection:** a document can contain "ignore your instructions and…". You can't reliably stop a model from being influenced by text it reads. So the design **removes the model's power** instead: no tools and no side effects, and it only ever sees data the caller was already authorized to see. Worst case, the answer to *that user* is distorted. That is the key mental model for securing LLM features: **limit capability, don't trust obedience.**

> **Interview:** *"How would you stop one tenant from seeing another tenant's documents through the chatbot?"*
> Wrong answer: "tell the model in the system prompt." Right answer: filtering before retrieval, verification after retrieval, and constraints in the database. The model never decides access.

---

## 9. Python concurrency for a Node.js developer

| | Node.js | Python |
|---|---|---|
| I/O concurrency | Event loop (async/await) | `asyncio` event loop: **same model** (FastAPI uses it) |
| CPU parallelism | Worker threads / cluster | **Processes.** The GIL lets only one thread run Python bytecode at a time per process. |
| Blocking the loop | Bad (`fs.readFileSync` in a handler) | Equally bad (a sync DB driver or `time.sleep` in an `async def`) |

Consequences in NexusRAG: the API is async; PDF extraction runs in a Celery **prefork** (multi-process) pool; embedding (mostly waiting on HTTP) can use higher concurrency because waiting on I/O releases the GIL.

---

## 10. Measuring RAG quality

You can't improve what you don't measure, and "it looks good on my five questions" isn't measurement.

- **Retrieval metrics** (need labelled relevant chunks per question):
  - **Recall@K:** did the right chunk appear in the top K?
  - **Precision@K:** how much of the top K is relevant?
  - **MRR:** 1 / rank of the first relevant result, averaged. It rewards getting the right chunk *first*.
- **Generation metrics:** faithfulness (is every claim supported by the context?), answer relevance, citation correctness.
- **Why not only LLM-as-judge:** judges are biased (they favour longer answers and their own style), they cost money, and they drift as models change. Combine them with deterministic checks (does the quoted text exist in the source? do citations point to real sources?) and a small human-labelled set.
- **Include unanswerable questions** on purpose. A good system says "I don't have evidence for that." Those questions are how the evidence-gate threshold is calibrated.

> **Try it (Phase 6):** change one setting (chunk size, or turning the reranker on and off), re-run the evaluation, and explain the metric delta. This "change → measure → explain" loop is the core habit interviewers look for.

---

## 11. The FDE lens: requirements discovery

Look at [requirements.md §4](../requirements.md#4-missing-requirements-and-assumptions). Those "missing requirements" are exactly the questions a Forward Deployed Engineer asks a customer in week one:
- What makes two files "the same document"?
- Are there scanned PDFs (do we need OCR)?
- What languages?
- Who must *not* see what (document-level permissions)?
- What latency feels acceptable to your users?
- What is your budget per 1,000 documents?

Practice turning each technical decision into a one-sentence business explanation, for example: *"We store originals in S3 and only derived data in the search index, so deleting a document truly removes it everywhere within minutes."*

---

## Self-check before approving the design

You should be able to answer these without looking:
1. Why does the job have both a `status` CAS **and** an `attempt` fence? What does each one protect against?
2. Walk through what happens if Redis restarts with 500 jobs queued.
3. Why is chunk text stored in Postgres and not in Qdrant? What do we pay for that choice?
4. Why is `SUPERSEDED` a version state and not a job state?
5. Where exactly is the tenant enforced on a query, and what happens if the Qdrant filter is forgotten?
6. What do you predict will limit throughput for a 1,000-document batch, and how will you prove it?
