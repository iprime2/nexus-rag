"""Tests for scripts/fetch_faa_dataset.py.

No network: every test uses httpx.MockTransport, so the fetcher's logic (skip, verify,
pin, reject non-PDFs) is tested here, but the real FAA URLs are not.
"""

import csv
import hashlib
from pathlib import Path

import httpx
import pytest

from scripts.fetch_faa_dataset import (
    ManifestEntry,
    fetch_all,
    file_name,
    read_manifest,
    write_manifest,
)

PDF = b"%PDF-1.4\n fake but has the magic bytes\n%%EOF\n"
PDF_SHA = hashlib.sha256(PDF).hexdigest()


def entry(doc_id: str = "AC 43-9D", sha256: str = "") -> ManifestEntry:
    return ManifestEntry(
        doc_id=doc_id,
        title="Maintenance Records",
        status="active",
        superseded_by="",
        url=f"https://example.test/{doc_id.replace(' ', '_')}.pdf",
        sha256=sha256,
    )


def client_returning(body: bytes, calls: list[str], status: int = 200) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(status, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_downloads_a_pdf_and_reports_its_checksum(tmp_path: Path) -> None:
    calls: list[str] = []
    results = fetch_all([entry()], tmp_path, client_returning(PDF, calls), delay_s=0)

    assert results[0].outcome == "downloaded"
    assert results[0].sha256 == PDF_SHA
    assert (tmp_path / file_name(entry())).read_bytes() == PDF
    assert len(calls) == 1


def test_skips_a_file_that_already_matches_the_pinned_checksum(tmp_path: Path) -> None:
    (tmp_path / file_name(entry())).write_bytes(PDF)
    calls: list[str] = []

    results = fetch_all([entry(sha256=PDF_SHA)], tmp_path, client_returning(PDF, calls), delay_s=0)

    assert results[0].outcome == "skipped"
    assert calls == []  # no request at all


def test_checksum_mismatch_fails_and_keeps_no_file(tmp_path: Path) -> None:
    # The FAA replaced the PDF behind the same URL (e.g. an editorial update).
    # We must notice, not silently ingest a different document.
    calls: list[str] = []
    results = fetch_all([entry(sha256="0" * 64)], tmp_path, client_returning(PDF, calls), delay_s=0)

    assert results[0].outcome == "failed"
    assert "checksum mismatch" in results[0].detail
    assert not (tmp_path / file_name(entry())).exists()


def test_rejects_a_response_that_is_not_a_pdf(tmp_path: Path) -> None:
    # A moved document often returns an HTML page with status 200.
    calls: list[str] = []
    results = fetch_all(
        [entry()], tmp_path, client_returning(b"<html>Page moved</html>", calls), delay_s=0
    )

    assert results[0].outcome == "failed"
    assert "not a PDF" in results[0].detail
    assert list(tmp_path.iterdir()) == []


def test_http_error_fails_one_entry_but_continues_with_the_rest(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "missing" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, content=PDF)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    results = fetch_all([entry("missing"), entry("AC 43-9D")], tmp_path, client, delay_s=0)

    assert [r.outcome for r in results] == ["failed", "downloaded"]
    assert "404" in results[0].detail


def test_manifest_round_trip_keeps_rows_and_pins_checksums(tmp_path: Path) -> None:
    path = tmp_path / "manifest.csv"
    write_manifest(path, [entry("AC 43-9C"), entry("AC 43-9D", sha256=PDF_SHA)])

    rows = read_manifest(path)

    assert [r.doc_id for r in rows] == ["AC 43-9C", "AC 43-9D"]
    assert rows[1].sha256 == PDF_SHA
    with path.open(newline="") as f:
        assert next(csv.reader(f)) == [
            "doc_id",
            "title",
            "status",
            "superseded_by",
            "url",
            "sha256",
        ]


def test_committed_manifest_is_valid() -> None:
    rows = read_manifest(Path("datasets/faa/manifest.csv"))

    assert rows, "manifest must not be empty"
    assert len({file_name(r) for r in rows}) == len(rows), "file names must be unique"
    ids = {r.doc_id for r in rows}
    for r in rows:
        assert r.url.startswith("https://")
        assert r.status in {"active", "cancelled"}
        # A cancelled AC must name its replacement, and the replacement must be in the set:
        # that pair is what the "never cite a superseded revision" evaluation needs.
        if r.status == "cancelled":
            assert r.superseded_by in ids


@pytest.mark.parametrize(
    ("doc_id", "expected"),
    [("AC 43.13-1B CHG 1", "AC_43.13-1B_CHG_1.pdf"), ("AC 43-9D", "AC_43-9D.pdf")],
)
def test_file_name_is_safe_and_readable(doc_id: str, expected: str) -> None:
    assert file_name(entry(doc_id)) == expected
