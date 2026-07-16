"""Cross-pillar themes endpoint — D5 Context "themes that touch this
entity" card. Surfaces the catalogue's `ccg_cross_pillar_stories` filtered
to the entity's scored subcaps so the AE only sees patterns they can
actually act on.

State-transition contract (for `/cross-pillar-stories?pillar=`):
  - full_match              → entity's subvertical has scored subcaps;
                              cross-pillar story rows exist for them at
                              the run's catalogue version.
  - no_subverticals_match   → entity's subcaps don't appear in any
                              cross-pillar story for the requested
                              pillar → return empty list, state set.
  - catalogue_version_drift → run was scored against v5/v6; the
                              ccg_cross_pillar_stories table has rows
                              only for v7. Resolver returns whatever
                              matches, state flagged.
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text

from app.deps import SessionDep, ViewModeDep, require_analyst
from app.schemas.cross_pillar import (
    CrossPillarResponse,
    CrossPillarStoryListResponse,
    CrossPillarStoryOut,
    ThemeClusterOut,
)
from app.services.audience_strip import strip_and_respond
from app.services.cross_pillar import StoryRow, aggregate_cross_pillar

router = APIRouter(
    prefix="/api/v1/entities",
    tags=["cross-pillar"],
    # D5 Context is Analyst+; cross-pillar themes ride alongside it.
    dependencies=[Depends(require_analyst)],
)


@router.get("/{display_id}/cross-pillar", response_model=CrossPillarResponse)
async def cross_pillar_themes(
    display_id: str,
    session: SessionDep,
    view: ViewModeDep,
) -> CrossPillarResponse:
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
                "SELECT id, ccg_catalog_version FROM runs "
                "WHERE entity_id = :eid AND status = 'ACTIVE' "
                "ORDER BY completed_at DESC NULLS LAST LIMIT 1"
            ),
            {"eid": ent.id},
        )
    ).first()
    if run is None:
        return CrossPillarResponse(
            entity_display_id=display_id,
            catalogue_version="unknown",
            total_stories=0,
            themes=[],
        )

    scored = (
        await session.execute(
            text(
                "SELECT subcap_id FROM subcap_scores WHERE run_id = :rid"
            ),
            {"rid": run.id},
        )
    ).all()
    scored_ids = {r.subcap_id for r in scored}

    story_rows = (
        await session.execute(
            text(
                """
                SELECT cps.story_key, cps.origin_pillar, cps.origin_subcap_id,
                       cps.origin_l1_capability AS origin_capability,
                       cps.target_pillar, cps.themes
                FROM ccg_cross_pillar_stories cps
                WHERE cps.version = :ver
                """
            ),
            {"ver": run.ccg_catalog_version},
        )
    ).all()
    stories = [
        StoryRow(
            story_key=r.story_key,
            origin_pillar=r.origin_pillar,
            origin_subcap_id=r.origin_subcap_id,
            origin_capability=r.origin_capability,
            target_pillar=r.target_pillar,
            themes=list(r.themes or []),
        )
        for r in story_rows
    ]
    report = aggregate_cross_pillar(stories, entity_scored_subcap_ids=scored_ids)
    payload = CrossPillarResponse(
        entity_display_id=display_id,
        catalogue_version=run.ccg_catalog_version,
        total_stories=report.total_stories,
        themes=[
            ThemeClusterOut(
                theme=t.theme,
                story_count=t.story_count,
                target_pillars=t.target_pillars,
                origin_capabilities=t.origin_capabilities,
            )
            for t in report.themes
        ],
    )
    return strip_and_respond(payload, view.audience, CrossPillarResponse)


@router.get(
    "/{display_id}/cross-pillar-stories",
    response_model=CrossPillarStoryListResponse,
)
async def cross_pillar_stories(
    display_id: str,
    session: SessionDep,
    pillar: Literal["P1", "P2", "P3", "P4"] | None = Query(default=None),
) -> CrossPillarStoryListResponse:
    """Detailed cross-pillar stories that touch this entity's subcaps.

    Plan §3 — D5 Context surface. Each row carries enough metadata for
    the UI to render: theme name, origin pillar → target pillar chain,
    subcaps touched, and a one-line "Why this matters" derived from the
    entity's actual gap profile.
    """
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
    run = (
        await session.execute(
            text(
                "SELECT id, ccg_catalog_version FROM runs "
                "WHERE entity_id = :eid AND status = 'ACTIVE' "
                "ORDER BY completed_at DESC NULLS LAST LIMIT 1"
            ),
            {"eid": ent.id},
        )
    ).first()
    if run is None:
        return CrossPillarStoryListResponse(
            entity_display_id=display_id,
            catalogue_version="unknown",
            pillar_filter=pillar,
            total=0,
            stories=[],
            state="no_active_run",
        )

    # Pull scored subcap IDs + their scores so we can compute below-median.
    score_rows = (
        await session.execute(
            text(
                """
                SELECT s.subcap_id, s.score, COALESCE(s.peer_median, 0) AS peer_median,
                       cs.name AS subcap_name
                FROM subcap_scores s
                LEFT JOIN ccg_subcaps cs
                  ON cs.version = :ver AND cs.subcap_id = s.subcap_id
                WHERE s.run_id = :rid
                """
            ),
            {"ver": run.ccg_catalog_version, "rid": run.id},
        )
    ).all()
    scored_by_id: dict[str, dict[str, object]] = {}
    for r in score_rows:
        scored_by_id[r.subcap_id] = {
            "score": float(r.score) if r.score is not None else 0.0,
            "peer_median": float(r.peer_median) if r.peer_median is not None else 0.0,
            "name": r.subcap_name or r.subcap_id,
        }

    # Pull cross-pillar story rows for this catalogue version, optionally
    # filtered to a calling pillar (the "this came from P1, now affects
    # P4" chain — `pillar` is the ORIGIN pillar in the call).
    where = ["cps.version = :ver"]
    params: dict[str, object] = {"ver": run.ccg_catalog_version}
    if pillar is not None:
        where.append("cps.origin_pillar = :p")
        params["p"] = pillar

    story_rows = (
        await session.execute(
            text(
                f"""
                SELECT cps.story_key, cps.origin_pillar, cps.origin_subcap_id,
                       cps.origin_l1_capability AS origin_capability,
                       cps.target_pillar, cps.themes
                FROM ccg_cross_pillar_stories cps
                WHERE {' AND '.join(where)}
                """
            ),
            params,
        )
    ).all()

    if not story_rows:
        state = ("catalogue_version_drift" if run.ccg_catalog_version != "v7.0"
                 else "no_subverticals_match")
        return CrossPillarStoryListResponse(
            entity_display_id=display_id,
            catalogue_version=run.ccg_catalog_version,
            pillar_filter=pillar,
            total=0,
            stories=[],
            state=state,
        )

    out: list[CrossPillarStoryOut] = []
    for sr in story_rows:
        # The story "touches" this entity if its origin_subcap_id is in
        # the entity's scored set (or if any subcap in the same L1
        # capability is scored — broader match).
        touched = []
        sample_names: list[str] = []
        if sr.origin_subcap_id in scored_by_id:
            touched.append(sr.origin_subcap_id)
            sample_names.append(str(scored_by_id[sr.origin_subcap_id]["name"]))
        else:
            # broader match: any subcap with the same L1 prefix
            prefix = ".".join(sr.origin_subcap_id.split(".")[:2])
            for sid in scored_by_id:
                if sid.startswith(prefix):
                    touched.append(sid)
                    sample_names.append(str(scored_by_id[sid]["name"]))
        if not touched:
            continue
        # "Why this matters": flag if the origin subcap is below median.
        why = None
        for sid in touched:
            info = scored_by_id[sid]
            if info["peer_median"] and info["score"] < info["peer_median"]:
                why = (
                    f"{ent.name} scores {info['score']:.1f} on "
                    f"{info['name']} vs peer median "
                    f"{info['peer_median']:.1f}; this cross-pillar story "
                    f"links it to {sr.target_pillar}."
                )
                break
        out.append(CrossPillarStoryOut(
            story_key=sr.story_key,
            origin_pillar=sr.origin_pillar,
            origin_subcap_id=sr.origin_subcap_id,
            origin_capability=sr.origin_capability,
            target_pillar=sr.target_pillar,
            themes=list(sr.themes or []),
            subcaps_touched=touched,
            sample_subcap_names=sample_names[:3],
            why_this_matters=why,
        ))

    state = "full_match" if out else "no_subverticals_match"
    return CrossPillarStoryListResponse(
        entity_display_id=display_id,
        catalogue_version=run.ccg_catalog_version,
        pillar_filter=pillar,
        total=len(out),
        stories=out,
        state=state,
    )
