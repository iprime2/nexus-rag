# ADR-0012: Document text extraction, cleaning and OCR

- **Status:** Accepted (2026-11-24, owner decision: free tools now, explore alternatives later)
- **Date:** 2026-11-24

## Context
Every later RAG stage (chunks, embeddings, retrieval, the LLM's answer) only sees the text this stage produces, so extraction quality caps answer quality. PDFs store positioned glyphs, not paragraphs, which leads to repeated headers/footers, hyphenation breaks, ligatures, multi-column interleaving, flattened tables, and **no text at all** for scanned documents. Many tools and services solve parts of this, at very different cost, license and accuracy.

## Decision
**Now (walking skeleton, W1):** free and simple, behind our own pipeline functions.

| Stage | Choice | License |
|---|---|---|
| PDF text | **pypdf** (page by page, lazy reading) | BSD-3 |
| TXT | Standard library (UTF-8 → Windows-1252 fallback; form feeds = pages) | — |
| Cleaning | **Own code**: Unicode NFKC, hyphenation repair, whitespace, header/footer detection (owner's design) | — |
| Guard | **Own code**: `NO_TEXT_LAYER` if no page has ≥ 20 letters/digits | — |

**Planned (hardening, H3):** OCR for scanned PDFs with **Tesseract** via **OCRmyPDF** (adds a text layer, then pypdf reads it), on its own worker queue because OCR is slow. Also DOCX (python-docx) and HTML (BeautifulSoup).

## Options catalogue (for later exploration)

### Libraries (self-hosted)
| Tool | What it does well | License | Cost / weight | Notes |
|---|---|---|---|---|
| **pypdf** ✅ | Plain text per page | BSD | Light, pure Python | No layout or table understanding |
| pdfplumber / pdfminer.six | Character positions, tables | MIT | Light | Slower; good for layout heuristics |
| PyMuPDF / pymupdf4llm | Fast, good quality, Markdown output | **AGPL** ⚠️ | Light | AGPL is a problem for a hosted commercial service |
| **Docling** (IBM) | Layout, reading order, tables → Markdown | MIT | ML models, heavier | **First candidate to evaluate** against pypdf |
| **Unstructured** | Typed elements (title, text, table), many formats, OCR hooks | Apache 2.0 | Heavy dependencies | Also offered as a hosted API |
| Marker | High-quality PDF → Markdown | GPL ⚠️ (weights restricted) | ML models | License blocks commercial hosting |
| MinerU | Strong on scientific PDFs | AGPL ⚠️ | ML models | License blocks commercial hosting |

### OCR
| Tool | Type | License / cost | Trade-off |
|---|---|---|---|
| **Tesseract** + **OCRmyPDF** ✅ (planned) | Local | Apache 2.0 / MPL 2.0 | Free; system package; seconds per page on CPU |
| docTR, PaddleOCR, EasyOCR | Local deep learning | Apache 2.0 | More accurate; heavy, GPU helps |
| AWS Textract | Cloud | Per page | Fits Phase 8 (AWS); tables and forms |
| Azure Document Intelligence, Google Document AI | Cloud | Per page | Enterprise-grade |
| Mistral OCR, LlamaParse | Hosted APIs | Per page | Markdown output, LLM-assisted |
| Vision LLMs (GPT-4o-class, Claude, Gemini) | Any LLM API | Per page | Excellent on messy layouts; **can invent text**, a serious risk for a RAG system that must quote sources faithfully |

## How alternatives will be evaluated
Not by popularity: by the **evaluation set (Phase 6)**. Swap the extractor, re-ingest the same corpus, compare retrieval Recall@K, answer faithfulness, cost per 1,000 pages and latency. The pipeline's function boundaries (extract → clean → guard) make that swap a local change.

## Consequences
- No new heavy dependencies; licenses stay permissive.
- Known limitations until H3: no OCR, no table structure, multi-column PDFs may interleave lines.
- Header/footer detection is a heuristic with unavoidable ambiguity (a line repeated at the edge of most pages *is* treated as boilerplate). It's documented and tested, including the cases it can't distinguish.
