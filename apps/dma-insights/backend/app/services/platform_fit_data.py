"""DB assembly for the platform fit engine v2 (Part 7.1).

Framework-free (no fastapi) so the persist path, the derive-chain
recompute script (`app.scripts.recompute_platform_fit`) and the API
router can all share one context loader + one compute + one persister —
the audit found the router and the ingest persister disagreeing on the
target band precisely because they each rebuilt the inputs.

Responsibilities:
  - `load_fit_context()`   — one round of queries per run: subcap scores
    joined to catalogue names/categories, insight severities, per-subcap
    evidence (E-IDs + tier + freshness → evidence_strength), value-chain
    stages, confirmed-absent platform families from tech_stack_entries,
    prereq checks, and rec-dependency platform edges.
  - `compute_v2_rows()`    — pure engine call + sequence ranks.
  - `persist_v2_rows()`    — UPSERT into platform_scores (fit_score,
    readiness_index, state, fit_breakdown, sequence_rank).

Absent-family detection mirrors the frontend SCORED_PLATFORM_FAMILIES
regexes (TechStackPage/InsightsPage) so the D4 tile badge and the tech
stack gap rows count the same families — but runs server-side against
`tech_stack_entries` (the audit: the notion existed only client-side).
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text

from app.services.kg_reasoning import build_kg_reasoning
from app.services.platform_affinity import (
    incumbent_covered_subcaps,
    load_catalogue_affinity,
    load_incumbent_subcap_coverage,
    load_l3_affinity,
    top_l3_for_gaps,
)
from app.services.platform_display import PLATFORM_DISPLAY, platform_capability
from app.services.platform_fit import (
    PlatformFitV2Row,
    SubcapForFit,
    compute_platform_fit_v2,
    compute_sequence_ranks,
    evidence_strength,
    stack_alignment,
)
from app.services.platform_prerequisites import prerequisites_for
from app.services.readiness_index import (
    PrereqCheck,
    aggregate_readiness,
    evaluate_prereq,
    failing_prereq_subcaps,
)
from app.services.use_case_stories import load_playbooks

# Semantic platform↔sub-capability fit floor — the same support bar the rest of
# the derive path holds a citation to. A pair at/above this is "addressable by
# NLP" even if the catalogue carried no keyword tag for it.
_SEM_FIT_FLOOR = 0.30
# (platform_id, subcap_name) → fused cross-encoder support. The pairing is
# catalogue-stable (a subcap's NAME doesn't change across runs), so memoizing
# turns 94 runs x 5 platforms x ~130 subcaps into ~650 unique CE evaluations.
_SEM_FIT_CACHE: dict[tuple[str, str], float] = {}


def build_semantic_fit_by_platform(
    subcaps: list, platform_ids: list[str], *, floor: float = _SEM_FIT_FLOOR,
) -> dict[str, dict[str, float]]:
    """Per-platform ``{subcap_id: fused_support}`` — how strongly each platform's
    capability descriptor SUPPORTS each scored sub-capability, via the bi-encoder
    recall + cross-encoder precision tier (the same scorer heatmap grounding +
    citations use). Returns an EMPTY dict when the NLP tier is cold, so the fit
    engine then behaves exactly as the keyword-only path (zero regression).
    Never raises."""
    named = [(sc.subcap_id, (sc.name or "").strip())
             for sc in subcaps if (getattr(sc, "name", None) or "").strip()]
    if not named:
        return {}
    try:
        from app.services.nlp import rerank
        from app.services.nlp.semantic import SemanticIndex, model_available
        if not model_available():
            return {}
        idx = SemanticIndex()
        out: dict[str, dict[str, float]] = {}
        for pid in platform_ids:
            cap = platform_capability(pid)
            if not cap:
                continue
            uncached = [(sid, nm) for sid, nm in named
                        if (pid, nm) not in _SEM_FIT_CACHE]
            if uncached:
                sups = rerank.support_scores(
                    cap, [(nm, idx.relevance(cap, nm)) for _sid, nm in uncached])
                for j, (_sid, nm) in enumerate(uncached):
                    _SEM_FIT_CACHE[(pid, nm)] = float(sups[j])
            out[pid] = {sid: _SEM_FIT_CACHE[(pid, nm)] for sid, nm in named
                        if _SEM_FIT_CACHE.get((pid, nm), 0.0) >= floor}
        return out
    except Exception:
        return {}


# Server-side twin of the frontend SCORED_PLATFORM_FAMILIES — keep the
# two in lockstep (frontend/src/pages/TechStackPage.tsx:96).
PLATFORM_FAMILY_PATTERNS: dict[str, re.Pattern[str]] = {
    "salesforce": re.compile(
        r"salesforce|mulesoft|tableau crm|marketing cloud|data cloud", re.I),
    "databricks": re.compile(r"databricks", re.I),
    "tableau": re.compile(r"tableau", re.I),
    "twilio": re.compile(r"twilio|segment", re.I),
    "ncino": re.compile(r"ncino", re.I),
}

# Family products used for the tile's "N absent" badge: how many of the
# family's scored products are missing from the detected stack. Mirrors
# the prototype tile (which showed a per-family absent product count).
FAMILY_PRODUCTS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "salesforce": [
        ("Financial Services Cloud", re.compile(r"financial services cloud|fsc\b", re.I)),
        ("Data Cloud", re.compile(r"data cloud", re.I)),
        ("Marketing Cloud", re.compile(r"marketing cloud", re.I)),
        ("Agentforce", re.compile(r"agentforce", re.I)),
        ("MuleSoft", re.compile(r"mulesoft", re.I)),
    ],
    "databricks": [
        ("Databricks Lakehouse", re.compile(r"databricks|lakehouse", re.I)),
        ("Mosaic AI", re.compile(r"mosaic", re.I)),
    ],
    "tableau": [
        ("Tableau", re.compile(r"tableau", re.I)),
        ("Tableau Pulse", re.compile(r"pulse", re.I)),
    ],
    "twilio": [
        ("Twilio", re.compile(r"twilio", re.I)),
        ("Segment", re.compile(r"segment", re.I)),
    ],
    "ncino": [
        ("nCino", re.compile(r"ncino", re.I)),
    ],
}

# Map the SPECIFIC Zennify product's vendor_family (services.platform_products)
# onto the coarse platform_scores card family. MuleSoft is a Salesforce-platform
# product; Snowflake groups with the databricks (data-platform) card. Advisory
# workshops map to no platform family.
_PRODUCT_FAMILY_TO_PLATFORM: dict[str, str] = {
    "salesforce": "salesforce", "mulesoft": "salesforce",
    "tableau": "tableau", "ncino": "ncino", "twilio": "twilio",
    "databricks": "databricks", "snowflake": "databricks",
}

# Catalogue ccg_l4_features.vendor → card family, for the L3/L4-coverage factor.
_VENDOR_TO_PLATFORM: dict[str, str] = {
    "salesforce": "salesforce", "mulesoft": "salesforce", "slack": "salesforce",
    "tableau": "tableau", "ncino": "ncino", "twilio": "twilio",
    "segment": "twilio", "databricks": "databricks", "snowflake": "databricks",
}


def _build_rec_signal(rec_rows: list) -> dict:
    """Aggregate a run's analyst recommendations into a per-platform-family
    RecSignal — the input to the recommendation-driven fit. Groups each rec by
    its extracted product's family, keeps the most-urgent (lowest priority_rank)
    rec as the family's lead, and unions the deficient subcaps / evidence /
    integration effort. A rec that maps to no family is skipped (residual)."""
    import re as _re

    from app.services import platform_products as _pp
    from app.services.platform_fit import RecSignal

    by_family: dict[str, RecSignal] = {}
    for idx, r in enumerate(rec_rows):
        product = getattr(r, "zennify_product", None)
        fam = (_PRODUCT_FAMILY_TO_PLATFORM.get(_pp.vendor_family(product) or "")
               if product else None)
        if not fam:
            fam = getattr(r, "platform_id", None)
            fam = fam if fam in PLATFORM_FAMILY_PATTERNS else None
        if not fam:
            continue
        prio = getattr(r, "priority_rank", None)
        if prio is not None:
            prio = int(prio)
        else:
            # No numeric analyst rank (the lettered-schema recs ship none). Recs
            # are listed most-urgent-first, so the 1-based list position is the
            # priority proxy — REC-NN ordinal when present, else enumeration
            # order (query is ORDER BY rec_id). Without this the composite's
            # priority factor collapses to worst-case and a recommended family
            # can fall below an unrecommended family's residual fit.
            _m = _re.search(r"(\d+)", str(getattr(r, "rec_id", "") or ""))
            prio = min(int(_m.group(1)) if _m else (idx + 1), 9)
        sig = by_family.get(fam)
        if sig is None:
            sig = RecSignal(recommended=True, best_priority=9, effort_band="LOW")
            by_family[fam] = sig
        sig.rec_count += 1
        sig.so_count += len(getattr(r, "strategic_objectives", None) or [])
        sig.evidence_count += len(getattr(r, "root_cause_e_ids", None) or [])
        eff = getattr(r, "effort_band", None) or "LOW"
        _order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        if _order.get(eff, 0) > _order.get(sig.effort_band, 0):
            sig.effort_band = eff
        subs = list(getattr(r, "target_subcap_ids", None) or [])
        sig.deficient_subcaps = tuple(dict.fromkeys(
            list(sig.deficient_subcaps) + subs))
        if prio < sig.best_priority:
            sig.best_priority = prio
            if product:
                sig.lead_product_id = product
                sig.lead_product = _pp.display_name(product)
            sig.lead_rec_title = getattr(r, "title", None)
    return by_family


async def load_fit_context(
    session: Any,
    *,
    run_id: Any,
    entity_id: Any,
    catalogue_version: str,
) -> dict:
    """All fit-engine inputs for one run. Returns a plain dict so tests
    can build it by hand."""
    sc_rows = (
        await session.execute(
            text(
                """
                SELECT s.subcap_id, s.score, s.peer_median, s.platform_tags,
                       cs.name,
                       cl.category_id
                FROM subcap_scores s
                LEFT JOIN ccg_subcaps cs
                  ON cs.version = :ver AND cs.subcap_id = s.subcap_id
                LEFT JOIN ccg_l1_capabilities cl
                  ON cl.version = :ver AND cl.l1_id = cs.l1_id
                WHERE s.run_id = :rid
                """
            ),
            {"ver": catalogue_version, "rid": run_id},
        )
    ).all()

    ic_rows = (
        await session.execute(
            text(
                """
                SELECT severity, linked_subcap_id AS sid
                FROM insight_cards
                WHERE run_id = :rid AND linked_subcap_id IS NOT NULL
                """
            ),
            {"rid": run_id},
        )
    ).all()
    sev_by_subcap: dict[str, list[str]] = {}
    for r in ic_rows:
        sev_by_subcap.setdefault(r.sid, []).append((r.severity or "medium").lower())

    ev_rows = (
        await session.execute(
            text(
                """
                SELECT e.e_id, e.tier, e.freshness_band, sid.sid
                FROM evidence_index e,
                     LATERAL unnest(e.linked_subcap_ids) AS sid(sid)
                WHERE e.run_id = :rid
                ORDER BY e.tier ASC, e.e_id ASC
                """
            ),
            {"rid": run_id},
        )
    ).all()
    ev_by_subcap: dict[str, list[tuple[str, int | None, str]]] = {}
    ev_by_category: dict[str, list[tuple[str, int | None, str]]] = {}
    for r in ev_rows:
        # tier None = source stated no canonical tier (migration 059).
        item = (r.e_id, int(r.tier) if r.tier is not None else None,
                r.freshness_band or "undated")
        ev_by_subcap.setdefault(r.sid, []).append(item)
        cat = _category_prefix(r.sid)
        if cat:
            bucket = ev_by_category.setdefault(cat, [])
            if len(bucket) < 24:
                bucket.append(item)

    # Run-level rung of the evidence ladder (plan 7.1 "card evidence_ids
    # zero for 18 clients x5"): those entities ship evidence rows with
    # ZERO subcap links at any grain. Their best-tier evidence still
    # grounds the entity — attach it at a 0.5 discount so cards carry
    # real E-IDs; near-evidence-less entities stay below EVIDENCE_FLOOR
    # (honest INSUFFICIENT_EVIDENCE).
    run_level_ev: list[tuple[str, int | None, str]] = []
    if not ev_by_subcap:
        top_rows = (
            await session.execute(
                text(
                    """
                    SELECT e_id, tier, freshness_band
                    FROM evidence_index
                    WHERE run_id = :rid
                    ORDER BY tier ASC, e_id ASC
                    LIMIT 24
                    """
                ),
                {"rid": run_id},
            )
        ).all()
        run_level_ev = [
            (r.e_id, int(r.tier) if r.tier is not None else None,
             r.freshness_band or "undated")
            for r in top_rows
        ]

    # Value-chain stages (populated once the D3 loader fix lands; empty
    # today — the interconnect factor then rides category adjacency only).
    vc_rows = (
        await session.execute(
            text(
                """
                SELECT subcap_id, value_chain_stages
                FROM ccg_vc_mapping WHERE version = :ver
                """
            ),
            {"ver": catalogue_version},
        )
    ).all()
    stages_by_subcap: dict[str, list[str]] = {}
    for r in vc_rows:
        stages_by_subcap.setdefault(r.subcap_id, []).extend(
            list(r.value_chain_stages or [])
        )

    tech_rows = (
        await session.execute(
            text(
                """
                SELECT vendor, product FROM tech_stack_entries
                WHERE entity_id = :eid
                """
            ),
            {"eid": entity_id},
        )
    ).all()
    stack_hay = " ".join(
        f"{r.vendor or ''} {r.product or ''}" for r in tech_rows
    ).lower()

    absent_families: dict[str, list[str]] = {}
    absent_counts: dict[str, int] = {}
    for pid, rx in PLATFORM_FAMILY_PATTERNS.items():
        family_absent = not rx.search(stack_hay)
        absent_products = [
            name for name, prx in FAMILY_PRODUCTS.get(pid, [])
            if not prx.search(stack_hay)
        ]
        absent_families[pid] = (
            [PLATFORM_DISPLAY.get(pid, {}).get("name", pid)] if family_absent else []
        )
        absent_counts[pid] = len(absent_products)

    # ── Reasoned stack/scale signals (2026-07-06 mandate) ──────────────
    # Evidence excerpts that NAME a platform family are first-class fit
    # inputs: an "in use" mention corrects a tech-stack table that missed
    # the product (E-ID-cited); firmographic scale bounds the greenfield
    # read on heavy platforms. Pure classification in platform_signals.
    from app.services.platform_signals import (
        absent_boost_adjustment,
        classify_stack_mentions,
        evidence_confirms_in_use,
        scale_context,
    )

    mention_rows = (
        await session.execute(
            text(
                """
                SELECT e_id, excerpt FROM evidence_index
                WHERE run_id = :rid
                  AND excerpt ~* :family_rx
                ORDER BY tier ASC NULLS LAST, e_id ASC
                LIMIT 80
                """
            ),
            {
                "rid": run_id,
                "family_rx": (
                    r"salesforce|mulesoft|marketing cloud|data cloud|"
                    r"tableau|databricks|twilio|segment|ncino|agentforce|"
                    r"financial services cloud"
                ),
            },
        )
    ).all()
    stack_signals = classify_stack_mentions(
        [(r.e_id, r.excerpt or "") for r in mention_rows],
        family_patterns=PLATFORM_FAMILY_PATTERNS,
        family_products=FAMILY_PRODUCTS,
    )

    firm_row = (
        await session.execute(
            text(
                """
                SELECT aum_usd, headcount FROM firmographics
                WHERE entity_id = :eid
                """
            ),
            {"eid": entity_id},
        )
    ).first()
    scale = scale_context(
        float(firm_row.aum_usd) if firm_row and firm_row.aum_usd is not None else None,
        int(firm_row.headcount) if firm_row and firm_row.headcount is not None else None,
    )

    # ── Cohort adoption + category incumbents + vertical scope ─────────
    # (2026-07-14 skew audit) Three inputs the boost ladder was blind to:
    # the entity's subvertical, the cohort's per-family deployment share
    # (the SAME family_share behind the techstack "N% of cohort peers
    # deploy it" notes), and third-party incumbents occupying the family's
    # functional category (Snowflake ⇒ the databricks argument is
    # integration, not greenfield).
    from app.services.platform_incumbents import (
        detect_category_incumbents,
        stack_lens,
        vertical_relevance,
    )
    from app.services.techstack_read import load_cohort_coverage

    sv_row = (
        await session.execute(
            text("SELECT subvertical FROM entities WHERE id = :eid"),
            {"eid": entity_id},
        )
    ).first()
    subvertical = sv_row.subvertical if sv_row else None
    cov = await load_cohort_coverage(session, subvertical=subvertical)
    incumbents = detect_category_incumbents(stack_hay)

    absent_boosts: dict[str, float] = {}
    absent_reasons: dict[str, tuple[str | None, list[str]]] = {}
    lens_by_platform: dict[str, dict] = {}
    relevance_by_platform: dict[str, tuple[float, str | None]] = {}
    for pid in PLATFORM_FAMILY_PATTERNS:
        family_absent = bool(absent_families.get(pid))
        graded = stack_alignment(
            absent_family=family_absent,
            absent_count=int(absent_counts.get(pid) or 0),
            peer_coverage=cov.family_share.get(pid),
        )
        boost, reason, cites = absent_boost_adjustment(
            platform_id=pid,
            base_absent=family_absent,
            signals=stack_signals.get(pid, []),
            scale=scale,
            category_incumbents=incumbents.get(pid) or [],
            graded_base=graded if family_absent else None,
        )
        absent_boosts[pid] = boost
        absent_reasons[pid] = (reason, cites)
        lens_by_platform[pid] = {
            "lens": stack_lens(
                family_absent=family_absent,
                incumbents=incumbents.get(pid) or [],
                evidence_in_use=evidence_confirms_in_use(
                    stack_signals.get(pid, [])),
            ),
            "incumbents": incumbents.get(pid) or [],
            "peer_coverage": cov.family_share.get(pid),
        }
        relevance_by_platform[pid] = vertical_relevance(pid, subvertical)

    ps_rows = (
        await session.execute(
            text(
                """
                SELECT platform_id, prerequisite_checks
                FROM platform_scores WHERE run_id = :rid
                """
            ),
            {"rid": run_id},
        )
    ).all()
    prereq_specs_by_platform: dict[str, list[dict]] = {}
    for r in ps_rows:
        specs = r.prerequisite_checks or []
        if isinstance(specs, list) and specs:
            prereq_specs_by_platform[r.platform_id] = specs

    # Rec dependency edges at platform grain: rec on platform B lists a
    # rec on platform A as prerequisite ⇒ (A, B).
    rec_rows = (
        await session.execute(
            text(
                """
                SELECT rec_id, platform_id, prerequisite_rec_ids, title, phase,
                       zennify_product, priority_rank, strategic_objectives,
                       effort_band, root_cause_e_ids, target_subcap_ids
                FROM recommendations WHERE run_id = :rid
                ORDER BY rec_id
                """
            ),
            {"rid": run_id},
        )
    ).all()
    platform_by_rec = {r.rec_id: r.platform_id for r in rec_rows}
    rec_platform_edges: list[tuple[str, str]] = []
    for r in rec_rows:
        for prereq in r.prerequisite_rec_ids or []:
            a = platform_by_rec.get(prereq)
            b = r.platform_id
            if a and b and a != b:
                rec_platform_edges.append((a, b))
    rec_signal_by_platform = _build_rec_signal(rec_rows)

    # L3/L4 → subcap coverage per platform family (the L3/L4-alignment factor
    # for the recommendation-driven fit). Empty when the catalogue isn't loaded
    # (offline) → the fit uses a neutral prior.
    l4_rows = (
        await session.execute(
            text(
                """
                SELECT vendor, subcap_id FROM ccg_l4_features
                WHERE version = :ver AND subcap_id IS NOT NULL
                """
            ),
            {"ver": catalogue_version},
        )
    ).all()
    l4_subcaps_by_platform: dict[str, set[str]] = {}
    for lr in l4_rows:
        fam = _VENDOR_TO_PLATFORM.get((lr.vendor or "").strip().lower())
        if fam:
            l4_subcaps_by_platform.setdefault(fam, set()).add(lr.subcap_id)
    # Backing recs per family (2026-07-14 W4 reconciliation): the analyst
    # report's own recommendations that the derive chain inferred onto this
    # platform family. Cards cross-link to them; a hot card with no backing
    # rec is flagged "engine-derived". Keyed by the inferred platform_id.
    backing_recs_by_platform: dict[str, list[dict]] = {}
    for r in rec_rows:
        if not r.platform_id or not r.title:
            continue
        backing_recs_by_platform.setdefault(r.platform_id, []).append({
            "rec_id": r.rec_id,
            "title": str(r.title),
            "phase": r.phase,
        })

    subcaps: list[SubcapForFit] = []
    for r in sc_rows:
        cat = r.category_id or _category_prefix(r.subcap_id)
        # Evidence ladder (plan 6.3/7.1): direct subcap links first, else
        # the category roll-up at a 0.75 discount — the E-IDs are still
        # the entity's real evidence, just one grain coarser. Kills the
        # audit's "card evidence_ids zero" class without fabricating.
        ev = ev_by_subcap.get(r.subcap_id, [])
        es: float | None
        if ev:
            es = evidence_strength(
                [t for _, t, _ in ev], [f for _, _, f in ev],
            )
        else:
            cat_ev = ev_by_category.get(cat or "", [])
            if cat_ev:
                ev = cat_ev
                es = round(0.75 * evidence_strength(
                    [t for _, t, _ in cat_ev], [f for _, _, f in cat_ev],
                ), 4)
            elif run_level_ev:
                ev = run_level_ev
                es = round(0.5 * evidence_strength(
                    [t for _, t, _ in run_level_ev],
                    [f for _, _, f in run_level_ev],
                ), 4)
            else:
                es = None
        subcaps.append(SubcapForFit(
            subcap_id=r.subcap_id,
            current_score=float(r.score) if r.score is not None else 0.0,
            platform_ids=list(r.platform_tags or []),
            linked_insight_severities=sev_by_subcap.get(r.subcap_id, []),
            name=r.name,
            peer_median=float(r.peer_median) if r.peer_median is not None else None,
            category_id=cat,
            vc_stages=stages_by_subcap.get(r.subcap_id, []),
            evidence_e_ids=list(dict.fromkeys(e for e, _, _ in ev[:6])),
            evidence_strength=es,
            evidence_tier=min((t for _, t, _ in ev if t is not None),
                              default=None),
        ))

    # ── Knowledge-graph reasoning (2026-07-15): validated deficiency -> L4
    # feature -> user-story -> platform grounding (app.services.kg_reasoning).
    # ADDITIVE — it feeds the composers' "why" + a validation signal; it does
    # NOT alter the fit ranking, so the analyst-recommendation-driven order
    # (and its no-salesforce-skew property) is untouched. HIGH-tier anti-pattern
    # subcaps are dropped inside the fold; MEDIUM-tier flagged. Loaded here so
    # the affinity (memoized) is reused by the return below.
    _affinity = await load_catalogue_affinity(session, catalogue_version)
    _playbooks = await load_playbooks(session, catalogue_version)
    _kg_defs: dict[str, float] = {}
    _kg_names: dict[str, str] = {}
    for r in sc_rows:
        if not r.subcap_id or r.score is None:
            continue
        _kg_names[r.subcap_id] = r.name or r.subcap_id
        _gap = max(0.0, min(1.0, (4.0 - float(r.score)) / 4.0))  # gap vs target band 4.0
        if _gap > 0.05:
            _kg_defs[r.subcap_id] = _gap
    _pf_by_subcap: dict[str, dict[str, list]] = {}
    for _plat, _subs in _affinity.items():
        for _sid, _d in _subs.items():
            _feats = _d.get("features") if isinstance(_d, dict) else None
            if _feats:
                _pf_by_subcap.setdefault(_sid, {})[_plat] = list(_feats)
    kg_reasoning_by_platform = build_kg_reasoning(
        _kg_defs, _kg_names, _playbooks, _pf_by_subcap)

    return {
        "subcaps": subcaps,
        "scores_by_subcap": {
            r.subcap_id: float(r.score or 0.0) for r in sc_rows
        },
        # KG grounding per platform (KgReasoning objects; additive — composers
        # cite the validated features/stories, apply_recommendation_fit reads it
        # as a confidence/validation signal). Never reorders the fit.
        "kg_reasoning_by_platform": kg_reasoning_by_platform,
        "absent_families": absent_families,
        "absent_counts": absent_counts,
        "prereq_specs_by_platform": prereq_specs_by_platform,
        "rec_platform_edges": rec_platform_edges,
        "rec_signal_by_platform": rec_signal_by_platform,
        "l4_subcaps_by_platform": l4_subcaps_by_platform,
        "backing_recs_by_platform": backing_recs_by_platform,
        # Reasoned signals (2026-07-06): evidence-text stack mentions,
        # firmographic scale, and the adjusted greenfield boosts + the
        # auditable (reason, E-IDs) behind each.
        "stack_signals": {
            pid: [s.to_dict() for s in sigs]
            for pid, sigs in stack_signals.items()
        },
        "scale": scale,
        "absent_boosts": absent_boosts,
        "absent_reasons": absent_reasons,
        # 2026-07-14 skew-audit inputs: entity subvertical, cohort family
        # adoption shares (peer coverage), the per-family argument lens
        # (greenfield | integrate | expand + named category incumbents),
        # and the vertical-relevance multiplier per family.
        "subvertical": subvertical,
        "family_peer_coverage": dict(cov.family_share),
        "cohort": {"size": cov.cohort_size, "label": cov.cohort_label},
        "stack_lens": lens_by_platform,
        "vertical_relevance": relevance_by_platform,
        # NLP platform↔subcap fit: {platform_id: {subcap_id: support}} (empty
        # when the tier is cold → keyword-only fit, zero regression).
        "semantic_fit_by_platform": build_semantic_fit_by_platform(
            subcaps, list(PLATFORM_DISPLAY.keys())),
        # v7 L4-layer catalogue affinity (curated subcap→platform feature
        # links; empty when the layer isn't loaded → prior behaviour).
        "catalogue_fit_by_platform": _affinity,
        # Per-family per-L3 aggregates (sub-product grain) → the card resolves
        # WHICH Zennify L3/vehicle (Data Cloud, MuleSoft Anypoint, Unity
        # Catalog) best covers the ENTITY'S actual gaps, instead of a bare
        # family label (2026-07-14 solutioning audit).
        "l3_affinity_by_family": await load_l3_affinity(
            session, catalogue_version),
        # Per-family set of gapped subcaps the customer's INSTALLED incumbent
        # already covers (v7 L4) → the engine discounts the challenger's
        # marginal opportunity there. Resolved from the detected category
        # incumbents; empty when none detected or L4 cold.
        "incumbent_covered_by_platform": {
            pid: incumbent_covered_subcaps(
                (lens_by_platform.get(pid, {}) or {}).get("incumbents") or [],
                await load_incumbent_subcap_coverage(session, catalogue_version),
            )
            for pid in PLATFORM_FAMILY_PATTERNS
        },
    }


def _category_prefix(subcap_id: str) -> str | None:
    m = re.match(r"^(P[1-4]C\d+)", subcap_id or "")
    return m.group(1) if m else None


def evaluate_platform_prereqs(
    platform_id: str,
    scores_by_subcap: dict[str, float],
    prereq_specs_by_platform: dict[str, list[dict]] | None = None,
) -> list[PrereqCheck]:
    """Evaluate the platform's prereq spec (persisted spec first, module
    defaults otherwise) against the run's scores."""
    specs = (
        (prereq_specs_by_platform or {}).get(platform_id)
        or prerequisites_for(platform_id)
    )
    return [
        evaluate_prereq(
            name=str(p.get("name", "unnamed")),
            required_subcap_id=str(p["required_subcap_id"]),
            threshold=float(p["threshold"]),
            scores_by_subcap=scores_by_subcap,
        )
        for p in specs
        if isinstance(p, dict) and "required_subcap_id" in p and "threshold" in p
    ]


def compute_v2_rows(ctx: dict) -> tuple[list[PlatformFitV2Row], dict[str, list[PrereqCheck]]]:
    """Pure step: prereqs → readiness → engine v2 → sequence ranks."""
    platform_ids = list(PLATFORM_DISPLAY.keys())
    scores_by_subcap: dict[str, float] = ctx["scores_by_subcap"]

    checks_by_platform: dict[str, list[PrereqCheck]] = {}
    readiness_by_platform: dict[str, str] = {}
    unmet_by_platform: dict[str, list[str]] = {}
    for pid in platform_ids:
        checks = evaluate_platform_prereqs(
            pid, scores_by_subcap, ctx.get("prereq_specs_by_platform"),
        )
        checks_by_platform[pid] = checks
        readiness_by_platform[pid] = aggregate_readiness(checks)
        unmet_by_platform[pid] = failing_prereq_subcaps(checks)

    # Graded current-stack factor (platform v3): refine the binary
    # absent_boost with the breadth of absent family products + peer prior.
    absent_families = ctx.get("absent_families") or {}
    absent_counts = ctx.get("absent_counts") or {}
    peer_cov = ctx.get("family_peer_coverage") or {}
    l3_affinity = ctx.get("l3_affinity_by_family") or {}
    backing_recs = ctx.get("backing_recs_by_platform") or {}
    stack_alignment_by_platform = {
        pid: stack_alignment(
            absent_family=bool(absent_families.get(pid)),
            absent_count=int(absent_counts.get(pid) or 0),
            peer_coverage=peer_cov.get(pid),
        )
        for pid in platform_ids
    }

    rows = compute_platform_fit_v2(
        ctx["subcaps"],
        platform_ids,
        readiness_by_platform=readiness_by_platform,
        absent_families_by_platform=absent_families,
        absent_count_by_platform=absent_counts,
        stack_alignment_by_platform=stack_alignment_by_platform,
        semantic_fit_by_platform=ctx.get("semantic_fit_by_platform"),
        absent_boost_by_platform=ctx.get("absent_boosts"),
        absent_reason_by_platform=ctx.get("absent_reasons") or {},
        stack_signals_by_platform=ctx.get("stack_signals") or {},
        scale=ctx.get("scale"),
        catalogue_fit_by_platform=ctx.get("catalogue_fit_by_platform"),
        vertical_relevance_by_platform=ctx.get("vertical_relevance") or {},
        stack_lens_by_platform=ctx.get("stack_lens") or {},
        incumbent_covered_by_platform=ctx.get("incumbent_covered_by_platform") or {},
    )

    # Recommendation-driven override (2026-07-15): rewrite fit as a READ of the
    # analyst's recommendations — the recommended product the analyst
    # prioritised leads; families the assessment never recommended keep only a
    # residual so they can't top the sequence. l4_subcaps_by_platform is the
    # catalogue L3/L4→subcap coverage (empty offline → neutral prior).
    from app.services.platform_fit import apply_recommendation_fit
    rows = apply_recommendation_fit(
        rows,
        ctx.get("rec_signal_by_platform"),
        ctx["subcaps"],
        l4_subcaps_by_platform=ctx.get("l4_subcaps_by_platform"),
    )

    relevance_values = {
        pid: float(pair[0])
        for pid, pair in (ctx.get("vertical_relevance") or {}).items()
    }
    # Analyst's most-urgent recommended family leads the sequence.
    rec_sig = ctx.get("rec_signal_by_platform") or {}
    rec_priority_by_platform = {
        pid: sig.best_priority for pid, sig in rec_sig.items()
        if getattr(sig, "recommended", False)
    }
    ranks = compute_sequence_ranks(
        platform_ids=platform_ids,
        unmet_prereq_subcaps=unmet_by_platform,
        addressable_by_platform={r.platform_id: r.addressable_subcap_ids for r in rows},
        rec_platform_edges=ctx.get("rec_platform_edges") or [],
        readiness_by_platform=readiness_by_platform,
        fit_by_platform={r.platform_id: r.fit_score for r in rows},
        relevance_by_platform=relevance_values,
        rec_priority_by_platform=rec_priority_by_platform,
    )
    ranked_after: dict[str, list[str]] = {pid: [] for pid in platform_ids}
    for pid in platform_ids:
        ranked_after[pid] = [
            p for p in platform_ids
            if p != pid and ranks.get(p, 99) < ranks.get(pid, 99)
        ]
    for r in rows:
        r.sequence_rank = ranks.get(r.platform_id)
        r.breakdown["sequence"] = {
            "rank": r.sequence_rank,
            "after": ranked_after.get(r.platform_id, []),
        }
        # Prereq drilldown payload for the D4 accordion (backing subcaps
        # resolve at read time; the spec snapshot keeps the drawer honest).
        r.breakdown["prereqs"] = {
            c.required_subcap_id: {
                "name": c.name,
                "threshold": c.threshold,
                "status": c.status,
                "current_score": c.current_score,
            }
            for c in checks_by_platform.get(r.platform_id, [])
        }
        # Name the concrete failing prereqs inside the readiness step of
        # the reasoning record — "readiness red" alone isn't auditable.
        failing = [
            c for c in checks_by_platform.get(r.platform_id, [])
            if c.status in ("UNMET", "PARTIAL", "MISSING")
        ]
        if failing:
            for step in r.breakdown.get("reasoning", []):
                if step.get("factor") == "readiness":
                    step["subcap_ids"] = [c.required_subcap_id for c in failing][:4]
                    step["detail"] += " — failing: " + "; ".join(
                        f"{c.name} ({c.required_subcap_id}) "
                        + (f"{c.current_score:.1f}" if c.current_score is not None
                           else "unscored")
                        + f" vs {c.threshold:.1f} ({c.status})"
                        for c in failing[:3]
                    )
                    break
        # 2026-07-14 solutioning: name the concrete Zennify L3 platform(s)
        # / integration vehicle that cover THIS card's top gap drivers, so
        # the play cites "Salesforce Data Cloud + MuleSoft Anypoint" rather
        # than a bare family label. Resolved over the card's own top_subcaps
        # (the gap drivers) against the per-L3 affinity map; empty when the
        # L4 layer isn't loaded (graceful — prior behaviour).
        fam_l3 = (l3_affinity or {}).get(r.platform_id, {})
        gap_ids = [t.get("subcap_id") for t in (r.breakdown.get("top_subcaps") or [])
                   if t.get("subcap_id")]
        vehicles = top_l3_for_gaps(fam_l3, gap_ids, limit=3) if fam_l3 and gap_ids else []
        if vehicles:
            r.breakdown["l3_solution"] = {
                "platforms": vehicles,
                # the best integration-layer L3 (iPaaS/CDP) for the
                # integrate-lens play, when one covers the gaps
                "integration_vehicle": next(
                    (v for v in vehicles if v.get("is_integration")), None),
            }
        # W4 analyst-rec reconciliation (no score change): cross-link the
        # analyst report's own recommendations that landed on this family,
        # and flag a hot card the analyst never recommended as engine-derived.
        backing = backing_recs.get(r.platform_id) or []
        r.breakdown["analyst_backing"] = {
            "backed": bool(backing),
            "recs": backing[:3],
            "note": (
                None if backing else
                "engine-derived from the capability data — not among the "
                "analyst report's explicit recommendations"
            ),
        }
    return rows, checks_by_platform


async def persist_v2_rows(
    session: Any,
    *,
    run_id: Any,
    entity_id: Any,
    rows: list[PlatformFitV2Row],
) -> int:
    """UPSERT engine-v2 results into platform_scores. Prereq spec snapshots
    (`prerequisite_checks`) are left as persisted by ingest; only the
    v2-owned columns are written."""
    import json as _json

    n = 0
    for r in rows:
        await session.execute(
            text(
                """
                INSERT INTO platform_scores (
                    run_id, entity_id, platform_id, fit_score,
                    readiness_index, prerequisite_checks,
                    addressable_subcap_ids, state,
                    fit_breakdown, sequence_rank, computed_at
                ) VALUES (
                    :rid, :eid, :pid, :fit, :readiness,
                    CAST(:prereqs AS JSONB),
                    CAST(:asids AS VARCHAR[]), :state,
                    CAST(:breakdown AS JSONB), :rank, NOW()
                )
                ON CONFLICT (run_id, platform_id) DO UPDATE SET
                    fit_score = EXCLUDED.fit_score,
                    readiness_index = EXCLUDED.readiness_index,
                    addressable_subcap_ids = EXCLUDED.addressable_subcap_ids,
                    state = EXCLUDED.state,
                    fit_breakdown = EXCLUDED.fit_breakdown,
                    sequence_rank = EXCLUDED.sequence_rank,
                    computed_at = NOW()
                """
            ),
            {
                "rid": run_id,
                "eid": entity_id,
                "pid": r.platform_id,
                "fit": r.fit_score,
                "readiness": r.readiness,
                "prereqs": _json.dumps(
                    prerequisites_for(r.platform_id)
                ),
                "asids": r.addressable_subcap_ids,
                "state": r.state,
                "breakdown": _json.dumps(r.breakdown),
                "rank": r.sequence_rank,
            },
        )
        n += 1
    return n
