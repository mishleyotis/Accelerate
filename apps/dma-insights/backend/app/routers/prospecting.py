"""Prospecting endpoint — surfaces entities flagged for analyst follow-up.

Three composable flags:
  - LOW_MATURITY → entity's most recent ACTIVE run has overall score < 2.5 (M2)
  - STALE_RUN    → no ACTIVE run completed in the last 180 days
  - UNASSIGNED   → no current entity_assignment

Auth: all authenticated users (gated by `CurrentUserDep`); customer view
gets it stripped because Prospecting is internal-only.

The query is intentionally a single SQL roundtrip — the table is bounded
by entity count (~hundreds) and we paginate later if needed. Per-flag
counts are returned alongside the items so the UI chips can show counts
without a second request.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep
from app.services.scorecard_export import (
    PillarScore,
    PlatformFit,
    ScorecardData,
    render_scorecard_html,
    render_scorecard_pdf,
)

router = APIRouter(prefix="/api/v1", tags=["prospecting"])

_PILLAR_NAMES = {
    "P1": "Strategy & Governance",
    "P2": "Customer Experience",
    "P3": "Operations & Workflow",
    "P4": "Data & Technology",
}
_PLATFORM_NAMES = {
    "salesforce": "Salesforce", "databricks": "Databricks",
    "tableau": "Tableau", "twilio": "Twilio", "ncino": "nCino",
}

# Score cutoffs for the LOW_MATURITY flag.
LOW_MATURITY_SCORE_THRESHOLD = 2.5

# Staleness window (days) for the STALE_RUN flag.
STALE_RUN_DAYS = 180


def _band(score: float | None) -> str | None:
    if score is None:
        return None
    if score < 1.5:
        return "M1"
    if score < 2.5:
        return "M2"
    if score < 3.5:
        return "M3"
    if score < 4.5:
        return "M4"
    return "M5"


@router.get("/prospecting")
async def list_prospecting(
    _user: CurrentUserDep,
    session: SessionDep,
    flag: str | None = Query(None, pattern="^(LOW_MATURITY|STALE_RUN|UNASSIGNED|all)?$"),
    subvertical: str | None = Query(None, max_length=16),
) -> dict:
    """Return prospecting candidates with computed flags + per-flag counts."""
    # Single SQL: join entities to their most recent ACTIVE run + assignment.
    rows = (
        await session.execute(
            text(
                """
                WITH latest_run AS (
                    SELECT DISTINCT ON (r.entity_id)
                        r.entity_id, r.completed_at,
                        (SELECT AVG(s.score)::float
                         FROM subcap_scores s WHERE s.run_id = r.id) AS overall_score
                    FROM runs r
                    WHERE r.status = 'ACTIVE'
                    ORDER BY r.entity_id, r.completed_at DESC NULLS LAST
                ),
                current_assignment AS (
                    SELECT DISTINCT ON (a.entity_id)
                        a.entity_id, u.name AS assigned_ae
                    FROM entity_assignments a
                    LEFT JOIN users u ON u.id = a.user_id
                    WHERE a.superseded_at IS NULL
                    ORDER BY a.entity_id, a.assigned_at DESC
                )
                SELECT
                    e.id AS entity_id,
                    e.display_id,
                    e.name,
                    e.subvertical,
                    e.status,
                    lr.overall_score,
                    lr.completed_at AS last_run_at,
                    EXTRACT(DAY FROM NOW() - lr.completed_at)::int AS days_since_run,
                    ca.assigned_ae
                FROM entities e
                LEFT JOIN latest_run lr ON lr.entity_id = e.id
                LEFT JOIN current_assignment ca ON ca.entity_id = e.id
                WHERE e.status = 'ACTIVE'
                  AND (CAST(:subvertical AS TEXT) IS NULL
                       OR e.subvertical = CAST(:subvertical AS TEXT))
                ORDER BY
                    -- Surface the most actionable first: low maturity, then stale, then unassigned
                    (lr.overall_score IS NULL OR lr.overall_score < :score_threshold) DESC,
                    lr.overall_score ASC NULLS LAST,
                    e.name ASC
                """
            ),
            {
                "subvertical": subvertical if subvertical and subvertical != "all" else None,
                "score_threshold": LOW_MATURITY_SCORE_THRESHOLD,
            },
        )
    ).all()

    items: list[dict] = []
    counts = {"low_maturity": 0, "stale_run": 0, "unassigned": 0}
    for r in rows:
        flags: list[str] = []
        if r.overall_score is not None and r.overall_score < LOW_MATURITY_SCORE_THRESHOLD:
            flags.append("LOW_MATURITY")
            counts["low_maturity"] += 1
        if r.last_run_at is None or (
            r.days_since_run is not None and r.days_since_run > STALE_RUN_DAYS
        ):
            flags.append("STALE_RUN")
            counts["stale_run"] += 1
        if not r.assigned_ae:
            flags.append("UNASSIGNED")
            counts["unassigned"] += 1
        items.append(
            {
                "entity_id": str(r.entity_id),
                "display_id": r.display_id,
                "name": r.name,
                "subvertical": r.subvertical,
                "overall_score": r.overall_score,
                "maturity_band": _band(r.overall_score),
                "last_run_at": r.last_run_at.isoformat() if r.last_run_at else None,
                "days_since_run": r.days_since_run,
                "assigned_ae": r.assigned_ae,
                "status": r.status,
                "flags": flags,
            }
        )

    # Filter by flag chip AFTER computing counts so the chips always show
    # totals (UX expectation: counts don't shift when you click a chip).
    if flag and flag != "all":
        items = [it for it in items if flag in it["flags"]]

    return {
        "items": items,
        "total": len(items),
        "filter_counts": counts,
    }


async def _build_scorecard(session, display_id: str) -> ScorecardData:
    ent = (
        await session.execute(
            text(
                "SELECT id, display_id, name, subvertical "
                "FROM entities WHERE display_id = :did"
            ),
            {"did": display_id},
        )
    ).first()
    if ent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"entity {display_id} not found",
        )
    run = (
        await session.execute(
            text(
                "SELECT id, completed_at "
                "FROM runs WHERE entity_id = :eid AND status = 'ACTIVE' "
                "ORDER BY completed_at DESC NULLS LAST LIMIT 1"
            ),
            {"eid": ent.id},
        )
    ).first()

    pillars: list[PillarScore] = []
    overall: float | None = None
    assessment_date: str | None = None
    top_platforms: list[PlatformFit] = []
    if run is not None:
        assessment_date = (
            run.completed_at.date().isoformat() if run.completed_at else None
        )
        # Overall + per-pillar scores are computed from subcap_scores (there
        # is no denormalised overall_score column). Pillar is the leading two
        # chars of the subcap_id (PnCn.n.n), matching the catalogue convention
        # used across the heatmap/platform surfaces.
        ov = (
            await session.execute(
                text(
                    "SELECT AVG(score)::float AS avg FROM subcap_scores "
                    "WHERE run_id = :rid"
                ),
                {"rid": run.id},
            )
        ).scalar_one_or_none()
        overall = float(ov) if ov is not None else None
        pillar_rows = (
            await session.execute(
                text(
                    "SELECT LEFT(subcap_id, 2) AS pid, AVG(score)::float AS avg "
                    "FROM subcap_scores WHERE run_id = :rid "
                    "GROUP BY LEFT(subcap_id, 2)"
                ),
                {"rid": run.id},
            )
        ).all()
        by_pillar = {r.pid: r.avg for r in pillar_rows}
        for pid in ("P1", "P2", "P3", "P4"):
            v = by_pillar.get(pid)
            pillars.append(
                PillarScore(
                    pillar_id=pid, name=_PILLAR_NAMES[pid],
                    score=float(v) if v is not None else None,
                )
            )
        plat_rows = (
            await session.execute(
                text(
                    "SELECT platform_id, fit_score FROM platform_scores "
                    "WHERE run_id = :rid ORDER BY fit_score DESC LIMIT 3"
                ),
                {"rid": run.id},
            )
        ).all()
        top_platforms = [
            PlatformFit(
                name=_PLATFORM_NAMES.get(p.platform_id, p.platform_id),
                fit_score=float(p.fit_score),
            )
            for p in plat_rows
        ]

    return ScorecardData(
        entity_name=ent.name,
        subvertical=ent.subvertical,
        display_id=ent.display_id,
        overall=overall,
        assessment_date=assessment_date,
        pillars=pillars,
        top_platforms=top_platforms,
    )


@router.post("/prospecting/{display_id}/export")
async def export_scorecard(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    format: str = Query("html", pattern="^(html|pdf)$"),
) -> Response:
    """B-6 — customer-safe scorecard export (D14 Prospecting).

    `format=html` always works; `format=pdf` requires the optional
    `export` extra (weasyprint) and returns 501 when it is unavailable
    rather than fabricating a file.
    """
    data = await _build_scorecard(session, display_id)
    stem = f"dma-scorecard-{display_id}"
    if format == "pdf":
        try:
            pdf = render_scorecard_pdf(data)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc),
            ) from exc
        return Response(
            content=pdf,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{stem}.pdf"'
            },
        )
    html = render_scorecard_html(data)
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{stem}.html"'},
    )
