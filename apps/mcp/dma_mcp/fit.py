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
import re

from . import subverticals
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


# `[L3-SF-DC-CORE] Data Cloud (count: 3)` is one real catalogue value. The
# CODE is the stable identifier; the label drifts (a producer writes "Data
# Cloud", the catalogue writes "Salesforce Data Cloud") and the "(count: N)"
# suffix is a vote tally welded onto the label, which the platform page
# already strips at render. So the code decides the match when there is one,
# and the cleaned label when there is not.
_AREA_CODE = re.compile(r"\[\s*(L3-[A-Z0-9-]+)\s*\]", re.I)
_AREA_COUNT = re.compile(r"\(\s*count\s*:\s*\d+\s*\)", re.I)


def _norm_area(v) -> str:
    s = str(v or "").strip()
    if not s:
        return ""
    m = _AREA_CODE.search(s)
    if m:
        return m.group(1).upper()
    s = _AREA_COUNT.sub(" ", _AREA_CODE.sub(" ", s))
    return " ".join(s.lower().split())


# A producer states readiness as the page's own verdict phrase, not as a
# traffic light. Both are accepted; an unrecognised phrase is RED rather than
# green, because the multiplier is a safety property — guessing green on a
# phrase nobody mapped is how a red platform renders hot.
_READINESS_VERDICT = {
    "READY": "green",
    "READY WITH CONDITIONS": "amber",
    "CONDITIONAL": "amber",
    "NOT READY": "red",
    # The reference client writes this one on three of its five cards, two of
    # which were promoted at rank 2 and 3 with fits of 70.0 and 73.0 — the
    # "red but hot" shape, live.
    "NOT READY YET": "red",
    "BLOCKED": "red",
    "GREEN": "green", "AMBER": "amber", "RED": "red",
}


def _readiness_token(raw) -> str:
    if isinstance(raw, dict):
        raw = raw.get("verdict") or raw.get("state") or raw.get("status")
    key = " ".join(str(raw or "").strip().upper().split())
    if not key:
        return "green"
    return _READINESS_VERDICT.get(key, "red")


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


def _entity_subvertical(cur, run_id):
    cur.execute("""SELECT e.sub_vertical FROM runs r
                     JOIN entities e ON e.id = r.entity_id
                    WHERE r.id = %s""", (run_id,))
    row = cur.fetchone()
    return row[0] if row else None


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


def _register_staged(cur, run_id) -> tuple:
    """(cells an ABSENT register row names, cells an incumbent row names) —
    from the run's own PROMOTED techstack register, by `linked_subcap_ids`.

    `techstack_raw` is the ingest tier and it is EMPTY on both promoted runs:
    their packages carried no tech workbook, so the producer registered the
    stack from evidence into the techstack page instead. Reading only the raw
    tier made the greenfield term and the incumbent discount silently zero —
    on the reference client, while its own served register carried MuleSoft,
    Data Cloud and CRM Analytics as ABSENT rows and the incumbent model
    platform sat linked to the exact cells the rank-1 card recommends.

    Rules, deliberately narrow:
      · CONFIRMED and INFERRED hold a cell. CLAIMED does not — a claim is
        provisional by the register's own vocabulary and must not discount a
        recommendation, nor deny a greenfield term.
      · A cell both held and absent is HELD: never award greenfield where any
        row says the layer is occupied.
    """
    try:
        cur.execute(
            """SELECT payload FROM submissions
                WHERE run_id = %s AND page = 'techstack'
                  AND superseded_at IS NULL
                ORDER BY submitted_at DESC LIMIT 1""", (run_id,))
        row = cur.fetchone()
    except Exception:                              # noqa: BLE001
        return set(), set()
    payload = row[0] if row else None
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return set(), set()
    if not isinstance(payload, dict):
        return set(), set()
    items = ((payload.get("techstack") or {}).get("items")) or []
    absent_sids, held_sids = set(), set()
    for it in items:
        if not isinstance(it, dict):
            continue
        status = str(it.get("status") or "").upper()
        sids = {str(s) for s in (it.get("linked_subcap_ids") or []) if s}
        if status == "ABSENT":
            absent_sids |= sids
        elif status in ("CONFIRMED", "INFERRED"):
            held_sids |= sids
    return absent_sids - held_sids, held_sids


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
    absent_sids, held_sids = _register_staged(cur, run_id)
    entity_code = subverticals.resolve_subvertical(
        _entity_subvertical(cur, run_id))

    def _cell(sid, area_held):
        return engine.Cell(
            subcap_id=sid,
            current_score=cells[sid]["score"],
            category_id=cells[sid]["category"],
            severities=sev.get(sid, ()),
            evidence_strength=strength.get(sid),
            incumbent_covers=area_held or sid in held_sids,
            peer_median=cells[sid]["peer"])

    # THE RUN'S WHOLE GAP SURFACE. Interconnect is the share of the gap mass a
    # platform's core would LIFT without addressing, so it is meaningless
    # without the cells the platform does NOT touch — and 0.0 rather than a
    # guess when they are absent.
    all_gaps = [_cell(sid, False) for sid in sorted(cells)
                if cells[sid]["score"] is not None]

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
        rows = [_cell(sid, area in held_areas) for sid in sorted(sids)]
        # Greenfield from either tier: the raw register names an ABSENT area,
        # or the promoted register carries an ABSENT row linked to this
        # candidate's own cells (Data Cloud absent, linked to the member-data
        # cells, is greenfield ground for the Data Cloud candidate).
        family_absent = (area in absent_areas
                         or bool(absent_sids & set(sids)))
        # THE VERTICAL GUARD. "Out-of-vertical rank-1 is a defect: a carrier
        # platform must not top a bank's list." Relevance is the share of the
        # area's cells this entity's sub-vertical actually serves — computed
        # from the catalogue, not taken from the producer, because it is a
        # fact about the client rather than a judgement about the platform.
        # Unknown sub-vertical keeps every cell (`serves` is one-sided by
        # design: not knowing who you are is not grounds for hiding scores).
        if entity_code and sids:
            served = sum(1 for sid in sids
                         if subverticals.serves(sid, entity_code))
            relevance = served / len(sids)
        else:
            relevance = 1.0
        align = raw.get("alignment")
        built.append(engine.Candidate(
            platform=str(raw.get("platform") or "").strip() or "(unnamed)",
            l3_area=raw.get("l3_area"),
            cells=rows,
            family_absent=family_absent,
            readiness=_readiness_token(raw.get("readiness")),
            alignment=None if align is None else float(align),
            alignment_quote=raw.get("alignment_quote"),
            depends_on=tuple(raw.get("depends_on") or ()),
            relevance=relevance))

    ranked = engine.rank(built, all_gap_cells=all_gaps)
    # WHAT THE ENGINE ACTUALLY HAD TO WORK WITH.
    #
    # `issue_register_raw` and `techstack_raw` are both EMPTY for at least one
    # promoted run. Empty is not neutral: with no issues every cell falls to
    # the medium severity weight, and with no register no platform can earn
    # the greenfield term or the incumbent discount. Returning the scores
    # without saying so is the shape this build keeps removing — a term that
    # could not run, reading as a term that ran and found nothing.
    with_evidence = sum(1 for sid in cells if sid in strength)
    context = {
        "cells_scored": sum(1 for c in cells.values() if c["score"] is not None),
        "cells_with_citable_evidence": with_evidence,
        "issue_rows": len(sev),
        "register_rows_absent": len(absent_areas),
        "register_rows_held": len(held_areas),
        "register_cells_absent": len(absent_sids),
        "register_cells_held": len(held_sids),
        "entity_subvertical_code": entity_code,
        "notes": [],
    }
    if not sev:
        context["notes"].append(
            "The issue register is empty for this run, so every cell carries "
            "the neutral severity weight. Severity is not flat because the "
            "capabilities are equally urgent; it is flat because nothing was "
            "linked.")
    if not absent_areas and not held_areas and not absent_sids \
            and not held_sids:
        context["notes"].append(
            "Neither the ingested technology register nor the promoted one "
            "carries a row for this run, so no platform can earn the "
            "greenfield term and no cell can be discounted for an incumbent. "
            "Both read as zero, and zero here means unmeasured.")
    elif not absent_areas and not held_areas:
        context["notes"].append(
            "techstack_raw is empty for this run (the package carried no "
            "tech workbook); the greenfield term and the incumbent discount "
            "were read from the promoted techstack register instead, by "
            "linked_subcap_ids. CLAIMED rows bind nothing either way.")
    if not with_evidence:
        context["notes"].append(
            "No cell on this run carries a citable evidence span, so every "
            "opportunity is computed on the neutral prior.")
    if entity_code is None:
        context["notes"].append(
            "The entity's sub-vertical did not resolve, so the vertical guard "
            "kept every cell — not knowing who the client is is not grounds "
            "for hiding scores, but it does mean relevance is unchecked.")
    elif all(p.get("relevance", 1.0) >= 0.999 for p in ranked):
        # SAY WHAT THE GUARD COULD SEE. Relevance is the share of the area's
        # cells this sub-vertical serves, and the cells reaching this function
        # were already scoped at ingest — so on a well-scoped run the term is
        # 1.0 for everything and binds on nothing. It fires on a variant cell
        # belonging to another sub-vertical, which a correctly scoped run does
        # not carry. A guard that reads clean because it had nothing to catch
        # must not read as a guard that caught nothing.
        context["notes"].append(
            "Vertical relevance is 1.0 on every candidate. The cells reaching "
            "this engine were already sub-vertical scoped at ingest, so the "
            "guard had nothing to bind on — that is a clean scope upstream, "
            "not a platform set it examined and approved.")
    return {
        "run_id": str(run_id),
        "platforms": ranked,
        "context": context,
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
            # THE FUSION, DECLARED. Every row already carries `signal_ranks`,
            # `rrf_score`, `rrf_rank` and `fusion_note`; without the
            # parameters beside them a producer reading a card that placed
            # third on one signal and first on three others cannot tell
            # whether the order it sees was fused or merely sorted.
            "fusion": {
                "method": "reciprocal rank fusion (Cormack et al., SIGIR 2009)",
                "k": engine.RRF_K,
                "band": engine.FUSION_BAND,
                "lists": [f["name"] for f in (ranked[0]["factors"] if ranked else ())]
                         + [engine.FIT_LIST],
                "rule": ("Fusion resolves NEAR-TIES only: it may reorder two "
                         "cards whose fits differ by at most the band, and "
                         "never a card the arithmetic separates. Each row's "
                         "fusion_note says whether it moved and by how much."),
            },
            "rule": ("Readiness MULTIPLIES. A platform whose prerequisites are "
                     "red cannot reach the hot band. Read these numbers into "
                     "the payload; explaining them is the producer's job, "
                     "recomputing them is not. The ORDER is fit then fusion "
                     "then dependency sequencing — all three are on the row."),
        },
    }
