"""Cleaning and header/footer detection.

The first four tests are the owner's specification from the W1 lesson.
"""

from app.ingestion.extraction.cleaning import (
    clean_pages,
    clean_text,
    find_repeated_lines,
    normalize_line,
)
from app.ingestion.extraction.models import PageText

TOPICS = ["travel", "expenses", "security", "holidays", "equipment", "training", "remote work"]
VERBS = ["covers", "explains", "lists", "describes", "defines", "summarises", "updates"]


def body(n: int) -> list[str]:
    """Realistic body text: pages differ in *words*, not only in numbers.

    (Lines that differ only by digits look exactly like a footer such as
    "Page 3 of 40" after normalization, by design.)
    """
    topic, verb = TOPICS[n % len(TOPICS)], VERBS[n % len(VERBS)]
    return [f"This section {verb} the {topic} rules.", f"Questions about {topic} go to HR."]


# ------------------------------------------------- owner's spec (W1 lesson)


def test_spec_repeated_header_is_detected() -> None:
    pages = [["ACME Corp — Confidential", *body(n)] for n in range(5)]

    assert find_repeated_lines(pages) == {"acme corp — confidential"}


def test_spec_page_numbers_are_detected_after_normalization() -> None:
    pages = [[*body(n), f"Page {n} of 5"] for n in range(1, 6)]

    assert find_repeated_lines(pages) == {"page # of #"}


def test_spec_too_few_pages_detects_nothing() -> None:
    pages = [["Title", *body(n)] for n in range(2)]

    assert find_repeated_lines(pages) == set()


def test_spec_line_below_the_ratio_is_kept() -> None:
    pages = [["Rare banner", *body(n)] if n < 2 else body(n) for n in range(10)]

    assert find_repeated_lines(pages) == set()  # 2/10 pages < 60%


# ------------------------------------------------- refinements


def test_cover_page_without_header_still_detects_it() -> None:
    pages = [["Annual Report 2026"]] + [["ACME Corp — Confidential", *body(n)] for n in range(4)]

    assert "acme corp — confidential" in find_repeated_lines(pages)  # 4/5 = 80%


def test_line_repeated_twice_on_one_page_counts_once() -> None:
    pages = [["Draft", "Draft", *body(n)] if n == 0 else body(n) for n in range(4)]

    assert find_repeated_lines(pages) == set()  # 1/4 pages, not 2/4


def test_repeated_text_in_the_middle_of_pages_is_not_boilerplate() -> None:
    filler = [f"filler line {i} unique {i * 7}" for i in range(4)]
    pages = [[*filler, "See section 2 for details.", *filler] for _ in range(5)]

    assert "see section # for details." not in find_repeated_lines(pages)


def test_normalize_line() -> None:
    assert normalize_line("  Page 3   of 40 ") == "page # of #"
    assert normalize_line("\ufb01nance\u00a0Report") == "finance report"  # "ﬁ" ligature + NBSP


# ------------------------------------------------- clean_text


def test_rejoins_hyphenated_words_but_keeps_real_hyphens() -> None:
    assert clean_text("informa-\ntion is key") == "information is key"
    assert clean_text("Jean-\nPierre said") == "Jean-\nPierre said"  # capital: likely a name


def test_unicode_whitespace_and_control_characters() -> None:
    raw = "ﬁnance\x07  report\r\n\r\n\r\n\r\nnext   para\t\tend "
    assert clean_text(raw) == "finance report\n\nnext para end"


# ------------------------------------------------- clean_pages


def test_clean_pages_removes_boilerplate_only_at_page_edges() -> None:
    def page(n: int) -> PageText:
        topic = TOPICS[n % len(TOPICS)]
        lines = [
            "ACME Corp — Confidential",  # header (top edge)
            *body(n),
            "ACME Corp — Confidential is our motto.",  # repeated, but in the middle: content
            f"Contact the {topic} team for exceptions.",
            f"The {topic} policy is reviewed every year.",
            f"Page {n} of 4",  # footer (bottom edge)
        ]
        return PageText(n, "\n".join(lines))

    cleaned, removed = clean_pages([page(n) for n in range(1, 5)])

    assert removed == {"acme corp — confidential", "page # of #"}
    assert cleaned[0].text.splitlines() == [
        "This section explains the expenses rules.",
        "Questions about expenses go to HR.",
        "ACME Corp — Confidential is our motto.",
        "Contact the expenses team for exceptions.",
        "The expenses policy is reviewed every year.",
    ]


def test_repeated_sentence_near_the_bottom_of_every_page_is_boilerplate() -> None:
    """A tagline repeated at the page edge *is* boilerplate: the heuristic can't tell otherwise."""
    pages = [[*body(n), "Building better workplaces since 1990.", f"Page {n}"] for n in range(5)]

    assert "building better workplaces since #." in find_repeated_lines(pages)
