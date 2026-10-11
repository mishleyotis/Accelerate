"""The prose three programs agree on, and the one normalisation they share.

An excerpt the engine emits is verified AGAIN by the research ledger
(`engine/fetch.py`) and by the connector (`apps/mcp/dma_mcp/fetching.py`),
each against text ITS OWN extractor produced from the same bytes, each
with `normalise(excerpt) in normalise(text)`. So this module carries a
byte-for-byte copy of the connector's extractor (`connector_html_text`,
`connector_pdf_fold`) and of its normalisation (`normalise`), and
`tests/test_textnorm_matches_connector.py` pins the copy to the original by
importing it from the checkout when one is present. Trafilatura's cleaner
main-content text is used for RANKING and SELECTION; a span is emitted only
when it is also present in the connector-shaped text (see
`excerpt.verify_against_both`).

Pure: no network, no disk, no model.
"""
from __future__ import annotations

import hashlib
import html as _html
import re

# ── copied from apps/mcp/dma_mcp/fetching.py, pinned by test ──────────────

_LIGATURES = (("ﬀ", "ff"), ("ﬁ", "fi"), ("ﬂ", "fl"),
              ("ﬃ", "ffi"), ("ﬄ", "ffl"), ("ﬅ", "st"),
              ("’", "'"), ("‘", "'"),
              ("“", '"'), ("”", '"'))


def connector_pdf_fold(text: str) -> str:
    """The ligature/quote folds the connector applies to PDF text."""
    for lig, plain in _LIGATURES:
        text = text.replace(lig, plain)
    return text


def connector_html_text(markup: str) -> str:
    """The prose of an HTML document, exactly as the connector extracts it:
    scripts/styles/head dropped, block tags become a space, inline tags
    close up, entities unescaped."""
    s = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", markup)
    s = re.sub(r"(?is)<!--.*?-->", " ", s)
    s = re.sub(r"(?i)</?(p|div|br|hr|tr|td|th|li|ul|ol|dl|dd|dt|h[1-6]|table|"
               r"thead|tbody|tfoot|section|article|header|footer|nav|aside|"
               r"blockquote|pre|figure|figcaption|option)\b[^>]*>", " ", s)
    s = re.sub(r"<[^>]+>", "", s)
    return _html.unescape(s)


def normalise(text: str) -> str:
    """What "verbatim" means to every verifier: whitespace collapsed,
    stripped, case folded. NOTHING else. (The connector uses `lower`; the
    research ledger uses `casefold`; for the ASCII and Latin text this
    corpus holds they agree, and casefold is the stricter of the two so a
    span that passes here passes both.)"""
    return re.sub(r"\s+", " ", text or "").strip().casefold()


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256((text or "").encode("utf-8")).hexdigest()


# ── sentence segmentation (deterministic, no model) ────────────────────────

_ABBREV = {"mr", "mrs", "ms", "dr", "prof", "inc", "ltd", "co", "corp", "llc",
           "st", "no", "vs", "etc", "jr", "sr", "u.s", "e.g", "i.e", "fig",
           "approx", "dept", "est", "govt", "assn", "u.s.a"}

_SENT_END = re.compile(r"([.!?]['\")\]]*)(\s+)(?=[A-Z0-9\"'(\[])")


def sentences(text: str) -> list[tuple[int, int]]:
    """[(start, end)] of sentence spans in `text`, half-open, non-overlapping,
    covering every non-blank character run. A boundary is a terminal mark
    followed by whitespace and an upper-case/digit/quote opener, unless the
    token before the mark is a known abbreviation or a single initial.
    A newline always splits: the extractors emit one line per block, so a
    heading and the dateline under it are two spans, never one excerpt
    (measured 2026-10-10 on the fixture site)."""
    spans: list[tuple[int, int]] = []
    if not text:
        return spans
    # paragraphs first
    pos = 0
    for para in re.finditer(r"[^\n]+", text):
        p_start, p_end = para.start(), para.end()
        cur = p_start
        for m in _SENT_END.finditer(text, p_start, p_end):
            end = m.end(1)
            before = text[cur:end].rstrip("'\")]")
            tok = re.split(r"\s+", before[:-1].strip())[-1].lower() if before.strip() else ""
            if tok in _ABBREV or re.fullmatch(r"[a-z]", tok) or re.fullmatch(r"\d+", tok) and len(tok) <= 2:
                continue
            spans.append((cur, end))
            cur = m.end()
        if cur < p_end:
            spans.append((cur, p_end))
        pos = p_end
    # trim whitespace inside each span
    out = []
    for s, e in spans:
        while s < e and text[s].isspace():
            s += 1
        while e > s and text[e - 1].isspace():
            e -= 1
        if e > s:
            out.append((s, e))
    return out


def word_count(s: str) -> int:
    return len(re.findall(r"\S+", s or ""))
