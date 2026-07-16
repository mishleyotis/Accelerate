"""D5 Context + Tech stack endpoints.

D5 Context is AE-level (Part 8.1 access fix — the audit found AEs hitting
a dead-end 403 on a visible tab; the customer audience stays server-side
stripped via ``strip_and_respond``). Tech stack is open to all
authenticated users.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from app.deps import (
    CurrentUserDep,
    SessionDep,
    ViewModeDep,
    require_ae,
)
from app.schemas.context import (
    ContextResponse,
    TechStackDetailResponse,
    TechStackResponse,
    TimelineEventOut,
)
from app.services.audience_strip import strip_and_respond
from app.services.context_extras import (
    acquisitions_from_timeline,
    derive_trend_md,
    financials_view,
    has_open_regulatory_issue,
    leadership_view,
    regulatory_view,
    sentiment_view,
    to_issue_register,
)
from app.services.parsers.facts_extractor import extract_regulatory_standing
from app.services.section_routing import (
    build_narrative_context,
    load_sections_for_run,
)

router = APIRouter(prefix="/api/v1/entities", tags=["context"])


@router.get(
    "/{display_id}/context",
    response_model=ContextResponse,
    dependencies=[Depends(require_ae)],
)
async def context(
    display_id: str,
    session: SessionDep,
    view: ViewModeDep,
    run: str | None = None,
) -> ContextResponse:
    # 2026-06-05: honour ?run= via the soft resolver -- context still
    # renders entity-level surfaces (timeline_events, firmographics)
    # even when no run has completed yet, so missing runs returns None
    # rather than 404.
    from app.services.run_resolver import maybe_resolve_entity_run
    resolved = await maybe_resolve_entity_run(
        session, display_id, run_request_id=run,
    )
    # Re-read entity id (+ name — the acquisition frame scoper needs it)
    # for the entity-scoped queries below.
    ent = (
        await session.execute(
            text("SELECT id, name FROM entities WHERE display_id = :did"),
            {"did": display_id},
        )
    ).first()
    if ent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"entity {display_id} not found",
        )

    # Migration 047 (Part 8.2): signal / date_precision / evidence_e_ids
    # / subcap_ids ride the same SELECT. Try with the new columns; fall
    # back to the legacy list for envs without migration 047 applied
    # (the new TimelineEventOut fields keep their None/[] defaults).
    try:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, event_date, kind, title, body, source_url, e_id,
                           signal, date_precision, evidence_e_ids, subcap_ids
                    FROM timeline_events
                    WHERE entity_id = :eid
                    ORDER BY event_date DESC LIMIT 200
                    """
                ),
                {"eid": ent.id},
            )
        ).all()
    except Exception:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id, event_date, kind, title, body, source_url, e_id
                    FROM timeline_events
                    WHERE entity_id = :eid
                    ORDER BY event_date DESC LIMIT 200
                    """
                ),
                {"eid": ent.id},
            )
        ).all()
    timeline = [
        TimelineEventOut(
            id=str(r.id), event_date=r.event_date, kind=r.kind, title=r.title,
            body=r.body, source_url=r.source_url, e_id=r.e_id,
            signal=getattr(r, "signal", None),
            date_precision=getattr(r, "date_precision", None),
            evidence_e_ids=list(getattr(r, "evidence_e_ids", None) or []),
            subcap_ids=list(getattr(r, "subcap_ids", None) or []),
        )
        for r in rows
    ]
    # Part 8.2 step 3: derive_context persists the verified-regulatory-
    # absence signal as a kind='regulatory_standing' row (facts[] have no
    # other DB home). It is NOT a timeline dot — lift it out here; it feeds
    # the regulatory block below.
    persisted_standing = next(
        (t for t in timeline if t.kind == "regulatory_standing"), None,
    )
    timeline = [t for t in timeline if t.kind != "regulatory_standing"]

    # F5c (2026-06-07 follow-up): include narrative_md in the SELECT so
    # the D5 Context "About" panel can render the analyst's prose
    # paragraph. The column was added by migration 018 and now
    # populated by the parser (F5c) but D5 was reading the legacy
    # column list and silently dropping the field. Try/except retries
    # with the legacy list for envs without the column.
    try:
        firm = (
            await session.execute(
                text(
                    """
                    SELECT primary_regulator, leadership, thought_leadership,
                           financial_highlights, sentiment, sentiment_synced_at,
                           narrative_md, parsed_facts
                    FROM firmographics WHERE entity_id = :eid
                    """
                ),
                {"eid": ent.id},
            )
        ).first()
        firm_narrative_md = firm.narrative_md if firm is not None else None
    except Exception:
        firm = (
            await session.execute(
                text(
                    """
                    SELECT primary_regulator, leadership, thought_leadership,
                           financial_highlights, sentiment, sentiment_synced_at
                    FROM firmographics WHERE entity_id = :eid
                    """
                ),
                {"eid": ent.id},
            )
        ).first()
        firm_narrative_md = None

    firmographics: dict | None = None
    sentiment: dict | None = None
    financials: dict | None = None
    if firm is not None:
        # Part 8.6: leadership rows are view-time cleaned/enriched
        # (tenure_months from date phrases, parentheticals → note, garble →
        # explicit gap rows) for the D5 leadership panel.
        firmographics = {
            "primary_regulator": firm.primary_regulator,
            "leadership": leadership_view(firm.leadership),
            "thought_leadership": firm.thought_leadership,
        }
        if firm_narrative_md:
            firmographics["narrative_md"] = firm_narrative_md
        # 2026-06-09: surface the structured classification firmographics
        # the flat entity_profile.json parser extracts (ticker / sub_vertical
        # / size_tier / entity_type). They live in parsed_facts JSONB; the
        # D5 "Regulatory & firmographics" KV card renders them. Only clean
        # scalar keys are forwarded — financials (total_deposits/roe/…) stay
        # in parsed_facts for the dedicated D5 financial-trajectory card, and
        # list/prose extras (affiliate_banks/key_context) are not KV-shaped.
        pf = getattr(firm, "parsed_facts", None) or {}
        for k in ("ticker", "sub_vertical", "size_tier", "entity_type"):
            v = pf.get(k)
            if isinstance(v, str) and v and firmographics.get(k) is None:
                firmographics[k] = v
        # Part 8.5: structured, drillable sentiment rows (rating+review-count
        # fragments merged; polarity/themes/drilldown/evidence per source).
        sentiment = sentiment_view(firm.sentiment)
        # B-3 / Part 8.4: guarded year alignment + labelled per-metric series.
        financials = financials_view(firm.financial_highlights)
        # Part 8.6: license_type/charter + jurisdictions — verbatim spans
        # mined from parsed_facts / narrative / financial lines (honest-null).
        reg = regulatory_view(
            pf, firm_narrative_md, (financials or {}).get("lines"),
        )
        for k, v in reg.items():
            if v is not None and firmographics.get(k) is None:
                firmographics[k] = v

    # B-2: surface the ingested issue register for the active run (D5 Gantt).
    # 2026-07-06 defect-family fix: the AE-facing register shows the
    # CLIENT's issues only — assessment-QA meta rows (kind =
    # 'assessment_qa': run_manifest/sheet-naming checks about the
    # deliverable itself) stay in the table for the Health page but
    # never render here; blank titles are excluded defensively (ingest
    # no longer persists them). Ordering matches the DB's lowercase
    # canonical severities (the old MATERIAL/MAJOR/MINOR CASE never
    # matched a row).
    issue_register = []
    if resolved is not None:
        issue_rows = (
            await session.execute(
                text(
                    """
                    SELECT id, issue_id, title, severity, rationale,
                           opened_on, resolved_on, linked_subcap_ids,
                           kind, status, dma_impact, caps
                    FROM issue_register
                    WHERE run_id = :rid
                      AND COALESCE(kind, 'client') <> 'assessment_qa'
                      AND BTRIM(COALESCE(title, '')) <> ''
                    ORDER BY
                      CASE LOWER(severity)
                           WHEN 'critical' THEN 0
                           WHEN 'high' THEN 1
                           WHEN 'medium' THEN 2
                           WHEN 'low' THEN 3 ELSE 4 END,
                      opened_on DESC NULLS LAST,
                      issue_id
                    """
                ),
                {"rid": resolved.id},
            )
        ).all()
        issue_register = to_issue_register(issue_rows)

    # B-4 / Part 8.3: acquisitions = timeline kind='acquisition' rows that
    # carry a REAL acquisition frame (acquirer+target NER, scoped to this
    # entity); strategy intent / complaints / peer M&A are rejected.
    acquisitions = acquisitions_from_timeline(timeline, entity_name=ent.name)

    # Part 8.2/8.6: the timeline SUPPRESSES negated-absence rows ("NEGATIVE
    # SEARCH RESULT: No formal enforcement…"); the strongest regulatory
    # absence surfaces instead as ONE explicit clean-standing signal on the
    # regulatory block — only when no OPEN regulatory issue contradicts it.
    # Tier 1: the derive_context-persisted kind='regulatory_standing' row
    # (facts-derived); tier 2: negated-absence mining over persisted
    # evidence excerpts.
    if firmographics is not None and not has_open_regulatory_issue(issue_register):
        standing: dict | None = None
        if persisted_standing is not None:
            standing = {
                "label": persisted_standing.title,
                "note": persisted_standing.body,
                "e_id": persisted_standing.e_id,
                "as_of": persisted_standing.event_date.isoformat(),
            }
        if standing is None:
            ev_rows = (
                await session.execute(
                    text(
                        """
                        SELECT e_id, excerpt, published_date AS publish_date
                        FROM evidence_index
                        WHERE entity_id = :eid
                          AND excerpt ~* '(enforcement|consent order|penalt|cease and desist|sanction)'
                        LIMIT 200
                        """
                    ),
                    {"eid": ent.id},
                )
            ).all()
            standing = extract_regulatory_standing(ev_rows)
        if standing is not None:
            firmographics["regulatory_standing"] = standing

    # Individual peer roster (D5 "Peer comparison" card) — named comparators
    # with per-category scores + computed overall, grounded in the package's
    # 06_peers files. Best-effort: empty when the package shipped no peer scores.
    peers: list[dict] = []
    if resolved is not None:
        peer_rows = (
            await session.execute(
                text(
                    """
                    SELECT peer_name, role, overall_score, category_scores
                    FROM entity_peers WHERE entity_id = :eid
                    ORDER BY overall_score DESC NULLS LAST, peer_name
                    """
                ),
                {"eid": resolved.entity_id},
            )
        ).all()
        peers = [
            {
                "peer_name": r.peer_name,
                "role": r.role,
                "overall_score": float(r.overall_score) if r.overall_score is not None else None,
                "category_scores": r.category_scores or {},
            }
            for r in peer_rows
        ]

    narrative: dict | None = None
    if resolved is not None:
        sections = await load_sections_for_run(session, resolved.id, entity_id=resolved.entity_id)
        narrative = build_narrative_context(sections)
    # Part 8.6: when the assessment report shipped no trend narrative
    # (audit: 70/94 missing), compose a grounded 1-2 sentence trend from
    # the REAL financial series — provenance-stamped `derived_financials`.
    if not (narrative or {}).get("trend_md"):
        derived_trend = derive_trend_md(financials)
        if derived_trend:
            narrative = dict(narrative or {})
            narrative.setdefault("issue_register_md", None)
            narrative["trend_md"] = derived_trend
            narrative["trend_md_source"] = "derived_financials"

    payload = ContextResponse(
        entity_display_id=display_id,
        run_request_id=resolved.request_id if resolved else None,
        timeline_events=timeline,
        issue_register=issue_register,
        acquisitions=acquisitions,
        firmographics=firmographics,
        financials=financials,
        sentiment=sentiment,
        peers=peers,
        narrative=narrative,
    )
    return strip_and_respond(payload, view.audience, ContextResponse)


async def _load_stack_view(
    display_id: str, session, *, with_absent: bool = True,
):
    """Shared read-model assembly for the techstack endpoints (Part 9).

    Returns ``(entity_row, triage, cohort_coverage, resolved_run, items)``
    where ``items`` are the AE-facing entries: taxonomy-flagged rows
    (ENGINEERING_SIGNAL / UNKNOWN_VENDOR) excluded, honest 4-state status,
    real ``since``/``note``/``peer_coverage``, plus server-generated ABSENT
    gap rows per scored platform family missing from the detected stack.
    """
    from app.services.run_resolver import maybe_resolve_entity_run
    from app.services.techstack_read import (
        build_absent_rows,
        detected_haystack,
        load_cohort_coverage,
        load_evidence_meta,
        to_entry_out,
        triage_rows,
    )

    ent = (
        await session.execute(
            text(
                "SELECT id, subvertical, explorium_synced_at "
                "FROM entities WHERE display_id = :did"
            ),
            {"did": display_id},
        )
    ).first()
    if ent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"entity {display_id} not found")
    rows = (
        await session.execute(
            text(
                """
                SELECT id, tech_id, vendor, product, layer, status, source, l3_id,
                       evidence_e_ids, linked_subcap_ids, detected_at
                FROM tech_stack_entries WHERE entity_id = :eid
                ORDER BY layer, vendor, product
                """
            ),
            {"eid": ent.id},
        )
    ).all()
    triage = triage_rows(rows)
    cov = await load_cohort_coverage(session, subvertical=ent.subvertical)
    all_e_ids = [e for r in triage.surfaced for e in (r.evidence_e_ids or [])]
    evidence_meta = await load_evidence_meta(
        session, entity_id=str(ent.id), e_ids=all_e_ids,
    )
    items = [
        to_entry_out(r, evidence_meta=evidence_meta, cov=cov)
        for r in triage.surfaced
    ]
    resolved = await maybe_resolve_entity_run(session, display_id)
    if with_absent and (items or triage.engineering or triage.review):
        # Gap rows only when the entity HAS technographic data — an entity
        # with zero tech rows renders the honest "still building" empty
        # state, not five fabricated gaps.
        items += await build_absent_rows(
            session, run_id=resolved.id if resolved else None,
            detected_haystack=detected_haystack(items), cov=cov,
        )
    return ent, triage, cov, resolved, items


@router.get("/{display_id}/techstack", response_model=TechStackResponse)
async def techstack(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
) -> TechStackResponse:
    ent, triage, _cov, _resolved, items = await _load_stack_view(
        display_id, session,
    )
    return TechStackResponse(
        entity_display_id=display_id,
        items=items,
        last_synced_at=ent.explorium_synced_at or triage.last_detected_at,
        engineering_signal_count=len(triage.engineering),
        engineering_signals=sorted({
            (r.vendor or "").strip() for r in triage.engineering
            if (r.vendor or "").strip()
        }),
        review_queue_count=len(triage.review),
    )


# IMPORTANT: register `/techstack/landscape` BEFORE the dynamic
# `/techstack/{tech_id}` route below so the FastAPI regex match-order
# treats it as a static path. Otherwise `tech_id="landscape"` wins and
# the frontend page gets a 404.
@router.get("/{display_id}/techstack/landscape")
async def techstack_landscape(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
) -> dict:
    """Tech stack grouped by layer for the InsightsPage tech landscape
    summary (`frontend/src/pages/InsightsPage.tsx:247`). Composes the
    base `techstack()` query and groups items by `layer` (Channel /
    Origination / Servicing / Data / Infrastructure / unknown)."""
    base = await techstack(display_id, _user, session)
    by_layer: dict[str, list[dict]] = {}
    for item in base.items:
        layer = (item.layer or "unknown").strip() or "unknown"
        by_layer.setdefault(layer, []).append(item.model_dump())
    return {
        "entity_display_id": display_id,
        "layers": by_layer,
        "layer_counts": {k: len(v) for k, v in by_layer.items()},
        "total_entries": len(base.items),
        "last_synced_at": (
            base.last_synced_at.isoformat() if base.last_synced_at else None
        ),
    }


@router.get(
    "/{display_id}/techstack/{tech_id}",
    response_model=TechStackDetailResponse,
)
async def techstack_detail(
    display_id: str,
    tech_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
) -> TechStackDetailResponse:
    from app.services.techstack_read import (
        gap_zones_for,
        load_impacts,
        load_peer_deployments,
    )

    ent, _triage, cov, resolved, items = await _load_stack_view(
        display_id, session,
    )
    entry = next((i for i in items if i.tech_id == tech_id), None)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"tech_id {tech_id} not found for this entity")

    catalog_version = resolved.ccg_catalog_version if resolved else None
    impacts = await load_impacts(
        session, run_id=resolved.id if resolved else None,
        subcap_ids=entry.linked_subcap_ids, catalog_version=catalog_version,
    )
    peer_names = await load_peer_deployments(
        session, entity_id=str(ent.id), subvertical=cov.subvertical,
        vendor=entry.vendor, l3_id=entry.l3_id,
    )
    # Cohort adoption count: entities of the cohort carrying this canonical
    # tech/family (share x cohort size). For legacy compatibility the field
    # keeps its name; the % bar uses peer_coverage + cohort_size.
    peer_count = (
        round(entry.peer_coverage * cov.cohort_size)
        if entry.peer_coverage is not None and cov.cohort_size
        else 0
    )
    return TechStackDetailResponse(
        entry=entry,
        linked_subcap_ids=entry.linked_subcap_ids,
        evidence_e_ids=entry.evidence_e_ids,
        peer_adoption_count=peer_count,
        peer_coverage=entry.peer_coverage,
        cohort_size=cov.cohort_size,
        cohort_label=cov.cohort_label,
        peer_names=peer_names,
        impacts=impacts,
        gap_zones=gap_zones_for(entry, impacts, cov.cohort_label),
    )
