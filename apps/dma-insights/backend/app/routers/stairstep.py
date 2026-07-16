"""D4 StairstepCurve endpoint — composes the pure stairstep service over
the entity's ACTIVE run's subcap_scores + recommendations.

State-branch contract:
  - Entity not found             → 404
  - No ACTIVE run                → empty_state=null + empty steps
                                   (frontend renders no-run empty state)
  - Run exists but no scores     → service emits empty_state='no-gaps'
  - Run exists but no recs       → service emits empty_state='no-recs'
  - Recs target above-target
    pillars only                 → service emits 'no-applicable-uplift'
  - Happy path                   → 4 pillars x steps with cumulative
                                   score_before/after, all <= ceiling=5.0
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep
from app.schemas.stairstep import StairStepOut, StairstepResponse
from app.services.stairstep import (
    PILLARS,
    RecForStair,
    compute_average_by_pillar,
    compute_stairstep,
)

router = APIRouter(prefix="/api/v1/entities", tags=["stairstep"])


@router.get(
    "/{display_id}/stairstep",
    response_model=StairstepResponse,
)
async def stairstep(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
) -> StairstepResponse:
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
    run = (
        await session.execute(
            text(
                "SELECT id, request_id, overall_score FROM runs "
                "WHERE entity_id = :eid AND status = 'ACTIVE' "
                "ORDER BY completed_at DESC NULLS LAST LIMIT 1"
            ),
            {"eid": ent.id},
        )
    ).first()
    if run is None:
        return StairstepResponse(
            entity_display_id=display_id,
            run_request_id=None,
            steps_by_pillar={p: [] for p in PILLARS},
            current_by_pillar=dict.fromkeys(PILLARS, 0.0),
            end_score_by_pillar=dict.fromkeys(PILLARS, 0.0),
            empty_state=None,
        )

    # Load subcap_scores → current_by_pillar
    score_rows = (
        await session.execute(
            text(
                "SELECT subcap_id, score FROM subcap_scores WHERE run_id = :rid"
            ),
            {"rid": run.id},
        )
    ).all()
    current = compute_average_by_pillar(
        (r.subcap_id, float(r.score))
        for r in score_rows
        if r.score is not None
    )

    # Load recommendations → RecForStair
    rec_rows = (
        await session.execute(
            text(
                """
                SELECT rec_id, title, target_subcap_ids, uplift_per_pillar
                FROM recommendations WHERE run_id = :rid
                """
            ),
            {"rid": run.id},
        )
    ).all()
    recs = [
        RecForStair(
            rec_id=r.rec_id,
            title=r.title,
            target_subcap_ids=list(r.target_subcap_ids or []),
            uplift_per_pillar=dict(r.uplift_per_pillar) if r.uplift_per_pillar else None,
        )
        for r in rec_rows
    ]

    # Position fallback: a run with no scored subcaps to average must still
    # place the client on the curve from its overall maturity (the operator's
    # Zions report). runs.overall_score survives even when subcap_scores is
    # empty, so the stairstep never falsely claims "no scored subcaps". (No
    # independent per-pillar store exists in this schema — the per-pillar
    # averages ARE the subcap rollup — so overall maturity is the fallback.)
    overall_maturity = (
        float(run.overall_score) if run.overall_score is not None else None
    )
    result = compute_stairstep(
        current_by_pillar=current,
        recommendations=recs,
        overall_maturity_fallback=overall_maturity,
    )
    # The stair may have been positioned from a fallback when the run had no
    # scored subcaps — surface THAT position so current + steps agree.
    effective_current = result.current_by_pillar or current

    return StairstepResponse(
        entity_display_id=display_id,
        run_request_id=run.request_id,
        steps_by_pillar={
            p: [
                StairStepOut(
                    rec_id=s.rec_id, title=s.title, pillar=s.pillar,
                    score_before=s.score_before, score_after=s.score_after,
                    uplift=s.uplift,
                )
                for s in result.steps_by_pillar.get(p, [])
            ]
            for p in PILLARS
        },
        current_by_pillar={
            p: getattr(effective_current, p) for p in PILLARS
        },
        end_score_by_pillar={
            p: result.end_score_by_pillar.get(p, getattr(effective_current, p))
            for p in PILLARS
        },
        empty_state=result.empty_state,
        position_source=result.position_source,
    )
