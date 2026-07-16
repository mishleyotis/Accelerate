"""Sentence/clause segmentation + sentence-safe clipping.

Why: the audits found 16% of top findings truncated mid-word
("uneve—" / "consol—") and SCQA bodies clipped mid-sentence, because
every script did its own ``text[:n]``. This module is the single
segmentation authority: spaCy ``doc.sents`` when the model is loaded,
a regex splitter with an abbreviation guard otherwise — and
:func:`clip_sentences` NEVER cuts mid-sentence or mid-word and appends
nothing (no ellipsis; titles that want "…" go through titlecraft).
"""
from __future__ import annotations

import re

# Tokens that end with "." but do not end a sentence. Checked against the
# word immediately preceding a candidate boundary (lowercased, no dot).
_ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "rev", "hon", "jr", "sr", "st",
    "inc", "corp", "co", "ltd", "llc", "llp", "plc",
    "vs", "etc", "eg", "e.g", "ie", "i.e", "cf", "al", "approx", "est",
    "no", "vol", "fig", "dept", "div", "ave", "blvd", "rd",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "u.s", "u.k", "d.c", "n.a", "a.m", "p.m",
})

# Candidate sentence boundary: terminal punctuation, then whitespace,
# then an opening quote/bracket/uppercase/digit.
_BOUNDARY_RE = re.compile(r"[.!?]+[\"'”’)\]]*\s+(?=[\"'“‘(\[A-Z0-9])")  # noqa: RUF001


def _nlp():  # deferred import — avoids a circular import at package init
    from app.services.nlp import get_nlp

    return get_nlp()


def sentences(text: str) -> list[str]:
    """Split ``text`` into sentences (whitespace-normalized, non-empty).

    spaCy ``doc.sents`` when available; otherwise a regex split on
    ``[.!?]`` boundaries guarded against common abbreviations (``Inc.``,
    ``Dr.``, ``e.g.``) so "Fiserv Inc. runs the core." stays one
    sentence.
    """
    if not text or not text.strip():
        return []
    nlp = _nlp()
    # spaCy raises E088 (ValueError) when len(text) > nlp.max_length (default
    # 1,000,000). A concatenated evidence/DOCX blob can exceed that once spaCy
    # is installed — clamp to the model limit and fall back to the regex
    # splitter on the over-length tail so this NEVER raises (audit 2026-07-03).
    if nlp is not None:
        limit = getattr(nlp, "max_length", 1_000_000)
        if len(text) < limit:
            try:
                doc = nlp(text)
                return [s.text.strip() for s in doc.sents if s.text.strip()]
            except Exception:
                pass  # any spaCy error → degrade to the regex tier below
    return _regex_sentences(text)


def _regex_sentences(text: str) -> list[str]:
    out: list[str] = []
    start = 0
    for m in _BOUNDARY_RE.finditer(text):
        candidate = text[start : m.end()]
        # The word right before the punctuation — abbreviation guard.
        preceding = re.search(r"([\w.]+)[.!?]+[\"'”’)\]]*\s*$", candidate)  # noqa: RUF001
        if preceding:
            word = preceding.group(1).rstrip(".").lower()
            if word in _ABBREVIATIONS or (len(word) == 1 and word.isalpha()):
                continue  # "J. Smith" initials / "Inc." — not a boundary
        piece = candidate.strip()
        if piece:
            out.append(piece)
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def ends_sentence(chunk: str) -> bool:
    """True when ``chunk`` ends at a genuine sentence boundary: terminal
    punctuation (closing quotes/brackets/markdown tolerated) whose final
    word is not an abbreviation or initial. The guard for callers that
    re-join or re-paragraph model/spaCy sentence units — spaCy's
    sentencizer can split at citation brackets or ALL-CAPS tokens that
    are NOT sentence ends (2026-07-14 prose audit)."""
    tail = re.sub(r"[)\]\"'”’*_]+$", "", (chunk or "").rstrip()).rstrip()  # noqa: RUF001
    if not re.search(r"[.!?:]$", tail):
        return False
    m = re.search(r"([\w.]+)[.!?:]+$", tail)
    if m:
        word = m.group(1).rstrip(".").lower()
        if word in _ABBREVIATIONS or (len(word) == 1 and word.isalpha()):
            return False
    return True


def clip_sentences(text: str, max_chars: int) -> str:
    """Clip ``text`` to at most ``max_chars`` without cutting mid-sentence.

    Whole sentences are accumulated while they fit. When even the first
    sentence exceeds the budget the clip falls back to the last WORD
    boundary inside it — never mid-word — and appends nothing (callers
    that want an ellipsis marker own that decision).
    """
    if max_chars <= 0 or not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    kept: list[str] = []
    used = 0
    for sent in sentences(text):
        extra = len(sent) + (1 if kept else 0)
        if used + extra > max_chars:
            break
        kept.append(sent)
        used += extra
    if kept:
        return " ".join(kept)
    # First sentence alone is over budget — clip at a word boundary.
    head = text[: max_chars + 1]
    cut = head.rfind(" ")
    if cut <= 0:
        return text[:max_chars]
    return text[:cut].rstrip(" ,;:—–-")  # noqa: RUF001


def clip_excerpt_verbatim(text: str, max_chars: int) -> str:
    """Sentence-safe clip of an EVIDENCE EXCERPT quoted in derived prose.

    Hard user mandate (2026-07-06): extracted evidence excerpts are
    verbatim — a clip may only drop WHOLE trailing sentences and must
    mark the omission with an ellipsis; it must never cut mid-claim
    (mid-sentence, mid-number, mid-qualifier). Consequences vs
    :func:`clip_sentences`:

      - whenever anything is dropped, ``" …"`` is appended;
      - when even the FIRST sentence exceeds the budget it is kept
        WHOLE — an over-budget verbatim claim beats a truncated one
        (the surrounding storage fields are TEXT / generously bounded).
    """
    text = (text or "").strip()
    if not text or len(text) <= max_chars:
        return text
    kept: list[str] = []
    used = 0
    sents = sentences(text)
    for sent in sents:
        extra = len(sent) + (1 if kept else 0)
        if used + extra > max_chars:
            break
        kept.append(sent)
        used += extra
    if not kept:  # first sentence alone over budget — keep it whole
        kept = sents[:1] or [text]
    out = " ".join(kept)
    # sentences() normalizes whitespace, so compare against the number of
    # sentences kept rather than raw length to detect omission.
    return out if len(kept) >= len(sents) else f"{out} …"


# A truncation point must never split a number off its unit/qualifier
# ("$20", "300", "54.3" with the "%"/"M"/"complaints" tail cut away) —
# that changes the claim. Detected on the kept side's trailing token.
_DANGLING_NUM_RE = re.compile(r"(?:[$€£~≈<>]|\b)\d[\d,.]*\s*$")


def clip_quote(text: str, max_chars: int) -> str:
    """Verbatim-quote clipping (2026-07-06 mandate): quoted evidence must
    stay verbatim; if it does not fit, the cut lands at a sentence — else
    clause, else word — boundary, an ellipsis marks the truncation, and
    the cut NEVER strands a number from its unit/qualifier (a mid-claim
    cut would change what the evidence says).

    Returns "" when nothing fits; the full text (no ellipsis) when no
    truncation was needed.
    """
    if max_chars <= 0 or not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    budget = max_chars - 2  # reserve room for the ellipsis marker
    clipped = clip_sentences(text, budget)
    if not clipped:
        return ""
    # Retreat while the tail would strand a number mid-claim.
    while clipped and _DANGLING_NUM_RE.search(clipped):
        cut = clipped.rfind(" ")
        if cut <= 0:
            return ""
        clipped = clipped[:cut].rstrip(" ,;:—–-")  # noqa: RUF001
    if not clipped:
        return ""
    # A cut at a sentence end reads "…" after the period ("no CDP. …");
    # a mid-sentence word-boundary cut runs straight into it ("across…").
    return clipped + (" …" if clipped[-1] in ".!?" else "…")


# Clause splitters for the regex tier: semicolons, em/en dashes used as
# separators, and commas followed by a connective or relative pronoun.
_CLAUSE_SPLIT_RE = re.compile(
    r";\s+|\s+[—–]\s+|\s+-\s+|"  # noqa: RUF001
    r",\s+(?=(?:and|but|or|which|who|while|whereas|because|so|yet|although|though)\b)",
    re.IGNORECASE,
)


def clauses(sent: str) -> list[str]:
    """Split one sentence into clauses (non-destructive, order-preserving).

    spaCy path: break in front of tokens that open a new clause
    (dependency ``mark``/``cc`` attached to a verbal head, or a
    coordinated/adverbial verb) plus ``;``/dash separators. Regex path:
    semicolons, spaced dashes, and commas followed by a connective.
    """
    if not sent or not sent.strip():
        return []
    nlp = _nlp()
    if nlp is None:
        parts = _CLAUSE_SPLIT_RE.split(sent)
        return [p.strip(" ,;") for p in parts if p and p.strip(" ,;")]
    doc = nlp(sent)
    breaks: set[int] = set()
    for tok in doc:
        if tok.i == 0:
            continue
        if tok.text in {";", "—", "–"}:  # noqa: RUF001
            breaks.add(tok.i + 1)
        elif tok.dep_ in {"mark", "cc"} and tok.head.pos_ in {"VERB", "AUX"}:
            breaks.add(tok.i)
        elif tok.dep_ in {"advcl", "conj"} and tok.pos_ in {"VERB", "AUX"}:
            # Clause head without an explicit marker — break at the
            # left edge of its subtree so the subject travels with it.
            left = min(t.i for t in tok.subtree)
            if left > 0:
                breaks.add(left)
    idxs = sorted(b for b in breaks if 0 < b < len(doc))
    spans = []
    prev = 0
    for b in idxs:
        spans.append(doc[prev:b])
        prev = b
    spans.append(doc[prev:])
    out = [sp.text.strip(" ,;—–") for sp in spans]  # noqa: RUF001
    # A bare connective ("and", "but") between two breaks is glue, not a clause.
    return [c for c in out if c and c.lower() not in {"and", "but", "or", "yet", "so"}]
