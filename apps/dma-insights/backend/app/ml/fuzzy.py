"""Fuzzy entity/name matching built on rapidfuzz (offline, deterministic).

Used by the name-matching fallbacks in ``scripts/derive_peers`` and
``sheets_client.fuzzy_match_assignee``. The key contract is
``unambiguous_best``: it returns a match ONLY when the top candidate clears a
score cutoff AND beats the runner-up by a margin — so an ambiguous query is
rejected (returns None) rather than mis-assigned. A false match (wrong entity)
is worse than a miss, so the guard is deliberately conservative.

No heavy deps: rapidfuzz is already a runtime dependency. numpy/embeddings are
NOT required here.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    choice: str
    score: float
    index: int


def _scorer():
    from rapidfuzz import fuzz
    return fuzz.WRatio


def best_match(query: str, choices: list[str], *, cutoff: float = 0.0) -> Match | None:
    """Highest-scoring choice for query (rapidfuzz WRatio), or None below cutoff."""
    from rapidfuzz import process
    if not query or not choices:
        return None
    hit = process.extractOne(query, choices, scorer=_scorer(), score_cutoff=cutoff)
    if hit is None:
        return None
    choice, score, idx = hit
    return Match(choice=choice, score=float(score), index=int(idx))


def extract_top(query: str, choices: list[str], *, k: int = 3) -> list[Match]:
    from rapidfuzz import process
    if not query or not choices:
        return []
    hits = process.extract(query, choices, scorer=_scorer(), limit=k)
    return [Match(choice=c, score=float(s), index=int(i)) for c, s, i in hits]


def unambiguous_best(
    query: str, choices: list[str], *, cutoff: float = 88.0, margin: float = 5.0,
) -> Match | None:
    """Return the best match only if it clears `cutoff` AND leads the runner-up
    by at least `margin`. Otherwise None (ambiguous → refuse to guess)."""
    top = extract_top(query, choices, k=2)
    if not top:
        return None
    best = top[0]
    if best.score < cutoff:
        return None
    if len(top) > 1 and (best.score - top[1].score) < margin:
        return None
    return best
