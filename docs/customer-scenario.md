# Customer scenario: SkyBridge Regional (fictional)

NexusRAG is built for a realistic, but **fictional**, customer. The scenario keeps design decisions honest ("would this help SkyBridge?") and gives the evaluation set real questions with real source documents. The company is invented; the documents are real, public FAA publications.

## The customer

| | |
|---|---|
| **Company** | SkyBridge Regional: a fictional US regional airline operating under 14 CFR Part 121 |
| **Team** | Maintenance & Engineering: ~150 aircraft maintenance technicians (AMTs) across several line stations, plus a 10-person Quality & Compliance group |
| **Buyer** | Director of Quality & Compliance |
| **Daily users** | Technicians (quick answers on the hangar floor), quality inspectors and auditors (exact references) |

## The problem

- Maintenance guidance is spread across **hundreds of FAA Advisory Circulars (ACs) and handbooks**, each hundreds of pages long. Technicians search PDFs by hand or ask a senior colleague.
- **Revisions matter.** ACs are revised and cancelled (e.g. AC 43-9C was cancelled by AC 43-9D). Relying on a cancelled revision can produce a **finding** in an FAA or internal audit.
- Generic chatbots answer confidently, without sources, and can mix revisions. Quality won't accept an answer it can't trace to a paragraph.

## What success looks like

The targets below are **requirements, not results**. No number here has been measured yet; the evaluation set (PR E) and benchmarks will measure them, and the README will only report measured values.

| Requirement | How we will measure it |
|---|---|
| Every answer **cites** the document and page (later: paragraph) it is based on | Citation correctness on the golden set |
| Answers come only from **active** revisions unless the user asks about history | Golden-set questions built on active/cancelled pairs (AC 43-9C/9D, AC 120-16E/16G) |
| When the documents don't contain the answer, the system **says so** instead of guessing | "Unanswerable" questions in the golden set; refusal rate |
| Answers are fast enough to use on the hangar floor | p50/p95 latency from benchmarks (target set after the first measurement) |
| One tenant never sees another tenant's documents | Isolation tests (already a hard rule: ADR-0008) |

## Constraints (they shape the architecture)

| Constraint | Consequence in NexusRAG |
|---|---|
| Documents and logs stay in **SkyBridge's own AWS account** | Self-hostable stack (Postgres, Qdrant, S3); AWS deployment in the portfolio cut |
| **Audit trail**: who asked what, which sources were used | Request IDs and structured logs now; answer/citation logging with W5 |
| Multiple stations and later other operators | Multi-tenant from day one (tenant = operator) |
| Mixed document quality (old scanned ACs) | `NO_TEXT_LAYER` guard now; OCR later (ADR-0012) |

## The demo dataset

| | |
|---|---|
| **What** | FAA Advisory Circulars on maintenance (starter set of 5 in [`datasets/faa/manifest.csv`](../datasets/faa/manifest.csv)); FAA maintenance handbooks (FAA-H-8083-30/31/32) may be added later, as they are very large |
| **Why these** | Real, long, technical PDFs with paragraph numbering, tables and revision history: the hard parts of enterprise RAG |
| **Licence** | Works of the US federal government are not subject to copyright in the US (17 U.S.C. §105). *Owner to confirm:* check the FAA website's terms before publishing a demo that redistributes the files. The repository commits only URLs and checksums, never the PDFs. |
| **Source** | FAA AC index (faa.gov → Regulations & Policies → Advisory Circulars). Older revisions may also be in the US DOT ROSA P archive. |
| **Status column** | `active`/`cancelled`, as shown by the FAA AC index in web search results on 2026-11-25. *Owner to verify* each status on the AC index page before relying on it. |

Starter set, chosen to include two **active/cancelled pairs** for the "only current revisions" requirement:

| Document | Status | Why it's in the set |
|---|---|---|
| AC 43.13-1B (with Change 1) | active | The core "acceptable methods" reference; very long; many tables |
| AC 43-9D | active | Maintenance records; replaces 43-9C |
| AC 43-9C | cancelled → 43-9D | Superseded revision: the system must not answer from it by default |
| AC 120-16G | active | Air carrier maintenance programs (Part 121, our customer's world) |
| AC 120-16E (with Change 1) | cancelled → 120-16G | Second superseded pair |

### Getting the files

The PDFs are not in the repository. On your own machine:

```bash
uv run python -m scripts.fetch_faa_dataset --pin
```

This downloads into `data/raw/faa/` (gitignored), rejects anything that isn't a PDF, and with `--pin` writes each file's SHA-256 into the manifest. Commit the pinned manifest: later runs then detect if the FAA replaced a file behind the same URL (which is how a new revision or editorial update shows up).

**faa.gov blocks scripted downloads** (HTTP 403 from a cloud container and from a home Mac, 2026-11-25). We don't disguise the script as a browser, because that would work around the site's bot protection. Instead:
1. Open each URL from the manifest in a browser and save the PDF into `data/raw/faa/` under the name the script expects (`AC 43-9D` → `AC_43-9D.pdf`; spaces become `_`).
2. Check and pin them without downloading:
   ```bash
   uv run python -m scripts.fetch_faa_dataset --offline --pin
   ```

**Open question for the owner:** AC 43-9D also has an "editorial update" PDF on faa.gov. Which file does the AC index mark as current? It's a good real example of why checksums are pinned.

## Out of scope for the scenario

- Aircraft-specific manufacturer manuals (proprietary; not available).
- Regulatory advice: NexusRAG retrieves and cites guidance; it does not certify airworthiness. The UI and answers will say so.
