"""PDF and TXT extraction, and the whole extract → clean → guard pipeline."""

from pathlib import Path

import pytest

from app.ingestion.extraction import ExtractionError, extract_document
from app.ingestion.extraction.pdf import extract_pdf
from app.ingestion.extraction.text import decode_text, extract_txt
from tests.unit.extraction.pdf_builder import build_pdf, encrypt_pdf

POLICY = "Our travel policy allows a daily allowance of 80 USD for meals."


SECTIONS = [
    [POLICY, "Flights above six hours may be booked in premium econ-", "omy class if approved."],
    ["Hotels must be booked through the travel portal.", "Receipts are required for all costs."],
    ["Rental cars need prior approval.", "Fuel is reimbursed at cost with receipts."],
    ["Conference fees are covered once a year.", "Training budgets are set per team."],
]


def report(path: Path, pages: int = 4) -> Path:
    """A realistic report: header and footer on every page, different body text per page."""
    return build_pdf(
        path,
        [
            ["ACME Corp - Confidential", *SECTIONS[(n - 1) % len(SECTIONS)], f"Page {n} of {pages}"]
            for n in range(1, pages + 1)
        ],
    )


# ------------------------------------------------- PDF


def test_pdf_pages_are_numbered_from_one(tmp_path: Path) -> None:
    pages = list(extract_pdf(report(tmp_path / "r.pdf", pages=3)))

    assert [page.page_number for page in pages] == [1, 2, 3]
    assert POLICY in pages[0].text


def test_encrypted_pdf_is_a_permanent_error(tmp_path: Path) -> None:
    locked = encrypt_pdf(report(tmp_path / "r.pdf"), tmp_path / "locked.pdf", "s3cret")

    with pytest.raises(ExtractionError) as error:
        list(extract_pdf(locked))
    assert error.value.code == "ENCRYPTED_DOCUMENT"


def test_pdf_locked_only_with_an_empty_password_is_readable(tmp_path: Path) -> None:
    restricted = encrypt_pdf(report(tmp_path / "r.pdf"), tmp_path / "restricted.pdf", "")

    assert POLICY in next(extract_pdf(restricted)).text


def test_corrupt_pdf_is_a_permanent_error(tmp_path: Path) -> None:
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4\nthis is not really a pdf")

    with pytest.raises(ExtractionError) as error:
        list(extract_pdf(broken))
    assert error.value.code == "CORRUPT_DOCUMENT"


def test_page_limit(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError) as error:
        list(extract_pdf(report(tmp_path / "r.pdf", pages=3), max_pages=2))
    assert error.value.code == "PAGE_LIMIT_EXCEEDED"


# ------------------------------------------------- TXT


def test_txt_form_feeds_become_pages(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("first page\fsecond page", encoding="utf-8")

    assert [page.text for page in extract_txt(path)] == ["first page", "second page"]


def test_txt_decoding_handles_bom_and_legacy_encodings() -> None:
    assert decode_text("﻿café".encode()) == "café"  # UTF-8 with BOM
    assert decode_text("café 100€".encode("cp1252")) == "café 100€"  # Windows-1252


def test_binary_file_disguised_as_txt_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "fake.txt"
    path.write_bytes(b"MZ\x00\x00\x90binary")

    with pytest.raises(ExtractionError) as error:
        list(extract_txt(path))
    assert error.value.code == "UNSUPPORTED_TYPE"


# ------------------------------------------------- whole pipeline


def test_pipeline_produces_clean_cited_text(tmp_path: Path) -> None:
    document = extract_document(report(tmp_path / "r.pdf"), "application/pdf")

    assert document.page_count == 4
    assert document.removed_boilerplate == {"acme corp - confidential", "page # of #"}
    first = document.pages[0]
    assert first.page_number == 1
    assert "Confidential" not in first.text and "Page 1 of 4" not in first.text
    assert "premium economy class" in first.text  # hyphenation repaired across the line break
    assert "Hotels must be booked" in document.pages[1].text  # body text survives on every page
    assert document.pages_without_text == []


def test_scanned_pdf_fails_with_no_text_layer(tmp_path: Path) -> None:
    scanned = build_pdf(tmp_path / "scan.pdf", [[], [], []])  # pages without any text

    with pytest.raises(ExtractionError) as error:
        extract_document(scanned, "application/pdf")
    assert error.value.code == "NO_TEXT_LAYER"


def test_partly_scanned_pdf_is_kept_and_reports_empty_pages(tmp_path: Path) -> None:
    mixed = build_pdf(tmp_path / "mixed.pdf", [[POLICY], [], [POLICY + " Again."]])

    document = extract_document(mixed, "application/pdf")

    assert document.pages_without_text == [2]


def test_unsupported_type(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError) as error:
        extract_document(tmp_path / "x.docx", "application/msword")
    assert error.value.code == "UNSUPPORTED_TYPE"


def test_cli_extract_prints_clean_pages(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from app.cli import main

    assert main(["extract", str(report(tmp_path / "r.pdf"))]) == 0
    out = capsys.readouterr().out
    assert (
        "pages: 4" in out
        and "----- page 1 -----" in out
        and "Confidential" not in out.split("----- page 1 -----")[1]
    )

    assert main(["extract", str(build_pdf(tmp_path / "scan.pdf", [[], [], []]))]) == 1
    assert "NO_TEXT_LAYER" in capsys.readouterr().err
