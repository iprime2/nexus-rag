# ADR-0013: Portfolio v1 cut line and target dates

- **Status:** Proposed
- **Date:** 2026-11-25
- **Deciders:** project owner

## Context
The design (Phases 0–9) is larger than the time available. The owner has **~10 hours/week**, and NexusRAG must be portfolio-ready by the **15 Feb 2027 milestone**, after which two more projects follow. The mentor review (2026-11-25) flagged scope as a top risk: without an explicit cut line, effort spreads across hardening work while the AI path, evaluation and a deployable demo stay unfinished.

A "portfolio v1" must let an interviewer see, in minutes: a real customer problem (`docs/customer-scenario.md`), cited answers over real documents, **measured** quality, and a running deployment. Each step also carries the ownership overhead from `CLAUDE.md` (lesson, owner spec, review gate, defense). That overhead is the point of the project, so the schedule must budget for it, not squeeze it.

## Decision

### In v1 (target: 2027-01-17)

| Item | Scope in v1 | Target date |
|---|---|---|
| W2 chunking, W3 embeddings | As in the roadmap (`PROJECT_STATUS.md`) | 2026-12-06 |
| W4 vector search, W5 cited answers | As in the roadmap; tenant filter in the Qdrant query (ADR-0008) | 2026-12-13 |
| Evaluation set + baseline report | 30–50 owner-verified questions on the FAA corpus, plain-Python metrics, one report from a real run (details in PR E) | 2026-12-20 |
| Tracing | Langfuse traces for retrieval and generation (self-hosted vs cloud decided in that step) | 2026-12-20 |
| H1 upload API, H2 Celery workers | As in the roadmap | 2027-01-03 |
| H4 hybrid retrieval (keyword + RRF) | Measured against the baseline report: keep it only with evidence that it helps | 2027-01-10 |
| `POST /v1/query` (JSON, not streamed) | Needed so the deployed demo is usable over HTTP, not only from the CLI | 2027-01-10 |
| One AWS deployment | The simplest setup that runs the stack in one AWS account. ECS + Terraform vs. a single host with Compose is decided in that step, with costs. | 2027-01-17 |
| Demo video + README results | Shows only measured numbers | 2027-01-17 |

**Order change on purpose:** the evaluation baseline comes *before* H1–H4. Without a baseline, H4 can't show whether hybrid retrieval actually improves answers.

**H3 (DOCX/HTML extractors, deep validation)** is in v1 only if the 2026-12-20 checkpoint is on schedule. Otherwise it is the **first item cut**: the FAA corpus is all PDF.

### Deferred (not dropped)

| Item | Why deferred | Revisit when |
|---|---|---|
| H5 failure drills (F1–F3, F5, F9, F12) | Time. The CAS/fencing logic already has integration tests. **Until drills run, the README makes no reliability claims beyond those tests.** | First item after v1 |
| Reranker | Evidence-gated, like ADR-0009 | The evaluation report shows ranking errors that RRF doesn't fix |
| OCR (Tesseract/OCRmyPDF) | ADR-0012: later; scanned pages are rejected with `NO_TEXT_LAYER` | Scanned FAA documents matter for the golden set |
| SSE streaming answers | Not needed to show quality; adds client complexity | A UI or a latency requirement needs it |
| Anthropic / Bedrock providers | OpenAI is enough to prove the design; the provider interface (ADR-0007) stays | Cost comparison or a data-residency need |
| Users/JWT, document-level ACL, Postgres RLS (Phase 5) | API-key tenant auth and the three isolation layers cover the scenario | A second user role is needed in the demo |
| Shared Redis token bucket for embedding rate limits | The demo corpus is small; v1 uses retry with backoff on `429` | Measured `429`s with several workers |
| Prometheus/Grafana metrics and alerting (Phase 6) | Structured logs + Langfuse cover v1 debugging | After v1, with the AWS deployment |
| Benchmarks and scalability work (Phase 7) | No scale claims in v1 (hard rule) | After v1 |
| Web UI | The demo uses the HTTP API, CLI and video | Feedback says a UI is needed to understand the demo |
| ADR-0009 extensions (GraphRAG, agents, vLLM, Kubernetes) | Still gated on evidence | As ADR-0009 says |

### Checkpoints
- **2026-12-13** (end of the walking skeleton): if W4–W5 slipped by more than a week, move tracing after H2.
- **2026-12-20**: decide on H3 (above).
- **2027-01-17**: v1 done, or cut the remaining hardening item. **2027-02-15** is the latest date, not a second plan.

## Alternatives considered
| Option | Pros | Cons |
|---|---|---|
| Finish all phases before calling it done | Complete system | Doesn't fit ~10 h/week before Feb 2027; quality and measurement come last |
| Walking skeleton only (W1–W5) + evaluation | Smallest, fastest | No upload API, workers or deployment: hard to show production engineering in an FDE interview |
| **Cut line above (chosen)** | AI path, measured quality, one deployment and the core reliability design | Some hardening (drills, metrics) and polish (UI, streaming) come after v1 |
| W2–W5 by 2026-12-06 (original date) | Earlier AI demo | About 15 hours for four steps, each with lesson, spec, review and defense: the defenses would be rushed (owner chose the later date, 2026-11-25) |

## Consequences
- Every new idea is checked against this table. Anything not in "In v1" goes to "Deferred" with a reason, via a new ADR that supersedes this one if the cut line changes.
- `PROJECT_STATUS.md` shows the target dates; slips are recorded there, not hidden.
- The README must not claim scalability, high availability or reliability beyond what v1 measured or tested. The current intro ("horizontally scalable workers" for "500–1,000+ documents") describes design goals, and must be worded that way before the v1 README is published.
- Revisit this ADR at each checkpoint above, or if the available hours per week change.
