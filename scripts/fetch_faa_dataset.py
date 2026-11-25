"""Download the FAA demo corpus listed in datasets/faa/manifest.csv.

Usage (run on your own machine; this downloads public US-government PDFs):

    uv run python -m scripts.fetch_faa_dataset           # download into data/raw/faa/
    uv run python -m scripts.fetch_faa_dataset --pin     # also write checksums into the manifest

Why a manifest instead of committing the PDFs: the files are large and public. The manifest
(URL + SHA-256) makes the corpus reproducible and detects when the FAA replaces a file
behind the same URL, which matters because citing the wrong revision is the failure this
project's customer scenario cares about most (docs/customer-scenario.md).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import sys
import time
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path
from typing import Literal

import httpx

MANIFEST = Path("datasets/faa/manifest.csv")
OUTPUT_DIR = Path("data/raw/faa")
# Generic client name: no personal details in requests to outside services.
USER_AGENT = "nexus-rag-dataset-fetcher/0.1"
DELAY_S = 2.0  # be polite to a public government site
TIMEOUT_S = 120.0  # some ACs are several hundred pages
PDF_MAGIC = b"%PDF-"

Outcome = Literal["downloaded", "skipped", "failed"]


@dataclass(frozen=True)
class ManifestEntry:
    doc_id: str
    title: str
    status: str  # "active" or "cancelled", as listed in the FAA AC index
    superseded_by: str  # doc_id of the replacement, for cancelled entries
    url: str
    sha256: str  # empty until pinned with --pin


@dataclass(frozen=True)
class FetchResult:
    entry: ManifestEntry
    outcome: Outcome
    sha256: str = ""
    detail: str = ""


def read_manifest(path: Path) -> list[ManifestEntry]:
    with path.open(newline="", encoding="utf-8") as f:
        return [
            ManifestEntry(**{k: (v or "").strip() for k, v in row.items()})
            for row in csv.DictReader(f)
        ]


def write_manifest(path: Path, entries: list[ManifestEntry]) -> None:
    names = [f.name for f in fields(ManifestEntry)]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        writer.writerows(asdict(e) for e in entries)


def file_name(entry: ManifestEntry) -> str:
    """'AC 43.13-1B CHG 1' -> 'AC_43.13-1B_CHG_1.pdf' (no spaces, no path separators)."""
    return re.sub(r"[^A-Za-z0-9.\-]+", "_", entry.doc_id).strip("_") + ".pdf"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch_one(entry: ManifestEntry, out_dir: Path, client: httpx.Client) -> FetchResult:
    target = out_dir / file_name(entry)

    if entry.sha256 and target.exists() and _sha256(target.read_bytes()) == entry.sha256:
        return FetchResult(entry, "skipped", entry.sha256, "already present, checksum matches")

    try:
        response = client.get(entry.url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        return FetchResult(entry, "failed", detail=f"{type(exc).__name__}: {exc}")

    body = response.content
    if not body.startswith(PDF_MAGIC):
        # A moved document often answers 200 with an HTML page.
        return FetchResult(entry, "failed", detail="response is not a PDF")

    digest = _sha256(body)
    if entry.sha256 and digest != entry.sha256:
        return FetchResult(
            entry,
            "failed",
            digest,
            "checksum mismatch: the file behind this URL changed (new revision?). "
            "Check the FAA AC index before re-pinning.",
        )

    # Write to a temporary name, then rename: an interrupted run never leaves a
    # half-written PDF that a later run would treat as complete.
    tmp = target.with_suffix(".part")
    tmp.write_bytes(body)
    tmp.replace(target)
    return FetchResult(entry, "downloaded", digest)


def fetch_all(
    entries: list[ManifestEntry], out_dir: Path, client: httpx.Client, delay_s: float = DELAY_S
) -> list[FetchResult]:
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[FetchResult] = []
    for i, entry in enumerate(entries):
        result = fetch_one(entry, out_dir, client)
        results.append(result)
        if result.outcome == "downloaded" and i < len(entries) - 1:
            time.sleep(delay_s)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR)
    parser.add_argument(
        "--pin", action="store_true", help="write checksums of new downloads into the manifest"
    )
    args = parser.parse_args(argv)

    entries = read_manifest(args.manifest)
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=TIMEOUT_S, follow_redirects=True) as client:
        results = fetch_all(entries, args.out, client)

    for r in results:
        line = f"{r.outcome:<10} {r.entry.doc_id:<20} {r.sha256[:12] or '-':<12} {r.detail}"
        print(line.rstrip())

    if args.pin:
        pinned = {r.entry.doc_id: r.sha256 for r in results if r.outcome == "downloaded"}
        write_manifest(
            args.manifest, [replace(e, sha256=pinned.get(e.doc_id, e.sha256)) for e in entries]
        )

    failed = sum(r.outcome == "failed" for r in results)
    print(f"\n{len(results) - failed}/{len(results)} OK, files in {args.out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
