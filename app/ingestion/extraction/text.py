"""Plain-text extraction.

Text files have no pages. If the file contains form-feed characters (``\\f``),
which many "export to text" tools insert between pages, we split on them so
citations still have page numbers. Otherwise the whole file is page 1.
"""

from collections.abc import Iterator
from pathlib import Path

from app.ingestion.extraction.models import ExtractionError, PageText

FORM_FEED = "\f"


def decode_text(raw: bytes) -> str:
    """UTF-8 (with or without BOM) first; Windows-1252 as a fallback.

    Windows-1252 maps almost every byte, so legacy files still decode. Bytes it
    can't map become U+FFFD, never an exception.
    """
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def extract_txt(path: Path, *, max_bytes: int = 50 * 1024 * 1024) -> Iterator[PageText]:
    size = path.stat().st_size
    if size > max_bytes:
        raise ExtractionError(
            "FILE_TOO_LARGE", f"The file is {size} bytes; the limit is {max_bytes}."
        )
    text = decode_text(path.read_bytes())
    if "\x00" in text:
        raise ExtractionError("UNSUPPORTED_TYPE", "The file looks binary, not plain text.")
    for number, page in enumerate(text.split(FORM_FEED), start=1):
        yield PageText(page_number=number, text=page)
