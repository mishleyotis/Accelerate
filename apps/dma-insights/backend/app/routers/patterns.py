"""Pattern recognition endpoints — surfaces deep AI similarity across the
cohort. All endpoints are cohort-aware (read adjacency from the
admin-editable table) and respect entity privacy (no entity_id leaked;
only entity_name + counts).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep, get_redis
from app.schemas.drift import (
    DriftReportOut,
    PillarDriftOut,
    SubcapDriftOut,
)
from app.schemas.patterns import (
    RecurringSubcapResponse,
    RecurringSubcapTheme,
    SimilarInsightOut,
    SimilarInsightsResponse,
    SimilarRecommendationOut,
    SimilarRecommendationsResponse,
)
from app.services.pattern_drift import compute_drift
from app.services.pattern_recognition import (
    find_similar_insights,
    find_similar_recommendations,
)
from app.services.rag_cohort import EntityProfile, RagCohortRouter

router = APIRouter(prefix="/api/v1/patterns", tags=["patterns"])


async def _cohort_for_entity(
    session, entity_id: str | None, cross_vertical: str = "auto",
):
    """Resolve the entity's profile then build cohort weights."""
    if entity_id is None:
        return {}, "cross_vertical", 0
    row = (
        await session.execute(
            text("SELECT subvertical, lobs FROM entities WHERE id = CAST(:eid AS uuid)"),
            {"eid": entity_id},
        )
    ).first()
    if row is None:
        return {}, "cross_vertical", 0
    profile = EntityProfile(
        entity_id=entity_id,
        subvertical=row.subvertical,
        lobs=list(row.lobs or []),
    )
    redis = await get_redis()
    router_svc = RagCohortRouter(session, redis=redis)
    cohort = await router_svc.select(profile, cross_vertical=cross_vertical)
    return cohort.weights, cohort.mode, cohort.n_estimated


@router.get(
    "/insights/{insight_card_id}/similar",
    response_model=SimilarInsightsResponse,
)
async def similar_insights(
    insight_card_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    top_k: int = Query(default=8, ge=1, le=50),
    cross_vertical: str = Query(default="auto"),
) -> SimilarInsightsResponse:
    """For a given insight card, find similar IC narratives across the
    cohort. Each result carries `combined_score = cohort_match * text_similarity`
    so the UI can rank patterns by relevance to *this* entity's cohort."""
    seed_row = (
        await session.execute(
            text(
                "SELECT ic_id, entity_id FROM insight_cards "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"id": insight_card_id},
        )
    ).first()
    if seed_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"insight card {insight_card_id} not found",
        )
    weights, mode, _n = await _cohort_for_entity(
        session, str(seed_row.entity_id), cross_vertical,
    )
    results = await find_similar_insights(
        session,
        seed_insight_id=insight_card_id,
        cohort_weights=weights,
        top_k=top_k,
        exclude_entity_id=str(seed_row.entity_id),
    )
    return SimilarInsightsResponse(
        seed_ic_id=seed_row.ic_id,
        cohort_mode=mode,
        items=[
            SimilarInsightOut(
                insight_card_id=r.insight_card_id,
                ic_id=r.ic_id,
                entity_name=r.entity_name,
                title=r.title,
                severity=r.severity,
                linked_subcap_id=r.linked_subcap_id,
                cohort_match=r.cohort_match,
                text_similarity=r.text_similarity,
                combined_score=r.combined_score,
            )
            for r in results
        ],
    )


@router.get(
    "/recommendations/{recommendation_id}/similar",
    response_model=SimilarRecommendationsResponse,
)
async def similar_recommendations(
    recommendation_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    top_k: int = Query(default=8, ge=1, le=50),
    cross_vertical: str = Query(default="auto"),
) -> SimilarRecommendationsResponse:
    seed_row = (
        await session.execute(
            text(
                "SELECT rec_id, entity_id FROM recommendations "
                "WHERE id = CAST(:id AS uuid)"
            ),
            {"id": recommendation_id},
        )
    ).first()
    if seed_row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"recommendation {recommendation_id} not found",
        )
    weights, mode, _n = await _cohort_for_entity(
        session, str(seed_row.entity_id), cross_vertical,
    )
    results = await find_similar_recommendations(
        session,
        seed_rec_id=recommendation_id,
        cohort_weights=weights,
        top_k=top_k,
        exclude_entity_id=str(seed_row.entity_id),
    )
    return SimilarRecommendationsResponse(
        seed_rec_id=seed_row.rec_id,
        cohort_mode=mode,
        items=[
            SimilarRecommendationOut(
                recommendation_id=r.recommendation_id,
                rec_id=r.rec_id,
                entity_name=r.entity_name,
                title=r.title,
                platform_id=r.platform_id,
                cohort_match=r.cohort_match,
                text_similarity=r.text_similarity,
                combined_score=r.combined_score,
            )
            for r in results
        ],
    )


@router.get(
    "/subcaps/{subcap_id}/recurring",
    response_model=RecurringSubcapResponse,
)
async def recurring_subcap_themes(
    subcap_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    subvertical: str | None = None,
    top_k: int = Query(default=5, ge=1, le=20),
    cross_vertical: str = Query(default="auto"),
) -> RecurringSubcapResponse:
    """Group insight_cards by (title, severity) for entities in the cohort
    whose IC is linked to this subcap_id. Returns the top themes by
    occurrence_count — surfaces "this pattern appears N times" in D2/D3.
    """
    weights: dict[str, float] = {}
    mode = "cross_vertical"
    if subvertical:
        redis = await get_redis()
        router_svc = RagCohortRouter(session, redis=redis)
        cohort = await router_svc.select(
            EntityProfile(entity_id=None, subvertical=subvertical, lobs=[]),
            cross_vertical=cross_vertical,
        )
        weights, mode = cohort.weights, cohort.mode

    # Subvertical filter: only matters if we have a primary anchor.
    where_extra = ""
    params: dict[str, object] = {"sid": subcap_id, "top_k": top_k}
    if subvertical:
        where_extra = "AND e.subvertical = :sv"
        params["sv"] = subvertical

    rows = (
        await session.execute(
            text(
                f"""
                SELECT
                  ic.title,
                  ic.severity,
                  COUNT(*) AS n,
                  ARRAY_AGG(DISTINCT e.name) FILTER (WHERE e.name IS NOT NULL)
                    AS entity_names
                FROM insight_cards ic
                JOIN entities e ON e.id = ic.entity_id
                JOIN runs r ON r.id = ic.run_id AND r.status = 'ACTIVE'
                WHERE ic.linked_subcap_id = :sid
                  {where_extra}
                GROUP BY ic.title, ic.severity
                ORDER BY COUNT(*) DESC, ic.severity ASC
                LIMIT :top_k
                """
            ),
            params,
        )
    ).all()
    themes = [
        RecurringSubcapTheme(
            title=r.title,
            severity=r.severity,
            occurrence_count=int(r.n),
            sample_entities=list(r.entity_names or [])[:5],
        )
        for r in rows
    ]
    _ = weights  # reserved for future weighted ranking
    return RecurringSubcapResponse(
        subcap_id=subcap_id,
        cohort_mode=mode,
        themes=themes,
    )


@router.get(
    "/entities/{display_id}/drift",
    response_model=DriftReportOut,
)
async def entity_drift(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
) -> DriftReportOut:
    """Deep-AI signal: how does this entity's score profile diverge from
    its cohort norm? Returns a per-subcap + per-pillar drift report with
    buckets (critical_low/below/nominal/above/critical_high) plus
    transparent skip reasons (cohort_insufficient / entity_missing) so
    the UI can render an honest "we don't have enough data" surface
    instead of fabricating a drift signal.
    """
    ent = (
        await session.execute(
            text(
                "SELECT id, subvertical FROM entities "
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
    run = (
        await session.execute(
            text(
                "SELECT id FROM runs "
                "WHERE entity_id = :eid AND status = 'ACTIVE' "
                "ORDER BY completed_at DESC NULLS LAST LIMIT 1"
            ),
            {"eid": ent.id},
        )
    ).first()
    if run is None:
        return DriftReportOut(entity_display_id=display_id)

    score_rows = (
        await session.execute(
            text(
                "SELECT subcap_id, score FROM subcap_scores WHERE run_id = :rid"
            ),
            {"rid": run.id},
        )
    ).all()
    entity_scores = [(r.subcap_id, float(r.score)) for r in score_rows]

    # Pull cohort medians from peer_benchmarks. Filter by subvertical;
    # the cohort_insufficient bucket already handles the n < min_n case.
    peer_rows = (
        await session.execute(
            text(
                """
                SELECT subcap_id, median, n
                FROM peer_benchmarks
                WHERE subvertical = :sv
                """
            ),
            {"sv": ent.subvertical or ""},
        )
    ).all()
    peers = [(r.subcap_id, float(r.median), int(r.n)) for r in peer_rows]

    report = compute_drift(entity_scores=entity_scores, peer_benchmarks=peers)
    return DriftReportOut(
        entity_display_id=display_id,
        cohort_insufficient_count=report.cohort_insufficient_count,
        entity_missing_count=report.entity_missing_count,
        overall_drift=report.overall_drift,
        pillar_drifts=[
            PillarDriftOut(
                pillar=pd.pillar,
                drift_score=pd.drift_score,
                subcap_count=pd.subcap_count,
                by_bucket=pd.by_bucket,
            )
            for pd in report.pillar_drifts
        ],
        subcap_drifts=[
            SubcapDriftOut(
                subcap_id=sd.subcap_id,
                pillar=sd.pillar,
                bucket=sd.bucket,
                drift_score=sd.drift_score,
                entity_score=sd.entity_score,
                peer_median=sd.peer_median,
                peer_n=sd.peer_n,
            )
            for sd in report.subcap_drifts
        ],
    )
