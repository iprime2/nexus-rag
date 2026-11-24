"""Extract → clean → guard: from a file on disk to clean, page-numbered text.

All three stages are pure functions (file in, text out; no database, no
network), so each is unit-tested in milliseconds. Celery workers will call
``extract_document`` later; for now the CLI does.
"""

from pathlib import Path

from app.ingestion.extraction.cleaning import clean_pages
from app.ingestion.extraction.models import ExtractedDocument, ExtractionError, PageText
from app.ingestion.extraction.pdf import extract_pdf
from app.ingestion.extraction.text import extract_txt

SUPPORTED_MIME_TYPES = {"application/pdf", "text/plain"}
# A page needs at least this many letters/digits to count as having text.
# Scanned pages often yield a few stray characters (page numbers, noise).
MIN_ALNUM_PER_PAGE = 20


def _alnum_count(text: str) -> int:
    return sum(character.isalnum() for character in text)


def guard_has_text(pages: list[PageText]) -> list[int]:
    """Fail if no page has real text; otherwise return the page numbers that have none.

    No text at all is a permanent, document-level problem (a scanned PDF needs
    OCR, ADR-0012), so it raises ``NO_TEXT_LAYER`` instead of letting an empty
    document flow through the pipeline and silently answer nothing.
    """
    empty = [page.page_number for page in pages if _alnum_count(page.text) < MIN_ALNUM_PER_PAGE]
    if len(empty) == len(pages):
        raise ExtractionError(
            "NO_TEXT_LAYER",
            "No extractable text found. The document may be scanned images (OCR is not enabled).",
        )
    return empty


def extract_document(path: Path, mime_type: str) -> ExtractedDocument:
    if mime_type == "application/pdf":
        raw_pages = list(extract_pdf(path))
    elif mime_type == "text/plain":
        raw_pages = list(extract_txt(path))
    else:
        raise ExtractionError("UNSUPPORTED_TYPE", f"Unsupported document type: {mime_type}")

    if not raw_pages:
        raise ExtractionError("NO_TEXT_LAYER", "The document has no pages.")

    pages, boilerplate = clean_pages(raw_pages)
    empty_pages = guard_has_text(pages)
    return ExtractedDocument(
        pages=pages, pages_without_text=empty_pages, removed_boilerplate=boilerplate
    )
