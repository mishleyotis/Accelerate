"""Bytes → two texts: one to rank and select from, one to verify against.

WHY TWO. `trafilatura` gives clean main content — no nav, no cookie
banner, no footer — which is what ranking and excerpt selection should
see. But the span the engine emits is re-verified by the research ledger
and the connector against THEIR extraction, a tag-stripping pass that keeps
everything (`textnorm.connector_html_text`). A span is therefore chosen
from the clean text and checked against the connector-shaped text, and
emitted only when both contain it (`excerpt.verify_against_both`).

PDFs: `pypdfium2` (BSD/Apache) for the ranking text; the verification text
is the connector's own path — `pypdf` page texts joined with "\\n" and the
ligature folds applied — when `pypdf` is importable, else the pypdfium2
text with the same folds (and `verify_basis` says so).

Pure given bytes. No network, no model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .textnorm import connector_html_text, connector_pdf_fold, sha256_text

_PDF_MAGIC = b"%PDF"


@dataclass
class Extracted:
    text: str
    verify_text: str
    title: str = ""
    kind: str = "html"            # html | pdf | text
    verify_basis: str = "connector_html_text"
    text_basis: str = "trafilatura"


def is_pdf(body: bytes, content_type: str = "") -> bool:
    return body[:5].lstrip().startswith(_PDF_MAGIC) or "application/pdf" in (content_type or "").lower()


def _clean_ws(s: str) -> str:
    # keep paragraph breaks (sentence segmentation uses them), collapse the rest
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = re.sub(r"[ \t\f\v]+", " ", s)
    s = re.sub(r" *\n *", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def html_to_texts(markup: str, url: str = "") -> Extracted:
    title = ""
    text = None
    try:
        import trafilatura  # type: ignore
        text = trafilatura.extract(markup, url=url or None, include_comments=False,
                                   include_tables=True, favor_recall=True,
                                   output_format="txt", deduplicate=False)
        try:
            meta = trafilatura.extract_metadata(markup, default_url=url or None)
            title = (getattr(meta, "title", None) or "") if meta is not None else ""
        except Exception:  # noqa: BLE001
            title = ""
    except Exception:  # noqa: BLE001
        text = None
    verify = _clean_ws(connector_html_text(markup))
    if not title:
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", markup)
        title = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""
    if not text or len(text.strip()) < 40:
        # trafilatura abstained (a thin page, a listing): fall back to the
        # connector text so a span can still be found and verified.
        return Extracted(text=verify, verify_text=verify, title=title, kind="html",
                         text_basis="connector_html_text (trafilatura abstained)")
    return Extracted(text=_clean_ws(text), verify_text=verify, title=title, kind="html")


def pdf_to_texts(body: bytes) -> Extracted | None:
    """None when the PDF has no text layer (a scan) — unreachable, not empty."""
    rank_text = None
    try:
        import pypdfium2 as pdfium  # type: ignore
        pdf = pdfium.PdfDocument(body)
        pages = []
        for i in range(len(pdf)):
            page = pdf[i]
            tp = page.get_textpage()
            pages.append(tp.get_text_range() or "")
            tp.close()
            page.close()
        pdf.close()
        rank_text = connector_pdf_fold("\n".join(pages))
    except Exception:  # noqa: BLE001
        rank_text = None
    verify_text, basis = None, "pypdf (connector path)"
    try:
        import io
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(io.BytesIO(body))
        verify_text = connector_pdf_fold("\n".join((p.extract_text() or "") for p in reader.pages))
    except Exception:  # noqa: BLE001
        verify_text, basis = None, "pypdfium2 (pypdf unavailable)"
    if verify_text is None:
        verify_text = rank_text
    if rank_text is None:
        rank_text = verify_text
    if not rank_text or not rank_text.strip():
        return None
    return Extracted(text=_clean_ws(rank_text), verify_text=_clean_ws(verify_text or ""),
                     kind="pdf", verify_basis=basis, text_basis="pypdfium2")


def extract(body: bytes, content_type: str = "", url: str = "") -> Extracted | None:
    if is_pdf(body, content_type):
        return pdf_to_texts(body)
    enc = "utf-8"
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    if m:
        enc = m.group(1)
    try:
        markup = body.decode(enc, errors="replace")
    except LookupError:
        markup = body.decode("utf-8", errors="replace")
    if "<" not in markup[:2000] and ">" not in markup[:2000]:
        text = _clean_ws(markup)
        return Extracted(text=text, verify_text=text, kind="text",
                         verify_basis="plain text", text_basis="plain text") if text else None
    return html_to_texts(markup, url)


def content_hash(text: str) -> str:
    return sha256_text(text)
