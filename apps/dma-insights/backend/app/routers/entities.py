"""Entity directory + per-entity overview endpoints.

GET /api/v1/entities?owner=me|all   — directory; "me" gates by entity_assignments
GET /api/v1/entities/{display_id}/overview — D1 surface payload
GET /api/v1/entities/{display_id}/runs    — run history
"""
from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep, ViewModeDep
from app.schemas.entities import (
    DashboardResponse,
    EntityListResponse,
    EntityOverviewResponse,
    EntitySummary,
    RunListResponse,
    RunSummary,
    TopPlatform,
)
from app.services.audience_strip import strip_and_respond
from app.services.nlp.evidence_hygiene import clean_finding_items
from app.services.overview_cards import financial_trajectory_card, sentiment_card
from app.services.platform_display import platform_short
from app.services.section_routing import (
    build_narrative_overview,
    load_sections_for_run,
)

# Shared contamination twin — the SAME badge/nulling the offline pack
# patcher applies (qa_pack_parity structural contract on data_quality).
from app.services.startup_enrich import apply_contamination_badge

router = APIRouter(prefix="/api/v1", tags=["entities"])

# Coarse Setup→Final pill index (1..6) for the dashboard Active-runs card,
# keyed on the latest run's status. This is an HONEST low-resolution signal:
# the bot does not yet report a real per-batch number, so we map the run
# lifecycle states we DO have onto the 6-pill strip. Completed/ACTIVE runs
# return None — the Active-runs card only renders pills for in-progress
# runs, and `current_batch ?? 1` on the frontend defaults a just-started
# run to pill 1. Upgrades for free the moment the bot emits real batches.
_RUN_STATUS_TO_BATCH: dict[str, int] = {
    "IN_PROGRESS": 2,
    "PENDING_REVIEW": 5,
}

_CITY_STATE_RE = re.compile(r"([A-Z][A-Za-z.\-' ]+?),?\s+([A-Z]{2})\b")


def _clean_hq(raw: str | None) -> str | None:
    """Card-ready HQ string. firmographics.hq_address is inconsistent across
    the corpus — some rows hold a clean "City, ST", others a Python-repr dict
    ({'address': …, 'city': …, 'primary': …}) or a long street address. The
    entity card subtitle ("· San Antonio, TX") rendered those raw dicts
    verbatim. Normalise to a concise locality: prefer an explicit city(+state),
    else extract a "City, ST" from the address, else a short truncation.
    """
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("{"):
        try:
            import ast
            d = ast.literal_eval(s)
            if isinstance(d, dict):
                city = d.get("city") or d.get("hq_city")
                state = d.get("state") or d.get("hq_state")
                if city:
                    return f"{city}, {state}" if state else str(city)
                addr = (d.get("address") or d.get("primary")
                        or next((v for v in d.values()
                                 if isinstance(v, str) and v.strip()), None))
                s = str(addr) if addr else s
        except Exception:
            pass
    m = _CITY_STATE_RE.search(s)
    if m:
        return f"{m.group(1).strip()}, {m.group(2)}"
    return s[:42].rstrip(" ,;") + ("…" if len(s) > 42 else "")


@router.get("/entities", response_model=EntityListResponse)
async def list_entities(
    user: CurrentUserDep,
    session: SessionDep,
    owner: Literal["me", "all"] = Query(default="all"),
    subvertical: str | None = None,
    search: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> EntityListResponse:
    """Returns paginated entity summaries with assignment + last-run info."""
    where: list[str] = ["e.status = 'ACTIVE'"]
    params: dict[str, object] = {"limit": limit, "offset": offset}

    if owner == "me":
        where.append(
            "EXISTS (SELECT 1 FROM entity_assignments ea "
            "WHERE ea.entity_id = e.id AND ea.user_id = :uid "
            "AND ea.superseded_at IS NULL)"
        )
        params["uid"] = user.user_id
    if subvertical:
        where.append("e.subvertical = :sv")
        params["sv"] = subvertical
    if search:
        where.append("(e.name ILIKE :q OR e.display_id ILIKE :q)")
        params["q"] = f"%{search}%"
    where_clause = " AND ".join(where)

    rows = (
        await session.execute(
            text(
                f"""
                WITH latest_run AS (
                    -- Widen to include PENDING_REVIEW so newly-ingested
                    -- runs waiting on a catalogue load still surface a
                    -- card state instead of looking like the entity has
                    -- never been assessed. Order ACTIVE > PENDING_REVIEW
                    -- > IN_PROGRESS so the "current" run for the card is
                    -- the most authoritative one.
                    SELECT DISTINCT ON (entity_id)
                        entity_id, id AS run_id, request_id, completed_at,
                        status, data_source,
                        assessment_date,
                        overall_score AS official_overall
                    FROM runs
                    WHERE status IN ('ACTIVE', 'IN_PROGRESS', 'PENDING_REVIEW')
                    ORDER BY entity_id,
                             CASE status WHEN 'ACTIVE' THEN 0
                                         WHEN 'PENDING_REVIEW' THEN 1
                                         ELSE 2 END,
                             completed_at DESC NULLS LAST, created_at DESC
                ),
                pillar_agg AS (
                    -- Aggregate per-pillar means over the latest run's
                    -- subcap_scores. P1/P2/P3/P4 are derived from the
                    -- first 2 chars of the subcap_id (canonical schema:
                    -- {{Pillar}}{{Category}}.{{Cap}}.{{Subcap}}).
                    SELECT
                      ss.run_id,
                      LEFT(ss.subcap_id, 2) AS pillar_id,
                      AVG(ss.score)::float AS mean_score,
                      COUNT(*) AS n
                    FROM subcap_scores ss
                    WHERE ss.run_id IN (SELECT run_id FROM latest_run)
                    GROUP BY ss.run_id, LEFT(ss.subcap_id, 2)
                ),
                pillar_pivot AS (
                    SELECT
                      run_id,
                      jsonb_object_agg(pillar_id, ROUND(mean_score::numeric, 2))
                        AS pillar_scores_json,
                      SUM(n) AS subcap_count,
                      AVG(mean_score)::float AS overall_score
                    FROM pillar_agg
                    GROUP BY run_id
                ),
                owner AS (
                    SELECT DISTINCT ON (ea.entity_id)
                        ea.entity_id, u.email, u.name
                    FROM entity_assignments ea
                    LEFT JOIN users u ON u.id = ea.user_id
                    WHERE ea.superseded_at IS NULL
                    ORDER BY ea.entity_id, ea.assigned_at DESC
                )
                SELECT
                    e.id, e.display_id, e.name, e.domain, e.subvertical,
                    e.lobs, e.status, e.updated_at,
                    lr.completed_at AS last_run_at,
                    lr.request_id AS last_run_request_id,
                    lr.status AS last_run_status,
                    lr.data_source AS data_source,
                    lr.assessment_date,
                    pp.pillar_scores_json,
                    COALESCE(lr.official_overall, pp.overall_score)
                        AS overall_score,
                    pp.subcap_count,
                    owner.email AS owner_email,
                    owner.name AS owner_name,
                    -- 2026-06-06 QA-M4: per-entity open alerts count.
                    -- Uses ix_alerts_open partial index (entity_id, opened_at)
                    -- so it scans the open-alerts subset only.
                    COALESCE(
                        (SELECT COUNT(*) FROM alerts a
                          WHERE a.entity_id = e.id AND a.closed_at IS NULL),
                        0
                    ) AS open_alerts,
                    -- Prototype parity (2026-06-13): " · HQ" suffix + the
                    -- entity-card top-OSS chip. hq is firmographics.hq_address;
                    -- the LATERAL is the single highest-fit platform on the
                    -- latest run (no N+1 — one join per entity row).
                    f.hq_address AS hq,
                    tp.platform_id AS top_platform_id,
                    tp.fit_score AS top_fit_score,
                    COUNT(*) OVER () AS total_count
                FROM entities e
                LEFT JOIN latest_run lr ON lr.entity_id = e.id
                LEFT JOIN pillar_pivot pp ON pp.run_id = lr.run_id
                LEFT JOIN owner ON owner.entity_id = e.id
                LEFT JOIN firmographics f ON f.entity_id = e.id
                LEFT JOIN LATERAL (
                    SELECT ps.platform_id, ps.fit_score
                    FROM platform_scores ps
                    WHERE ps.run_id = lr.run_id
                    ORDER BY ps.fit_score DESC NULLS LAST
                    LIMIT 1
                ) tp ON TRUE
                WHERE {where_clause}
                ORDER BY e.updated_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).all()

    total = int(rows[0].total_count) if rows else 0
    items: list[EntitySummary] = []
    for r in rows:
        pscores: dict[str, float] | None = None
        if r.pillar_scores_json:
            # asyncpg decodes jsonb_object_agg as a dict already.
            raw = r.pillar_scores_json
            if isinstance(raw, str):
                import json as _json
                try:
                    raw = _json.loads(raw)
                except Exception:
                    raw = {}
            if isinstance(raw, dict):
                pscores = {k: float(v) for k, v in raw.items()
                           if v is not None and k in ("P1", "P2", "P3", "P4")}
        status_lc = (r.last_run_status or "").upper()
        top_platform = None
        # Only surface the top-OSS chip when there is a REAL fit signal
        # (fit_score > 0). The corpus backfill does not compute platform
        # fit yet (all 0.0), and ORDER BY fit_score DESC over all-zero ties
        # returns an arbitrary platform — surfacing it would be a fabricated
        # "SF 0". The prototype renders this chip conditionally ({top ? …}),
        # so omitting it here matches the wireframe exactly. Lights up for
        # free once platform fit is computed.
        if getattr(r, "top_platform_id", None) and (r.top_fit_score or 0) > 0:
            top_platform = TopPlatform(
                platform_id=r.top_platform_id,
                short=platform_short(r.top_platform_id),
                fit_score=float(r.top_fit_score),
            )
        items.append(EntitySummary(
            id=str(r.id),
            display_id=r.display_id,
            name=r.name,
            domain=r.domain,
            subvertical=r.subvertical,
            lobs=list(r.lobs or []),
            status=r.status,
            last_run_at=r.last_run_at,
            last_run_request_id=r.last_run_request_id,
            owner_email=r.owner_email,
            owner_name=r.owner_name,
            updated_at=r.updated_at,
            last_run_status=r.last_run_status,
            data_source=r.data_source,
            in_progress=status_lc in ("IN_PROGRESS", "PENDING_REVIEW"),
            pillar_scores=pscores or None,
            overall_score=float(r.overall_score) if r.overall_score is not None else None,
            subcap_count=int(r.subcap_count) if r.subcap_count is not None else None,
            open_alerts=int(r.open_alerts) if r.open_alerts is not None else 0,
            assessment_date=r.assessment_date,
            hq=_clean_hq(getattr(r, "hq", None)),
            top_platform=top_platform,
            current_batch=_RUN_STATUS_TO_BATCH.get(status_lc),
        ))
    return EntityListResponse(items=items, total=total, owner_filter=owner)


async def _safe_mapping_rows(session, sql: str, params: dict) -> list[dict]:
    """Best-effort read-only fetch for the Gemini read-path merge.

    Two failure shapes it must survive (both observed against a
    pre-045 local DB, 2026-07-02):
      1. The relation itself is missing (pre-migration deployment) —
         return [] so the merge is a no-op.
      2. An EARLIER best-effort probe in the same request (e.g. the
         migration-045 evidence_summary read) already failed and left
         the session transaction ABORTED — every subsequent query then
         raises InFailedSQLTransaction. Roll back and retry ONCE so a
         schema gap in one optional surface can't silently disable the
         Gemini merge. The overview handler is read-only, so the
         rollback discards nothing.
    """
    for attempt in (0, 1):
        try:
            res = await session.execute(text(sql), params)
            return [dict(r) for r in res.mappings().all()]
        except Exception:
            try:
                await session.rollback()
            except Exception:  # pragma: no cover — connection gone
                return []
            if attempt:
                return []
    return []


@router.get(
    "/entities/{display_id}/overview",
    response_model=EntityOverviewResponse,
)
async def entity_overview(
    display_id: str,
    user: CurrentUserDep,
    view: ViewModeDep,
    session: SessionDep,
    run: str | None = None,
) -> EntityOverviewResponse:
    """D1 Overview payload."""
    ent_row = (
        await session.execute(
            text(
                """
                SELECT e.id, e.display_id, e.name, e.domain, e.subvertical, e.lobs,
                       e.status, e.updated_at
                FROM entities e
                WHERE e.display_id = :did
                """
            ),
            {"did": display_id},
        )
    ).first()
    if ent_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"entity {display_id} not found"
        )

    # 2026-06-05: honour ?run= via resolve_entity_run, then re-fetch the
    # full row for the extra fields the overview surface needs
    # (data_source, evidence_mode, scqa, why_now_signals, top_findings).
    # Pre-fix this endpoint silently rendered the ACTIVE run regardless
    # of which run was selected in ClientBar.
    from app.services.run_resolver import maybe_resolve_entity_run
    resolved = await maybe_resolve_entity_run(
        session, display_id, run_request_id=run, allow_in_progress=True,
    )
    run_row = None
    assumptions_register_data: list[dict] = []
    if resolved is not None:
        # C11 (2026-06-07): assumptions_register surfaced from runs
        # JSONB column. Try with the new column; fall back to the
        # legacy SELECT without it so envs without migration 030
        # applied still return valid data (assumptions_register
        # stays empty list).
        try:
            run_row = (
                await session.execute(
                    text(
                        """
                        SELECT id, request_id, status, data_source, evidence_mode,
                               ccg_catalog_version, started_at, completed_at,
                               created_at, updated_at,
                               assessment_date, assessment_date_source,
                               overall_score,
                               scqa, why_now_signals, top_findings,
                               assumptions_register
                        FROM runs
                        WHERE id = :rid
                        LIMIT 1
                        """
                    ),
                    {"rid": resolved.id},
                )
            ).first()
            if run_row is not None and run_row.assumptions_register:
                raw = run_row.assumptions_register
                if isinstance(raw, list):
                    assumptions_register_data = raw
        except Exception:
            # Column missing (migration 030 not yet applied) — retry
            # with the legacy column list so the rest of the response
            # still populates.
            run_row = (
                await session.execute(
                    text(
                        """
                        SELECT id, request_id, status, data_source, evidence_mode,
                               ccg_catalog_version, started_at, completed_at,
                               created_at, updated_at,
                               scqa, why_now_signals, top_findings
                        FROM runs
                        WHERE id = :rid
                        LIMIT 1
                        """
                    ),
                    {"rid": resolved.id},
                )
            ).first()

    firm_row = (
        await session.execute(
            text(
                """
                SELECT aum_usd, revenue_usd, headcount, hq_address, primary_regulator,
                       leadership, thought_leadership, sentiment, clay_synced_at,
                       tl_synced_at, sentiment_synced_at, parsed_facts, narrative_md,
                       financial_highlights
                FROM firmographics WHERE entity_id = :eid
                """
            ),
            {"eid": ent_row.id},
        )
    ).first()

    entity = EntitySummary(
        id=str(ent_row.id),
        display_id=ent_row.display_id,
        name=ent_row.name,
        domain=ent_row.domain,
        subvertical=ent_row.subvertical,
        lobs=list(ent_row.lobs or []),
        status=ent_row.status,
        updated_at=ent_row.updated_at,
    )

    # 2026-06-11 corpus QA: 24/95 runs persist no why_now_signals —
    # deterministic fallback derives up to 3 triggers from the entity's
    # latest timeline_events (kind → trigger label), provenance-flagged.
    why_now_data = []
    if run_row is not None and run_row.why_now_signals:
        # Read-time hygiene (same contract as the findings polish below):
        # persisted signal details carry analyst-note shout leads
        # ("FINTRAC ENFORCEMENT ACTION", "PRIOR FINDING REVERSED") —
        # proofread is deterministic, idempotent and never grows text.
        from app.services.nlp.quality import proofread as _pf
        from app.services.startup_enrich import _headline_safe as _hs
        for _s in run_row.why_now_signals:
            if isinstance(_s, dict):
                _s = dict(_s)
                for _fld in ("text", "detail"):
                    if isinstance(_s.get(_fld), str) and _s[_fld].strip():
                        _s[_fld] = _pf(_s[_fld]) or _s[_fld]
                # S16 headline gate: the persisted LABEL is served raw and can
                # still carry a trailing ellipsis/dangling connective or a
                # quoted score — normalize it at the serialization chokepoint so
                # the pack (and the UI) never render a mid-thought headline.
                if isinstance(_s.get("label"), str) and _s["label"].strip():
                    _s["label"] = _hs(_s["label"]) or _s["label"]
            why_now_data.append(_s)
    elif run_row is not None:
        tl = (await session.execute(text(
            """
            SELECT kind, title, event_date, e_id FROM timeline_events
            WHERE entity_id = :eid ORDER BY event_date DESC NULLS LAST
            LIMIT 3
            """), {"eid": ent_row.id})).all()
        kind_label = {"acquisition": "M&A", "regulatory": "REGULATORY",
                      "leadership": "LEADERSHIP", "milestone": "MILESTONE"}
        why_now_data = [
            {"kind": kind_label.get((t.kind or "").lower(), (t.kind or "SIGNAL").upper()),
             "text": t.title,
             "date": t.event_date.isoformat() if t.event_date else None,
             "evidence": [t.e_id] if t.e_id else [],
             "derived_from": "timeline_events"}
            for t in tl
        ]

    # 2026-06-11 corpus QA: 18/95 runs persist no top_findings (their
    # packages shipped none) — the wireframe's Top-findings card sat
    # empty for them. Read-time fallback: derive the top 4 from the
    # run's own insight_cards (severity-ranked), flagged via
    # derived_from so the UI can badge provenance. Persisted findings
    # always win.
    top_findings_data = []
    if run_row is not None and run_row.top_findings:
        # Read-time hygiene: the persisted findings on ~14 clients carry raw
        # ingest annotation ("[ERS: 4.60] [FACT] [E-021:F1] … (T1, LEGACY):") and
        # one client persisted a leaked prompt-scaffold fragment AS a finding.
        # clean_finding_items strips the annotation and drops the scaffold so the
        # D1 story reads like consultant prose. Persisted rows are untouched.
        top_findings_data = clean_finding_items(list(run_row.top_findings))
        from app.services.narrative_polish import polish_narrative
        from app.services.startup_enrich import finding_headline
        for tf in top_findings_data:
            if isinstance(tf, dict):
                for fld in ("title", "name", "what", "why", "body",
                            "so_what"):
                    if isinstance(tf.get(fld), str) and tf[fld].strip():
                        tf[fld] = polish_narrative(
                            tf[fld], target_kind="finding",
                            target_id=f"{run_row.id}:{tf.get('title', '')[:24]}:{fld}",
                        ) or tf[fld]
                # v3 headline standard (read-time, same contract as the
                # deepen-composed path): note fragments / band jargon
                # regenerate from the finding's own first claim
                from app.services.startup_enrich import (
                    _headline_safe as _hs2,
                )
                from app.services.startup_enrich import (
                    finalize_title_text,
                )
                for fld in ("title", "name"):
                    if isinstance(tf.get(fld), str) and tf[fld].strip():
                        tf[fld] = finding_headline(
                            tf[fld], tf.get("subcap_id"), tf.get("score"),
                            tf.get("peer_median"),
                            what=tf.get("what") or tf.get("body"))
                        # finding_headline can regenerate the title from the
                        # BODY, which may still carry an internal register code
                        # ("… unknown (URF-01)") or ellipsis — finalize it, then
                        # S16-normalize (no trailing dangle/ellipsis/score).
                        tf[fld] = finalize_title_text(tf[fld], tf.get("what") or "")
                        tf[fld] = _hs2(tf[fld]) or tf[fld]
    elif run_row is not None:
        ic_rows = (await session.execute(text(
            """
            SELECT ic_id, title,
                   COALESCE(NULLIF(so_what_text,''), NULLIF(why_text,''),
                            what_text, '') AS body,
                   severity, linked_subcap_id
            FROM insight_cards WHERE run_id = :rid
            ORDER BY CASE lower(severity) WHEN 'critical' THEN 0
                     WHEN 'high' THEN 1 WHEN 'opportunity' THEN 2
                     ELSE 3 END, ic_id LIMIT 4
            """), {"rid": run_row.id})).all()
        top_findings_data = [
            {"title": r.title, "body": r.body,
             "evidence": [], "platforms": [],
             "subcap_id": r.linked_subcap_id,
             "derived_from": "insight_cards"}
            for r in ic_rows
        ]

    run = None
    if run_row is not None:
        # getattr: the legacy fallback query (pre-039 column list) omits
        # the run-identity fields — RunSummary defaults keep them None.
        _ovr = getattr(run_row, "overall_score", None)
        run = RunSummary(
            id=str(run_row.id),
            request_id=run_row.request_id,
            status=run_row.status,
            data_source=run_row.data_source,
            evidence_mode=run_row.evidence_mode,
            ccg_catalog_version=run_row.ccg_catalog_version,
            started_at=run_row.started_at,
            completed_at=run_row.completed_at,
            created_at=run_row.created_at,
            updated_at=run_row.updated_at,
            assessment_date=getattr(run_row, "assessment_date", None),
            assessment_date_source=getattr(
                run_row, "assessment_date_source", None,
            ),
            overall_score=float(_ovr) if _ovr is not None else None,
        )

    firmographics: dict | None = None
    if firm_row is not None:
        firmographics = {
            "aum_usd": float(firm_row.aum_usd) if firm_row.aum_usd is not None else None,
            "revenue_usd": float(firm_row.revenue_usd) if firm_row.revenue_usd is not None else None,
            "headcount": firm_row.headcount,
            "hq_address": firm_row.hq_address,
            "primary_regulator": firm_row.primary_regulator,
            "leadership": firm_row.leadership,
            "thought_leadership": firm_row.thought_leadership,
            "sentiment": firm_row.sentiment,
            "clay_synced_at": firm_row.clay_synced_at,
            "tl_synced_at": firm_row.tl_synced_at,
            "sentiment_synced_at": firm_row.sentiment_synced_at,
            # F5c: analyst-prose paragraph from the Client Profile DOCX
            # Entity Profile section. D5 Context "About" panel reads it.
            "narrative_md": firm_row.narrative_md,
            # 2026-06-11 corpus QA: 95/95 rows carry financial_highlights
            # (trend/CAGR/asset prose + metrics) but the overview never
            # emitted it — the D1 card mines it for CAGR/Trend rows.
            "financial_highlights": firm_row.financial_highlights,
        }
        # Batch 6 (migration 027): inline the parser-extracted string-form
        # firmographics so the React Overview FirmographicsRows reads them
        # at top-level. The DB stores them in `parsed_facts JSONB`; we
        # flatten the dict into the response so the frontend doesn't have
        # to know about the storage layout. Top-level fields win over
        # parsed_facts when both populate (Clay-synced data is more
        # authoritative than parser regex extraction).
        pf = firm_row.parsed_facts or {}
        # 2026-06-11 corpus QA: only 3 keys were whitelisted, so any
        # other parser-extracted fact (cagr, footprint, employee/branch
        # count variants, charter…) never reached the UI and the D1
        # firmographics card read as blank for most entities. Flatten
        # EVERY scalar parsed fact; columns still win on collision.
        for k, v in pf.items():
            if v is None or isinstance(v, dict | list):
                continue
            if firmographics.get(k) is None:
                firmographics[k] = v
        # Also expose `hq` so the React render layer (which reads
        # `firm.hq` per the Batch 4.2 port) doesn't need to know that
        # the DB column is named `hq_address`.
        if firm_row.hq_address and "hq" not in firmographics:
            firmographics["hq"] = firm_row.hq_address

    # Pillar score rollup — D1 ScoreRing + PillarBars read this. Before
    # 2026-05-26 the response always set `pillar_scores=[]` because the
    # router never aggregated subcap_scores — the UI rendered an empty
    # ScoreRing even when 60+ scored subcaps were in the DB. Fix: compute
    # per-pillar AVG + overall AVG inline.
    #
    # Also computes peer_median per pillar (AVG of subcap-level
    # peer_medians from `subcap_scores.peer_median`) so the PillarBar's
    # peer-median tick renders from REAL benchmark data instead of the
    # earlier hardcoded `entity_score + 0.3` fake value. peer_median
    # may be NULL when the run hasn't been peer-benchmarked yet; UI
    # then hides the tick + the delta chip.
    #
    # State branches:
    #   no_run / no_scores  → empty list (UI renders "no data" copy)
    #   scores only         → 4 rows, peer_median=null per pillar
    #   scores + benchmarks → 4 rows with real peer_median
    pillar_scores: list[dict] = []
    if run_row is not None:
        ps_rows = (
            await session.execute(
                text(
                    """
                    SELECT
                        substring(subcap_id, 1, 2) AS pillar_id,
                        ROUND(AVG(score)::numeric, 2) AS pillar_score,
                        ROUND(
                            AVG(peer_median) FILTER (WHERE peer_median IS NOT NULL)
                            ::numeric, 2
                        ) AS peer_median,
                        COUNT(*) AS subcaps_scored,
                        COUNT(peer_median) AS peer_benchmarked
                    FROM subcap_scores
                    WHERE run_id = :rid AND score IS NOT NULL
                    GROUP BY 1
                    ORDER BY 1
                    """
                ),
                {"rid": run_row.id},
            )
        ).all()
        pillar_scores = [
            {
                "pillar_id": r.pillar_id,
                "score": float(r.pillar_score) if r.pillar_score is not None else None,
                "peer_median": (
                    float(r.peer_median) if r.peer_median is not None else None
                ),
                "subcaps_scored": int(r.subcaps_scored),
                "peer_benchmarked": int(r.peer_benchmarked or 0),
            }
            for r in ps_rows
        ]

    # Narrative — populated from document_sections via section_routing.
    # `None` when no Assessment_Report DOCX was ingested for this run.
    narrative: dict | None = None
    if run_row is not None:
        # entity_id scoping (cross-wire defense, 2026-06-10): D1 was the
        # ONE call site that didn't pass it — the exact page where the
        # "CU"-renders-FNBO mis-attachment was reported.
        sections = await load_sections_for_run(
            session, run_row.id, entity_id=resolved.entity_id,
        )
        narrative = build_narrative_overview(sections)

    # Evidence freshness rollup — populated from evidence_index when the
    # migration is applied; gracefully degrades to None on older schemas.
    evidence_freshness: dict | None = None
    try:
        fresh_row = (
            await session.execute(
                text(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE freshness_band = 'current')  AS current_count,
                        COUNT(*) FILTER (WHERE freshness_band = 'aging')    AS aging_count,
                        COUNT(*) FILTER (WHERE freshness_band = 'dated')    AS dated_count,
                        COUNT(*) FILTER (WHERE freshness_band = 'stale')    AS stale_count,
                        COUNT(*) FILTER (WHERE freshness_band = 'undated')  AS undated_count,
                        COUNT(*)                                              AS total,
                        MIN(published_date)                                   AS oldest_published_date,
                        -- (CURRENT_DATE - published_date) is INTEGER days in
                        -- Postgres (date - date → int, NOT an interval), so
                        -- EXTRACT(EPOCH FROM ...) fails with "function
                        -- pg_catalog.extract(unknown, integer) does not
                        -- exist". Divide the day-count directly by the mean
                        -- days-per-month (2026-05-29 fix).
                        AVG((CURRENT_DATE - published_date) / 30.4375)
                            FILTER (WHERE published_date IS NOT NULL)         AS mean_age_months,
                        CASE WHEN COUNT(*) = 0 THEN 0
                             ELSE ROUND(
                                100.0 * COUNT(*) FILTER (WHERE freshness_band = 'stale')
                                / COUNT(*), 2)
                        END                                                   AS stale_pct
                    FROM evidence_index
                    WHERE entity_id = :eid
                    """
                ),
                {"eid": ent_row.id},
            )
        ).first()
        if fresh_row is not None and (fresh_row.total or 0) > 0:
            evidence_freshness = {
                "current_count": int(fresh_row.current_count or 0),
                "aging_count": int(fresh_row.aging_count or 0),
                "dated_count": int(fresh_row.dated_count or 0),
                "stale_count": int(fresh_row.stale_count or 0),
                "undated_count": int(fresh_row.undated_count or 0),
                "total": int(fresh_row.total or 0),
                "oldest_published_date": (
                    fresh_row.oldest_published_date.isoformat()
                    if fresh_row.oldest_published_date else None
                ),
                "median_age_months": (
                    round(float(fresh_row.mean_age_months), 1)
                    if fresh_row.mean_age_months is not None else None
                ),
                "stale_pct": float(fresh_row.stale_pct or 0),
            }
    except Exception:  # pragma: no cover — pre-migration deployments
        evidence_freshness = None

    # Persistent intelligence card — None until first profile recompute.
    intelligence_profile: dict | None = None
    try:
        ip_row = (
            await session.execute(
                text(
                    """
                    SELECT total_runs, maturity_velocity, recurring_themes,
                           emerging_themes, persistent_gap_subcap_ids,
                           closed_gap_subcap_ids, intelligence_summary_md,
                           computed_at, catalogue_version
                    FROM customer_intelligence_profiles
                    WHERE entity_id = :eid
                    """
                ),
                {"eid": ent_row.id},
            )
        ).first()
        if ip_row is not None:
            intelligence_profile = {
                "total_runs": int(ip_row.total_runs or 0),
                "maturity_velocity": (
                    float(ip_row.maturity_velocity)
                    if ip_row.maturity_velocity is not None else None
                ),
                "recurring_themes": list(ip_row.recurring_themes or []),
                "emerging_themes": list(ip_row.emerging_themes or []),
                "persistent_gap_subcap_ids": list(
                    ip_row.persistent_gap_subcap_ids or []
                ),
                "closed_gap_subcap_ids": list(ip_row.closed_gap_subcap_ids or []),
                "intelligence_summary_md": ip_row.intelligence_summary_md,
                "computed_at": (
                    ip_row.computed_at.isoformat() if ip_row.computed_at else None
                ),
                "catalogue_version": ip_row.catalogue_version,
            }
    except Exception:  # pragma: no cover — pre-migration deployments
        intelligence_profile = None

    # Pull the latest run's parser_warnings JSONB so D1 can surface a
    # chip when the run was parsed with warnings. The AE shouldn't have
    # to know to look in Admin → Import Audit (which they can't access
    # anyway) to learn that the data they're drawing conclusions from
    # had structural issues during ingest.
    parser_warnings: dict | None = None
    if run_row is not None:
        try:
            pw_row = (
                await session.execute(
                    text("SELECT parser_warnings FROM runs WHERE id = :rid"),
                    {"rid": run_row.id},
                )
            ).first()
            if pw_row is not None and pw_row.parser_warnings:
                pw = pw_row.parser_warnings
                # Accept dict (post-migration) OR list-of-strings (legacy).
                if isinstance(pw, dict) and pw:
                    parser_warnings = pw
                elif isinstance(pw, list) and pw:
                    # Coerce legacy list into a dict keyed by index for UI.
                    parser_warnings = {f"warning_{i}": str(w) for i, w in enumerate(pw)}
        except Exception:
            # Best-effort — pre-migration deployments may lack the column.
            parser_warnings = None

    # Migration 045 (Part 4.6): the three "Evidence & benchmarks" JSONB
    # surfaces written by derive_evidence_surfaces. Best-effort separate
    # query (parser_warnings pattern) so pre-045 deployments keep
    # serving the rest of the overview; None → frontend honest-empty.
    evidence_summary_data: dict | None = None
    coverage_stats_data: dict | None = None
    uncertainty_bands_data: dict | None = None
    if run_row is not None:
        try:
            ds_row = (
                await session.execute(
                    text(
                        "SELECT evidence_summary, coverage_stats, "
                        "uncertainty_bands FROM runs WHERE id = :rid"
                    ),
                    {"rid": run_row.id},
                )
            ).first()
            if ds_row is not None:
                if isinstance(ds_row.evidence_summary, dict):
                    evidence_summary_data = ds_row.evidence_summary
                if isinstance(ds_row.coverage_stats, dict):
                    coverage_stats_data = ds_row.coverage_stats
                if isinstance(ds_row.uncertainty_bands, dict):
                    uncertainty_bands_data = ds_row.uncertainty_bands
        except Exception:
            # Columns missing (migration 045 not yet applied) — the
            # three cards keep their honest-empty state.
            pass

    # ── Gemini read-path merge (RC1 fix, 2026-07-02) ──────────────────
    # The deploy pipeline persists Gemini output (vertex_synthesis_cache
    # via enrich_corpus; parsed_facts._gemini_extracted; ai_enrichments)
    # but this endpoint never read any of it back — enrichment was
    # invisible to AEs. Merge policy lives in the pure helper
    # services/overview_gemini_merge.merge_gemini_overview (unit-tested
    # with faked rows): validator-passed rows only; deterministic values
    # never overwritten; every merged field stamped source:"vertex" +
    # model_id + synthesized_at. Both reads degrade silently on
    # pre-migration schemas (table absent → no merge).
    _gem_cache_rows = await _safe_mapping_rows(
        session,
        """
        SELECT surface, output_text, output_json, model,
               created_at, cited_evidence_ids, validators_passed
        FROM vertex_synthesis_cache
        WHERE target_kind = 'entity'
          AND target_id = :did
          AND surface IN ('why_now', 'firmographics_extraction',
                          'thought_leadership_extraction')
          AND validators_passed
          AND invalidated_at IS NULL
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY surface, created_at DESC
        """,
        {"did": display_id},
    )
    _gem_enrich_rows = await _safe_mapping_rows(
        session,
        """
        SELECT surface, enrichment_text, model, created_at,
               grounding_evidence_ids, validators_passed
        FROM ai_enrichments
        WHERE target_kind = 'entity'
          AND target_id = :eid
          AND validators_passed
          AND superseded_by IS NULL
        ORDER BY created_at DESC
        LIMIT 8
        """,
        {"eid": ent_row.id},
    )
    if _gem_cache_rows or _gem_enrich_rows:
        from app.services.overview_gemini_merge import merge_gemini_overview
        why_now_data, firmographics = merge_gemini_overview(
            why_now_signals=why_now_data,
            firmographics=firmographics,
            parsed_facts=(firm_row.parsed_facts or {}) if firm_row else {},
            cache_rows=_gem_cache_rows,
            enrichment_rows=_gem_enrich_rows,
        )

    # Server-computed overall_score so every surface (directory card,
    # overview ScoreRing, scorecard export) renders the same number.
    # It MUST equal the canonical the scorecard/dashboard/summary render —
    # COALESCE(official runs.overall_score, AVG(subcap score)). The prior
    # mean(pillar_scores) is UNWEIGHTED, so it drifts from the subcap-count-
    # weighted canonical on 26/94 clients — the AE saw a different overall on
    # the overview than on every other surface (audit 2026-07-03). Fall back
    # to mean(pillars) only if the run is unresolved.
    overall_score: float | None = None
    if run_row is not None:
        try:
            # Replicate the directory/scorecard producer EXACTLY:
            # COALESCE(official runs.overall_score, AVG(pillar mean)) where
            # each pillar mean = AVG(subcap score) over LEFT(subcap_id,2). This
            # is the unweighted mean-of-pillar-means, NOT a flat AVG of subcaps.
            _canon = (await session.execute(text(
                "WITH pa AS ("
                "  SELECT AVG(s.score) AS mean_score FROM subcap_scores s "
                "  WHERE s.run_id = :rid GROUP BY LEFT(s.subcap_id, 2)"
                ") "
                "SELECT COALESCE(r0.overall_score, "
                "                (SELECT AVG(mean_score) FROM pa)) "
                "FROM runs r0 WHERE r0.id = :rid"
            ), {"rid": run_row.id})).scalar()
            if _canon is not None:
                overall_score = round(float(_canon), 2)
        except Exception:
            overall_score = None
    if overall_score is None and pillar_scores:
        nums = [p["score"] for p in pillar_scores
                if isinstance(p, dict) and isinstance(p.get("score"), int | float)]
        if nums:
            overall_score = round(sum(nums) / len(nums), 2)

    payload = EntityOverviewResponse(
        entity=entity,
        run=run,
        scqa=run_row.scqa if run_row else None,
        why_now_signals=why_now_data,
        top_findings=top_findings_data,
        firmographics=firmographics,
        pillar_scores=pillar_scores,
        narrative=narrative,
        evidence_freshness=evidence_freshness,
        intelligence_profile=intelligence_profile,
        parser_warnings=parser_warnings,
        overall_score=overall_score,
        assumptions_register=assumptions_register_data,
        evidence_summary=evidence_summary_data,
        coverage_stats=coverage_stats_data,
        uncertainty_bands=uncertainty_bands_data,
        # Project the firmographics blobs into the D1 card shapes — the data
        # is derived into firmographics but the FinancialTrajectoryCard /
        # SentimentCard read the top-level fields (audit 2026-07-02: both
        # rendered empty despite populated firmographics).
        financial_trajectory=financial_trajectory_card(
            (firmographics or {}).get("financial_highlights")),
        sentiment=sentiment_card((firmographics or {}).get("sentiment")),
    )
    # Shared contamination twin (qa_pack_parity structural contract): the
    # offline pack patcher stamps the source-misattribution data_quality
    # badge (+ tier-A ticker nulling) on the SERIALIZED page — run the
    # SAME function on the live payload so a confidently-wrong assessment
    # never renders unflagged on either serve path. Contamination is a
    # property of the rendered JSON (foreign tickers/run-ids/FI names in
    # the prose), so serve time is the only place both twins see the same
    # input.
    _ov_dict = payload.model_dump(mode="json")
    if apply_contamination_badge(_ov_dict):
        payload = EntityOverviewResponse.model_validate(_ov_dict)
    # Apply audience-strip + return — helper bypasses schema
    # revalidation on customer view so stripped keys stay GONE
    # (see strip_and_respond docstring for the recurring null-leak
    # bug it eliminates).
    return strip_and_respond(payload, view.audience, EntityOverviewResponse)


@router.get("/entities/{display_id}/runs", response_model=RunListResponse)
async def entity_runs(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> RunListResponse:
    ent_row = (
        await session.execute(
            text("SELECT id FROM entities WHERE display_id = :did"),
            {"did": display_id},
        )
    ).first()
    if ent_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"entity {display_id} not found")
    # 2026-06-05 QA finding 8: compute overall_score (AVG over
    # subcap_scores) per run so the Score column on ClientRunsPage
    # actually renders. Uses a single CTE join instead of N+1.
    rows = (
        await session.execute(
            text(
                """
                SELECT r.id, r.request_id, r.status, r.data_source,
                       r.evidence_mode, r.ccg_catalog_version,
                       r.started_at, r.completed_at,
                       r.created_at, r.updated_at,
                       r.assessment_date, r.assessment_date_source,
                       COALESCE(r.overall_score, agg.overall_score)
                           AS overall_score,
                       agg.subcap_count
                FROM runs r
                LEFT JOIN (
                    SELECT run_id, AVG(score) AS overall_score,
                           COUNT(*) AS subcap_count
                    FROM subcap_scores GROUP BY run_id
                ) agg ON agg.run_id = r.id
                WHERE r.entity_id = :eid
                ORDER BY r.assessment_date DESC NULLS LAST,
                         r.created_at DESC LIMIT :lim
                """
            ),
            {"eid": ent_row.id, "lim": limit},
        )
    ).all()
    items = [
        RunSummary(
            id=str(r.id), request_id=r.request_id, status=r.status,
            data_source=r.data_source, evidence_mode=r.evidence_mode,
            ccg_catalog_version=r.ccg_catalog_version,
            started_at=r.started_at, completed_at=r.completed_at,
            created_at=r.created_at, updated_at=r.updated_at,
            overall_score=float(r.overall_score) if r.overall_score is not None else None,
            subcap_count=int(r.subcap_count) if r.subcap_count is not None else None,
            assessment_date=r.assessment_date,
            assessment_date_source=r.assessment_date_source,
        )
        for r in rows
    ]
    active_id = next((i.id for i in items if i.status == "ACTIVE"), None)
    return RunListResponse(items=items, active_run_id=active_id)


@router.get("/entities/{display_id}/run-history")
async def entity_run_history(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
):
    """Return the full supersede chain for an entity's runs.

    State transitions:
      no runs exist for display_id → 404
      run has no parent_request_id → parent_chain = []
      run has a parent → parent_chain walked newest→oldest via request_id
    """
    from app.schemas.enrichment import RunHistoryItem, RunHistoryResponse

    ent_row = (
        await session.execute(
            text("SELECT id::text AS id FROM entities WHERE display_id = :did"),
            {"did": display_id},
        )
    ).first()
    if ent_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"entity {display_id} not found")
    rows = (
        await session.execute(
            text(
                """
                SELECT r.request_id, r.parent_request_id, r.status,
                       r.ccg_catalog_version, r.started_at, r.completed_at,
                       r.assessment_date,
                       (SELECT COUNT(*) FROM subcap_scores s
                          WHERE s.run_id = r.id) AS subcap_count,
                       (SELECT COUNT(*) FROM evidence_index ev
                          WHERE ev.run_id = r.id) AS evidence_count
                FROM runs r
                WHERE r.entity_id = CAST(:eid AS uuid)
                ORDER BY r.assessment_date DESC NULLS LAST,
                         r.completed_at DESC NULLS LAST, r.created_at DESC
                """
            ),
            {"eid": ent_row.id},
        )
    ).all()

    # Build chain walker from request_id → parent
    rid_to_parent = {r.request_id: r.parent_request_id for r in rows}
    parent_chain: list[str] = []
    if rows:
        cursor = rows[0].request_id
        seen = set()
        while rid_to_parent.get(cursor):
            parent = rid_to_parent[cursor]
            if parent in seen:
                break  # cycle defense
            seen.add(parent)
            parent_chain.append(parent)
            cursor = parent

    items = [
        RunHistoryItem(
            request_id=r.request_id,
            parent_request_id=r.parent_request_id,
            status=r.status,
            catalogue_version=r.ccg_catalog_version,
            completed_at=r.completed_at,
            started_at=r.started_at,
            subcap_count=int(r.subcap_count or 0),
            evidence_count=int(r.evidence_count or 0),
            assessment_date=r.assessment_date,
        )
        for r in rows
    ]
    return RunHistoryResponse(
        entity_id=ent_row.id, items=items, parent_chain=parent_chain,
    )


@router.get("/entities/{display_id}/archetype")
async def entity_archetype(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
):
    """Closest maturity-archetype lookup.

    State transitions:
      entity has no subvertical or no ACTIVE run → insufficient_data=True
      no peer_archetypes rows for (subvertical, catalogue_version)
        → insufficient_data=True
      otherwise → closest archetype by Euclidean distance over the
        entity's subcap-score vector vs. each archetype centroid
    """
    from app.schemas.enrichment import ArchetypeMatch, ArchetypeResponse

    ent_row = (
        await session.execute(
            text(
                """
                SELECT e.id::text AS eid, e.subvertical,
                       (SELECT r.ccg_catalog_version FROM runs r
                          WHERE r.entity_id = e.id AND r.status = 'ACTIVE'
                          LIMIT 1) AS catalogue_version,
                       (SELECT r.id FROM runs r
                          WHERE r.entity_id = e.id AND r.status = 'ACTIVE'
                          LIMIT 1) AS active_run
                FROM entities e WHERE display_id = :did
                """
            ),
            {"did": display_id},
        )
    ).first()
    if ent_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"entity {display_id} not found")
    if not ent_row.subvertical or not ent_row.catalogue_version:
        return ArchetypeResponse(insufficient_data=True)

    arch_rows = (
        await session.execute(
            text(
                """
                SELECT archetype_label, subvertical, catalogue_version,
                       centroid_vector, defining_subcap_ids, sample_count,
                       silhouette_score
                FROM peer_archetypes
                WHERE subvertical = :sv AND catalogue_version = :ver
                ORDER BY sample_count DESC
                """
            ),
            {"sv": ent_row.subvertical, "ver": ent_row.catalogue_version},
        )
    ).all()
    if not arch_rows:
        return ArchetypeResponse(insufficient_data=True)

    # Entity's score vector along each archetype's defining_subcap_ids.
    # We compute distance per archetype individually (their defining
    # subcap sets may differ).
    scores_map = {}
    score_rows = (
        await session.execute(
            text(
                "SELECT subcap_id, score FROM subcap_scores "
                "WHERE run_id = :rid"
            ),
            {"rid": ent_row.active_run},
        )
    ).all()
    for s in score_rows:
        scores_map[s.subcap_id] = float(s.score)

    matches: list[ArchetypeMatch] = []
    for a in arch_rows:
        defining = list(a.defining_subcap_ids or [])
        centroid = [float(x) for x in (a.centroid_vector or [])]
        if not defining or not centroid or len(defining) != len(centroid):
            continue
        # Euclidean distance over common subcaps
        sq = 0.0
        used = 0
        for sid, c in zip(defining, centroid, strict=False):
            v = scores_map.get(sid)
            if v is None:
                continue
            sq += (v - c) ** 2
            used += 1
        if used == 0:
            continue
        dist = (sq / used) ** 0.5
        matches.append(
            ArchetypeMatch(
                archetype_label=a.archetype_label,
                subvertical=a.subvertical,
                catalogue_version=a.catalogue_version,
                distance=round(dist, 4),
                defining_subcap_ids=defining,
                sample_count=int(a.sample_count or 0),
                silhouette_score=(
                    float(a.silhouette_score) if a.silhouette_score is not None
                    else None
                ),
            )
        )
    matches.sort(key=lambda m: m.distance)
    closest = matches[0] if matches else None
    return ArchetypeResponse(
        closest=closest,
        all_archetypes=matches,
        insufficient_data=closest is None,
    )


@router.get("/archetypes")
async def list_archetypes(
    _user: CurrentUserDep,
    session: SessionDep,
    subvertical: str | None = Query(None),
    catalogue_version: str | None = Query(None),
):
    """List peer archetypes (D6 Health "Patterns" tab data source).

    State transitions:
      no filters     → returns every archetype in `peer_archetypes`
      subvertical    → filters to that subvertical
      catalogue_version → filters to that catalogue version
      no rows match  → returns {items: []}; UI shows empty state
    """
    sql = """
        SELECT archetype_label, subvertical, catalogue_version,
               defining_subcap_ids, sample_count, silhouette_score,
               computed_at
        FROM peer_archetypes
        WHERE 1=1
    """
    params: dict[str, object] = {}
    if subvertical:
        sql += " AND subvertical = :sv"
        params["sv"] = subvertical
    if catalogue_version:
        sql += " AND catalogue_version = :ver"
        params["ver"] = catalogue_version
    sql += " ORDER BY subvertical, sample_count DESC NULLS LAST"
    try:
        rows = (await session.execute(text(sql), params)).all()
    except Exception:
        rows = []
    items = [
        {
            "archetype_label": r.archetype_label,
            "subvertical": r.subvertical,
            "catalogue_version": r.catalogue_version,
            "defining_subcap_ids": list(r.defining_subcap_ids or [])[:5],
            "sample_count": int(r.sample_count or 0),
            "silhouette_score": (
                float(r.silhouette_score) if r.silhouette_score is not None
                else None
            ),
            "computed_at": r.computed_at,
        }
        for r in rows
    ]
    return {"items": items}


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    user: CurrentUserDep,
    session: SessionDep,
    scope: Literal["mine", "all"] = Query(default="all"),
) -> DashboardResponse:
    """Dashboard tiles + active-run list."""
    now_row = (
        await session.execute(text("SELECT NOW() AS now"))
    ).first()
    now = now_row.now if now_row is not None else None

    # Tile: my_clients
    my_clients = (
        await session.execute(
            text(
                "SELECT COUNT(*) AS n FROM entity_assignments "
                "WHERE user_id = :uid AND superseded_at IS NULL"
            ),
            {"uid": user.user_id},
        )
    ).scalar_one()

    # Tile: active runs
    if scope == "mine":
        active_rows = (
            await session.execute(
                text(
                    """
                    SELECT r.id, r.request_id, r.status, r.data_source,
                           r.evidence_mode, r.ccg_catalog_version,
                           r.started_at, r.completed_at, r.created_at, r.updated_at
                    FROM runs r
                    JOIN entity_assignments ea ON ea.entity_id = r.entity_id
                       AND ea.superseded_at IS NULL
                    WHERE r.status IN ('ACTIVE', 'IN_PROGRESS')
                      AND ea.user_id = :uid
                    ORDER BY r.updated_at DESC LIMIT 50
                    """
                ),
                {"uid": user.user_id},
            )
        ).all()
    else:
        active_rows = (
            await session.execute(
                text(
                    """
                    SELECT id, request_id, status, data_source, evidence_mode,
                           ccg_catalog_version, started_at, completed_at,
                           created_at, updated_at
                    FROM runs WHERE status IN ('ACTIVE', 'IN_PROGRESS')
                    ORDER BY updated_at DESC LIMIT 50
                    """
                )
            )
        ).all()

    open_alerts = (
        await session.execute(
            text("SELECT COUNT(*) AS n FROM alerts WHERE closed_at IS NULL")
        )
    ).scalar_one()

    in_progress = sum(1 for r in active_rows if r.status == "IN_PROGRESS")
    # 2026-06-06 QA-M5: insight_count tile -- pre-fix the frontend
    # Dashboard read `data.insight_count` via cast (no such field) so the
    # KPI always rendered "—". Sources from insight_cards rows linked to
    # ACTIVE runs only so superseded runs' cards don't inflate the count.
    insight_count = (
        await session.execute(
            text(
                "SELECT COUNT(*) AS n FROM insight_cards ic "
                "JOIN runs r ON r.id = ic.run_id "
                "WHERE r.status='ACTIVE'"
            )
        )
    ).scalar_one()
    # 2026-07-02 (plan Part 11.2): count DISTINCT entities in the SAME
    # entity set the directory lists (entities.status='ACTIVE'). Pre-fix
    # this was COUNT(*) over runs — duplicate-entity twin runs (e.g. the
    # IMA/MidFirst/Pentegra duplicate folders) made the tile read 95
    # while the directory showed 94 (the exporter dedupes, the dashboard
    # didn't). Parity-by-construction with list_entities/assessment_count.
    recent_completions = (
        await session.execute(
            text(
                "SELECT COUNT(DISTINCT r.entity_id) AS n FROM runs r "
                "JOIN entities e ON e.id = r.entity_id AND e.status='ACTIVE' "
                "WHERE r.status='ACTIVE' "
                "AND r.completed_at >= NOW() - INTERVAL '7 days'"
            )
        )
    ).scalar_one()
    # 2026-07-02 (plan Part 11.2): the tile rendered "—" whenever no
    # version row was frozen — locally/backfill only the persist_package
    # STUB rows exist (frozen_at IS NULL, see package_persist.py), so the
    # strict `frozen_at IS NOT NULL` filter matched nothing. Prefer the
    # canonical frozen row, fall back to the latest released (stub) row,
    # then to the version the ACTIVE runs actually resolve against.
    catalogue_version = (
        await session.execute(
            text(
                "SELECT version FROM ccg_catalog_versions "
                "ORDER BY (frozen_at IS NOT NULL) DESC, "
                "released_at DESC NULLS LAST LIMIT 1"
            )
        )
    ).first()
    if catalogue_version is None:
        catalogue_version = (
            await session.execute(
                text(
                    "SELECT ccg_catalog_version AS version FROM runs "
                    "WHERE status='ACTIVE' AND ccg_catalog_version IS NOT NULL "
                    "GROUP BY ccg_catalog_version "
                    "ORDER BY COUNT(*) DESC LIMIT 1"
                )
            )
        ).first()

    # 2026-06-13 prototype parity: the wireframe's KPI strip needs an
    # "Active assessments" count + an "Avg maturity" value as SERVER tiles
    # (they were a client-side reduce before → stale/empty on first paint).
    assessment_count = (
        await session.execute(
            text(
                "SELECT COUNT(DISTINCT e.id) AS n FROM entities e "
                "JOIN runs r ON r.entity_id = e.id AND r.status='ACTIVE' "
                "WHERE e.status='ACTIVE'"
            )
        )
    ).scalar_one()
    # avg_maturity mirrors the entity-card overall EXACTLY: per ACTIVE run,
    # COALESCE(official runs.overall_score, AVG of per-pillar means), then
    # averaged across entities. Parity-by-construction with list_entities.
    avg_maturity = (
        await session.execute(
            text(
                """
                WITH lr AS (
                    SELECT DISTINCT ON (entity_id)
                        entity_id, id AS run_id, overall_score AS official
                    FROM runs WHERE status='ACTIVE'
                    ORDER BY entity_id, completed_at DESC NULLS LAST,
                             created_at DESC
                ),
                pillar_means AS (
                    SELECT run_id, LEFT(subcap_id, 2) AS p,
                           AVG(score)::float AS m
                    FROM subcap_scores
                    WHERE run_id IN (SELECT run_id FROM lr)
                    GROUP BY run_id, LEFT(subcap_id, 2)
                ),
                per_run AS (
                    SELECT run_id, AVG(m)::float AS overall
                    FROM pillar_means GROUP BY run_id
                )
                SELECT AVG(COALESCE(lr.official, pr.overall))::float AS avg
                FROM lr LEFT JOIN per_run pr ON pr.run_id = lr.run_id
                WHERE COALESCE(lr.official, pr.overall) IS NOT NULL
                """
            )
        )
    ).scalar_one_or_none()

    tiles = [
        {"kind": "my_clients", "label": "My clients",
         "value": int(my_clients), "last_refreshed_at": now},
        {"kind": "assessment_count", "label": "Active assessments",
         "value": int(assessment_count), "last_refreshed_at": now},
        {"kind": "avg_maturity", "label": "Avg maturity",
         "value": round(float(avg_maturity), 2) if avg_maturity is not None else 0.0,
         "last_refreshed_at": now},
        {"kind": "active_runs", "label": "In progress",
         "value": int(in_progress), "last_refreshed_at": now},
        {"kind": "open_alerts", "label": "Open alerts",
         "value": int(open_alerts), "last_refreshed_at": now},
        {"kind": "recent_completions", "label": "Completed (7d)",
         "value": int(recent_completions), "last_refreshed_at": now},
        {"kind": "insight_count", "label": "Insight cards",
         "value": int(insight_count), "last_refreshed_at": now},
        {"kind": "catalogue_version", "label": "Catalogue",
         "value": catalogue_version.version if catalogue_version else "—",
         "last_refreshed_at": now},
    ]
    return DashboardResponse(
        scope=scope,
        tiles=list(tiles),  # type: ignore[arg-type]
        active_runs=[
            RunSummary(
                id=str(r.id), request_id=r.request_id, status=r.status,
                data_source=r.data_source, evidence_mode=r.evidence_mode,
                ccg_catalog_version=r.ccg_catalog_version,
                started_at=r.started_at, completed_at=r.completed_at,
                created_at=r.created_at, updated_at=r.updated_at,
            )
            for r in active_rows
        ],
    )
