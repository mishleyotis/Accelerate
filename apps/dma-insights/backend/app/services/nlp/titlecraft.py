"""<=60-char human titles from excerpts (subject-verb-object compression).

Why: the timeline audit measured 51% garbage titles — raw excerpts with
subcap-ID prefixes ("P3C2.1.4 …"), ALL-CAPS researcher headers
("NEGATIVE SEARCH RESULT:"), trailing citations ("[E-214]") and 200+
char walls cut mid-word. :func:`make_title` produces the display title:
strip the artifacts, compress to the subject-verb-object core when the
spaCy dep parse finds one (first clause otherwise), sentence-case, and
truncate ONLY at a word boundary — "…" appears only when truncation
actually happened.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.nlp.segment import clauses, sentences

_SUBCAP_PREFIX_RE = re.compile(r"^\s*P\d+C[\d.]+\S*\s*[:\-—–]?\s*")  # noqa: RUF001
# ALL-CAPS header prefix: uppercase words then a separator then content.
_ALLCAPS_PREFIX_RE = re.compile(
    r"^\s*[A-Z][A-Z0-9&/']*(?:\s+[A-Z0-9][A-Z0-9&/']*)*\s*(?::|—|–|-)\s+"  # noqa: RUF001
)
_CITATION_RE = re.compile(r"\s*\[E-\d+(?:\s*[,;]\s*E?-?\d+)*\]")
# Parenthesized E-ID notes — "(E-051/E-081)", "(E-067 carry-forward)".
_PAREN_EID_RE = re.compile(r"\s*\(\s*E-\d+[^)]{0,40}\)")
# Markdown emphasis debris from researcher notes ("**September 10, 2025").
_MD_STRONG_RE = re.compile(r"\*\*+|__+")
_MD_STRAY_RE = re.compile(r"(^|\s)[*_]+(?=\S)|(?<=\S)[*_]+(?=\s|$)")
# Enumeration/list markers — leading "- ", "• ", "(e) ", "a) ", "1. " and the
# same single-letter "(a)" tokens mid-text (researcher list shorthand).
_LIST_MARKER_RE = re.compile(
    r"^\s*(?:[-•▪*]+\s+|\(?[a-z0-9]{1,2}[.)]\s+|\(\s*[a-z0-9]{1,2}\s*\)\s*)",
    re.IGNORECASE,
)
_INLINE_MARKER_RE = re.compile(r"\(\s*[a-z]\s*\)\s+")
# A leading date + separator ("September 10, 2025 — X") demotes to X: the
# event date is carried by the row itself, and a bare date is not a title.
_LEADING_DATE_RE = re.compile(
    r"^\s*(?:(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|"
    r"Dec)\.?\s+\d{1,2},?\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})"
    r"\s*[—–:,-]\s*"  # noqa: RUF001
)
_TRAIL_DEBRIS = " ,;:—–-=*_#|~+&"  # noqa: RUF001 — em/en dashes are real corpus debris
_ELLIPSIS = "…"


def _nlp() -> Any:  # deferred — avoids circular import at package init
    from app.services.nlp import get_nlp

    return get_nlp()


def _strip_artifacts(text: str) -> str:
    text = _CITATION_RE.sub("", text)
    text = _PAREN_EID_RE.sub("", text)
    # Markdown emphasis + list/enumeration debris (2026-07-02 stress-test:
    # "(e) **September 10, 2025" was emitted as a live TITLE).
    text = _MD_STRONG_RE.sub("", text)
    text = _MD_STRAY_RE.sub(lambda m: m.group(1) or "", text)
    for _ in range(3):  # marker→emphasis→marker stacks
        cleaned = _LIST_MARKER_RE.sub("", text, count=1)
        if cleaned == text:
            break
        text = cleaned
    text = _INLINE_MARKER_RE.sub("", text)
    stripped = _SUBCAP_PREFIX_RE.sub("", text, count=1)
    candidate = _ALLCAPS_PREFIX_RE.sub("", stripped, count=1)
    if candidate.strip():
        stripped = candidate
    return re.sub(r"\s+", " ", stripped).strip()


def _svo_core(text: str) -> str | None:
    """Subject-verb-object span via the dep parse, or None."""
    nlp = _nlp()
    if nlp is None:
        return None
    doc = nlp(text)
    root = next((t for t in doc if t.dep_ == "ROOT" and t.pos_ in {"VERB", "AUX"}), None)
    if root is None:
        return None
    subj = next((c for c in root.children if c.dep_ in {"nsubj", "nsubjpass"}), None)
    if subj is None:
        return None
    parts: list[str] = []
    subj_tokens = sorted(subj.subtree, key=lambda t: t.i)
    parts.append("".join(t.text_with_ws for t in subj_tokens).strip())
    verb_bits = [c.text for c in root.children if c.dep_ in {"aux", "auxpass", "neg"}]
    verb_bits.append(root.text)
    parts.append(" ".join(verb_bits))
    obj = next(
        (c for c in root.children if c.dep_ in {"dobj", "attr", "oprd", "dative", "acomp"}),
        None,
    )
    if obj is None:
        prep = next((c for c in root.children if c.dep_ == "prep"), None)
        if prep is not None:
            obj = prep
    if obj is not None:
        obj_tokens = sorted(obj.subtree, key=lambda t: t.i)
        parts.append("".join(t.text_with_ws for t in obj_tokens).strip())
    core = " ".join(p for p in parts if p).strip(" ,;")
    return core or None


def _sentence_case(text: str) -> str:
    words = [
        w.capitalize() if (w.isalpha() and w.isupper() and len(w) >= 5) else w
        for w in text.split(" ")
    ]
    out = " ".join(words)
    return out[0].upper() + out[1:] if out else out


def _clip_word_boundary(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text.rfind(" ", 0, max_chars)  # room for the ellipsis char
    if cut <= 0:
        return text[:max_chars]
    return text[:cut].rstrip(" ,;:—–-.") + _ELLIPSIS  # noqa: RUF001


def make_title(excerpt: str, max_chars: int = 60) -> str:
    """Compress an excerpt into a clean display title (≤ ``max_chars``).

    Pipeline: strip subcap-ID / ALL-CAPS-header / list-marker / markdown-
    emphasis prefixes and E-ID citations → demote a leading "date —"
    (the row carries the date; a bare date is not a title) → SVO core
    (dep parse) or first clause → sentence case → word-boundary clip →
    trailing-debris strip (``=``, ``*``, ``|`` …). Never ends mid-word;
    "…" appears only when the title was actually truncated.
    """
    if not excerpt or not excerpt.strip() or max_chars <= 0:
        return ""
    text = _strip_artifacts(excerpt)
    if not text:
        return ""
    sents = sentences(text)
    first = sents[0] if sents else text
    m = _LEADING_DATE_RE.match(first)
    if m and len(first[m.end():].strip(_TRAIL_DEBRIS)) >= 12:
        first = first[m.end():].strip()
    core = _svo_core(first)
    # a recomposed core must be a CONTIGUOUS span of the source — the dep
    # parse can drop tokens inside hyphen compounds ("BSA/AML
    # Re-Architecture Is Non-Negotiable" -> "Re- Is Non", 2026-07-13
    # Beacon vetting); a non-substring core is a mangle, not a headline
    if core is not None and core not in first:
        core = None
    if core is None or len(core) < 12:
        first_clauses = clauses(first)
        core = first_clauses[0] if first_clauses else first
    core = core.strip(_TRAIL_DEBRIS).rstrip(".").strip(_TRAIL_DEBRIS)
    if not core:
        core = first.strip(_TRAIL_DEBRIS).rstrip(".")
    title = _clip_word_boundary(_sentence_case(core), max_chars)
    if title.endswith(_ELLIPSIS):
        return title[:-1].rstrip(_TRAIL_DEBRIS) + _ELLIPSIS
    return title.rstrip(_TRAIL_DEBRIS)
