"""The run's own facts, fed to the shared platform-fit engine.

The producer supplies JUDGEMENT and nothing else — which platforms are under
consideration, the L3 area each belongs to, how well each serves an objective
the entity itself states, and whether its prerequisites are green. Everything
FACTUAL comes from the run: which cells the area reaches, how far each sits
from the target band, how heavily an issue weighs on it, how well it is
evidenced, and whether the register says the family is absent.

That split is the contract's, not this module's invention: "fit_score from
platform_fit.py engine v2 … read, never recomputed — the agent EXPLAINS it,
never recomputes or re-ranks it". It is also the split `register_evidence`
already uses for the rank score, which is computed server-side and ignored if
sent.

No model is called. Every value here is read from a table or computed by a
pure function in `packages/shared/platform_fit.py`.
"""
from __future__ import annotations

import json

from .shared_path import ensure as _ensure_shared

_ensure_shared(__file__)
import platform_fit as engine  # noqa: E402  packages/shared/platform_fit.py

# Tier and freshness weights for the per-cell evidence strength. Mirrors the
# ladder the evidence tier already uses; a T1 regulator filing read this
# quarter is fully bankable, a T5 vendor page from four years ago is not.
_TIER_WEIGHT = {"T1": 1.00, "T2": 0.92, "T3": 0.80, "T4": 0.55, "T5": 0.50}
_FRESHNESS_WEIGHT = {"CURRENT": 1.00, "RECENT": 1.00, "AGING": 0.90,
                     "DATED": 0.75, "STALE": 0.55, "ARCHIVAL": 0.55,
                     "UNVERIFIED": 0.70}


def _norm_area(v) -> str:
    return " ".join(str(v or "").strip().lower().split())


def _areas_of(raw) -> list:
    """`l3_platform_areas` is a text array on the catalogue row, and a couple
    of loads wrote it as a JSON string. Both shapes are read rather than one
    being declared correct after the fact."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [_norm_area(x) for x in raw if str(x or "").strip()]
    s = str(raw).strip()
    if s.startswith("["):
        try:
            return [_norm_area(x) for x in json.loads(s) if str(x or "").strip()]
        except Exception:                          # noqa: BLE001
            pass
    return [_norm_area(x) for x in s.strip("{}").split(",") if x.strip()]


def _cells_for_run(cur, run_id) -> dict:
    """subcap_id -> {score, category, areas} for every cell this run serves."""
    cur.execute("""
        SELECT s.subcap_id, s.score, s.category_id, s.peer_median,
               c.l3_platform_areas
          FROM subcap_scores s
          JOIN runs r ON r.id = s.run_id
          LEFT JOIN ccg_subcaps c
                 ON c.subcap_id = s.subcap_id
                AND c.version = COALESCE(
                      r.ccg_catalog_version,
                      (SELECT version FROM ccg_versions WHERE is_current))
         WHERE s.run_id = %s""", (run_id,))
    out = {}
    for sid, score, cat, peer, areas in cur.fetchall():
        out[sid] = {"score": float(score) if score is not None else None,
                    "category": cat, "peer": float(peer) if peer is not None else None,
                    "areas": _areas_of(areas)}
    return out


def _evidence_strength(cur, run_id) -> dict:
    """subcap_id -> 0..1, the best linked item's tier x freshness.

    BEST rather than mean: one strong citation makes a reading bankable, and
    averaging it against weaker siblings punishes a cell for carrying more
    evidence. Only items with a verbatim span count — an item that cannot be
    quoted cannot ground anything (invariant 4)."""
    cur.execute("""
        SELECT l.subcap_id, e.tier::text, e.recency_band::text
          FROM evidence_subcap_links l
          JOIN evidence_index e ON e.e_id = l.e_id
         WHERE l.run_id = %s
           AND e.excerpt IS NOT NULL AND length(btrim(e.excerpt)) > 0""",
                (run_id,))
    out: dict = {}
    for sid, tier, band in cur.fetchall():
        v = (_TIER_WEIGHT.get((tier or "").upper(), 0.5)
             * _FRESHNESS_WEIGHT.get((band or "").upper(), 0.70))
        if v > out.get(sid, 0.0):
            out[sid] = v
    return out


def _severities(cur, run_id) -> dict:
    """subcap_id -> the severities of the issues linked to it."""
    cur.execute("SELECT payload FROM issue_register_raw WHERE run_id = %s",
                (run_id,))
    out: dict = {}
    for (payload,) in cur.fetchall():
        p = payload if isinstance(payload, dict) else json.loads(payload or "{}")
        sev = str(p.get("severity") or p.get("level") or "").lower()
        if not sev:
            continue
        for sid in (p.get("linked_subcap_ids") or p.get("subcap_ids") or []):
            out.setdefault(sid, set()).add(sev)
    return {k: tuple(sorted(v)) for k, v in out.items()}


def _register(cur, run_id) -> tuple:
    """(areas the register says are ABSENT, areas an incumbent already holds).

    A family the register confirms absent is greenfield ground; a layer an
    installed third party already covers is not net-new, so its cells are
    discounted rather than dropped."""
    cur.execute("SELECT payload FROM techstack_raw WHERE run_id = %s", (run_id,))
    absent, held = set(), set()
    for (payload,) in cur.fetchall():
        p = payload if isinstance(payload, dict) else json.loads(payload or "{}")
        status = str(p.get("status") or p.get("presence") or "").upper()
        for a in _areas_of(p.get("l3_area") or p.get("layer") or p.get("area")):
            if status == "ABSENT":
                absent.add(a)
            elif status in ("CONFIRMED", "INFERRED"):
                held.add(a)
    return absent, held


def platform_fit(conn, run_id, candidates) -> dict:
    """Score and rank the candidate platforms for one run.

    `candidates`: [{platform, l3_area, alignment, alignment_quote, readiness}].
    `alignment` is 0..1 quoting the entity's OWN stated objective, or omitted
    where the producer could not establish one — omitted renormalises, it does
    not score as zero.
    """
    cur = conn.cursor()
    cur.execute("SELECT id FROM runs WHERE id = %s", (run_id,))
    if cur.fetchone() is None:
        return {"error": "unknown_run", "platforms": []}

    cells = _cells_for_run(cur, run_id)
    strength = _evidence_strength(cur, run_id)
    sev = _severities(cur, run_id)
    absent_areas, held_areas = _register(cur, run_id)

    by_area: dict = {}
    for sid, c in cells.items():
        for a in c["areas"]:
            by_area.setdefault(a, []).append(sid)

    built, unmatched = [], []
    for raw in candidates or []:
        if not isinstance(raw, dict):
            continue
        area = _norm_area(raw.get("l3_area"))
        sids = by_area.get(area, [])
        if not sids:
            unmatched.append({"platform": raw.get("platform"),
                              "l3_area": raw.get("l3_area"),
                              "reason": "no cell this run serves lists this L3 area"})
        rows = [engine.Cell(
            subcap_id=sid,
            current_score=cells[sid]["score"],
            category_id=cells[sid]["category"],
            severities=sev.get(sid, ()),
            evidence_strength=strength.get(sid),
            incumbent_covers=area in held_areas,
            peer_median=cells[sid]["peer"]) for sid in sorted(sids)]
        align = raw.get("alignment")
        built.append(engine.Candidate(
            platform=str(raw.get("platform") or "").strip() or "(unnamed)",
            l3_area=raw.get("l3_area"),
            cells=rows,
            family_absent=area in absent_areas,
            readiness=str(raw.get("readiness") or "green").lower(),
            alignment=None if align is None else float(align),
            alignment_quote=raw.get("alignment_quote")))

    ranked = engine.rank(built)
    return {
        "run_id": str(run_id),
        "platforms": ranked,
        # Named rather than dropped: a candidate whose area reaches no cell
        # this run serves scores zero, and a producer reading only the ranking
        # would think the engine disagreed with them rather than that the area
        # did not match.
        "unmatched": unmatched,
        "engine": {
            "weights": {"opportunity": engine.W_OPPORTUNITY,
                        "interconnect": engine.W_INTERCONNECT,
                        "absent": engine.W_ABSENT,
                        "alignment": engine.W_ALIGNMENT},
            "readiness_multiplier": engine.READINESS_MULTIPLIER,
            "hot_threshold": engine.HOT_THRESHOLD,
            "cap": engine.FIT_CAP,
            "rule": ("Readiness MULTIPLIES. A platform whose prerequisites are "
                     "red cannot reach the hot band. Read these numbers into "
                     "the payload; explaining them is the producer's job, "
                     "recomputing them is not."),
        },
    }
