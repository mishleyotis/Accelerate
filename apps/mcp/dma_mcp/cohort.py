"""Sub-vertical cohort benchmarks: the peer score a run compares against.

Owner decision, 2026-10-06 (First Tech): "peer scores being an average of
current entities in the same subvert already assessed". A named peer set is
IDENTIFIED (the run locks it and the reports name it); it is not SCORED one
peer at a time — nobody has assessed PenFed. What the platform HAS assessed
is every other entity in the sub-vertical with a scored run — promoted or
not (2026-10-15, below) — so the comparison figure is their mean, per
category, computed here where the scores live.

Rules, each one a property a test holds:
  · one figure per ENTITY (its active promoted run, else its latest scored
    run — `assessed_runs`), so an entity assessed twice counts once;
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


#: Entities whose identity is unconfirmed or retired are not peers: a
#: PENDING_REVIEW row is the corpus's own "this may be a duplicate of another
#: entity" flag, and counting it would count one brokerage twice.
_PEER_STATUSES = ("ACTIVE",)


def _code(raw) -> str | None:
    from .subverticals import resolve_subvertical
    return resolve_subvertical(raw)


def assessed_runs(cur, sub_vertical: str) -> list:
    """[(run_id, entity_key, lowered name, promoted)] — ONE run per assessed
    entity of the sub-vertical: its active promoted run, else its latest
    scored run.

    Measured 2026-10-15 on AAA Western and Central New York's first
    promotion: the IB cohort read 2 entities and every peer median shipped
    null, while the store held six scored brokerages (OneDigital, TowneBank,
    Virtuity, Alera, Alliant, IMA — 597 to 702 scored cells each). Two
    filters hid them, and both fail every first-time client in a thin
    sub-vertical:

      · `promoted_at IS NOT NULL` — an assessed package is assessed whether
        or not anyone has produced its pages yet (owner, 2026-10-06: "an
        average of current entities in the same subvert already assessed").
        Promotion writes no score; `subcap_scores` is the ingest tier for a
        promoted and an unpromoted run alike.
      · `lower(e.sub_vertical) = lower('IB')` — the corpus writes
        "Insurance Brokers", "Insurance Brokerages (IB)" and NULL. The
        sub-vertical is resolved through the one alias table
        (`subverticals.resolve_subvertical`); a NULL one is inferred from the
        run's own scored variant cells only when they name ONE sub-vertical.

    Excluded: withdrawn runs, and every run of a request a withdrawal named
    (a run is withdrawn because its content was wrong; its sibling ingest
    carries the same scores); superseded runs; entities not ACTIVE."""
    want = _code(sub_vertical) or str(sub_vertical or "").strip().upper()
    cur.execute(
        """
        SELECT DISTINCT ON (r.entity_id)
               r.id::text, COALESCE(e.display_id, e.id::text) AS ent,
               lower(COALESCE(e.legal_name, e.trading_name, '')) AS name,
               e.sub_vertical,
               (r.is_active AND r.promoted_at IS NOT NULL) AS promoted
          FROM runs r
          JOIN entities e ON e.id = r.entity_id
         WHERE r.withdrawn_at IS NULL
           AND r.status::text <> 'SUPERSEDED'
           AND COALESCE(e.status::text, 'ACTIVE') = ANY(%s)
           AND NOT EXISTS (SELECT 1 FROM runs w
                            WHERE w.entity_id = r.entity_id
                              AND w.withdrawn_at IS NOT NULL
                              AND w.request_id IS NOT DISTINCT FROM r.request_id)
           AND EXISTS (SELECT 1 FROM subcap_scores s
                        WHERE s.run_id = r.id AND s.score IS NOT NULL)
         ORDER BY r.entity_id,
                  (r.is_active AND r.promoted_at IS NOT NULL) DESC,
                  r.completed_at DESC NULLS LAST, r.run_seq DESC
        """,
        (list(_PEER_STATUSES),))
    rows = cur.fetchall()
    out, unresolved = [], {}
    for run_id, ent, name, sv, promoted in rows:
        code = _code(sv)
        if code is None and sv is None:
            unresolved[str(run_id)] = (run_id, ent, name, promoted)
        elif code == want:
            out.append((str(run_id), ent, name, bool(promoted)))
    if unresolved:
        from .subverticals import variant_subvertical
        cur.execute(
            """SELECT s.run_id::text, s.subcap_id FROM subcap_scores s
                WHERE s.run_id::text = ANY(%s) AND s.score IS NOT NULL
                  AND s.subcap_id ~ '[.][A-Z]+[0-9]+$'""",
            (sorted(unresolved),))
        codes: dict = {}
        for rid, sid in cur.fetchall():
            c = variant_subvertical(sid)
            if c:
                codes.setdefault(str(rid), set()).add(c)
        for rid, (run_id, ent, name, promoted) in unresolved.items():
            if codes.get(rid) == {want}:
                out.append((str(run_id), ent, name, bool(promoted)))
    return out


def _scores(cur, runs, ex_id: str, ex_name: str, grain: str, subcap_ids=None):
    """(entity_key, key, value) rows for the chosen runs, the asking entity
    dropped. `grain` 'category' averages a run's cells per category."""
    keep = {rid: ent for rid, ent, name, _ in runs
            if not ((ex_id and str(ent).lower() == ex_id)
                    or (ex_name and name == ex_name))}
    if not keep:
        return [], 0
    if grain == "category":
        cur.execute(
            """SELECT s.run_id::text, s.category_id, AVG(s.score)
                 FROM subcap_scores s
                WHERE s.run_id::text = ANY(%s)
                  AND s.score IS NOT NULL AND s.category_id IS NOT NULL
                GROUP BY s.run_id, s.category_id""",
            (sorted(keep),))
    else:
        cur.execute(
            """SELECT s.run_id::text, s.subcap_id, AVG(s.score)
                 FROM subcap_scores s
                WHERE s.run_id::text = ANY(%s)
                  AND s.score IS NOT NULL AND s.subcap_id = ANY(%s)
                GROUP BY s.run_id, s.subcap_id""",
            (sorted(keep), list(subcap_ids)))
    rows = [(keep[str(rid)], k, float(v) if v is not None else None)
            for rid, k, v in cur.fetchall() if str(rid) in keep]
    unpromoted = sum(1 for rid, _, _, p in runs if rid in keep and not p)
    return rows, unpromoted


def _basis(runs, unpromoted: int) -> dict:
    """Counts only — no entity, name or run id leaves this module."""
    return {"assessed_unpromoted": unpromoted,
            "method": "mean of each assessed entity's category mean on its active "
                      "promoted run, else its latest scored run; withdrawn, "
                      "superseded and non-ACTIVE entities excluded; the asking "
                      "entity excluded"}


def cohort_benchmarks(conn, sub_vertical: str, exclude_display_id: str = "",
                      exclude_entity_name: str = "") -> dict:
    """Mean category score across the sub-vertical's other assessed entities.

    An entity's figure is the mean of its subcap scores in that category on
    the ONE run `assessed_runs` chooses for it (promoted first)."""
    sv = str(sub_vertical or "").strip()
    if not sv:
        return {"error": "sub_vertical_required"}
    cur = conn.cursor()
    runs = assessed_runs(cur, sv)
    rows, unpromoted = _scores(cur, runs, str(exclude_display_id or "").strip().lower(),
                               str(exclude_entity_name or "").strip().lower(),
                               "category")
    out = summarise(rows)
    out.update({"sub_vertical": sv, "basis": "recomputed", **_basis(runs, unpromoted)})
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
    runs = assessed_runs(cur, sv)
    rows, unpromoted = _scores(cur, runs, str(exclude_display_id or "").strip().lower(),
                               str(exclude_entity_name or "").strip().lower(),
                               "cell", ids)
    out = summarise(rows)
    cells = out.pop("categories")
    for v in cells.values():        # summarise speaks of categories; this is a cell
        if v.get("reason"):
            v["reason"] = v["reason"].replace("for this category", "for this cell")
    for sid in ids:                 # a cell no peer scored is stated, never dropped
        cells.setdefault(sid, {"n": 0, "mean": None, "median": None, "p25": None,
                               "p75": None,
                               "reason": f"0 assessed entities in the cohort score "
                                         f"this cell; the floor is {FLOOR}"})
    basis = _basis(runs, unpromoted)
    basis["method"] = basis["method"].replace("category mean", "score for the cell")
    out.update({"cells": cells, "sub_vertical": sv, "basis": "recomputed",
                "grain": "cell", **basis})
    return out
