"""PDF text extraction with pypdf (ADR-0012).

pypdf reads the file lazily from disk: pages are parsed one at a time, so a
large PDF is never fully loaded into memory.
"""

from collections.abc import Iterator
from pathlib import Path

import structlog
from pypdf import PasswordType, PdfReader
from pypdf.errors import PdfReadError

from app.ingestion.extraction.models import ExtractionError, PageText

logger = structlog.get_logger(__name__)


def extract_pdf(path: Path, *, max_pages: int = 1_000) -> Iterator[PageText]:
    """Yield the raw text of each page, numbered from 1.

    Raises ``ExtractionError`` for encrypted, corrupt or oversized PDFs.
    """
    try:
        reader = PdfReader(path)
        # Many "encrypted" PDFs only restrict printing and open with an empty
        # password. Real password protection can't be processed. Note that
        # decrypt() *returns* a result instead of raising on a wrong password.
        if reader.is_encrypted and reader.decrypt("") == PasswordType.NOT_DECRYPTED:
            raise ExtractionError("ENCRYPTED_DOCUMENT", "The PDF is password-protected.")
        page_count = len(reader.pages)
    except ExtractionError:
        raise
    except (PdfReadError, ValueError, OSError) as error:
        raise ExtractionError("CORRUPT_DOCUMENT", "The PDF could not be read.") from error

    if page_count > max_pages:
        raise ExtractionError(
            "PAGE_LIMIT_EXCEEDED", f"The PDF has {page_count} pages; the limit is {max_pages}."
        )

    for index in range(page_count):
        try:
            text = reader.pages[index].extract_text() or ""
        except (PdfReadError, ValueError, KeyError) as error:
            # One broken page shouldn't sink the whole document: keep going.
            # The guard later decides if enough text remains.
            logger.warning(
                "extraction.page_failed", page=index + 1, error_type=type(error).__name__
            )
            text = ""
        yield PageText(page_number=index + 1, text=text)
