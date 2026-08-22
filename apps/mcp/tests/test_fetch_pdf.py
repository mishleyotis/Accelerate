"""A PDF is a source, and this fetcher used to be unable to read one.

MEM-0070, measured 2026-08-15 on the second client. Odlum Brown's WAF answers
403 to every HTML path while `/docs/*.pdf` returns 200, so the firm's
substantive disclosures — client agreement, statement guides, every career
posting — are reachable ONLY as PDFs. A producer working that entity registered
0 of 3 PDF sources and 13 of 13 HTML ones. It verified by hand that the span
`Your Account instructions must be either oral (but not left on voicemail) or
in writing (but not electronically).` was present in the fetched bytes; the
connector still answered `excerpt_not_verbatim`.

The cause was one line: `raw.decode("utf-8", "replace")` on a binary container,
comparing English prose against mojibake.

That refusal is the worst shape a fail-closed rule can take. It is
indistinguishable from the producer having invented the excerpt, and it leaves
an honest producer two moves — drop a true finding, or find a citation it can
pass. Regulatory filings, annual reports and client agreements are
overwhelmingly PDFs.
"""
import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

pypdf = pytest.importorskip("pypdf")
from dma_mcp import fetching as server  # noqa: E402


SPAN = ("Your Account instructions must be either oral (but not left on "
        "voicemail) or in writing (but not electronically).")


def _make_pdf(text: str) -> bytes:
    """A real PDF, built here rather than committed — a fixture binary nobody
    can read is a fixture nobody can check."""
    from pypdf import PdfWriter
    from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                               NameObject, NumberObject)

    def esc(s):
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    page = writer.pages[0]
    content = DecodedStreamObject()
    lines = "\n".join(f"({esc(l)}) Tj 0 -14 Td" for l in text.split("\n"))
    content.set_data(f"BT /F1 10 Tf 40 740 Td\n{lines}\nET".encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(content)
    font = DictionaryObject()
    font.update({NameObject("/Type"): NameObject("/Font"),
                 NameObject("/Subtype"): NameObject("/Type1"),
                 NameObject("/BaseFont"): NameObject("/Helvetica")})
    res = DictionaryObject()
    fonts = DictionaryObject()
    fonts[NameObject("/F1")] = writer._add_object(font)
    res[NameObject("/Font")] = fonts
    page[NameObject("/Resources")] = res
    page[NameObject("/MediaBox")] = ArrayObject(
        [NumberObject(0), NumberObject(0), NumberObject(612), NumberObject(792)])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_a_pdf_yields_its_text_not_mojibake():
    raw = _make_pdf(SPAN)
    assert raw[:5] == b"%PDF-", "the fixture is not a PDF"
    out = server._pdf_text(raw)
    assert out, "a text-bearing PDF returned nothing"
    assert "voicemail" in out, f"extraction lost the prose: {out[:200]!r}"


def test_the_span_that_was_refused_now_verifies():
    """End to end through the ACTUAL comparison register_evidence makes, so
    this cannot pass while the real check still fails."""
    from dma_mcp.register import _normalise
    out = server._pdf_text(_make_pdf(f"Section 4.2\n{SPAN}\nSection 4.3"))
    assert _normalise(SPAN) in _normalise(out), (
        "the span register_evidence compares is still not found in the "
        f"extracted text: {out!r}")


def test_the_old_decode_is_what_failed():
    """The negative control. If this ever stops failing, the bug was not what
    this fix addresses and the fix needs re-deriving."""
    from dma_mcp.register import _normalise
    raw = _make_pdf(SPAN)
    assert _normalise(SPAN) not in _normalise(raw.decode("utf-8", "replace")), (
        "utf-8-decoding the PDF found the span, so decoding was never the bug")


def test_a_scanned_pdf_reads_as_unreachable_not_as_a_mismatch():
    """An image-only PDF has no text layer. Returning "" would read as
    fetched-and-not-matching, which blames the excerpt for the document."""
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=612, height=792)
    buf = io.BytesIO()
    w.write(buf)
    assert server._pdf_text(buf.getvalue()) is None


def test_a_corrupt_pdf_returns_none_rather_than_raising():
    assert server._pdf_text(b"%PDF-1.7\nnot actually a pdf") is None


def test_magic_bytes_beat_the_content_type():
    """A filing served as application/octet-stream is still a PDF, and a .pdf
    path that 200s with an HTML error page is still HTML. The dispatch reads
    the bytes, so assert on the bytes."""
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "fetching.py").read_text()
    assert 'raw[:5] == b"%PDF-"' in src, (
        "the PDF branch no longer sniffs magic bytes; a mislabelled filing "
        "would go back to being decoded as text")
    assert "application/pdf" in src, "Accept must offer PDF to negotiating servers"


def test_a_span_that_wraps_across_lines_still_verifies():
    """The failure mode a synthetic one-liner would miss.

    Real filings wrap. pypdf emits a newline where the page has a line break,
    so the extracted text carries `\\n` exactly where the source sentence has a
    space. `_normalise` collapses all whitespace, which is what makes this
    work — assert it, because a future tightening of that normalisation would
    silently re-break every multi-line citation in the corpus."""
    from dma_mcp.register import _normalise
    wrapped = ("Your Account instructions must be either oral (but not\n"
               "left on voicemail) or in writing (but not\nelectronically).")
    out = server._pdf_text(_make_pdf(wrapped))
    assert _normalise(SPAN) in _normalise(out), (
        f"a wrapped span did not match: {out!r}")


def test_extraction_spans_pages():
    """A 40-page client agreement is not one page. If only page 1 were read,
    every citation past it would read as fabricated."""
    from pypdf import PdfWriter, PdfReader
    import io as _io
    w = PdfWriter()
    for part in ("first page filler text here", SPAN, "third page filler"):
        w.append(PdfReader(_io.BytesIO(_make_pdf(part))))
    buf = _io.BytesIO()
    w.write(buf)
    out = server._pdf_text(buf.getvalue())
    from dma_mcp.register import _normalise
    assert _normalise(SPAN) in _normalise(out), "page 2 was not read"
    assert "third page" in out, "page 3 was not read"
