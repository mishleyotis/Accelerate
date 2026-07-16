"""D6 Health + global Alerts endpoints.

D6 is Analyst+ only (AE gets 403). Alerts mirror role-gating for the waive
action (Analyst+).
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from app.deps import (
    CurrentUserDep,
    SessionDep,
    ViewModeDep,
    require_analyst,
)
from app.schemas.drive_feedback import FeedbackRefreshResponse
from app.schemas.health import (
    AlertActionRequest,
    AlertListResponse,
    AlertOut,
    AuditLogsOut,
    CapsAppliedOut,
    CrossEntityPatternOut,
    EvidenceAgeOut,
    GlobalPatternOut,
    GlobalPatternsResponse,
    HealthPatternsResponse,
    HealthResponse,
    QaVerdictOut,
    SafeguardGateOut,
)
from app.services.audience_strip import strip_and_respond
from app.services.section_routing import (
    build_narrative_health,
    load_sections_for_run,
)

health_router = APIRouter(prefix="/api/v1/entities", tags=["health"])
alerts_router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@health_router.get(
    "/{display_id}/health",
    response_model=HealthResponse,
    dependencies=[Depends(require_analyst)],
)
async def health(
    display_id: str,
    session: SessionDep,
    view: ViewModeDep,
    run: str | None = None,
) -> HealthResponse:
    # 2026-06-05: honour ?run= via the soft resolver (health gracefully
    # renders empty when no runs yet).
    from app.services.run_resolver import maybe_resolve_entity_run
    resolved = await maybe_resolve_entity_run(
        session, display_id, run_request_id=run,
    )
    if resolved is None:
        return HealthResponse(
            entity_display_id=display_id, run_request_id=None,
            thin_evidence_subcap_ids=[], safeguard_gates=[], alerts=[],
        )

    thin_rows = (
        await session.execute(
            text(
                "SELECT subcap_id FROM subcap_scores "
                "WHERE run_id = :rid AND is_thin_evidence = TRUE"
            ),
            {"rid": resolved.id},
        )
    ).all()
    gates = (
        await session.execute(
            text(
                """
                SELECT gate_id, status, detail, evaluated_at
                FROM safeguard_gates WHERE run_id = :rid
                ORDER BY gate_id
                """
            ),
            {"rid": resolved.id},
        )
    ).all()
    alerts_rows = (
        await session.execute(
            text(
                """
                SELECT id, kind, severity, title, body,
                       linked_subcap_ids, linked_e_ids,
                       opened_at, closed_at, resolution,
                       evidence_count, recommended_action, proxy_searched
                FROM alerts
                WHERE entity_id = :eid AND closed_at IS NULL
                ORDER BY CASE severity WHEN 'critical' THEN 0
                                       WHEN 'high' THEN 1
                                       WHEN 'medium' THEN 2
                                       WHEN 'low' THEN 3 ELSE 4 END,
                         opened_at DESC
                """
            ),
            {"eid": resolved.entity_id},
        )
    ).all()

    # B-5: per-evidence freshness for the Age tab. `freshness_band` is the
    # STORED generated column (migration 018) — surface it directly, oldest
    # first (stale → undated → dated → aging → current) so the tab leads
    # with the rows most in need of refresh.
    age_rows = (
        await session.execute(
            text(
                """
                SELECT e_id, source_name, tier, published_date,
                       recency_months,
                       COALESCE(freshness_band, 'undated') AS freshness_band
                FROM evidence_index
                WHERE run_id = :rid
                ORDER BY
                  CASE COALESCE(freshness_band, 'undated')
                    WHEN 'stale'   THEN 0
                    WHEN 'undated' THEN 1
                    WHEN 'dated'   THEN 2
                    WHEN 'aging'   THEN 3
                    WHEN 'current' THEN 4 ELSE 5 END,
                  published_date ASC NULLS FIRST,
                  e_id
                """
            ),
            {"rid": resolved.id},
        )
    ).all()

    # C10 (2026-06-07): caps_applied_log rows for the Gates tab. Sorted
    # by subcap_id then log_id for deterministic render order. Empty
    # list when the source package shipped no caps_applied_log.csv (or
    # migration 028 hasn't been applied yet — silent best-effort).
    caps_rows: list[CapsAppliedOut] = []
    try:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT log_id, subcap_id, cap_type, trigger_condition,
                           cap_ceiling, trigger_evidence, affected_categories,
                           severity, date_applied, recalc_verified
                    FROM caps_applied_log
                    WHERE run_id = :rid
                    ORDER BY subcap_id, log_id
                    """
                ),
                {"rid": resolved.id},
            )
        ).all()
        caps_rows = [
            CapsAppliedOut(
                log_id=r.log_id,
                subcap_id=r.subcap_id,
                cap_type=r.cap_type,
                trigger_condition=r.trigger_condition,
                cap_ceiling=r.cap_ceiling,
                trigger_evidence=list(r.trigger_evidence or []),
                affected_categories=list(r.affected_categories or []),
                severity=r.severity,
                date_applied=r.date_applied,
                recalc_verified=r.recalc_verified,
            )
            for r in rows
        ]
    except Exception:
        # Table missing (migration 028 not yet applied) — silently
        # return an empty list. The Gates tab renders without the
        # cap-events section in that case.
        caps_rows = []

    # C10 WSFS cascade (2026-06-07): when a package ships no
    # `caps_applied_log.csv` (WSFS-shape) the equivalent semantics live
    # inline on `subcap_scores.cap_reason` (per-subcap cap descriptor).
    # Cascade those into the same response so the Caps tab is
    # uniformly populated across all 5 real fixtures.
    #
    # Avoids duplicates: when the same subcap appears in BOTH the
    # canonical log AND on subcap_scores.cap_reason (Alma + Calprivate
    # paths overlap), the canonical log wins because it's richer
    # (Cap_Ceiling + Trigger_Evidence list + Affected_Categories).
    canonical_subcap_ids = {r.subcap_id for r in caps_rows}
    try:
        subcap_cap_rows = (
            await session.execute(
                text(
                    """
                    SELECT subcap_id, cap_reason
                    FROM subcap_scores
                    WHERE run_id = :rid
                      AND cap_applied IS TRUE
                      AND cap_reason IS NOT NULL
                      AND cap_reason <> ''
                    ORDER BY subcap_id
                    """
                ),
                {"rid": resolved.id},
            )
        ).all()
        for sr in subcap_cap_rows:
            if sr.subcap_id in canonical_subcap_ids:
                continue
            caps_rows.append(
                CapsAppliedOut(
                    # Synthesized log_id; readers should treat it as a
                    # synthetic anchor not a foreign-key reference.
                    log_id=f"INLINE-{sr.subcap_id}",
                    subcap_id=sr.subcap_id,
                    cap_type="INLINE_SUBCAP",
                    trigger_condition=sr.cap_reason,
                    cap_ceiling=None,
                    trigger_evidence=[],
                    affected_categories=[],
                    severity=None,
                    date_applied=None,
                    recalc_verified=None,
                )
            )
    except Exception:
        # Subcap_scores table missing or `cap_reason` not yet
        # populated by the parser — silent. Caps tab still renders
        # the canonical-log rows when available.
        pass

    # C5 (2026-06-07): L1 + L2 QA verdicts (the 2-stage governance
    # escalation chain). Both are nullable; the Gates tab renders
    # "L1 not reported" when the package shipped only L2 (Alma /
    # WSFS / Nicola pattern). Try/except so envs without migration
    # 029 applied return None cleanly.
    qa_verdict_l1: QaVerdictOut | None = None
    qa_verdict_l2: QaVerdictOut | None = None
    # C7 (2026-06-07): bot governance audit logs (D6 Audit tab,
    # Analyst-only). Loaded from runs.audit_logs JSONB; null when
    # the package shipped no audit-log files (Alma / Calprivate /
    # WSFS pattern).
    audit_logs: AuditLogsOut | None = None
    try:
        verdict_row = (
            await session.execute(
                text(
                    """
                    SELECT qa_verdict_l1, qa_verdict_l2, audit_logs
                    FROM runs WHERE id = :rid
                    """
                ),
                {"rid": resolved.id},
            )
        ).first()
        if verdict_row is not None:
            if verdict_row.qa_verdict_l1:
                qa_verdict_l1 = QaVerdictOut.model_validate(
                    verdict_row.qa_verdict_l1
                )
            if verdict_row.qa_verdict_l2:
                qa_verdict_l2 = QaVerdictOut.model_validate(
                    verdict_row.qa_verdict_l2
                )
            if verdict_row.audit_logs:
                audit_logs = AuditLogsOut.model_validate(
                    verdict_row.audit_logs
                )
    except Exception:
        # Columns missing (migration 029 / 031 not yet applied) —
        # silent. Gates tab renders without verdict chain + audit logs.
        qa_verdict_l1 = None
        qa_verdict_l2 = None
        audit_logs = None

    now = datetime.now(tz=UTC)
    sections = await load_sections_for_run(session, resolved.id, entity_id=resolved.entity_id)
    narrative = build_narrative_health(sections)
    payload = HealthResponse(
        entity_display_id=display_id,
        run_request_id=resolved.request_id,
        thin_evidence_subcap_ids=sorted(r.subcap_id for r in thin_rows),
        safeguard_gates=[
            SafeguardGateOut(
                gate_id=g.gate_id, status=g.status,
                detail=g.detail, evaluated_at=g.evaluated_at,
            )
            for g in gates
        ],
        alerts=[
            AlertOut(
                id=str(a.id), kind=a.kind, severity=a.severity, title=a.title,
                body=a.body,
                linked_subcap_ids=list(a.linked_subcap_ids or []),
                linked_e_ids=list(a.linked_e_ids or []),
                opened_at=a.opened_at, closed_at=a.closed_at,
                resolution=a.resolution,
                age_days=(now - a.opened_at).days,
                evidence_count=a.evidence_count,
                recommended_action=a.recommended_action,
                proxy_searched=a.proxy_searched,
            )
            for a in alerts_rows
        ],
        evidence_age=[
            EvidenceAgeOut(
                e_id=ag.e_id,
                source_name=ag.source_name,
                tier=int(ag.tier) if ag.tier is not None else None,
                published_date=ag.published_date,
                recency_months=ag.recency_months,
                freshness_band=ag.freshness_band,
            )
            for ag in age_rows
        ],
        caps_applied=caps_rows,
        qa_verdict_l1=qa_verdict_l1,
        qa_verdict_l2=qa_verdict_l2,
        audit_logs=audit_logs,
        narrative=narrative,
    )
    return strip_and_respond(payload, view.audience, HealthResponse)


@health_router.get(
    "/{display_id}/health/version-diff",
    dependencies=[Depends(require_analyst)],
)
async def health_version_diff(
    display_id: str,
    run_a: str,
    run_b: str,
    session: SessionDep,
) -> dict:
    """Run-vs-run diff for the D6 Health page (`frontend/src/pages/
    HealthPage.tsx:235`). Compares two runs of the same entity and
    returns: score delta per pillar, alerts opened/resolved, gates
    that flipped state, thin-evidence subcap turnover. Analyst+ only.

    `run_a` / `run_b` accept `request_id` (REQ-… / DMA-ASM-… /
    DMA-RES-…) — the canonical cross-system ID stored on `runs`.
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
    rows = (
        await session.execute(
            text(
                """
                SELECT id, request_id, completed_at
                FROM runs
                WHERE entity_id = :eid AND request_id IN (:a, :b)
                """
            ),
            {"eid": ent.id, "a": run_a, "b": run_b},
        )
    ).all()
    by_req = {r.request_id: r for r in rows}
    a_row, b_row = by_req.get(run_a), by_req.get(run_b)
    if a_row is None or b_row is None:
        missing = [
            x for x, r in (("run_a", a_row), ("run_b", b_row)) if r is None
        ]
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"missing runs for entity {display_id}: {missing}",
        )

    # `runs` has no denormalised overall_score / pillar_scores columns —
    # both are computed from subcap_scores (overall = AVG; per-pillar =
    # AVG grouped by the leading two chars of subcap_id, PnCn.n.n). This
    # mirrors the prospecting scorecard + dashboard derivations.
    async def _scores(run_id: str) -> tuple[float | None, dict[str, float]]:
        overall = (
            await session.execute(
                text("SELECT AVG(score)::float FROM subcap_scores WHERE run_id = :rid"),
                {"rid": run_id},
            )
        ).scalar_one_or_none()
        pillar_rows = (
            await session.execute(
                text(
                    "SELECT LEFT(subcap_id, 2) AS pid, AVG(score)::float AS avg "
                    "FROM subcap_scores WHERE run_id = :rid "
                    "GROUP BY LEFT(subcap_id, 2)"
                ),
                {"rid": run_id},
            )
        ).all()
        return overall, {r.pid: r.avg for r in pillar_rows}

    a_overall, a_pillars = await _scores(a_row.id)
    b_overall, b_pillars = await _scores(b_row.id)

    def _pillar_delta(a: dict | None, b: dict | None) -> dict:
        a, b = a or {}, b or {}
        keys = sorted(set(a) | set(b))
        return {k: float((b.get(k) or 0) - (a.get(k) or 0)) for k in keys}

    # Thin-evidence subcap turnover.
    thin_a = {
        r.subcap_id for r in (
            await session.execute(
                text(
                    "SELECT subcap_id FROM subcap_scores "
                    "WHERE run_id = :rid AND is_thin_evidence = TRUE"
                ),
                {"rid": a_row.id},
            )
        ).all()
    }
    thin_b = {
        r.subcap_id for r in (
            await session.execute(
                text(
                    "SELECT subcap_id FROM subcap_scores "
                    "WHERE run_id = :rid AND is_thin_evidence = TRUE"
                ),
                {"rid": b_row.id},
            )
        ).all()
    }
    # Alerts opened in B but not A, and vice-versa.
    alerts_a = {
        r.title for r in (
            await session.execute(
                text(
                    "SELECT DISTINCT title FROM alerts "
                    "WHERE entity_id = :eid AND opened_at <= "
                    "  COALESCE(:ts, NOW())"
                ),
                {"eid": ent.id, "ts": a_row.completed_at},
            )
        ).all()
    }
    alerts_b = {
        r.title for r in (
            await session.execute(
                text(
                    "SELECT DISTINCT title FROM alerts "
                    "WHERE entity_id = :eid AND opened_at <= "
                    "  COALESCE(:ts, NOW())"
                ),
                {"eid": ent.id, "ts": b_row.completed_at},
            )
        ).all()
    }
    return {
        "entity_display_id": display_id,
        "run_a": run_a,
        "run_b": run_b,
        "overall_score_delta": float((b_overall or 0) - (a_overall or 0)),
        "pillar_score_delta": _pillar_delta(a_pillars, b_pillars),
        "thin_subcap_added": sorted(thin_b - thin_a),
        "thin_subcap_resolved": sorted(thin_a - thin_b),
        "alerts_opened": sorted(alerts_b - alerts_a),
        "alerts_resolved": sorted(alerts_a - alerts_b),
    }


@alerts_router.get("", response_model=AlertListResponse)
async def list_alerts(
    _user: CurrentUserDep,
    session: SessionDep,
    resolution: str | None = None,
) -> AlertListResponse:
    # 2026-06-05 QA finding 9: JOIN entities so AlertsPage can navigate
    # to the real entity (pre-fix the page tried to derive an entity
    # slug from `linked_subcap_ids[0][:6]` which never matched).
    # 2026-07-02 (plan Part 11.2): LATERAL fetches the latest waive-action
    # note so the Waived tab renders each alert WITH its rationale (the
    # ≥50-char note the waive action enforces). One join, no N+1.
    # `?resolution=waive` scopes the page to waived rows — without it the
    # LIMIT-200 window over 1.5k+ open alerts crowds every closed row out
    # and the Waived tab would render empty even when waivers exist.
    where = ""
    params: dict[str, object] = {}
    if resolution is not None:
        where = "WHERE a.resolution = :res AND a.closed_at IS NOT NULL"
        params["res"] = resolution
    rows = (
        await session.execute(
            text(
                f"""
                SELECT a.id, a.kind, a.severity, a.title, a.body,
                       a.linked_subcap_ids, a.linked_e_ids,
                       a.opened_at, a.closed_at, a.resolution,
                       a.evidence_count, a.recommended_action,
                       a.proxy_searched,
                       e.id AS entity_id,
                       e.display_id AS entity_display_id,
                       e.name AS entity_name,
                       w.note AS waive_note
                FROM alerts a
                LEFT JOIN entities e ON e.id = a.entity_id
                LEFT JOIN LATERAL (
                    SELECT aa.note FROM alert_actions aa
                    WHERE aa.alert_id = a.id AND aa.action = 'waive'
                    ORDER BY aa.created_at DESC LIMIT 1
                ) w ON TRUE
                {where}
                ORDER BY a.opened_at DESC LIMIT 200
                """
            ),
            params,
        )
    ).all()
    now = datetime.now(tz=UTC)
    items = [
        AlertOut(
            id=str(r.id), kind=r.kind, severity=r.severity, title=r.title,
            body=r.body,
            linked_subcap_ids=list(r.linked_subcap_ids or []),
            linked_e_ids=list(r.linked_e_ids or []),
            opened_at=r.opened_at, closed_at=r.closed_at,
            resolution=r.resolution,
            age_days=(now - r.opened_at).days,
            entity_id=str(r.entity_id) if r.entity_id else None,
            entity_display_id=r.entity_display_id,
            entity_name=r.entity_name,
            evidence_count=r.evidence_count,
            recommended_action=r.recommended_action,
            proxy_searched=r.proxy_searched,
            waive_note=r.waive_note,
        )
        for r in rows
    ]
    # True corpus-wide open count — NOT len() of the LIMIT-200 page
    # (the sidebar badge + dashboard KPI read this; with the alerts
    # producer live the corpus carries >200 open rows).
    open_count = int((await session.execute(text(
        "SELECT COUNT(*) FROM alerts WHERE closed_at IS NULL"
    ))).scalar_one())
    return AlertListResponse(items=items, open_count=open_count)


@alerts_router.post(
    "/{alert_id}/actions",
    dependencies=[Depends(require_analyst)],
)
async def post_alert_action(
    alert_id: str,
    body: AlertActionRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, str]:
    if body.action == "waive" and (body.note is None or len(body.note) < 50):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="waive action requires a note of at least 50 characters",
        )
    await session.execute(
        text(
            """
            INSERT INTO alert_actions (alert_id, user_id, action, note)
            VALUES (CAST(:aid AS uuid), CAST(:uid AS uuid), :act, :note)
            """
        ),
        {"aid": alert_id, "uid": user.user_id, "act": body.action, "note": body.note},
    )
    if body.action in ("close", "waive"):
        await session.execute(
            text(
                "UPDATE alerts SET closed_at = NOW(), resolution = :res "
                "WHERE id = CAST(:aid AS uuid)"
            ),
            {"aid": alert_id, "res": body.action},
        )
    await session.commit()
    return {"status": "ok", "action": body.action}


@alerts_router.get(
    "/patterns",
    response_model=GlobalPatternsResponse,
    dependencies=[Depends(require_analyst)],
)
async def list_alert_patterns(
    session: SessionDep,
) -> GlobalPatternsResponse:
    """Fleet-wide recurring patterns for the AlertsPage "Patterns" tab
    (plan Part 11.2). Reads `cross_entity_patterns` (nightly
    cross_entity_patterns worker) across ALL subverticals — the
    per-entity variant lives at /entities/{id}/health/patterns.

    State branches:
      empty              → worker never wrote rows (honest empty state)
      insufficient_data  → worker ran but every cohort was below min N
      full               → at least one real pattern row
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT p.pattern_type, p.pattern_key, p.pattern_label,
                       p.subvertical, p.catalogue_version,
                       p.primary_subcap_id, p.entity_count,
                       p.severity_mix, p.median_peer_gap,
                       p.sample_subcap_ids,
                       ARRAY(
                           SELECT e.name FROM entities e
                           WHERE e.id = ANY(p.affected_entity_ids)
                             AND e.status = 'ACTIVE'
                           ORDER BY e.name
                       ) AS affected_entity_names
                FROM cross_entity_patterns p
                ORDER BY p.entity_count DESC, p.pattern_type, p.pattern_key
                LIMIT 200
                """
            )
        )
    ).all()
    if not rows:
        return GlobalPatternsResponse(items=[], state="empty")
    real = [r for r in rows if r.pattern_type != "insufficient_data"]
    if not real:
        return GlobalPatternsResponse(items=[], state="insufficient_data")
    items = [
        GlobalPatternOut(
            pattern_type=r.pattern_type,
            pattern_key=r.pattern_key,
            pattern_label=r.pattern_label,
            subvertical=r.subvertical,
            catalogue_version=r.catalogue_version,
            primary_subcap_id=r.primary_subcap_id,
            entity_count=int(r.entity_count),
            severity_mix=dict(r.severity_mix or {}),
            median_peer_gap=(
                float(r.median_peer_gap)
                if r.median_peer_gap is not None else None
            ),
            sample_subcap_ids=list(r.sample_subcap_ids or []),
            affected_entity_names=list(r.affected_entity_names or []),
        )
        for r in real
    ]
    return GlobalPatternsResponse(items=items, state="full")


@health_router.get(
    "/{display_id}/health/patterns",
    response_model=HealthPatternsResponse,
    dependencies=[Depends(require_analyst)],
)
async def health_patterns(
    display_id: str,
    session: SessionDep,
    run: str | None = None,
) -> HealthPatternsResponse:
    """Cross-entity recurring patterns this client SHARES with its cohort.

    Reads `cross_entity_patterns` (written by the cross_entity_patterns
    worker) for the entity's subvertical + catalogue version, filtered to the
    patterns whose `affected_entity_ids` include this entity. State branches:
    no_active_run | no_cohort | insufficient_data | full.
    """
    from app.services.run_resolver import maybe_resolve_entity_run
    resolved = await maybe_resolve_entity_run(
        session, display_id, run_request_id=run,
    )
    if resolved is None:
        return HealthPatternsResponse(
            entity_display_id=display_id, run_request_id=None,
            subvertical=None, catalogue_version=None, patterns=[],
            state="no_active_run",
        )
    ent = (
        await session.execute(
            text("SELECT subvertical FROM entities WHERE id = :eid"),
            {"eid": resolved.entity_id},
        )
    ).first()
    sv = ent.subvertical if ent else None
    ver = resolved.ccg_catalog_version
    if not sv:
        return HealthPatternsResponse(
            entity_display_id=display_id, run_request_id=resolved.request_id,
            subvertical=None, catalogue_version=ver, patterns=[],
            state="no_cohort",
        )
    rows = (
        await session.execute(
            text(
                """
                SELECT pattern_type, pattern_key, pattern_label,
                       primary_subcap_id, entity_count, severity_mix,
                       median_peer_gap, sample_subcap_ids
                FROM cross_entity_patterns
                WHERE subvertical = :sv AND catalogue_version = :ver
                  AND CAST(:eid AS uuid) = ANY(affected_entity_ids)
                ORDER BY entity_count DESC, pattern_type, pattern_key
                """
            ),
            {"sv": sv, "ver": ver, "eid": resolved.entity_id},
        )
    ).all()
    if any(r.pattern_type == "insufficient_data" for r in rows):
        return HealthPatternsResponse(
            entity_display_id=display_id, run_request_id=resolved.request_id,
            subvertical=sv, catalogue_version=ver, patterns=[],
            state="insufficient_data",
        )
    patterns = [
        CrossEntityPatternOut(
            pattern_type=r.pattern_type,
            pattern_key=r.pattern_key,
            pattern_label=r.pattern_label,
            primary_subcap_id=r.primary_subcap_id,
            entity_count=r.entity_count,
            severity_mix=dict(r.severity_mix or {}),
            median_peer_gap=(
                float(r.median_peer_gap) if r.median_peer_gap is not None else None
            ),
            sample_subcap_ids=list(r.sample_subcap_ids or []),
        )
        for r in rows
    ]
    return HealthPatternsResponse(
        entity_display_id=display_id, run_request_id=resolved.request_id,
        subvertical=sv, catalogue_version=ver, patterns=patterns,
        state="full" if patterns else "no_cohort",
    )


@health_router.post(
    "/{display_id}/feedback-files:refresh",
    response_model=FeedbackRefreshResponse,
    dependencies=[Depends(require_analyst)],
)
async def refresh_feedback_files(
    display_id: str,
    session: SessionDep,
    actor: CurrentUserDep,
) -> FeedbackRefreshResponse:
    """Re-run the PRD §17 Drive feedback-file write for this entity's ACTIVE
    run (the same write that auto-fires at ingest). Analyst+; prod/staging
    only (dev_skip locally; fail-closed on missing folder/perms)."""
    import json as _json

    from app.config import get_settings
    from app.services.drive_feedback import write_feedback_files
    from app.services.run_resolver import maybe_resolve_entity_run

    resolved = await maybe_resolve_entity_run(session, display_id)
    if resolved is None:
        return FeedbackRefreshResponse(
            entity_display_id=display_id, run_request_id=None,
            state="no_active_run",
        )
    ent = (
        await session.execute(
            text("SELECT drive_folder_id FROM entities WHERE id = :eid"),
            {"eid": resolved.entity_id},
        )
    ).mappings().first()
    result = await write_feedback_files(
        session=session,
        db_run_id=str(resolved.id),
        entity_id=str(resolved.entity_id),
        drive_folder_id=ent["drive_folder_id"] if ent else None,
        env=get_settings().env,
    )
    try:
        await session.execute(
            text(
                """
                INSERT INTO audit_log (
                    actor_user_id, actor_email, action, resource_type,
                    resource_id, after_json
                ) VALUES (
                    CAST(:aid AS uuid), :ae, 'refresh_feedback_files', 'entity',
                    :rid, CAST(:after AS jsonb)
                )
                """
            ),
            {
                "aid": actor.user_id, "ae": actor.email,
                "rid": str(resolved.entity_id),
                "after": _json.dumps({
                    "state": result.state, "written": result.written,
                    "failed": result.failed,
                }),
            },
        )
        await session.commit()
    except Exception:
        await session.rollback()
    return FeedbackRefreshResponse(
        entity_display_id=display_id,
        run_request_id=resolved.request_id,
        state=result.state,
        written=result.written,
        failed=result.failed,
    )
