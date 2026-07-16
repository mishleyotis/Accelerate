"""Verbatim-quote mining with source_path/page anchoring.

Why: focus areas and finding grounding require a REAL quote + page +
document — the audit found synthesized focus rows grounding on generated
paragraphs with NULL pages. This module only ever emits verbatim spans:
explicitly quoted text first, then high-salience declarative sentences
(ones that carry a number or a named entity — the sentences worth citing).
The caller supplies the anchoring ``source_path``/``page``; nothing is
paraphrased, so a grounding validator can substring-match every quote
back into the source document.
"""
from __future__ import annotations

import re

from app.services.nlp.entities import extract
from app.services.nlp.segment import sentences

_QUOTED_RE = re.compile(r"“([^”]{20,300})”|\"([^\"]{20,300})\"")

_MIN_SENT_LEN = 40
_MAX_SENT_LEN = 320


def _is_salient(sent: str) -> bool:
    """Worth citing: carries a number or a named entity."""
    if any(ch.isdigit() for ch in sent):
        return True
    ents = extract(sent)
    return bool(ents["persons"] or ents["orgs"] or ents["money"] or ents["percents"])


def mine_quotes(
    text: str, source_path: str | None = None, page: int | None = None
) -> list[dict]:
    """Mine verbatim quotes → ``[{quote, page, source_path}, ...]``.

    Quoted spans (straight or curly quotes, 20-300 chars) come first,
    then declarative high-salience sentences not already inside a quoted
    span. Every ``quote`` value is a verbatim substring of ``text``.
    """
    out: list[dict] = []
    if not text or not text.strip():
        return out
    seen: set[str] = set()
    quoted_spans: list[tuple[int, int]] = []

    def emit(quote: str) -> None:
        if quote in seen:
            return
        seen.add(quote)
        out.append({"quote": quote, "page": page, "source_path": source_path})

    for m in _QUOTED_RE.finditer(text):
        inner = (m.group(1) or m.group(2)).strip()
        quoted_spans.append(m.span())
        emit(inner)

    cursor = 0
    for sent in sentences(text):
        start = text.find(sent, cursor)
        if start == -1:
            start = text.find(sent)
        end = start + len(sent)
        cursor = max(cursor, end)
        if start != -1 and any(s < end and start < e for s, e in quoted_spans):
            continue  # already captured as an explicit quote
        stripped = sent.strip()
        if not (_MIN_SENT_LEN <= len(stripped) <= _MAX_SENT_LEN):
            continue
        if stripped.endswith("?"):
            continue  # not declarative
        if _is_salient(stripped):
            emit(stripped)
    return out
