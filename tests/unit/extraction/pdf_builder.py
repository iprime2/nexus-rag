"""Build small, real PDF files for tests, without any extra dependency.

A PDF is a set of numbered objects plus a cross-reference table of byte
offsets. Each page has a "content stream" of drawing instructions; text is
drawn with ``BT /F1 12 Tf <x> <y> Td (Hello) Tj ET``. Writing one by hand
shows what PDF text extraction really has to work from: positioned glyphs,
not paragraphs.
"""

from pathlib import Path

from pypdf import PdfReader, PdfWriter


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _content_stream(lines: list[str]) -> bytes:
    commands = []
    y = 780
    for line in lines:
        commands.append(f"BT /F1 11 Tf 50 {y} Td ({_escape(line)}) Tj ET")
        y -= 16
    return "\n".join(commands).encode("latin-1")


def build_pdf(path: Path, pages: list[list[str]]) -> Path:
    """Write a PDF where each page draws the given lines top to bottom.

    An empty list for a page produces a page with no text at all, which is
    what a scanned page looks like to a text extractor.
    """
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)  # object numbers start at 1

    font = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    pages_id = len(objects) + 1 + 2 * len(pages)  # reserved after page/content objects
    page_ids = []
    for lines in pages:
        stream = _content_stream(lines)
        content = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_ids.append(
            add(
                b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 612 792] "
                b"/Resources << /Font << /F1 %d 0 R >> >> /Contents %d 0 R >>"
                % (pages_id, font, content)
            )
        )
    kids = " ".join(f"{pid} 0 R" for pid in page_ids).encode()
    assert add(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))) == pages_id
    catalog = add(b"<< /Type /Catalog /Pages %d 0 R >>" % pages_id)

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        catalog,
        xref,
    )
    path.write_bytes(bytes(out))
    return path


def encrypt_pdf(source: Path, target: Path, password: str) -> Path:
    writer = PdfWriter()
    writer.append(PdfReader(source))
    writer.encrypt(user_password=password, owner_password=password)
    with target.open("wb") as handle:
        writer.write(handle)
    return target
