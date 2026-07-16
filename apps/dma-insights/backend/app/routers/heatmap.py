"""D3 Heatmap endpoint — 4 zoom levels + 3 view modes."""
from __future__ import annotations

import re as _re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep, ViewModeDep
from app.schemas.heatmap import (
    HeatmapCell,
    HeatmapResponse,
    ValueChainBucket,
)
from app.services.audience_strip import strip_and_respond
from app.services.catalogue_resolver import CatalogueResolver
from app.services.heatmap_aggregator import (
    SubcapInput,
    aggregate_for_zoom,
)
from app.services.nlp.evidence_hygiene import clean_and_dedupe_evidence
from app.services.section_routing import (
    build_narrative_heatmap,
    load_sections_for_run,
)
from app.services.subcap_synthesis import (
    load_subcap_synthesis_for_run,
    merge_subcap_synthesis,
)

router = APIRouter(prefix="/api/v1/entities", tags=["heatmap"])


@router.get("/{display_id}/heatmap", response_model=HeatmapResponse)
async def heatmap(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    view: ViewModeDep,
    zoom: Literal["pillar", "category", "capability", "subcap"] = Query(default="pillar"),
    hm: Literal["standard", "focus", "value_chain"] = Query(default="standard"),
    peer: bool = Query(default=False),
    issues: bool = Query(default=False),
    # NB: plain `None` default (not `Query(default=None)`) so that
    # `heatmap_subcap` can call `heatmap(...)` directly without FastAPI's
    # dependency-injection layer turning `run` into a `fastapi.params.Query`
    # sentinel object. Pre-2026-06-05 fix the Query sentinel landed at
    # the inner call site, `maybe_resolve_entity_run` tried to `.strip()`
    # it, and the whole /heatmap/subcap/{id} path 500'd against any
    # seeded entity (caught by tests/test_live_endpoint_smoke.py::
    # test_every_get_route_no_5xx_against_seeded_db).
    run: str | None = None,
) -> HeatmapResponse:
    # 1. Resolve entity + run via the soft resolver -- pre-2026-06-05
    # this endpoint silently rendered the ACTIVE run regardless of the
    # ?run= selection. allow_in_progress=True because the heatmap is
    # one of the surfaces the operator wants to see live during ingest.
    from app.services.run_resolver import maybe_resolve_entity_run
    resolved = await maybe_resolve_entity_run(
        session, display_id, run_request_id=run, allow_in_progress=True,
    )
    # Re-fetch entity for subvertical (used for peer cohort below).
    ent = (
        await session.execute(
            text(
                "SELECT id, display_id, subvertical FROM entities "
                "WHERE display_id = :did"
            ),
            {"did": display_id},
        )
    ).first()
    if ent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"entity {display_id} not found",
        )
    if resolved is None:
        return HeatmapResponse(
            entity_display_id=display_id, run_request_id=None,
            zoom=zoom, view_mode=hm, subvertical=ent.subvertical,
            peer_overlay=peer, issue_overlay=issues, cells=[],
            catalogue_version="unknown", warnings=["no_active_run"],
        )

    catalog_version = resolved.ccg_catalog_version

    # 2. Load subcap_scores for the run + the catalogue rows for naming.
    score_rows = (
        await session.execute(
            text(
                """
                SELECT s.subcap_id, s.source_subcap_id, s.alias_resolved_from,
                       s.score, s.band, s.peer_median, s.peer_gap,
                       s.is_thin_evidence, s.cap_applied, s.cap_reason,
                       s.data_source, s.parent_category_id,
                       cs.l1_id, cs.name AS subcap_name,
                       cl.category_id, cl.name AS l1_name,
                       cc.pillar_id, cc.name AS category_name,
                       cp.name AS pillar_name
                FROM subcap_scores s
                LEFT JOIN ccg_subcaps cs
                  ON cs.version = :ver AND cs.subcap_id = s.subcap_id
                LEFT JOIN ccg_l1_capabilities cl
                  ON cl.version = :ver AND cl.l1_id = cs.l1_id
                LEFT JOIN ccg_categories cc
                  ON cc.version = :ver AND cc.category_id = cl.category_id
                LEFT JOIN ccg_pillars cp
                  ON cp.version = :ver AND cp.pillar_id = cc.pillar_id
                WHERE s.run_id = :rid
                """
            ),
            {"ver": catalog_version, "rid": resolved.id},
        )
    ).all()

    warnings: list[str] = []

    # 3. If any rows came back without catalogue join (cs.l1_id IS NULL),
    # try alias-bridging through the resolver.
    resolver = CatalogueResolver(session)
    inputs: list[SubcapInput] = []
    for r in score_rows:
        l1_id = r.l1_id
        if l1_id is None:
            # NB: variable name `aliased_subcap` (not `resolved`) so it
            # doesn't shadow the run-resolution above. Pre-2026-06-05
            # this loop reassigned `resolved` mid-function and any code
            # after it that read resolved.id was actually reading a
            # subcap-resolver object's attribute.
            aliased_subcap = await resolver.resolve_subcap(
                r.subcap_id, catalog_version,
            )
            if hasattr(aliased_subcap, "subcap_id"):
                # Re-fetch parent info from the resolved (post-alias) row.
                bridge_row = (
                    await session.execute(
                        text(
                            """
                            SELECT cs.l1_id, cs.name AS subcap_name,
                                   cl.category_id, cl.name AS l1_name,
                                   cc.pillar_id, cc.name AS category_name,
                                   cp.name AS pillar_name
                            FROM ccg_subcaps cs
                            LEFT JOIN ccg_l1_capabilities cl
                              ON cl.version = cs.version AND cl.l1_id = cs.l1_id
                            LEFT JOIN ccg_categories cc
                              ON cc.version = cs.version AND cc.category_id = cl.category_id
                            LEFT JOIN ccg_pillars cp
                              ON cp.version = cs.version AND cp.pillar_id = cc.pillar_id
                            WHERE cs.version = :ver AND cs.subcap_id = :sid
                            """
                        ),
                        {
                            "ver": aliased_subcap.version,
                            "sid": aliased_subcap.subcap_id,
                        },
                    )
                ).first()
                if bridge_row is not None:
                    inputs.append(_input_from_rows(r, bridge_row, aliased_from=r.subcap_id))
                    continue
            warnings.append(f"unresolved_subcap:{r.subcap_id}")
            continue
        inputs.append(_input_from_rows(r, r, aliased_from=None))

    # 4. issue counts for overlay — CLIENT issues only (assessment-QA
    # meta rows never light cells), still-open only (stored canonical
    # status OR legacy resolved_on). Registers mostly attribute at
    # CATEGORY grain (P1C2) while cells key at SUBCAP grain (P1C2.1.1),
    # so linked codes prefix-expand against the run's own scored
    # subcaps — before this join the overlay was dark pack-wide.
    issue_counts: dict[str, int] = {}
    if issues:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT ss.subcap_id AS linked,
                           COUNT(DISTINCT i.issue_id) AS n
                    FROM issue_register i
                    CROSS JOIN LATERAL UNNEST(i.linked_subcap_ids) AS l(code)
                    JOIN subcap_scores ss
                      ON ss.run_id = i.run_id
                     AND (ss.subcap_id = l.code
                          OR ss.subcap_id LIKE l.code || '.%')
                    WHERE i.run_id = :rid
                      AND i.resolved_on IS NULL
                      AND COALESCE(i.status, 'OPEN') <> 'RESOLVED'
                      AND COALESCE(i.kind, 'client') = 'client'
                    GROUP BY ss.subcap_id
                    """
                ),
                {"rid": resolved.id},
            )
        ).all()
        issue_counts = {row.linked: int(row.n) for row in rows if row.linked}

    # 5. focus mode filter
    if hm == "focus":
        focus_rows = (
            await session.execute(
                text(
                    "SELECT involved_subcap_ids FROM focus_areas WHERE run_id = :rid"
                ),
                {"rid": resolved.id},
            )
        ).all()
        focus_set: set[str] = set()
        for r in focus_rows:
            for sid in r.involved_subcap_ids or []:
                focus_set.add(sid)
        if focus_set:
            inputs = [i for i in inputs if i.subcap_id in focus_set]

    # 6. Aggregate to the requested zoom
    agg = aggregate_for_zoom(inputs, zoom, issue_counts_by_subcap=issue_counts)

    # 6a. Pull active AI enrichments for this entity's subcap_scores so
    # the UI can render an "AI" pill in the cell corner + thread the
    # enrichment evidence into the EvidenceDrawer. Only enrichments
    # NOT superseded by a newer one are included.
    enrichment_eids_by_subcap: dict[str, list[str]] = {}
    ai_enriched_subcaps: set[str] = set()
    try:
        enrich_rows = (
            await session.execute(
                text(
                    """
                    SELECT s.subcap_id AS subcap_id,
                           ai.grounding_evidence_ids AS eids
                    FROM ai_enrichments ai
                    JOIN subcap_scores s ON s.id = ai.target_id
                    WHERE ai.target_kind = 'subcap_score'
                      AND ai.superseded_by IS NULL
                      AND s.run_id = :rid
                    """
                ),
                {"rid": resolved.id},
            )
        ).all()
        for r in enrich_rows:
            sid = r.subcap_id
            if not sid:
                continue
            enrichment_eids_by_subcap[sid] = list(r.eids or [])
            ai_enriched_subcaps.add(sid)
    except Exception:
        # ai_enrichments table absent on some test DBs — degrade silently.
        enrichment_eids_by_subcap = {}
        ai_enriched_subcaps = set()

    # 6b. Evidence-first attachment (2026-07 Part 6.3 — the audit measured
    # enrichment_evidence_ids populated on 0/63,219 cells because only
    # ai_enrichments fed it, and enrichment rows barely exist). The
    # evidence↔subcap links ALREADY exist in evidence_index.linked_
    # subcap_ids — union them in (tier-ordered, capped 8/cell) so the
    # SynthesisDrawer's "Source reports & evidence" list renders for
    # every evidenced cell. Router-side derivation, not pack.
    if zoom == "subcap":
        try:
            link_rows = (
                await session.execute(
                    text(
                        """
                        SELECT e_id, tier,
                               UNNEST(linked_subcap_ids) AS sid
                        FROM evidence_index
                        WHERE run_id = :rid
                        ORDER BY tier ASC, e_id ASC
                        """
                    ),
                    {"rid": resolved.id},
                )
            ).all()
            for r in link_rows:
                if not r.sid:
                    continue
                eids = enrichment_eids_by_subcap.setdefault(r.sid, [])
                if len(eids) < 8 and r.e_id not in eids:
                    eids.append(r.e_id)
        except Exception:
            pass

    cells = []
    for c in agg.cells:
        # For aggregated cells (pillar/category/capability), surface the
        # "has_enrichment" flag if ANY child subcap is enriched. We don't
        # attempt to surface evidence IDs at those levels; the drawer
        # opens at the subcap level anyway.
        cell_eids: list[str] = []
        has_enrichment = False
        if zoom == "subcap":
            cell_eids = enrichment_eids_by_subcap.get(c.id, [])
            # The "AI" pill stays tied to REAL ai_enrichments rows — the
            # 6b evidence union must not light it on every evidenced cell.
            has_enrichment = c.id in ai_enriched_subcaps
        else:
            # If any input subcap under this aggregate cell has an
            # enrichment, light the pill.
            for sid in ai_enriched_subcaps:
                # cheap prefix match using parent ID structure
                if sid.startswith(c.id.split("::")[0]):
                    has_enrichment = True
                    break
        cells.append(
            HeatmapCell(
                id=c.id, label=c.label, parent_id=c.parent_id,
                score=c.score, band=c.band,
                peer_median=c.peer_median if peer else None,
                peer_gap=c.peer_gap if peer else None,
                is_thin_evidence=c.is_thin_evidence,
                cap_applied=c.cap_applied,
                cap_reason=c.cap_reason,
                issue_count=c.issue_count if issues else 0,
                aliased_from=c.aliased_from,
                has_enrichment=has_enrichment,
                enrichment_evidence_ids=cell_eids,
                data_source=c.data_source,
                parent_category_id=c.parent_category_id,
            )
        )

    # 7. value_chain bucketing (only meaningful at subcap zoom)
    buckets: list[ValueChainBucket] = []
    if hm == "value_chain" and zoom == "subcap" and ent.subvertical:
        vc_rows = (
            await session.execute(
                text(
                    """
                    SELECT subcap_id, value_chain_stages
                    FROM ccg_vc_mapping
                    WHERE version = :ver AND subvertical_code = :sv
                    """
                ),
                {"ver": catalog_version, "sv": ent.subvertical},
            )
        ).all()
        if not vc_rows:
            # Version fallback (2026-07): only v7.0 workbooks ship the
            # per-subcap VC tab, but 17/95 runs are pinned to older
            # catalogue versions with no ccg_vc_mapping rows. Subcap ids
            # overlap almost entirely across versions, so bucket via the
            # NEWEST version that has rows for this subvertical instead
            # of rendering the empty state.
            vc_rows = (
                await session.execute(
                    text(
                        """
                        SELECT subcap_id, value_chain_stages
                        FROM ccg_vc_mapping
                        WHERE subvertical_code = :sv
                          AND version = (
                            SELECT MAX(version) FROM ccg_vc_mapping
                            WHERE subvertical_code = :sv
                          )
                        """
                    ),
                    {"sv": ent.subvertical},
                )
            ).all()
            if vc_rows:
                warnings.append("value_chain_from_fallback_catalogue")
        by_stage: dict[str, list[str]] = {}
        cell_ids = {c.id for c in cells}
        for r in vc_rows:
            if r.subcap_id not in cell_ids:
                continue
            for stage in r.value_chain_stages or []:
                if not _is_real_vc_stage(stage):
                    continue
                bucket_ids = by_stage.setdefault(stage, [])
                if r.subcap_id not in bucket_ids:
                    bucket_ids.append(r.subcap_id)
        buckets = [
            ValueChainBucket(stage=stage, cell_ids=sorted(ids))
            for stage, ids in sorted(by_stage.items())
            # Single-subcap buckets are almost always footnote noise on
            # this catalogue; a real stage groups multiple capabilities.
            if len(ids) >= 2
        ]

    # Narrative — pillar + benchmark + issue-register prose from DOCX.
    sections = await load_sections_for_run(session, resolved.id, entity_id=resolved.entity_id)
    narrative = build_narrative_heatmap(sections)
    # Shared twin of export_startup_pages' pack bake (qa_pack_parity
    # structural contract): fold durable subcap_narratives rows into the
    # grid narrative for EXACTLY the surface the exporter merges — the
    # standard subcap-grain grid (pillar/category/value_chain snapshots
    # stay unmerged on both sides). 2026-07-04 fresh-DB regen sim: the
    # route serving None here vs the baked dicts was 14 structural
    # parity findings.
    if hm == "standard" and zoom == "subcap":
        per_md, per_meta = await load_subcap_synthesis_for_run(session, resolved.id)
        _nwrap = {"narrative": narrative}
        merge_subcap_synthesis(_nwrap, per_md, per_meta)
        narrative = _nwrap["narrative"]

    payload = HeatmapResponse(
        entity_display_id=display_id,
        run_request_id=resolved.request_id,
        # 2026-06-06 QA-3: `run` is the query-string `str | None`,
        # NOT the resolved DB row -- getattr(str, "status", None)
        # silently returned None for every call. The resolved object
        # is the run row; its `status` is the canonical source.
        run_status=resolved.status,
        zoom=zoom,
        view_mode=hm,
        subvertical=ent.subvertical,
        peer_overlay=peer,
        issue_overlay=issues,
        cells=cells,
        value_chain_buckets=buckets,
        catalogue_version=catalog_version,
        warnings=warnings,
        narrative=narrative,
    )
    # Audience-strip: nested peer_median / peer_gap / peer_cohort_size
    # on every cell are removed for `?view=customer` (the heatmap is a
    # peer-cohort surface, so this stripping is the difference between
    # an internal AE view and a sharable customer view).
    return strip_and_respond(payload, view.audience, HeatmapResponse)


@router.get("/{display_id}/heatmap/subcap/{subcap_id}")
async def heatmap_subcap(
    display_id: str,
    subcap_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    view: ViewModeDep,
    # 2026-06-06 QA-2: `run` query param so the subcap drawer follows
    # the same selected-run as the parent /heatmap call. Before, the
    # drawer always read the active run; an operator on a historical
    # run got drawer content from a DIFFERENT (current) run -- a
    # serious audit-trust violation.
    run: str | None = None,
) -> dict:
    """Single-subcap detail extracted from the same heatmap aggregation.

    Frontend page `HeatmapPage.tsx:420` calls this when an operator
    clicks a subcap cell to drill into per-subcap detail (narrative +
    cell metadata + evidence threading). Composes existing `heatmap()`
    at zoom=subcap and filters to the requested subcap_id. 404 when the
    subcap isn't present in the active run (e.g. catalogue-bumped
    subcap no longer mapped).

    2026-05-29 fixes:
      - Added `view: ViewModeDep` + pass every Query-defaulted arg
        explicitly so the nested heatmap() call behaves like a real
        request (previously missing `view` → 500; unresolved Query
        defaults → Pydantic literal_error).
      - Call heatmap() with `audience='internal'` internally so it
        returns the typed `HeatmapResponse` model (when audience is
        'customer' the parent route returns a JSONResponse, which
        breaks `.cells` / `.narrative` attribute access here). We
        then apply strip_and_respond on OUR composed dict so the
        customer audience strip still fires at THIS route's boundary.
    """
    from app.deps import ViewMode as _VM
    internal_view = _VM(audience="internal")
    full = await heatmap(
        display_id, _user, session, internal_view,
        zoom="subcap", hm="standard", peer=False, issues=False,
        run=run,
    )
    cells = [c for c in (full.cells or []) if c.id == subcap_id]
    if not cells:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"subcap {subcap_id} not present in active run",
        )
    # narrative is `dict | None` on HeatmapResponse — build_narrative_heatmap
    # in section_routing.py returns a plain dict, not a Pydantic model. Calling
    # `.model_dump()` here raised AttributeError whenever a narrative was
    # present. Handle both shapes defensively in case the schema evolves
    # (e.g. a future HeatmapNarrative Pydantic class would have model_dump).
    if full.narrative is None:
        narrative_out = None
    elif isinstance(full.narrative, dict):
        narrative_out = full.narrative
    else:
        narrative_out = full.narrative.model_dump()
    # Batch 6: enrich the response with the polished rationale +
    # polished cap_reason fetched directly from subcap_scores. The
    # polish layer caches per (subcap_id, source-hash), so the second
    # render is a single SELECT.
    #
    # 2026-07 (Part 6.3): resolve the SAME run the composed heatmap()
    # used so every extra lookup below (rationale, subcap_narratives,
    # evidence, issue caps) is run-consistent with the cells — the old
    # raw_row query hardcoded the ACTIVE run even when ?run= selected a
    # historical one.
    from app.services.run_resolver import maybe_resolve_entity_run
    resolved = await maybe_resolve_entity_run(
        session, display_id, run_request_id=run, allow_in_progress=True,
    )
    run_id = str(resolved.id) if resolved is not None else None

    polished_rationale: str | None = None
    polished_cap_reason: str | None = None
    if run_id is not None:
        raw_row = (await session.execute(
            text(
                "SELECT rationale, cap_reason FROM subcap_scores "
                "WHERE run_id = CAST(:rid AS uuid) AND subcap_id = :sid "
                "LIMIT 1"
            ),
            {"rid": run_id, "sid": subcap_id},
        )).first()
        if raw_row is not None:
            from app.services.narrative_polish import polish_narrative
            polished_rationale = polish_narrative(
                raw_row.rationale,
                target_kind="subcap",
                target_id=f"{display_id}:{subcap_id}:rationale",
                catalogue_version=full.catalogue_version or "n/a",
            )
            polished_cap_reason = polish_narrative(
                raw_row.cap_reason,
                target_kind="subcap",
                target_id=f"{display_id}:{subcap_id}:cap_reason",
                catalogue_version=full.catalogue_version or "n/a",
            )

    # ── Per-subcap synthesis (migration 051; llm > heuristic) ──────────
    # The durable subcap_narratives row is the drawer's primary "AI
    # synthesis" body — validator-passed Gemini rows win over the
    # deterministic composer floor; both carry their grounding E-IDs.
    synthesis_md: str | None = None
    synthesis_source: str | None = None
    synthesis_evidence_e_ids: list[str] = []
    synthesis_model: str | None = None
    if run_id is not None:
        try:
            nar_row = (await session.execute(
                text(
                    """
                    SELECT narrative_md, meta, evidence_e_ids, model
                    FROM subcap_narratives
                    WHERE run_id = CAST(:rid AS uuid) AND subcap_id = :sid
                    ORDER BY CASE meta WHEN 'llm' THEN 0 ELSE 1 END
                    LIMIT 1
                    """
                ),
                {"rid": run_id, "sid": subcap_id},
            )).first()
            if nar_row is not None:
                synthesis_md = nar_row.narrative_md
                synthesis_source = nar_row.meta
                synthesis_evidence_e_ids = list(nar_row.evidence_e_ids or [])
                synthesis_model = nar_row.model
        except Exception:
            pass  # table absent on legacy test DBs — drawer falls back

    # ── Evidence-first list (prototype "Source reports & evidence") ────
    # Structured rows so the drawer renders tier chip + claim + recency +
    # title + excerpt BEFORE any AI section, each chip opening the
    # EvidenceDrawer scoped to its E-ID.
    evidence: list[dict] = []
    if run_id is not None:
        ev_rows = (await session.execute(
            text(
                """
                SELECT e_id, source_name, source_url, excerpt, claim_type,
                       tier, recency_months, published_date, freshness_band
                FROM evidence_index
                WHERE run_id = CAST(:rid AS uuid)
                  AND :sid = ANY(linked_subcap_ids)
                ORDER BY tier ASC, recency_months ASC NULLS LAST, e_id ASC
                LIMIT 24
                """
            ),
            {"rid": run_id, "sid": subcap_id},
        )).all()
        # The drawer is the AE's verification surface, so every chip must carry a
        # clean citation and a quotable sentence. ~1/3 of evidence_index rows are
        # ingest artifacts — column-cut multi-E-ID cells ("E-006:F1, E-007:") whose
        # excerpt is an annotation blob ("[CEILING: L3.5] [E-006:F1] Net Zero
        # Pathway: … [PRESENCE…]"), plus "(no excerpt)" / "NEGATIVE PROXY:" stubs.
        # clean_and_dedupe_evidence recovers the citable id + human sentence, drops
        # the unquotable stubs, and dedupes fragments against the canonical E-###
        # row. Read-time only — the persisted rows are never mutated.
        evidence = clean_and_dedupe_evidence([
            {
                "e_id": r.e_id,
                "source_name": r.source_name,
                "source_url": r.source_url,
                "excerpt": (r.excerpt or "")[:400],
                "claim_type": r.claim_type,
                "tier": int(r.tier),
                "recency_months": r.recency_months,
                "published_date": (
                    r.published_date.isoformat() if r.published_date else None
                ),
                "freshness_band": r.freshness_band,
            }
            for r in ev_rows
        ])

    # ── Issue caps (prototype caps block: per-issue chip + Cap M{n}) ───
    # Open CLIENT issues linked to this subcap (exact id or category
    # prefix — registers mostly attribute at P1C2 grain), each with the
    # REAL cap level: the issue's own parsed caps for this subcap/its
    # category first, caps_applied_log as fallback.
    issues: list[dict] = []
    if run_id is not None:
        issue_rows = (await session.execute(
            text(
                """
                SELECT i.issue_id, i.title, i.severity, i.rationale,
                       i.opened_on, i.dma_impact, i.caps,
                       (SELECT c.cap_ceiling FROM caps_applied_log c
                         WHERE c.run_id = i.run_id
                           AND c.subcap_id = :sid
                         ORDER BY c.date_applied DESC NULLS LAST
                         LIMIT 1) AS cap_ceiling
                FROM issue_register i
                WHERE i.run_id = CAST(:rid AS uuid)
                  AND i.resolved_on IS NULL
                  AND COALESCE(i.status, 'OPEN') <> 'RESOLVED'
                  AND COALESCE(i.kind, 'client') = 'client'
                  AND EXISTS (
                      SELECT 1 FROM UNNEST(i.linked_subcap_ids) AS l(code)
                      WHERE :sid = l.code OR :sid LIKE l.code || '.%'
                  )
                ORDER BY i.issue_id
                LIMIT 5
                """
            ),
            {"rid": run_id, "sid": subcap_id},
        )).all()

        def _issue_cap_for_subcap(caps_json, fallback):
            caps_map = caps_json or {}
            if not isinstance(caps_map, dict):
                return fallback
            # Exact subcap first, then the longest matching prefix
            # (category-grain cap covers its member subcaps).
            if subcap_id in caps_map:
                return caps_map[subcap_id]
            best = None
            for code, level in caps_map.items():
                if subcap_id.startswith(f"{code}.") and \
                        (best is None or len(code) > best[0]):
                    best = (len(code), level)
            return best[1] if best else fallback

        issues = [
            {
                "issue_id": r.issue_id,
                "title": r.title,
                "severity": r.severity,
                "rationale": (r.rationale or "")[:280] or None,
                "opened_on": r.opened_on.isoformat() if r.opened_on else None,
                "cap_ceiling": _issue_cap_for_subcap(r.caps, r.cap_ceiling),
                "dma_impact": r.dma_impact,
            }
            for r in issue_rows
        ]

    body = {
        "entity_display_id": display_id,
        "subcap_id": subcap_id,
        "cells": [c.model_dump() for c in cells],
        "narrative": narrative_out,
        "polished_rationale": polished_rationale,
        "polished_cap_reason": polished_cap_reason,
        "synthesis_md": synthesis_md,
        "synthesis_source": synthesis_source,
        "synthesis_evidence_e_ids": synthesis_evidence_e_ids,
        "synthesis_model": synthesis_model,
        "evidence": evidence,
        "issues": issues,
        "catalogue_version": full.catalogue_version,
        "run_request_id": full.run_request_id,
    }
    # Apply audience strip at THIS route's boundary so peer fields /
    # internal-only cell metadata get removed for customer view.
    from app.services.audience_strip import strip_internal
    return strip_internal(body, view.audience)


# Footnote strings the v7.0 VC tab embeds alongside real stages
# ("Not applicable — …", "- (N/A)", "(applicable via CIB pattern)",
# "(SV-Specific: …)", "Indirect: …"). They are cell annotations, not
# value-chain stages — bucketing them would render junk stage cards.
_VC_NOISE_RE = _re.compile(
    r"^(not applicable|n/?a$|- \(n/a\)|\(applicable via |\(sv-specific:|indirect:)",
    _re.IGNORECASE,
)


def _is_real_vc_stage(stage: str) -> bool:
    s = (stage or "").strip()
    if len(s) < 3:
        return False
    return not _VC_NOISE_RE.match(s)


def _input_from_rows(score_row, name_row, *, aliased_from: str | None) -> SubcapInput:
    return SubcapInput(
        subcap_id=score_row.subcap_id,
        score=float(score_row.score),
        band=score_row.band,
        peer_median=(float(score_row.peer_median)
                     if score_row.peer_median is not None else None),
        peer_gap=(float(score_row.peer_gap)
                  if score_row.peer_gap is not None else None),
        is_thin_evidence=bool(score_row.is_thin_evidence),
        cap_applied=bool(score_row.cap_applied),
        cap_reason=score_row.cap_reason,
        aliased_from=aliased_from,
        pillar_id=name_row.pillar_id or "P?",
        category_id=name_row.category_id or "?",
        l1_id=name_row.l1_id or "?",
        pillar_name=name_row.pillar_name or "",
        category_name=name_row.category_name or "",
        l1_name=name_row.l1_name or "",
        subcap_name=name_row.subcap_name or "",
        data_source=getattr(score_row, "data_source", None) or "direct",
        parent_category_id=getattr(score_row, "parent_category_id", None),
    )
