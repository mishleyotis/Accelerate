"""Corpus-IDF distinctiveness — the anti-generic signal at COMPOSE time.

The entity-swap scans (rubric ASK-CN-6, countercheck template_language)
MEASURE genericity after the fact; this module lets composers avoid it
while choosing what to write. Fitted once per process over the corpus's
evidence excerpts (deepen_narrative does it from one SQL), it scores any
candidate sentence by how entity-specific its vocabulary is:

  distinctiveness(s) = mean IDF of the sentence's content tokens over
                       the fitted corpus, squashed to [0,1], plus a
                       capped bonus for hard specifics (figures, years,
                       proper-noun runs) — the things a swappable
                       sentence never carries.

A sentence every client could ship ("the bank continues to invest in
digital capabilities") scores near the corpus floor; one carrying the
client's own numbers and names scores high. Unfitted → 0.0 for every
input, so consumers can add the term unconditionally with zero effect
on cold paths (tests, single-entity tools).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

_TOKEN_RE = re.compile(r"[A-Za-z][\w&'-]{2,}")
_HARD_SPECIFIC_RE = re.compile(
    r"\d|%|\$|\b(?:[A-Z][a-z]+ ){1,3}[A-Z][a-z]+\b")
_STOP = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was",
    "has", "have", "its", "their", "our", "will", "into", "over", "more",
    "than", "been", "also", "which", "who", "what", "when", "where",
}

_DF: Counter = Counter()
_N_DOCS = 0
_MAX_IDF = 1.0


def reset() -> None:
    global _DF, _N_DOCS, _MAX_IDF
    _DF = Counter()
    _N_DOCS = 0
    _MAX_IDF = 1.0


def fit_corpus(texts: Iterable[str]) -> int:
    """Document-frequency table over the corpus; returns docs fitted.
    Refitting replaces the table (idempotent per process)."""
    global _N_DOCS, _MAX_IDF
    reset()
    n = 0
    for t in texts:
        toks = {w.lower() for w in _TOKEN_RE.findall(t or "")} - _STOP
        if not toks:
            continue
        n += 1
        for w in toks:
            _DF[w] += 1
    globals()["_N_DOCS"] = n
    if n:
        globals()["_MAX_IDF"] = math.log(1.0 + n)
    return n


def is_fit() -> bool:
    return _N_DOCS > 0


def distinctiveness(sentence: str) -> float:
    """[0,1] entity-specificity of one sentence; 0.0 when unfitted."""
    if _N_DOCS <= 0:
        return 0.0
    toks = [w.lower() for w in _TOKEN_RE.findall(sentence or "")]
    toks = [w for w in toks if w not in _STOP]
    if not toks:
        return 0.0
    idfs = [math.log(1.0 + _N_DOCS / (1.0 + _DF.get(w, 0))) / _MAX_IDF
            for w in toks]
    base = sum(idfs) / len(idfs)
    bonus = 0.15 if _HARD_SPECIFIC_RE.search(sentence or "") else 0.0
    return round(min(1.0, base + bonus), 4)
