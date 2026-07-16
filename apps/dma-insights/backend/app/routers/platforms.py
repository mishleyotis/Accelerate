"""D4 Platforms endpoint — fit engine v2 + readiness + routing + starters.

Part 7.1/7.3 of the remediation plan. The GET /platforms endpoint now:
  - serves the PERSISTED engine-v2 scores (fit_breakdown + sequence_rank
    + honest state, written by `app.scripts.recompute_platform_fit` /
    the derive chain) and falls back to a live v2 computation for runs
    the recompute has not touched — the router and the engine can no
    longer disagree on the target band (M4, unified);
  - populates the prototype fit-tile badges (absent_count from the
    server-side tech-stack family scan, top-2 contributing subcap names);
  - composes conversation starters anchored on the platform's
    HIGHEST-OPPORTUNITY subcap with entity-specific facts (peer names
    from entity_peers, quantified metrics via nlp.quantities over the
    subcap's own evidence excerpts, E-ID citations).

The /platforms/roadmap endpoint replaces effort-band-only bucketing with
sequence-aware phasing (explicit corpus phase → prerequisite DAG level →
effort band) and emits per-phase target ("M2 → M3 in P4C1" computed from
before/after), metric (top extracted outcome metric), platform join,
customer_impact and dependencies — all additive to the legacy shape.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep, ViewModeDep
from app.schemas.platforms import (
    PlatformCard,
    PlatformsResponse,
    PrereqCheckOut,
)
from app.services.audience_strip import strip_and_respond

# Shared presentation twin — the SAME composer the offline pack patcher
# (apply_startup_data_fixes._enrich_platforms) runs, so pack==live on the
# opportunity_md key (qa_pack_parity structural contract).
from app.services.platform_dossier import compose_dossier
from app.services.platform_fit_data import (
    compute_v2_rows,
    load_fit_context,
)
from app.services.platform_routing import (
    GapSubcap,
    OfferingSubcapLink,
    route_offerings_per_pillar,
)
from app.services.platform_story import (
    StarterFacts,
    compose_conversation_starter,
    compose_conversation_starters,
    compose_platform_narrative,
    opportunity_areas_from_breakdown,
)
from app.services.readiness_index import aggregate_readiness, evaluate_prereq
from app.services.section_routing import (
    build_narrative_platform,
    load_sections_for_run,
)
from app.services.startup_enrich import compose_opportunity_md
from app.services.techstack_read import dominant_pillar

router = APIRouter(prefix="/api/v1/entities", tags=["platforms"])

# Static display names + pillar mappings for the 5 documented platforms.
# Defined in app.services.platform_display (framework-free) because the
# WORKER persist path needs it and the workers image has no fastapi
# (2026-06-10 incident). Re-exported here for existing imports.
from app.services.platform_display import PLATFORM_DISPLAY  # noqa: E402

# A card whose top contributing subcaps carry evidence weaker than this
# (tier/recency strength, 0..1) is grounded but THIN — surfaced as
# PENDING_REVIEW rather than a confident READY. Above the engine's
# EVIDENCE_FLOOR (0.10 → INSUFFICIENT_EVIDENCE); the two form the honest
# 3-tier ladder READY / PENDING_REVIEW / INSUFFICIENT_EVIDENCE the audit
# found collapsed to 100% READY.
THIN_EVIDENCE_STRENGTH = 0.30


async def _run_level_e_ids(session: SessionDep, run_id) -> list[str]:
    """The run's best-tier evidence E-IDs — the entity-level rung of the
    card evidence ladder (fallback when a card's own addressable subcaps
    surface none). Empty only for a genuinely evidence-less run."""
    rows = (
        await session.execute(
            text(
                """
                SELECT e_id FROM evidence_index
                WHERE run_id = :rid
                ORDER BY tier ASC, e_id ASC
                LIMIT 8
                """
            ),
            {"rid": run_id},
        )
    ).all()
    return [r.e_id for r in rows]


def _card_evidence_ids(breakdown: dict | None, run_level: list[str]) -> list[str]:
    """Union of the card's addressable-subcap E-IDs (the same evidence
    ladder the fit breakdown surfaces), falling back to the run-level
    evidence so every card on an evidenced entity carries ≥1 citation."""
    out: list[str] = []
    seen: set[str] = set()
    for t in (breakdown or {}).get("top_subcaps") or []:
        for e in t.get("e_ids") or []:
            e = str(e)
            if e and e not in seen:
                seen.add(e)
                out.append(e)
    if not out:
        out = list(run_level)
    return out[:8]


async def _starter_metric_phrases(
    session: SessionDep,
    run_id,
    e_ids: list[str],
) -> list[str]:
    """Quantified, E-ID-cited metric phrases mined from the entity's own
    evidence excerpts (nlp.quantities) — the starters' entity facts."""
    if not e_ids:
        return []
    rows = (
        await session.execute(
            text(
                """
                SELECT e_id, excerpt FROM evidence_index
                WHERE run_id = :rid AND e_id = ANY(:eids)
                ORDER BY tier ASC, e_id ASC
                """
            ),
            {"rid": run_id, "eids": e_ids},
        )
    ).all()
    from app.services.nlp.quantities import extract_metrics
    phrases: list[str] = []
    for r in rows:
        for m in extract_metrics(r.excerpt or "")[:2]:
            label = m.get("metric") or "reported figure"
            raw = m.get("raw") or m.get("value")
            if raw is None:
                continue
            phrases.append(f"{label} {raw} [{r.e_id}]")
        if len(phrases) >= 3:
            break
    return phrases[:3]


async def _entity_techstack_items(session: SessionDep, entity_id) -> list[dict]:
    """The entity's confirmed/inferred current systems in the pack techstack
    shape (product_name / status / dma_pillar / evidence_e_ids), so the
    deterministic dossier can NAME the current organizational capabilities.
    Defensive: a minimal test DB without the table yields []."""
    try:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT vendor, product, status, evidence_e_ids,
                           linked_subcap_ids
                    FROM tech_stack_entries
                    WHERE entity_id = :eid
                      AND status NOT IN ('ENGINEERING_SIGNAL', 'UNKNOWN_VENDOR')
                    """
                ),
                {"eid": entity_id},
            )
        ).all()
    except Exception:
        return []
    items: list[dict] = []
    for r in rows:
        sub_ids = list(r.linked_subcap_ids or [])
        items.append({
            "vendor": r.vendor,
            "product": r.product,
            "product_name": r.product or r.vendor,
            "status": r.status,
            "dma_pillar": dominant_pillar(sub_ids),
            "evidence_e_ids": list(r.evidence_e_ids or []),
            "peer_coverage": None,
            "linked_subcap_ids": sub_ids,
        })
    return items


@router.get("/{display_id}/platforms", response_model=PlatformsResponse)
async def platforms(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    view: ViewModeDep,
    run: str | None = None,
) -> PlatformsResponse:
    # 2026-06-05: honour the ?run=REQ-... selector via resolve_entity_run.
    from app.services.run_resolver import resolve_entity_run
    resolved = await resolve_entity_run(
        session, display_id, run_request_id=run,
    )

    # 1. Fit-engine context (subcap scores + names + evidence strength +
    #    absent families + prereq specs + rec dependency edges) — the same
    #    loader the derive-chain recompute uses, so router and persisted
    #    scores can never diverge on inputs.
    ctx = await load_fit_context(
        session,
        run_id=resolved.id,
        entity_id=resolved.entity_id,
        catalogue_version=resolved.ccg_catalog_version,
    )
    scores_by_subcap: dict[str, float] = ctx["scores_by_subcap"]

    # 2. Catalogue offering→subcap matrix joined to pillar (for the
    #    per-pillar offering router).
    matrix_rows = (
        await session.execute(
            text(
                """
                SELECT m.offering_id, m.subcap_id, cc.pillar_id
                FROM ccg_offering_subcap_matrix m
                JOIN ccg_subcaps cs
                  ON cs.version = m.version AND cs.subcap_id = m.subcap_id
                JOIN ccg_l1_capabilities cl
                  ON cl.version = cs.version AND cl.l1_id = cs.l1_id
                JOIN ccg_categories cc
                  ON cc.version = cl.version AND cc.category_id = cl.category_id
                WHERE m.version = :ver
                """
            ),
            {"ver": resolved.ccg_catalog_version},
        )
    ).all()

    gaps: list[GapSubcap] = []
    for sc in ctx["subcaps"]:
        target = 4.0  # M4 target band — unified with the fit engine
        gap = max(0.0, target - sc.current_score)
        if gap > 0:
            sev = (
                sorted(
                    sc.linked_insight_severities or ["medium"],
                    key=lambda s: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(s, 4),
                )[0]
            )
            pillar = sc.subcap_id[:2] if sc.subcap_id[:2] in ("P1", "P2", "P3", "P4") else None
            if pillar:
                gaps.append(GapSubcap(
                    subcap_id=sc.subcap_id, pillar=pillar,
                    severity=sev, gap_size=gap,
                ))

    catalogue_links = [
        OfferingSubcapLink(
            offering_id=row.offering_id,
            subcap_id=row.subcap_id,
            pillar=row.pillar_id or "P?",
        )
        for row in matrix_rows
    ]
    routing = route_offerings_per_pillar(
        catalogue_links=catalogue_links, entity_gaps=gaps,
    )
    pillar_offerings = {r.pillar: r.offerings for r in routing}

    # 3. Persisted v2 rows (fit_breakdown non-null ⇒ the derive-chain
    #    recompute owns the score); live v2 computation otherwise.
    ps_rows = (
        await session.execute(
            text(
                """
                SELECT platform_id, fit_score, readiness_index, state,
                       prerequisite_checks, addressable_subcap_ids,
                       fit_breakdown, sequence_rank
                FROM platform_scores WHERE run_id = :rid
                """
            ),
            {"rid": resolved.id},
        )
    ).all()
    persisted = {r.platform_id: r for r in ps_rows}
    have_v2 = all(
        persisted.get(pid) is not None
        and isinstance(persisted[pid].fit_breakdown, dict)
        for pid in PLATFORM_DISPLAY
    )

    v2_rows, checks_by_platform = compute_v2_rows(ctx)
    v2_by_pid = {r.platform_id: r for r in v2_rows}

    # 4. Peers for the starter facts (named peers, best first).
    peer_rows = (
        await session.execute(
            text(
                """
                SELECT peer_name FROM entity_peers
                WHERE entity_id = :eid
                ORDER BY overall_score DESC NULLS LAST, peer_name ASC
                LIMIT 3
                """
            ),
            {"eid": resolved.entity_id},
        )
    ).all()
    peer_names = [r.peer_name for r in peer_rows]
    entity_name_row = (
        await session.execute(
            text("SELECT name FROM entities WHERE id = :eid"),
            {"eid": resolved.entity_id},
        )
    ).first()
    entity_name = entity_name_row.name if entity_name_row else display_id

    run_level_e_ids = await _run_level_e_ids(session, resolved.id)

    # Verbatim excerpts for the cards' citing E-IDs + category display
    # names — inputs to the evidence-rich card narrative (2026-07-06).
    all_card_e_ids: set[str] = set(run_level_e_ids)
    for row_v2 in v2_rows:
        for t in (row_v2.breakdown or {}).get("top_subcaps") or []:
            all_card_e_ids.update(str(e) for e in (t.get("e_ids") or []))
    for pid_p in persisted:
        bd_p = persisted[pid_p].fit_breakdown
        if isinstance(bd_p, dict):
            for t in bd_p.get("top_subcaps") or []:
                all_card_e_ids.update(str(e) for e in (t.get("e_ids") or []))
    excerpts_by_e_id: dict[str, str] = {}
    if all_card_e_ids:
        ex_rows = (
            await session.execute(
                text(
                    """
                    SELECT e_id, excerpt FROM evidence_index
                    WHERE run_id = :rid AND e_id = ANY(:eids)
                    """
                ),
                {"rid": resolved.id, "eids": sorted(all_card_e_ids)},
            )
        ).all()
        excerpts_by_e_id = {r.e_id: (r.excerpt or "") for r in ex_rows}
    cat_name_rows = (
        await session.execute(
            text(
                """
                SELECT category_id, name
                FROM ccg_categories WHERE version = :ver
                """
            ),
            {"ver": resolved.ccg_catalog_version},
        )
    ).all()
    category_names = {r.category_id: r.name for r in cat_name_rows if r.name}

    # Entity techstack (named current systems) for the deterministic dossier.
    tech_items = await _entity_techstack_items(session, resolved.entity_id)

    # Validated Gemini platform stories from the enrich_corpus warm sweep
    # (pro model; keyed "{display_id}:{platform_id}"). Read-back closes the
    # loop the 2026-07-04 audit flagged: the most expensive warm slice was
    # persisted + deploy-asserted but never consumed. Latest row per platform.
    story_by_pid: dict[str, str] = {}
    try:
        story_rows = (
            await session.execute(
                text("""
                    SELECT DISTINCT ON (target_id) target_id, output_text
                    FROM vertex_synthesis_cache
                    WHERE surface = 'platform_story'
                      AND target_id LIKE :prefix
                      AND validators_passed
                      AND invalidated_at IS NULL
                    ORDER BY target_id, created_at DESC
                """),
                {"prefix": f"{display_id}:%"},
            )
        ).all()
        from app.services.text_hygiene import scrub_md
        for r in story_rows:
            pid_part = str(r.target_id).split(":", 1)[-1]
            if r.output_text:
                # Scrub the Vertex story on read-back so it matches the
                # deterministic dossier floor's hygiene — strips any raw P#C#
                # code / bare E-ID the model emitted despite the prompt rule,
                # preserving [E-…] chips (2026-07-09 QA: story_md was persisted
                # raw and never scrubbed).
                story_by_pid[pid_part] = scrub_md(str(r.output_text)) or str(r.output_text)
    except Exception:
        story_by_pid = {}  # cache table absent on minimal test DBs

    cards: list[PlatformCard] = []
    for pid, meta in PLATFORM_DISPLAY.items():
        live = v2_by_pid[pid]
        ps_row = persisted.get(pid)
        use_persisted = have_v2 and ps_row is not None

        fit_score = float(ps_row.fit_score) if use_persisted else live.fit_score
        state = ps_row.state if use_persisted and ps_row.state else live.state
        breakdown = (
            ps_row.fit_breakdown if use_persisted and isinstance(ps_row.fit_breakdown, dict)
            else live.breakdown
        )

        # Card evidence ladder (Part 7.1) + state honesty. evidence_ids is
        # broad (entity has evidence ⇒ card cites it); state is strict
        # (READY only when the DRIVING subcaps are well-grounded, else
        # PENDING_REVIEW; INSUFFICIENT_EVIDENCE when the card is empty).
        breakdown_dict = breakdown if isinstance(breakdown, dict) else None
        evidence_ids = _card_evidence_ids(breakdown_dict, run_level_e_ids)
        es_mean = float((breakdown_dict or {}).get("evidence_strength") or 0.0)
        if state == "READY" and es_mean < THIN_EVIDENCE_STRENGTH:
            state = "PENDING_REVIEW"
        if not evidence_ids and state == "READY":
            state = "INSUFFICIENT_EVIDENCE"
        sequence_rank = (
            ps_row.sequence_rank if use_persisted and ps_row.sequence_rank is not None
            else live.sequence_rank
        )
        addressable = (
            list(ps_row.addressable_subcap_ids or []) if use_persisted
            else live.addressable_subcap_ids
        )

        # Readiness is always evaluated live from the run's scores (same
        # inputs the persisted row used — cheap and always current).
        prereq_specs = (
            (ps_row.prerequisite_checks if ps_row else None)
            or None
        )
        if prereq_specs:
            prereq_checks = [
                evaluate_prereq(
                    name=str(p.get("name", "unnamed")),
                    required_subcap_id=str(p["required_subcap_id"]),
                    threshold=float(p["threshold"]),
                    scores_by_subcap=scores_by_subcap,
                )
                for p in prereq_specs
                if isinstance(p, dict)
                and "required_subcap_id" in p and "threshold" in p
            ]
        else:
            prereq_checks = checks_by_platform.get(pid, [])
        readiness = aggregate_readiness(prereq_checks)

        # Starter facts — anchored on the fit breakdown's TOP-OPPORTUNITY
        # subcap (never sorted[0]).
        top_subcaps = list(breakdown.get("top_subcaps") or [])
        facts = None
        metric_phrases: list[str] = []
        if top_subcaps:
            top = top_subcaps[0]
            top_e_ids = [str(e) for e in (top.get("e_ids") or [])]
            metric_phrases = await _starter_metric_phrases(
                session, resolved.id, top_e_ids,
            )
            seq = breakdown.get("sequence") or {}
            sequence_after = [
                PLATFORM_DISPLAY.get(p, {}).get("name", p)
                for p in (seq.get("after") or [])
            ][:2]
            facts = StarterFacts(
                entity_name=entity_name,
                top_subcap_id=str(top.get("subcap_id") or addressable[0]),
                top_subcap_name=top.get("name"),
                top_score=(
                    float(top["score"]) if top.get("score") is not None else None
                ),
                top_peer_median=(
                    float(top["peer_median"])
                    if top.get("peer_median") is not None else None
                ),
                top_e_ids=top_e_ids,
                metric_phrases=metric_phrases,
                peer_names=peer_names,
                absent_families=[
                    str(f) for f in (breakdown.get("absent_families") or [])
                ],
                sequence_after=sequence_after,
            )

        card = (
            PlatformCard(
                platform_id=pid,
                display_name=meta["name"],
                pillar=meta["pillar"],
                fit_score=fit_score,
                readiness_index=readiness,
                state=state,
                addressable_subcap_ids=addressable,
                prereq_checks=[
                    PrereqCheckOut(
                        name=c.name,
                        required_subcap_id=c.required_subcap_id,
                        threshold=c.threshold,
                        status=c.status,
                        current_score=c.current_score,
                        note=c.note,
                    )
                    for c in prereq_checks
                ],
                conversation_starter=compose_conversation_starter(
                    platform_name=meta["name"],
                    pillar=meta["pillar"],
                    fit_score=fit_score,
                    addressable_subcap_ids=addressable,
                    prereq_checks=prereq_checks,
                    readiness=readiness,
                ),
                conversation_starters=compose_conversation_starters(
                    platform_name=meta["name"],
                    pillar=meta["pillar"],
                    fit_score=fit_score,
                    addressable_subcap_ids=addressable,
                    prereq_checks=prereq_checks,
                    readiness=readiness,
                    facts=facts,
                ),
                story_md=story_by_pid.get(pid),
                story_source="vertex" if pid in story_by_pid else None,
                fit_breakdown=breakdown if isinstance(breakdown, dict) else None,
                sequence_rank=sequence_rank,
                absent_count=live.absent_count,
                top_subcap_names=(
                    [str(t["name"]) for t in top_subcaps[:2] if t.get("name")]
                    or None
                ),
                evidence_ids=evidence_ids,
            )
        )
        # Composed AFTER construction because the twin composer reads the
        # card's serialized shape (the exact dict the patcher sees in the
        # exported pack) — prereq status keys, fit_breakdown, top names.
        serialized = card.model_dump()
        card.opportunity_md = compose_opportunity_md(
            serialized, entity_key=entity_name)
        # 2026-07-06 platform-reasoning mandate: the evidence-rich
        # "where they stand" narrative (verbatim quotes + E-IDs) and the
        # ranked Zennify opportunity areas — both deterministic over the
        # breakdown + the entity's own excerpts.
        card.narrative_md = compose_platform_narrative(
            entity_name=entity_name,
            platform_name=meta["name"],
            fit_score=fit_score,
            readiness=readiness,
            state=state,
            breakdown=breakdown if isinstance(breakdown, dict) else None,
            excerpts_by_e_id=excerpts_by_e_id,
            category_names=category_names,
        )
        card.opportunity_areas = opportunity_areas_from_breakdown(
            breakdown if isinstance(breakdown, dict) else None,
            category_names,
        )
        # Deterministic dossier floor (platform v3) — the evidence-rich
        # narrative that can never be cold. A validated Gemini story (read
        # back into story_md above) WINS; otherwise the floor fills story_md.
        dossier_out = compose_dossier(
            serialized,
            techstack_items=tech_items,
            entity_name=entity_name,
            metric_phrases=metric_phrases,
        )
        card.dossier = dossier_out["dossier"]
        card.narrative_provenance = dossier_out["narrative_provenance"]
        if not card.story_md:
            card.story_md = dossier_out["story_md"]
            card.story_source = dossier_out["story_source"]
        cards.append(card)

    sections = await load_sections_for_run(session, resolved.id, entity_id=resolved.entity_id)
    narrative = build_narrative_platform(sections)

    payload = PlatformsResponse(
        entity_display_id=display_id,
        run_request_id=resolved.request_id,
        cards=cards,
        pillar_offerings=pillar_offerings,
        narrative=narrative,
    )
    return strip_and_respond(payload, view.audience, PlatformsResponse)


# ── Transformation roadmap (Part 7.3 — sequence-aware phasing) ─────────

_EFFORT_MONTHS = {"SMALL": 2, "MEDIUM": 4, "LARGE": 8, "XLARGE": 12}
_EFFORT_PHASE = {"SMALL": 1, "S": 1, "MEDIUM": 2, "M": 2,
                 "LARGE": 3, "L": 3, "XLARGE": 4, "XL": 4}
_PHASE_NAMES = {1: "Quick Wins", 2: "Foundational", 3: "Strategic", 4: "Aspirational"}


def _phase_from_effort_band(effort_band: str | None) -> tuple[int, str]:
    """Effort-band fallback bucketing (legacy tier — used only when a rec
    has neither an explicit corpus phase nor prerequisite edges)."""
    eb = (effort_band or "").upper()
    n = _EFFORT_PHASE.get(eb, 4 if eb else 4)
    if not eb:
        n = 4
    return n, _PHASE_NAMES[n]


def _band_label(score: float) -> str:
    if score < 1.5:
        return "M1"
    if score < 2.5:
        return "M2"
    if score < 3.5:
        return "M3"
    if score < 4.5:
        return "M4"
    return "M5"


def assign_phases(recs: list[dict]) -> dict[str, int]:
    """Sequence-aware phase per rec_id (1..4).

    Priority: explicit corpus `phase` → prerequisite-DAG level (a rec
    lands at least one phase after every prerequisite) → effort band →
    uplift magnitude (a +1.2-pillar transformation is not a quick win).
    Pure + deterministic; cycles collapse to the base phase.
    """
    by_id = {r["rec_id"]: r for r in recs}
    memo: dict[str, int] = {}

    def _base_phase(r: dict) -> int:
        explicit = r.get("phase")
        if isinstance(explicit, int) and 1 <= explicit <= 4:
            return explicit
        eb = (r.get("effort_band") or "").upper()
        if eb in _EFFORT_PHASE:
            return _EFFORT_PHASE[eb]
        uplift = r.get("uplift_per_pillar") or {}
        vals = [v for v in uplift.values() if isinstance(v, int | float)] \
            if isinstance(uplift, dict) else []
        if vals:
            best = max(vals)
            return 3 if best >= 1.2 else 2 if best >= 0.6 else 1
        return 2

    def level(rec_id: str, seen: frozenset[str]) -> int:
        if rec_id in memo:
            return memo[rec_id]
        r = by_id.get(rec_id)
        if r is None:
            return 0
        base = _base_phase(r)
        prereq_level = 0
        if rec_id not in seen:
            for dep in r.get("prerequisite_rec_ids") or []:
                if dep in by_id:
                    prereq_level = max(
                        prereq_level, level(dep, seen | {rec_id}),
                    )
        out = max(1, min(4, max(base, prereq_level + 1)))
        memo[rec_id] = out
        return out

    phases = {r["rec_id"]: level(r["rec_id"], frozenset()) for r in recs}

    # Uplift spread (the plan's third phasing input): when EVERY rec
    # collapsed into one phase (the audit's 91/94 single-phase page) and
    # there are enough recs to sequence, split by uplift — the biggest
    # jumps land first (quick-wins ordering), the long tail follows.
    if len(recs) >= 4 and len(set(phases.values())) == 1:
        base = next(iter(phases.values()))

        def _uplift_of(r: dict) -> float:
            uplift = r.get("uplift_per_pillar") or {}
            vals = [v for v in uplift.values() if isinstance(v, int | float)] \
                if isinstance(uplift, dict) else []
            return max(vals) if vals else 0.0

        ordered = sorted(recs, key=lambda r: (-_uplift_of(r), r["rec_id"]))
        n_groups = min(3, (len(ordered) + 1) // 2, 5 - base)
        if n_groups >= 2:
            size = -(-len(ordered) // n_groups)  # ceil division
            for i, r in enumerate(ordered):
                phases[r["rec_id"]] = min(4, base + i // size)

    return phases


_CAT_REF_RE = None


def _mine_categories(*texts: str | None) -> set[str]:
    """P1C1-style category references mined from rec title/metric prose."""
    global _CAT_REF_RE
    if _CAT_REF_RE is None:
        import re as _re
        _CAT_REF_RE = _re.compile(r"\bP[1-4]C\d+\b")
    out: set[str] = set()
    for t in texts:
        if t:
            out.update(_CAT_REF_RE.findall(t))
    return out


def _lift_from_metric(metric: str | None) -> float | None:
    """`"P1C1 score: 1.18 → 2.0+"` → +0.82 — the corpus quantifies its own
    maturity lift inside the outcome metric; use it when uplift_per_pillar
    never shipped (the audit's maturity_lift-null-89% fix)."""
    if not metric:
        return None
    import re as _re
    m = _re.search(
        r"(\d(?:\.\d+)?)\s*(?:→|->)\s*~?(\d(?:\.\d+)?)", metric,
    )
    if not m:
        return None
    a, b = float(m.group(1)), float(m.group(2))
    if 1.0 <= a <= 5.0 and 1.0 <= b <= 5.0 and b > a:
        return round(b - a, 2)
    return None


_ROADMAP_TARGET_BAND = 4.0  # M4 — unified with the fit engine + derive


def _rec_maturity_lift(
    r: dict,
    metric_txt: str | None,
    category_scores: dict[str, float],
    subcap_scores: dict[str, float],
) -> float | None:
    """Per-rec maturity lift via a grounding ladder (Part 7.2 close-out):

      explicit ``uplift_per_pillar`` -> the ``a -> b`` clause the
      corpus/derive writes into the outcome metric -> ``M4 - worst target
      subcap score`` -> ``M4 - worst mined-category score`` -> ``M4 - worst
      score in the rec's platform pillar``.

    Returns the positive lift-to-M4, or None when the rec targets nothing
    scored (genuinely uncomputable — the honest null)."""
    uplift = r.get("uplift_per_pillar") or {}
    if isinstance(uplift, dict) and uplift:
        vals = [v for v in uplift.values() if isinstance(v, int | float)]
        if vals:
            return max(vals)
    lv = _lift_from_metric(metric_txt)
    if lv is not None:
        return lv
    tgt = _ROADMAP_TARGET_BAND
    # target subcap scores (the plan's "target_band - current subcap score").
    subs = [s for s in (r.get("target_subcap_ids") or []) if s in subcap_scores]
    if subs:
        g = round(tgt - min(subcap_scores[s] for s in subs), 2)
        if g > 0:
            return g
    # mined P?C? categories (rec prose + target-subcap prefixes).
    cats = _mine_categories(r.get("title"), metric_txt) | {
        s[:4] for s in (r.get("target_subcap_ids") or []) if len(s) >= 4
    }
    hits = [c for c in cats if c in category_scores]
    if hits:
        g = round(tgt - min(category_scores[c] for c in hits), 2)
        if g > 0:
            return g
    # the rec's platform pillar → its worst-gap category.
    pid = r.get("platform_id")
    pil = PLATFORM_DISPLAY.get(pid, {}).get("pillar") if pid else None
    if pil:
        pillar_scores = [s for c, s in category_scores.items() if c[:2] == pil]
        if pillar_scores:
            g = round(tgt - min(pillar_scores), 2)
            if g > 0:
                return g
    return None


def _impact_entries(recs_in_phase: list[dict]) -> dict[str, str]:
    """Customer-impact KVs for the phase — one entry per quantified rec
    outcome metric (label: quantified part), prototype ROADMAP_IMPACTS
    style. Falls back to the maturity lift when metrics are absent."""
    impact: dict[str, str] = {}
    for r in recs_in_phase:
        outcomes = r.get("outcomes") or {}
        metric = outcomes.get("metric") if isinstance(outcomes, dict) else None
        if not metric:
            continue
        if ":" in metric:
            k, _, v = metric.partition(":")
            k, v = k.strip(), v.strip()
        else:
            import re as _re
            m = _re.search(r"[\d+\-−↓↑~≈]", metric)  # noqa: RUF001 — corpus metrics use U+2212
            if m and m.start() > 2:
                k, v = metric[:m.start()].strip(" :—-"), metric[m.start():].strip()
            else:
                k, v = "Outcome", metric.strip()
        if k and v and k not in impact:
            impact[k] = v
        if len(impact) >= 4:
            break
    return impact


def build_roadmap_phases(
    recs: list[dict],
    category_scores: dict[str, float],
    subcap_scores: dict[str, float] | None = None,
) -> list[dict]:
    """Assemble the sequenced multi-phase roadmap (pure — unit-tested).

    Each rec dict needs: rec_id, title, platform_id, platform_name,
    effort_band, uplift_per_pillar, phase, outcomes, prerequisite_rec_ids,
    target_subcap_ids, feature. ``category_scores`` maps 'P4C1' → current
    average score and ``subcap_scores`` maps 'P4C1.1.1' → current score —
    both feed the before→after target math and the per-rec maturity-lift
    ladder (``_rec_maturity_lift``).
    """
    subcap_scores = subcap_scores or {}
    if not recs:
        return []
    phase_of = assign_phases(recs)
    phases_acc: dict[int, dict] = {}
    for r in recs:
        n = phase_of[r["rec_id"]]
        bucket = phases_acc.setdefault(n, {
            "phase": n,
            "name": _PHASE_NAMES[n],
            "label": _PHASE_NAMES[n],
            "duration_months": 0,
            "recommendations": [],
            "_cat_uplift": {},
            "_deps": set(),
        })
        months = _EFFORT_MONTHS.get((r.get("effort_band") or "MEDIUM").upper(), 4)
        # Recs within a phase run in parallel — the phase lasts as long as
        # its longest rec (the old sum inflated 3 recs x 4mo to a year).
        bucket["duration_months"] = max(bucket["duration_months"], months)

        outcomes_d = r.get("outcomes") if isinstance(r.get("outcomes"), dict) else None
        metric_txt = (outcomes_d or {}).get("metric")

        # Maturity lift via the grounding ladder: explicit uplift → the
        # corpus/derive "a → b" metric clause → M4 minus scored target subcap
        # / category / platform-pillar. Only null when the rec targets nothing
        # scored (the audit's maturity_lift-null-86% fix).
        lift_val = _rec_maturity_lift(r, metric_txt, category_scores, subcap_scores)
        maturity_lift = f"+{lift_val}" if lift_val is not None else None

        # Category uplift attribution for the phase target math: target
        # subcap prefixes + category references in the rec's own prose.
        cats: set[str] = set()
        for sid in r.get("target_subcap_ids") or []:
            if len(sid) >= 4:
                cats.add(sid[:4])
        cats |= _mine_categories(r.get("title"), metric_txt)
        for c in cats:
            if c in category_scores:
                bucket["_cat_uplift"][c] = max(
                    bucket["_cat_uplift"].get(c, 0.0),
                    float(lift_val) if lift_val is not None else 0.4,
                )

        for dep in r.get("prerequisite_rec_ids") or []:
            bucket["_deps"].add(dep)

        bucket["recommendations"].append({
            "rec_id": r["rec_id"],
            "title": r.get("title") or "",
            "platform_id": r.get("platform_id") or "",
            "platform_name": r.get("platform_name") or "",
            "maturity_lift": maturity_lift,
            "feature": r.get("feature"),
            "metric": metric_txt,
            "outcomes": outcomes_d,
        })

    phases: list[dict] = []
    # Renumber to a CONTIGUOUS, 1-based display sequence while preserving each
    # bucket's semantic effort tier in `name`/`label` (2026-07-06 operator
    # report: "some roadmaps start on Phase 2"). A client whose recs never fall
    # in the Quick-Wins band still begins at Phase 1 — labelled by its true tier
    # (e.g. "Phase 1 · Foundational") rather than skipping the number.
    for display_idx, n in enumerate(sorted(phases_acc), start=1):
        b = phases_acc[n]
        b["phase"] = display_idx
        # target: "M2 → M3 in P4C1, P3C2" from the top-2 uplifted categories.
        cat_uplift: dict[str, float] = b.pop("_cat_uplift")
        target = None
        top_cats = sorted(
            cat_uplift.items(), key=lambda kv: (-kv[1], kv[0]),
        )[:2]
        if top_cats:
            # Band math on the top-uplifted category; up to 2 named.
            lead_cat, lead_lift = top_cats[0]
            before = category_scores[lead_cat]
            after = min(5.0, before + lead_lift)
            target = (
                f"{_band_label(before)} → {_band_label(after)} in "
                + ", ".join(c for c, _ in top_cats)
            )
        deps: set[str] = b.pop("_deps")
        in_phase = {r["rec_id"] for r in b["recommendations"]}
        platforms = sorted({
            r["platform_name"] for r in b["recommendations"] if r["platform_name"]
        })
        metrics = [r["metric"] for r in b["recommendations"] if r.get("metric")]
        b["platform"] = " · ".join(platforms[:2]) or None
        b["target"] = target
        b["metric"] = metrics[0] if metrics else None
        b["customer_impact"] = _impact_entries(b["recommendations"]) or None
        b["dependencies"] = sorted(d for d in deps if d not in in_phase)
        phases.append(b)
    return phases


@router.get("/{display_id}/platforms/roadmap")
async def platforms_roadmap(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    run: str | None = None,
) -> dict:
    """Transformation Roadmap — sequence-aware phases derived from the
    run's recommendations. Called by `frontend/src/pages/PlatformPage.tsx`.

    Backward-compatible shape (`{phases:[{phase,name,duration_months,
    recommendations:[...]}], total_duration_months}`) with the Part 7.3
    additive per-phase fields: label, target ("M2 → M3 in P4C1"), metric,
    platform, customer_impact, dependencies; per-rec feature/metric.
    """
    ent = (
        await session.execute(
            text("SELECT id FROM entities WHERE display_id = :did"),
            {"did": display_id},
        )
    ).first()
    if ent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"entity {display_id} not found",
        )
    # 2026-06-05: honour ?run= on the roadmap endpoint too.
    from app.services.run_resolver import maybe_resolve_entity_run
    resolved = await maybe_resolve_entity_run(
        session, display_id, run_request_id=run,
    )
    if resolved is None:
        return {
            "entity_display_id": display_id,
            "run_request_id": None,
            "phases": [],
            "total_duration_months": 0,
        }
    rows = (
        await session.execute(
            text(
                """
                SELECT r.rec_id, r.title,
                       COALESCE(r.platform_id, '') AS platform_id,
                       r.effort_band,
                       r.uplift_per_pillar,
                       r.phase, r.feature, r.outcomes,
                       r.prerequisite_rec_ids, r.target_subcap_ids
                FROM recommendations r
                WHERE r.run_id = :rid
                ORDER BY COALESCE(r.effort_band, 'ZZZ'), r.created_at
                """
            ),
            {"rid": resolved.id},
        )
    ).all()

    cat_rows = (
        await session.execute(
            text(
                """
                SELECT COALESCE(parent_category_id, LEFT(subcap_id, 4)) AS cat,
                       AVG(score) AS avg_s
                FROM subcap_scores
                WHERE run_id = :rid AND score IS NOT NULL
                GROUP BY 1
                """
            ),
            {"rid": resolved.id},
        )
    ).all()
    category_scores = {r.cat: float(r.avg_s) for r in cat_rows if r.cat}

    sc_rows = (
        await session.execute(
            text(
                """
                SELECT subcap_id, score FROM subcap_scores
                WHERE run_id = :rid AND score IS NOT NULL
                """
            ),
            {"rid": resolved.id},
        )
    ).all()
    subcap_scores = {r.subcap_id: float(r.score) for r in sc_rows}

    recs = [
        {
            "rec_id": r.rec_id,
            "title": r.title or "",
            "platform_id": r.platform_id or "",
            "platform_name": (
                PLATFORM_DISPLAY.get(r.platform_id, {}).get("name", r.platform_id)
                if r.platform_id else ""
            ),
            "effort_band": r.effort_band,
            "uplift_per_pillar": (
                dict(r.uplift_per_pillar) if r.uplift_per_pillar else None
            ),
            "phase": r.phase,
            "feature": r.feature,
            "outcomes": dict(r.outcomes) if isinstance(r.outcomes, dict) else None,
            "prerequisite_rec_ids": list(r.prerequisite_rec_ids or []),
            "target_subcap_ids": list(r.target_subcap_ids or []),
        }
        for r in rows
    ]
    phases = build_roadmap_phases(recs, category_scores, subcap_scores)
    total = sum(p["duration_months"] for p in phases)
    return {
        "entity_display_id": display_id,
        "run_request_id": resolved.request_id,
        "phases": phases,
        "total_duration_months": total,
    }
