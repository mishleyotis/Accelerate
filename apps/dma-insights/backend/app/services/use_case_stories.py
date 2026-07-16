"""v7 use-case story corpus → per-subcap implementation playbooks.

The catalogue's ``3_User_Stories_Catalogue`` sheets (13k rows, loaded by
the ccg_loader into ``ccg_user_stories``) pair every sub-capability with
VALIDATED use cases and the L4 feature bundles that implement them —
"train the models using the L3, L4 and use cases" (2026-07-12 directive).
This module folds that corpus into a per-subcap playbook the composers
can cite: the feature names that recur across the subcap's stories are
the proven implementation pattern, weighted by how many catalogued use
cases validate them.

Framework-free fold (:func:`build_playbooks`) + one memoized async DB
loader; consumers get ``{subcap_id: {"features": [...], "n_stories": n,
"confidence": max}}`` and weave prose themselves. Never raises — a cold
table returns {} and every consumer keeps its prior composition.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

# "Feature for {Subcap Name}" → "Feature" (the sheet suffixes most names);
# split bundles on ';' and ','.
_SPLIT_RE = re.compile(r"[;,]")
_MAX_FEATURES = 3

_CACHE: dict[str, dict[str, dict]] = {}


def _clean_feature(raw: str) -> str | None:
    f = str(raw or "").strip()
    if not f:
        return None
    f = f.split(" for ")[0].strip()
    return f if 2 < len(f) <= 80 else None


def build_playbooks(
    rows: list[tuple[str, str | None, float | None]],
) -> dict[str, dict]:
    """Pure fold: ``(subcap_id, l4_features_used, match_confidence)`` rows →
    per-subcap playbooks. Features rank by recurrence across the subcap's
    stories (a feature validated by 12 use cases beats a one-off)."""
    by_sid: dict[str, Counter] = {}
    n_stories: dict[str, int] = {}
    conf: dict[str, float] = {}
    for sid, feats, c in rows:
        if not sid:
            continue
        n_stories[sid] = n_stories.get(sid, 0) + 1
        if c is not None:
            conf[sid] = max(conf.get(sid, 0.0), float(c))
        counter = by_sid.setdefault(sid, Counter())
        for raw in _SPLIT_RE.split(feats or ""):
            f = _clean_feature(raw)
            if f:
                counter[f] += 1
    out: dict[str, dict] = {}
    for sid, counter in by_sid.items():
        top = [f for f, _ in counter.most_common(_MAX_FEATURES)]
        if top:
            out[sid] = {"features": top, "n_stories": n_stories.get(sid, 0),
                        "confidence": round(conf.get(sid, 0.0), 3)}
    return out


async def load_playbooks(session: Any, version: str = "v7.0") -> dict[str, dict]:
    """Memoized per catalogue version (the corpus is version-stable)."""
    from sqlalchemy import text
    key = version or "v7.0"
    if key in _CACHE:
        return _CACHE[key]
    try:
        rows = (await session.execute(text(
            "SELECT subcap_id, l4_features_used, match_confidence "
            "FROM ccg_user_stories WHERE version = :v"), {"v": key})).all()
        if not rows and key != "v7.0":
            return await load_playbooks(session, "v7.0")
        _CACHE[key] = build_playbooks(
            [(r.subcap_id, r.l4_features_used,
              float(r.match_confidence) if r.match_confidence is not None
              else None) for r in rows])
        return _CACHE[key]
    except Exception:
        return {}
