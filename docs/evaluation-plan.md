# Evaluation plan

**Goal:** every quality claim about NexusRAG comes from a measured run against a fixed, human-verified question set. No guessed numbers (`CLAUDE.md` hard rules; ADR-0013 puts the baseline **before** H1–H4 so later changes can be compared against it).

Owner decisions (2026-11-25): Claude drafts candidate questions, the owner verifies every one and writes at least a third (E1 = B); a format checker now (E2); the starting metrics below (E3).

## 1. What we evaluate, and why in two layers

| Layer | Question it answers | If it fails, you fix… |
|---|---|---|
| **Retrieval** | Did search return the page that holds the answer? | Chunking, embeddings, filters, hybrid search |
| **Generation** | Given those pages, is the answer correct, cited and honest? | Prompt, citation parsing, refusal rules, model |

Measuring both tells you *where* a wrong answer came from. High retrieval + low answer quality means the LLM step is failing; low retrieval means the LLM never saw the right page.

## 2. The golden set

File: [`eval/golden_set.jsonl`](../eval/golden_set.jsonl), one question per line. Checked by `uv run python -m app.cli check-golden-set` (also a unit test, so CI fails on a broken file).

| Field | Meaning |
|---|---|
| `id` | `q001`, `q002`, …; never reused |
| `type` | `factual` · `superseded` · `unanswerable` · `exact_term` (below) |
| `question` | Written the way a technician would ask it |
| `answerable` | `false` only for `unanswerable` questions |
| `expected_answer` | Short reference answer (answerable questions) |
| `evidence` | `[{doc_id, page, quote}]`: where the answer is written; `doc_id` must be in `datasets/faa/manifest.csv` |
| `written_by` | `owner` or `claude` (honest attribution) |
| `verified_on` | Date the owner checked the answer against the page; `null` = **draft**, skipped by eval runs |
| `notes` | Optional |

Example line:
```json
{"id": "q001", "type": "factual", "question": "What must a maintenance record entry contain?", "answerable": true, "expected_answer": "…", "evidence": [{"doc_id": "AC 43-9D", "page": 5, "quote": "…"}], "written_by": "owner", "verified_on": "2026-12-15"}
```

### Question types (mapped to the customer requirements)

| Type | Tests | Target count (of 30–50) |
|---|---|---|
| `factual` | Basic retrieval and answering | the rest |
| `superseded` | Answers come from the **active** revision (AC 43-9C/9D, AC 120-16E/16G). The checker rejects evidence from a cancelled document. | ≥ 5 |
| `unanswerable` | The system says it doesn't know instead of guessing | ≥ 5 |
| `exact_term` | Codes and form numbers (e.g. "Form 8130-3"): where keyword search should help, so H4 can be measured | ≥ 5 |

These are target **counts** for building the set, not results.

### Process
1. Claude drafts candidates from the PDFs (`written_by: claude`, `verified_on: null`).
2. The owner opens each cited page, checks the quote and the answer, and edits, rejects or verifies it (sets `verified_on`).
3. The owner writes at least a third of the questions (`written_by: owner`), in a technician's voice. Questions an LLM writes tend to be easy for an LLM to answer, so this guards against a flattering score.
4. `check-golden-set` must pass. Only verified questions count.
5. After the baseline run, the set changes only through reviewed commits. Every report names the commit of the set it used.

**Open (decided at that step):** how Claude reads the PDFs to draft questions, since faa.gov blocks scripted downloads. Options: the web-fetch tool, or the owner shares `app.cli extract` output.

## 3. Metrics (starting set)

The metric *functions* are core logic: the owner writes their spec when we build them (`CLAUDE.md` → Ownership rules). This table only defines what they measure.

| Metric | Layer | Definition | How it's computed |
|---|---|---|---|
| **Hit@5** | Retrieval | % of answerable questions where an evidence `(doc_id, page)` is among the top-5 retrieved chunks | Automatic |
| **Citation correctness** | Generation | % of answers whose citations include an evidence page | Automatic |
| **Refusal correctness** | Generation | Unanswerable: % correctly refused. Answerable: % wrongly refused. Both are reported. | Automatic (refusal is a structured field in the answer) |
| **Superseded avoidance** | Generation | % of `superseded` answers that cite no cancelled document | Automatic |
| **Answer correctness** | Generation | correct / partial / wrong against `expected_answer` | Owner grades the baseline by hand; later an LLM judge (RAGAS), calibrated against the owner's grades |
| **Latency p50 / p95** | System | End-to-end `ask` time, plus time per stage | Automatic |

## 4. Reports
- Saved as `eval/reports/<date>-<label>.md`, never edited after the run.
- Each report records the git commit, the golden-set commit, the configuration (chunk size, top-k, models), every metric, and the list of failed questions.
- The README and the demo only quote numbers that appear in a report.

## 5. Tools, in teaching order

| Stage | Tool | Why at this stage |
|---|---|---|
| 1 | Plain Python | Understand each metric before a library hides it |
| 2 | RAGAS | LLM-judged metrics (faithfulness, answer relevance). A new dependency, explained when added. |
| 3 | Langfuse | Traces of each retrieval and LLM call, linked to eval runs. Self-hosted vs. cloud decided then. |

## 6. Timeline (ADR-0013)

| When | What |
|---|---|
| ✅ 2026-11-25 | Owner downloaded the 5 PDFs in a browser and pinned their SHA-256 (`--offline --pin`) |
| After W3 (from 2026-12-07) | Claude drafts candidates; the owner verifies them and writes their own |
| After W5 (2026-12-13) | Metric specs (owner) → metric code → first run |
| **2026-12-20** | Baseline report + Langfuse tracing |
