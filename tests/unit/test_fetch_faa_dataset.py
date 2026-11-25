"""Tests for scripts/fetch_faa_dataset.py.

No network: every test uses httpx.MockTransport, so the fetcher's logic (skip, verify,
pin, reject non-PDFs) is tested here, but the real FAA URLs are not.
"""

import csv
import hashlib
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from scripts.fetch_faa_dataset import (
    ManifestEntry,
    check_local,
    fetch_all,
    file_name,
    main,
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


def test_committed_manifest_pins_every_file() -> None:
    # The owner pinned all five files (2026-11-25); an unpinned row would let a changed
    # file slip into the evaluation unnoticed.
    for r in read_manifest(Path("datasets/faa/manifest.csv")):
        assert len(r.sha256) == 64, f"{r.doc_id} is not pinned"


# The local file name is the last part of the URL: exactly what a browser's "Save" uses,
# so the owner never has to rename a download.
@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.faa.gov/a/b/AC_43.13-1B_w-chg1.pdf", "AC_43.13-1B_w-chg1.pdf"),
        ("https://www.faa.gov/a/AC43-9C.pdf", "AC43-9C.pdf"),
        ("https://www.faa.gov/a/AC_120-124.pdf?pubDate=20260430", "AC_120-124.pdf"),
        ("https://www.faa.gov/a/AC%2025-27.pdf", "AC 25-27.pdf"),  # browsers decode %20
    ],
)
def test_file_name_is_what_a_browser_saves(url: str, expected: str) -> None:
    assert file_name(replace(entry(), url=url)) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.test/..%2F..%2F.ssh%2Fauthorized_keys.pdf",  # path traversal
        "https://www.faa.gov/a/index.html",  # not a PDF
        "https://www.faa.gov/",  # no file name
    ],
)
def test_file_name_rejects_unsafe_or_non_pdf_urls(url: str) -> None:
    with pytest.raises(ValueError, match="file name"):
        file_name(replace(entry(), url=url))


# --- offline mode: the owner downloads the PDFs in a browser (faa.gov blocks scripts) ---


def test_offline_reports_a_missing_file_with_its_download_url(tmp_path: Path) -> None:
    result = check_local(entry(), tmp_path)

    assert result.outcome == "failed"
    assert "missing" in result.detail
    assert entry().url in result.detail  # tells the owner where to download it


def test_offline_finds_an_unpinned_pdf_and_computes_its_checksum(tmp_path: Path) -> None:
    (tmp_path / file_name(entry())).write_bytes(PDF)

    result = check_local(entry(), tmp_path)

    assert result.outcome == "found"
    assert result.sha256 == PDF_SHA


def test_offline_verifies_a_pinned_checksum(tmp_path: Path) -> None:
    (tmp_path / file_name(entry())).write_bytes(PDF)

    assert check_local(entry(sha256=PDF_SHA), tmp_path).outcome == "skipped"
    mismatch = check_local(entry(sha256="0" * 64), tmp_path)
    assert mismatch.outcome == "failed"
    assert "checksum mismatch" in mismatch.detail


def test_offline_rejects_a_saved_html_page(tmp_path: Path) -> None:
    # "Save as" on an error page gives an HTML file with a .pdf name.
    (tmp_path / file_name(entry())).write_bytes(b"<html>Access Denied</html>")

    result = check_local(entry(), tmp_path)

    assert result.outcome == "failed"
    assert "not a PDF" in result.detail


def test_main_offline_pin_writes_checksums_only_for_found_files(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    out = tmp_path / "raw"
    out.mkdir()
    write_manifest(manifest, [entry("AC 43-9C"), entry("AC 43-9D")])
    (out / file_name(entry("AC 43-9D"))).write_bytes(PDF)

    exit_code = main(["--offline", "--pin", "--manifest", str(manifest), "--out", str(out)])

    rows = {r.doc_id: r.sha256 for r in read_manifest(manifest)}
    assert rows == {"AC 43-9C": "", "AC 43-9D": PDF_SHA}
    assert exit_code == 1  # one file is still missing


def test_default_paths_work_from_any_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The owner ran the script from inside data/raw/faa/ and got FileNotFoundError for the
    # manifest. Defaults are resolved from the repository root, not the current folder.
    monkeypatch.chdir(tmp_path)

    exit_code = main(["--offline", "--out", str(tmp_path)])

    assert exit_code == 1  # the default manifest was found; its files are just not in tmp_path
