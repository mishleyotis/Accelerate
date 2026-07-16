"""Symmetric near-duplicate detection for why-now signals.

Shared by the DB-side miner (``deepen_narrative._push``), the persist-floor
backfill (``derive_insights``) and the Gemini read-path merge
(``overview_gemini_merge``) so every why-now producer applies ONE dedup
contract (audit 2026-07-06: the miner's asymmetric guard thresholded on the
NEW signal's tokens only, so a long restatement of a short already-pushed
signal — the WBB acquisition, the TriState CTO hire, the loanDepot AI
deployment — sailed through and rendered as duplicate tiles).

Why a dedicated tokenizer instead of ``startup_enrich.significant_tokens``:
that helper drops tokens under 4 chars ("AI", "Q4", "2025"), so two
restatements of the same AI/date-anchored trigger share almost no tokens
under it. Dedup needs the pack-audit tokenization — every alphanumeric run
of >=2 chars, lower-cased, stop-words removed — which is what the acceptance
measurement scripts use.

Pure logic, no imports beyond ``re`` — safe from any layer (services,
scripts, routers).
"""
from __future__ import annotations

import re
from collections.abc import Iterable

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")
# Function words + org-suffix boilerplate ("bank", "inc") that would inflate
# overlap between unrelated signals about the same institution.
_STOP = frozenset(
    "the an and or of to in for with on at by from is are was were be been being "
    "this that these those it its as has have had not no but their our your his her "
    "via than then them they will would can could should may might also into over "
    "across more most less least each per some any within without about above below "
    "other after before during since company firm bank group inc corp llc".split())


def dup_tokens(text: object) -> frozenset[str]:
    """Comparable content tokens (>=2 chars, stop-words removed)."""
    return frozenset(t for t in _TOKEN_RE.findall(str(text or "").lower())
                     if t not in _STOP)


def overlap_ratio(a: Iterable[str], b: Iterable[str]) -> float:
    """Directional containment: the fraction of ``a``'s tokens inside ``b``."""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa)


def token_containment(a_text: object, b_text: object) -> float:
    """Symmetric containment: shared tokens over the SMALLER token set, so a
    long restatement of a short signal scores the same as the reverse."""
    sa, sb = dup_tokens(a_text), dup_tokens(b_text)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / min(len(sa), len(sb))


def token_jaccard(a_text: object, b_text: object) -> float:
    sa, sb = dup_tokens(a_text), dup_tokens(b_text)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def near_duplicate(a_text: object, b_text: object, *,
                   containment_min: float = 0.5,
                   jaccard_min: float = 0.4) -> bool:
    """True when two prose bodies restate the same trigger: containment
    >= ``containment_min`` on the smaller set OR Jaccard >= ``jaccard_min``."""
    sa, sb = dup_tokens(a_text), dup_tokens(b_text)
    if not sa or not sb:
        return False
    shared = len(sa & sb)
    if shared / min(len(sa), len(sb)) >= containment_min:
        return True
    return shared / len(sa | sb) >= jaccard_min
