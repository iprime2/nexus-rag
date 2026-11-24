"""Turning raw extracted text into clean text worth embedding.

Every artifact removed here would otherwise end up inside chunks and their
embeddings: repeated headers make all chunks look alike, broken hyphenation
breaks keyword search, odd Unicode breaks matching.

Header/footer detection follows the design by the project owner (Phase W1
lesson): a line is boilerplate if, after normalization, it appears near the top
or bottom of most pages.
"""

import re
import unicodedata
from collections import Counter

from app.ingestion.extraction.models import PageText

_DIGITS = re.compile(r"\d+")
_SPACES = re.compile("[ \t\u00a0]+")  # spaces, tabs, non-breaking spaces
# A word broken across lines: "informa-\ntion" (lowercase continuation only,
# so real hyphenated names at line ends, like "Jean-\nPierre", are kept).
_HYPHEN_BREAK = re.compile(r"(\w)-\n(?=[a-z])")
_MANY_BLANK_LINES = re.compile(r"\n{3,}")
# Control characters except newline and tab.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def normalize_line(line: str) -> str:
    """'  Page 3 of 40 ' -> 'page # of #' (digits → #, lowercase, single spaces, trimmed)."""
    line = unicodedata.normalize("NFKC", line)
    line = _DIGITS.sub("#", line)
    return _SPACES.sub(" ", line).strip().lower()


# Headers and footers are short. A long line repeated across pages is content.
MAX_BOILERPLATE_LENGTH = 100


def _edges[T](items: list[T], edge_lines: int) -> list[T]:
    """The first and last ``k`` items, where ``k`` never covers the whole page.

    On a short page, "first 3 + last 3" would be *every* line, and repeated body
    lines would be mistaken for boilerplate (bug B2, caught by the W1 tests).
    So ``k`` is capped at half the page: the middle is always treated as content.
    """
    k = min(edge_lines, len(items) // 2)
    if k == 0:
        return []
    return items[:k] + items[-k:]


def find_repeated_lines(
    pages: list[list[str]],
    *,
    edge_lines: int = 3,
    min_ratio: float = 0.6,
    min_pages: int = 3,
) -> set[str]:
    """Return the normalized lines that are headers/footers.

    A line counts at most once per page, and only if it appears in the first or
    last ``edge_lines`` non-empty lines of at least ``min_ratio`` of the pages.
    Documents shorter than ``min_pages`` are never guessed about.
    """
    if len(pages) < min_pages:
        return set()

    counts: Counter[str] = Counter()
    for lines in pages:
        non_empty = [line for line in lines if line.strip()]
        candidates = {normalize_line(line) for line in _edges(non_empty, edge_lines)}
        # A set per page: a line counts at most once per page.
        counts.update(c for c in candidates if c and len(c) <= MAX_BOILERPLATE_LENGTH)

    threshold = min_ratio * len(pages)
    return {line for line, count in counts.items() if count >= threshold}


def clean_text(text: str) -> str:
    """Normalize Unicode, re-join hyphenated words, tidy whitespace."""
    text = unicodedata.normalize("NFKC", text)  # "ﬁ" -> "fi", full-width -> ASCII, …
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL.sub("", text)
    text = _HYPHEN_BREAK.sub(r"\1", text)
    text = "\n".join(_SPACES.sub(" ", line).strip() for line in text.split("\n"))
    return _MANY_BLANK_LINES.sub("\n\n", text).strip()


def clean_pages(
    pages: list[PageText], *, edge_lines: int = 3, min_pages: int = 3
) -> tuple[list[PageText], set[str]]:
    """Remove headers/footers (from page edges only), then clean each page's text.

    Returns the cleaned pages and the set of normalized lines that were removed.
    """
    split = [page.text.replace("\r\n", "\n").split("\n") for page in pages]
    boilerplate = find_repeated_lines(split, edge_lines=edge_lines, min_pages=min_pages)

    cleaned: list[PageText] = []
    for page, lines in zip(pages, split, strict=True):
        non_empty_positions = [i for i, line in enumerate(lines) if line.strip()]
        edges = set(_edges(non_empty_positions, edge_lines))  # only strip at the edges
        kept = [
            line
            for i, line in enumerate(lines)
            if not (i in edges and normalize_line(line) in boilerplate)
        ]
        cleaned.append(PageText(page.page_number, clean_text("\n".join(kept))))
    return cleaned, boilerplate
