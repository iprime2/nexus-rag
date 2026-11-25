# Phase 6 (started early): data and evaluation concepts

These lessons came up during the mentor-review follow-up (PRs C–F, 2026-11-25), before any evaluation code exists. ADR-0013 puts the evaluation baseline *before* hybrid search, so these ideas are needed early. The plan itself is in [docs/evaluation-plan.md](../evaluation-plan.md).

## 1. Revisions are metadata, not text (Q1)

**Scenario:** AC 43-9C (cancelled, 1998) and AC 43-9D (active, 2025) both explain maintenance records, in almost the same words. Both are indexed. A technician asks what a record entry must contain.

| Approach | What happens |
|---|---|
| Naive: top-k by similarity | Both revisions score almost the same, so the answer may come from 9C. For the customer that's an **audit finding**. |
| "Only answer above a similarity threshold" | Doesn't help: the threshold measures "is this text *about* the question", not "is this text *still valid*" |
| "Prefer the newest date" | Better instinct, wrong field: a document can be cancelled without replacement, and editorial updates change dates without changing rules |
| ✅ Store `status` (active / cancelled) on every chunk and **filter** before ranking | The FAA's own status decides, like the tenant filter decides ownership |

**Owner's answer:** use the revision date. The direction (decide on *information about* the document, not its text) was right; the reliable field is the status.

## 2. Measure before you change anything (Q3)

**Scenario:** hybrid search is added; five hand-picked questions "feel better". An interviewer asks: *by how much?*

- Without a "before" number there is no honest answer. Guessing ("50%, because we combine two methods") is the trap: combining methods doesn't add their benefits, and hybrid search can make some results worse.
- ✅ Run the **same fixed question set** before and after, and compare one metric.
- NestJS analogy: you benchmark an endpoint before adding a cache (p95 = 400 ms) and after (p95 = 120 ms). Without the first number, "faster" is a feeling.

## 3. Two layers, and what Hit@5 means (Q4)

- Search returns chunks ranked 1, 2, 3, … Only the **top 5** go to the LLM. If the right page isn't in them, the LLM never sees it.
- **Hit@5** = the share of questions whose correct page (from the golden set's `evidence`) is in the top 5.

| Question | Correct page ranked | Hit? |
|---|---|---|
| q001 | 2 | ✅ |
| q002 | 7 | ❌ |
| q003 | 1 | ✅ |
| q004 | not found | ❌ |

Hit@5 = 2 / 4 = **50%**.

**Debugging rule:** check the retrieval metric first. Hit@5 = 90% but only 50% correct answers means *search works and the LLM step fails*. Look at questions that hit but answered wrong: a chunk that cuts the answer in half, a prompt that doesn't force "answer only from the context", noisy context, or a cancelled revision in the context.

**Owner's answer:** "the search part". Corrected: high Hit@5 points at generation, not retrieval.

## 4. The golden set

A fixed list of questions with known answers and **source pages**, each checked by a person. Four types map to the customer's requirements: `factual`, `superseded` (trap), `unanswerable` (must refuse), `exact_term` (where keyword search should help). LLM-drafted questions tend to be easy for LLMs, so the owner writes at least a third.

## 5. Data provenance: pinning checksums

The FAA can replace a PDF behind the same URL. A SHA-256 per file in `datasets/faa/manifest.csv` makes every evaluation run traceable to exact files: a changed file shows up as `checksum mismatch` instead of silently shifting scores. The owner pinned all five files on 2026-11-25.

## 6. Make the mistake impossible (tool usability)

The owner hit two problems running the fetch script: browser file names didn't match the expected names, and running from another folder broke relative paths. Instead of documenting "rename the files" and "run from the root", the script now expects the browser's name and resolves paths from the repository root. **In FDE work customers run your tools without you: first ask whether the tool could have prevented the mistake; good error messages are second best.**

## Exercises
1. Open `datasets/faa/manifest.csv`. Change one character of a checksum and run `uv run python -m scripts.fetch_faa_dataset --offline`. What does it report? Undo the change.
2. Write one `unanswerable` question for the FAA corpus as a golden-set line, and run `uv run python -m app.cli check-golden-set` on it. (Don't commit it yet.)

## Interview questions
- **"How do you evaluate a RAG system?"** A fixed, human-verified golden set; separate retrieval metrics (Hit@k) from generation metrics (citation correctness, refusal, faithfulness); a baseline before every change; reports tied to a commit.
- **"Your answers cite outdated documents. How do you fix it?"** Model document status as metadata and filter on it; add trap questions to the eval set; similarity can't separate revisions.
- **"Retrieval is good but answers are wrong. Where do you look?"** At the generation step: chunk boundaries, the grounding prompt, noisy context, and conflicting sources in the context.
