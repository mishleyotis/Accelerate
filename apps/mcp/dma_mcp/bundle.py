"""Read tools (stage 2.3): get_report_bundle, get_capability_catalogue,
get_client_state — all idempotent, all side-effect free.

The bundle is the agent's input. Every score carries its source cell and
all four grain ids; stated pillar/category grains come from the
workbook's own tabs (never recomputed by averaging — cap logic and
weighting are applied when they are struck); capability rollups ARE
computed and say so. Prior runs are returned so a rerun is not
synthesised as though it were a first run.
"""
from __future__ import annotations

import json

from . import ledger


def _rows(cur, sql, args=()):
    cur.execute(sql, args)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _jsonable(v):
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if v.__class__.__name__ in ("Decimal",):
        return float(v)
    if v.__class__.__name__ == "UUID":
        return str(v)
    return v


def get_report_bundle(conn, run_id) -> dict:
    cur = conn.cursor()
    cur.execute(
        """SELECT r.id, r.entity_id, r.request_id, r.run_seq,
                  r.ccg_catalog_version, r.scored_cells, r.catalogue_cells,
                  r.composite, r.completed_at,
                  e.display_id, e.legal_name, e.sub_vertical, e.size_tier
             FROM runs r JOIN entities e ON e.id = r.entity_id
            WHERE r.id = %s""", (run_id,))
    row = cur.fetchone()
    if row is None:
        return {"error": "unknown_run", "run_id": str(run_id)}
    (rid, entity_id, request_id, run_seq, version, scored_cells,
     catalogue_cells, composite, completed_at,
     display_id, legal_name, sub_vertical, size_tier) = row

    scores = _rows(cur, """
        SELECT subcap_id, capability_id, category_id, pillar_id,
               score, enum_label(confidence) AS confidence,
               peer_median, peer_n, enum_label(peer_basis) AS peer_basis,
               proxy_disclosure, delta, linked_evidence_count,
               is_thin_evidence, source_cell
          FROM subcap_scores WHERE run_id = %s ORDER BY subcap_id""", (run_id,))

    cur.execute("SELECT payload FROM run_manifest WHERE run_id = %s", (run_id,))
    payload = (cur.fetchone() or [None])[0] or {}
    grains = payload.get("workbook_grains") or {}

    # Capability rollups ARE computed (grain 3 has no stated row anywhere
    # in the package); the basis is declared so no reader mistakes them
    # for struck figures.
    caps: dict = {}
    for s in scores:
        if s["score"] is not None:
            acc = caps.setdefault(s["capability_id"], [0, 0])
            acc[0] += float(s["score"])
            acc[1] += 1
    capabilities = {cid: {"score": round(total / n, 2), "n": n,
                          "basis": "computed_mean_of_subcaps"}
                    for cid, (total, n) in caps.items()}

    # A STATED GRAIN THAT DOES NOT EXIST IS NOT AN EMPTY ONE.
    #
    # `pillars` and `categories` are deliberately never recomputed: cap logic
    # and weighting are applied when the workbook strikes those rows, and a
    # mean taken here would discard both silently. That design is right, and
    # it left a hole. Measured 2026-08-23: a promoted run whose workbook
    # publishes no pillar tab served `pillars: []`, and the overview rendered
    # "No pillar figure is served on this run" four times over 355 scored
    # cells — a client looking at four blank bars cannot tell an absent
    # workbook tab from a broken page, which is MEM-0060's shape exactly.
    #
    # So the stated rows stay stated, `*_basis` says which case this is, and
    # a computed fallback is offered ALONGSIDE — never in place of them —
    # carrying the same declared basis the capability rollups already carry,
    # plus the warning that makes it safe to read. The producer decides
    # whether to serve it; the payload discloses what it served.
    def _mean_by(key):
        acc: dict = {}
        for s in scores:
            if s["score"] is not None and s.get(key):
                a = acc.setdefault(s[key], [0.0, 0])
                a[0] += float(s["score"])
                a[1] += 1
        return {k: {"score": round(t / n, 2), "n": n,
                    "basis": "computed_mean_of_subcaps",
                    "caution": "cap logic and weighting are NOT applied — "
                               "the workbook applies those when it strikes a "
                               "stated row, and this run states none"}
                for k, (t, n) in acc.items()}

    stated_pillars = grains.get("pillars") or []
    stated_categories = grains.get("categories") or []

    evidence = _rows(cur, """
        SELECT e.e_id, e.source_name, e.source_url, e.source_domain,
               e.excerpt, enum_label(e.tier) AS tier,
               enum_label(e.claim_type) AS claim_type, e.published_date,
               enum_label(e.recency_band) AS recency_band, e.ers,
               e.identity_ok,
               array_agg(DISTINCT l.subcap_id)
                 FILTER (WHERE l.subcap_id IS NOT NULL) AS linked_subcap_ids
          FROM evidence_index e
          LEFT JOIN evidence_subcap_links l
            ON l.e_id = e.e_id AND l.run_id = %s
         WHERE e.entity_id = %s
         GROUP BY e.e_id ORDER BY e.e_id""", (run_id, entity_id))

    report_sections = _rows(cur, """
        SELECT section_kind, pillar_id, heading, body, page
          FROM document_sections WHERE run_id = %s ORDER BY id""", (run_id,))

    recommendations = _rows(cur, """
        SELECT rec_id, payload FROM recommendations_raw
         WHERE run_id = %s ORDER BY rec_id""", (run_id,))

    peer_table = _rows(cur, """
        SELECT peer_name, category_id, subcap_id, pillar_id, score
          FROM peer_scores WHERE run_id = %s
         ORDER BY category_id, peer_name""", (run_id,))

    issues = _rows(cur, "SELECT issue_id, payload FROM issue_register_raw WHERE run_id = %s", (run_id,))
    techstack = _rows(cur, "SELECT item_id, payload FROM techstack_raw WHERE run_id = %s", (run_id,))
    fits = _rows(cur, "SELECT fit_id, payload FROM platform_fits_raw WHERE run_id = %s", (run_id,))
    firmographics = _rows(cur, "SELECT field, payload FROM firmographics_raw WHERE run_id = %s", (run_id,))

    value_chains = _rows(cur, """
        SELECT chain_id, sub_vertical, name, stage_order
          FROM ccg_value_chains WHERE version = %s
         ORDER BY sub_vertical, stage_order""", (version,))

    return _jsonable({
        "run_id": rid, "entity_id": entity_id, "display_id": display_id,
        "entity_name": legal_name, "request_id": request_id,
        "run_seq": run_seq, "ccg_catalog_version": version,
        "sub_vertical": sub_vertical, "size_tier": size_tier,
        "completed_at": completed_at, "scored_cells": scored_cells,
        "catalogue_cells": catalogue_cells, "composite": composite,
        "scores": scores,
        "rollups": {
            "pillars": stated_pillars,
            "categories": stated_categories,
            "capabilities": capabilities,
            # Which case an empty list is. "absent" means the workbook
            # publishes no such tab; "stated" means it does.
            "pillars_basis": "stated" if stated_pillars else "absent",
            "categories_basis": "stated" if stated_categories else "absent",
            # Offered only where nothing is stated, so a reader can never
            # mistake one for the other or quietly prefer the weaker figure.
            "pillars_computed": (_mean_by("pillar_id")
                                 if not stated_pillars else {}),
            "categories_computed": (_mean_by("category_id")
                                    if not stated_categories else {}),
            "note": "pillar and category rows are STATED (workbook tabs, "
                    "with source cells); capabilities are computed and say "
                    "so. Where a run states none, *_basis reads 'absent' and "
                    "*_computed carries a declared-basis mean WITHOUT cap "
                    "logic or weighting — serve it only with that disclosure, "
                    "and never as though the workbook had struck it",
        },
        "evidence": evidence,
        "report_sections": report_sections,
        "issues": issues,
        "recommendations": recommendations,
        "techstack": techstack,
        "firmographics": firmographics,
        "peer_table": peer_table,
        "fits": fits,
        "value_chains": value_chains,
    })


def get_capability_catalogue(conn, run_id) -> dict:
    """Canonical ids and NAMES for the run's pinned version, plus the
    alias bridge into it. Cell names come from here, never from prose."""
    cur = conn.cursor()
    cur.execute("SELECT ccg_catalog_version FROM runs WHERE id = %s", (run_id,))
    row = cur.fetchone()
    if row is None:
        return {"error": "unknown_run", "run_id": str(run_id)}
    version = row[0]

    subcaps = _rows(cur, """
        SELECT subcap_id, capability_id, category_id, pillar_id, name,
               weight, l3_platform_areas, l4_features
          FROM ccg_subcaps WHERE version = %s ORDER BY subcap_id""", (version,))
    aliases = _rows(cur, """
        SELECT from_subcap_id, from_version, to_subcap_id, reason
          FROM ccg_aliases WHERE to_version = %s
         ORDER BY from_subcap_id""", (version,))

    # Category names: the catalogue's own row where the version ships one
    # (v5.0 does), the run's stated grain otherwise (v7.0 ships ids only).
    # Pillar display names are assessment prose — per-run stated grains.
    cur.execute("SELECT payload FROM run_manifest WHERE run_id = %s", (run_id,))
    payload = (cur.fetchone() or [None])[0] or {}
    grains = payload.get("workbook_grains") or {}
    stated_names = {c["category_id"]: c.get("name")
                    for c in (grains.get("categories") or [])}
    cur.execute("""SELECT category_id, pillar_id, name FROM ccg_categories
                    WHERE version = %s ORDER BY category_id""", (version,))
    categories = [{"category_id": cid, "pillar_id": pid,
                   "name": name or stated_names.get(cid)}
                  for cid, pid, name in cur.fetchall()]

    # The L3 platform catalogue. `ccg_subcaps.l3_platform_areas` gives a
    # producer the CODES a cell maps to and this is the only place their
    # names live, so without it the producer writes the code into prose and
    # the page renders it. That is exactly what happened: `[L3-SF-DC-CORE]`
    # and six siblings reached a client's platform surface because no tool
    # in this system could turn one into "Salesforce Data Cloud".
    l3_platforms = _rows(cur, """
        SELECT l3_id, vendor, platform_name, category
          FROM ccg_l3_platforms WHERE version = %s ORDER BY l3_id""",
        (version,))

    return _jsonable({
        "ccg_catalog_version": version,
        "pillars": [{"pillar_id": p["pillar_id"], "name": p.get("name"),
                     "weight": p.get("weight")}
                    for p in (grains.get("pillars") or [])],
        "categories": categories,
        "subcaps": subcaps,
        "aliases": aliases,
        "l3_platforms": l3_platforms,
    })


#: Below this a trigram match is noise. Same threshold `memory.py` uses
#: against the findings corpus, for the same reason: a suggestion nobody
#: would accept is worse than none, because it invites a second wrong guess.
_NEAR_MIN = 0.20
_NEAR_LIMIT = 5


def near_display_ids(cur, display_id: str, limit: int = _NEAR_LIMIT) -> list:
    """Entities whose id or legal name is close to what was asked for.

    WHY A DEAD END WAS EXPENSIVE. Measured 2026-08-30: a session asked for
    `goeasy`, got `unknown_entity`, read that as "this client is not in the
    system yet" and fired the INTAKE routine — the entry point for a client
    with no package. The real display_id is `goeasy-ltd`, and it already had
    four ingested runs. The whole misroute rests on a lookup that knew the
    answer was one character-class away and said nothing.

    `unknown_entity` is still the answer; it is not softened into a match,
    because guessing which client somebody meant is exactly the kind of
    silent inference this system refuses everywhere else. What changes is
    that the refusal now carries the near misses, so the caller can see that
    a client LIKE this one exists before choosing a route on the assumption
    that none does.

    Matched on legal_name as well as display_id: a caller with the client's
    real name and not its slug is the same person making the same mistake.
    """
    cur.execute("""
        SELECT display_id, legal_name,
               GREATEST(similarity(display_id, %s),
                        similarity(COALESCE(legal_name, ''), %s)) AS sim
          FROM entities
         WHERE GREATEST(similarity(display_id, %s),
                        similarity(COALESCE(legal_name, ''), %s)) > %s
         ORDER BY sim DESC, display_id
         LIMIT %s""",
        (display_id, display_id, display_id, display_id, _NEAR_MIN, limit))
    return [{"display_id": r[0], "legal_name": r[1], "similarity": float(r[2])}
            for r in cur.fetchall()]


def get_client_state(conn, display_id: str) -> dict:
    """What is currently served, and prior runs — so a rerun is produced
    knowing what the last run said.

    An unknown id comes back with `did_you_mean`: near misses on display_id
    or legal name, so a dead end cannot be read as "this client is new".
    """
    cur = conn.cursor()
    cur.execute("""SELECT id, legal_name, sub_vertical, size_tier,
                          enum_label(status) FROM entities
                    WHERE display_id = %s""", (display_id,))
    row = cur.fetchone()
    if row is None:
        near = near_display_ids(cur, display_id)
        return {"error": "unknown_entity", "display_id": display_id,
                "did_you_mean": near,
                "hint": ("no entity carries this display_id. "
                         + (f"{len(near)} near match(es) exist — check them "
                            "before treating this client as new, because a "
                            "client that already has a package is SYNTHESIS "
                            "work and not an intake."
                            if near else
                            "Nothing resembles it either, so this client "
                            "genuinely has no package here."))}
    entity_id, legal_name, sub_vertical, size_tier, status = row
    runs = _rows(cur, """
        SELECT id AS run_id, request_id, run_seq, enum_label(status) AS status,
               ccg_catalog_version, composite, scored_cells, completed_at
          FROM runs WHERE entity_id = %s ORDER BY run_seq DESC""", (entity_id,))
    cur.execute("""SELECT s.page, s.promoted_at FROM submissions s
                    WHERE s.run_id IN (SELECT id FROM runs WHERE entity_id = %s)
                      AND s.promoted_at IS NOT NULL
                      AND s.superseded_at IS NULL""", (entity_id,))
    served = [{"page": p, "promoted_at": t.isoformat()} for p, t in cur.fetchall()]
    # The enrichment ledger's answer to "is this client done?". Reported
    # here because this is the call a producer makes to orient itself before
    # touching a client, and a facet that was enriched and never promoted is
    # the single most useful thing it can be told at that moment.
    #
    # Never fatal: a state read that fails must not cost the caller the run
    # history it actually asked for.
    out = {
        "entity_id": entity_id, "display_id": display_id,
        "entity_name": legal_name, "sub_vertical": sub_vertical,
        "size_tier": size_tier, "status": status,
        "runs": runs,
        "served_pages": served,
    }
    try:
        out["enrichment"] = ledger.summary(ledger.drift(cur, entity_id))
    except Exception as e:                # noqa: BLE001 — reported, not silent
        out["enrichment_error"] = str(e)[:200]
    return _jsonable(out)
