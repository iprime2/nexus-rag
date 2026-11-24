"""Data shapes passed between the extraction stages, plus their errors."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class PageText:
    """The text of one page. ``page_number`` is 1-based, as people count pages.

    Keeping text per page (not one long string) is what later lets an answer
    cite "Travel Policy, page 4".
    """

    page_number: int
    text: str


@dataclass(frozen=True)
class ExtractedDocument:
    pages: list[PageText]
    # Pages that produced no usable text (e.g. scanned images inside a PDF).
    pages_without_text: list[int] = field(default_factory=list)
    # Normalized header/footer lines that were removed (useful for debugging).
    removed_boilerplate: set[str] = field(default_factory=set)

    @property
    def page_count(self) -> int:
        return len(self.pages)


class ExtractionError(Exception):
    """A **permanent** problem with the document itself. Retrying won't help.

    ``code`` is stable and machine-readable; it is stored on the job
    (``error_code``) and shown to the tenant.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
