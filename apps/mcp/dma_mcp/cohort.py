"""Sub-vertical cohort benchmarks: the peer score a run compares against.

Owner decision, 2026-10-06 (First Tech): "peer scores being an average of
current entities in the same subvert already assessed". A named peer set is
IDENTIFIED (the run locks it and the reports name it); it is not SCORED one
peer at a time — nobody has assessed PenFed. What the platform HAS assessed
is every other entity in the sub-vertical with an active promoted run, so the
comparison figure is their mean, per category, computed here where the
scores live.

Rules, each one a property a test holds:
  · one figure per ENTITY (its active, promoted run), so an entity assessed
    twice counts once;
  · the asking entity is excluded — a client is not its own peer;
  · a category is only figured with at least FLOOR entities behind it
    (subcap_scores.peer_n: "cohort size actually used; floor of three"),
    otherwise it is returned with mean null and the reason — never imputed;
  · aggregates only: no entity id, name or run id leaves this module, for
    any caller (invariant 5 strips cohort entity_ids for every audience).
"""
from __future__ import annotations

import statistics

FLOOR = 3


def _q(xs: list[float], q: float) -> float:
    """Linear-interpolated quantile of a sorted list (q in [0, 1])."""
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def summarise(rows, *, exclude_entity: str | None = None, floor: int = FLOOR) -> dict:
    """Pure core. `rows`: (entity_key, category_id, category_mean) per entity.

    Returns per category {n, mean, median, p25, p75} or {n, mean: None,
    reason} below the floor; plus the cohort's distinct entity count."""
    ex = (exclude_entity or "").strip().lower()
    by_cat: dict[str, dict[str, float]] = {}
    entities = set()
    for ent, cat, score in rows:
        key = str(ent or "").strip().lower()
        if not key or (ex and key == ex) or score is None or not cat:
            continue
        entities.add(key)
        by_cat.setdefault(str(cat), {})[key] = float(score)
    cats = {}
    for cat, per in sorted(by_cat.items()):
        xs = sorted(per.values())
        if len(xs) < floor:
            cats[cat] = {"n": len(xs), "mean": None, "median": None, "p25": None,
                         "p75": None,
                         "reason": f"{len(xs)} assessed entit{'y' if len(xs) == 1 else 'ies'} "
                                   f"in the cohort for this category; the floor is {floor}"}
            continue
        cats[cat] = {"n": len(xs), "mean": round(statistics.fmean(xs), 2),
                     "median": round(statistics.median(xs), 2),
                     "p25": round(_q(xs, 0.25), 2), "p75": round(_q(xs, 0.75), 2)}
    return {"entities": len(entities), "floor": floor, "categories": cats}


def cohort_benchmarks(conn, sub_vertical: str, exclude_display_id: str = "",
                      exclude_entity_name: str = "") -> dict:
    """Mean category score across the sub-vertical's other assessed entities.

    An entity's figure is the mean of its subcap scores in that category on
    its ACTIVE, PROMOTED run. Matched on the entity's sub_vertical, case-
    insensitively."""
    sv = str(sub_vertical or "").strip()
    if not sv:
        return {"error": "sub_vertical_required"}
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(e.display_id, e.id::text) AS ent,
               lower(COALESCE(e.legal_name, e.trading_name, '')) AS name,
               s.category_id, AVG(s.score) AS cat_mean
          FROM runs r
          JOIN entities e ON e.id = r.entity_id
          JOIN subcap_scores s ON s.run_id = r.id
         WHERE r.is_active AND r.promoted_at IS NOT NULL
           AND lower(e.sub_vertical) = lower(%s)
           AND s.score IS NOT NULL AND s.category_id IS NOT NULL
         GROUP BY ent, name, s.category_id
        """,
        (sv,))
    ex_id = str(exclude_display_id or "").strip().lower()
    ex_name = str(exclude_entity_name or "").strip().lower()
    rows = []
    for ent, name, cat, mean in cur.fetchall():
        if (ex_id and str(ent).lower() == ex_id) or (ex_name and name == ex_name):
            continue
        rows.append((ent, cat, float(mean) if mean is not None else None))
    out = summarise(rows)
    out.update({"sub_vertical": sv, "basis": "recomputed",
                "method": "mean of each assessed entity's category mean on its active "
                          "promoted run; the asking entity excluded"})
    return out


#: At most this many cells per call: a page's drilldowns ask for tens, and an
#: unbounded list would turn one tool call into a corpus export.
CELL_LIMIT = 500


def cell_benchmarks(conn, sub_vertical: str, subcap_ids, exclude_display_id: str = "",
                    exclude_entity_name: str = "") -> dict:
    """The same cohort, at CELL grain: per subcap, the mean of the other
    assessed entities' scores for that cell on their active, promoted runs.

    Owner request, 2026-10-07 (Arbor Bank): the findings, opportunity cells and
    platform gap rows carry a cell's own peer figure, and the category mean is
    not that figure. Same rules as the category grain — one figure per entity,
    the asking entity excluded, null with its reason below the floor, and no
    entity, name or run id leaves the module."""
    sv = str(sub_vertical or "").strip()
    if not sv:
        return {"error": "sub_vertical_required"}
    ids = sorted({str(s).strip() for s in (subcap_ids or []) if str(s or "").strip()})
    if not ids:
        return {"error": "subcap_ids_required"}
    if len(ids) > CELL_LIMIT:
        return {"error": f"too_many_subcap_ids: {len(ids)} > {CELL_LIMIT}"}
    cur = conn.cursor()
    cur.execute(
        """
        SELECT COALESCE(e.display_id, e.id::text) AS ent,
               lower(COALESCE(e.legal_name, e.trading_name, '')) AS name,
               s.subcap_id, AVG(s.score) AS cell_score
          FROM runs r
          JOIN entities e ON e.id = r.entity_id
          JOIN subcap_scores s ON s.run_id = r.id
         WHERE r.is_active AND r.promoted_at IS NOT NULL
           AND lower(e.sub_vertical) = lower(%s)
           AND s.score IS NOT NULL AND s.subcap_id = ANY(%s)
         GROUP BY ent, name, s.subcap_id
        """,
        (sv, ids))
    ex_id = str(exclude_display_id or "").strip().lower()
    ex_name = str(exclude_entity_name or "").strip().lower()
    rows = []
    for ent, name, sid, score in cur.fetchall():
        if (ex_id and str(ent).lower() == ex_id) or (ex_name and name == ex_name):
            continue
        rows.append((ent, sid, float(score) if score is not None else None))
    out = summarise(rows)
    cells = out.pop("categories")
    for sid in ids:                 # a cell no peer scored is stated, never dropped
        cells.setdefault(sid, {"n": 0, "mean": None, "median": None, "p25": None,
                               "p75": None,
                               "reason": f"0 assessed entities in the cohort score "
                                         f"this cell; the floor is {FLOOR}"})
    out.update({"cells": cells, "sub_vertical": sv, "basis": "recomputed",
                "grain": "cell",
                "method": "mean of each assessed entity's score for the cell on its "
                          "active promoted run; the asking entity excluded"})
    return out
