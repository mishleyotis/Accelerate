"""Recommendation detail endpoint — D4 RecommendationModal grounding.

Per plan §⑦ + stage 9, every cited feature / platform construct /
agent on a recommendation card must resolve to a real catalogue row.
This endpoint enrich-loads the rec + cross-checks each cited string
against `ccg_l4_features`, `ccg_platform_constructs`, and
`ccg_agentforce_agents` for the run's pinned catalogue version, and
returns each citation with a `resolved` flag.

Unresolved cites are NOT silently dropped — they're returned with
resolved=false so the AE can see them and the Analyst can flag the
generator for review. `unresolved_count` is surfaced at the top level
so the UI can decide whether to gate the rec ("Pending review" banner)
or render normally.

State-branch contract:
  - rec_id not found        → 404
  - rec is fully resolved   → unresolved_count == 0 (UI renders happy)
  - rec has unresolved cites → unresolved_count > 0 + per-citation
                               resolved=false rows (UI surfaces a
                               "Pending review" amber banner)

ID contract (2026-07-06 drilldown-load fix): the path param accepts BOTH
identifier forms the frontend holds —
  - the UUID primary key (``recommendations.id``), and
  - the human-readable display code (``recommendations.rec_id``, e.g.
    ``REC-08``) that the stairstep / roadmap payloads carry. Display
    codes are only unique per run, so a code lookup is scoped by the
    optional ``display_id`` query param (the entity's ACTIVE run); an
    unscoped code that matches more than one entity is a 404 with an
    actionable detail — never a guess.
Previously a display code hit ``CAST(:rid AS uuid)`` → Postgres 22P02 →
500, so every rec opened from the stairstep curve or the roadmap chevrons
failed to load.
"""
from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from app.deps import CurrentUser, CurrentUserDep, SessionDep, ViewModeDep, require_ae
from app.schemas.recommendations import (
    CitedReference,
    RecommendationDetail,
    RecommendationNoteIn,
    RecommendationNoteOut,
)
from app.services.audience_strip import strip_and_respond

router = APIRouter(prefix="/api/v1", tags=["recommendations"])

# AE+ gate for the per-recommendation note write surface. `require_ae`
# (= require_role("AE")) 403s CUSTOMER; ADMIN/ANALYST/AE pass and the
# CurrentUser is returned so the PUT can stamp author_email.
AeUserDep = Annotated[CurrentUser, Depends(require_ae)]

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def is_uuid_literal(value: str) -> bool:
    """True when the path param is a UUID pk (vs a REC-NN display code)."""
    return bool(_UUID_RE.match(value or ""))


async def resolve_recommendation_uuid(
    session,
    recommendation_id: str,
    display_id: str | None,
) -> str:
    """Resolve the path param to the UUID pk.

    UUID literals pass through untouched (zero extra queries). Display
    codes resolve within ACTIVE runs — scoped to ``display_id`` when
    given. Raises 404 (never 500) when the code doesn't resolve or is
    ambiguous across entities without a scope.
    """
    if is_uuid_literal(recommendation_id):
        return recommendation_id
    # 2026-07-06 deploy review ("I cannot load the recommendation from the
    # platform page"): pack-baked roadmap rows carry rec_id forms ("R-01",
    # "REC-001"), not the stored code — match the exact code plus the
    # upper-cased and "R-"→"REC-" normalized variants the packs carry.
    code_uc = (recommendation_id or "").upper()
    params: dict = {
        "code": recommendation_id,
        "code_uc": code_uc,
        "code_alt": code_uc.replace("R-", "REC-").replace("RECEC-", "REC-"),
    }
    scope_sql = ""
    if display_id:
        scope_sql = " AND e.display_id = :did"
        params["did"] = display_id
    rows = (
        await session.execute(
            text(
                """
                SELECT r.id FROM recommendations r
                JOIN runs run ON run.id = r.run_id
                JOIN entities e ON e.id = r.entity_id
                WHERE (r.rec_id = :code
                       OR UPPER(r.rec_id) IN (:code_uc, :code_alt))
                  AND run.status = 'ACTIVE'
                """
                + scope_sql
                + """
                ORDER BY run.completed_at DESC NULLS LAST
                LIMIT 2
                """
            ),
            params,
        )
    ).all()
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"recommendation {recommendation_id} not found",
        )
    if len(rows) > 1 and not display_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"recommendation code {recommendation_id} matches multiple "
                "entities — pass ?display_id= to scope the lookup"
            ),
        )
    return str(rows[0].id)


@router.get("/entities/{display_id}/recommendations")
async def list_entity_recommendations(
    display_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
) -> list[dict]:
    """Rec list for the entity's ACTIVE run — {id, rec_id, title,
    platform_id} plus the Part-7.2 rich-card fields (feature, phase,
    root_cause_e_ids, outcomes) so the D4 Recommendations panel can
    render the prototype's root-cause chips + outcomes grid + phase
    pill. Also lets the StairstepCurve resolve a clicked rec_id to the
    UUID needed by /recommendations/{id}.

    Empty list when there's no ACTIVE run — caller renders nothing.
    """
    ent = (
        await session.execute(
            text("SELECT id FROM entities WHERE display_id = :did"),
            {"did": display_id},
        )
    ).first()
    if ent is None:
        return []
    run = (
        await session.execute(
            text(
                "SELECT id FROM runs WHERE entity_id = :eid AND status = 'ACTIVE' "
                "ORDER BY completed_at DESC NULLS LAST LIMIT 1"
            ),
            {"eid": ent.id},
        )
    ).first()
    if run is None:
        return []
    rows = (
        await session.execute(
            text(
                "SELECT id, rec_id, title, platform_id, "
                "       feature, phase, root_cause_e_ids, outcomes "
                "FROM recommendations WHERE run_id = :rid "
                "ORDER BY rec_id"
            ),
            {"rid": run.id},
        )
    ).all()
    # Batch 6: polish bot-emitted recommendation titles into Zennify
    # voice via the cached deterministic rewriter (anchor-safe).
    from app.services.narrative_polish import polish_narrative
    return [
        {
            "id": str(r.id),
            "rec_id": r.rec_id,
            "title": polish_narrative(
                r.title,
                target_kind="recommendation",
                target_id=f"{r.id}:title",
            ),
            "platform_id": r.platform_id,
            # Part 7.2 rich-card fields (additive; None until enriched).
            "feature": r.feature,
            "phase": r.phase,
            "root_cause_e_ids": list(r.root_cause_e_ids or []),
            "outcomes": dict(r.outcomes) if isinstance(r.outcomes, dict) else None,
        }
        for r in rows
    ]


@router.get("/recommendations/{recommendation_id}", response_model=RecommendationDetail)
async def recommendation_detail(
    recommendation_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
    view: ViewModeDep,
    display_id: str | None = None,
    entity: str | None = None,
) -> RecommendationDetail:
    # Accept BOTH the UUID pk and the REC-NN display code — the stairstep /
    # roadmap / platform-page openers only hold the code (pack drift forms
    # like "R-01"/"REC-001" are normalized in the resolver). The scoping
    # query param arrives as ?display_id= (drilldown fix branch) or
    # ?entity= (deploy branch); either works — same semantics.
    recommendation_id = await resolve_recommendation_uuid(
        session, recommendation_id, display_id or entity,
    )
    # Migration 048 (Part 7.2): feature / phase / root_cause_e_ids /
    # outcomes ride the same SELECT. Try with the new columns; fall back
    # to the legacy list for envs without migration 048 applied (the new
    # RecommendationDetail fields keep their None/[] defaults).
    try:
        rec = (
            await session.execute(
                text(
                    """
                    SELECT r.id, r.rec_id, r.title, r.description, r.platform_id,
                           r.target_subcap_ids, r.addressable_offerings,
                           r.cited_l4_features, r.cited_constructs, r.cited_agents,
                           r.uplift_per_pillar, r.effort_band,
                           r.prerequisite_rec_ids,
                           r.feature, r.phase, r.root_cause_e_ids, r.outcomes,
                           e.display_id AS entity_display_id,
                           run.ccg_catalog_version
                    FROM recommendations r
                    JOIN entities e ON e.id = r.entity_id
                    JOIN runs run ON run.id = r.run_id
                    WHERE r.id = CAST(:rid AS uuid)
                    """
                ),
                {"rid": recommendation_id},
            )
        ).first()
    except Exception:
        rec = (
            await session.execute(
                text(
                    """
                    SELECT r.id, r.rec_id, r.title, r.description, r.platform_id,
                           r.target_subcap_ids, r.addressable_offerings,
                           r.cited_l4_features, r.cited_constructs, r.cited_agents,
                           r.uplift_per_pillar, r.effort_band,
                           r.prerequisite_rec_ids,
                           e.display_id AS entity_display_id,
                           run.ccg_catalog_version
                    FROM recommendations r
                    JOIN entities e ON e.id = r.entity_id
                    JOIN runs run ON run.id = r.run_id
                    WHERE r.id = CAST(:rid AS uuid)
                    """
                ),
                {"rid": recommendation_id},
            )
        ).first()
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"recommendation {recommendation_id} not found",
        )

    ver = rec.ccg_catalog_version
    cited_features = list(rec.cited_l4_features or [])
    cited_constructs = list(rec.cited_constructs or [])
    cited_agents = list(rec.cited_agents or [])

    feature_refs = await _resolve_features(session, ver, cited_features)
    construct_refs = await _resolve_constructs(session, ver, cited_constructs)
    agent_refs = await _resolve_agents(session, ver, cited_agents)

    unresolved = (
        sum(1 for r in feature_refs if not r.resolved)
        + sum(1 for r in construct_refs if not r.resolved)
        + sum(1 for r in agent_refs if not r.resolved)
    )

    # Batch 6: rewrite bot-emitted narrative into Zennify voice via
    # the cached deterministic rewriter. Anchor-preservation guarantees
    # E-IDs / subcap IDs / monetary values are not dropped; on any
    # validator rejection the wrapper serves the original text.
    from app.services.narrative_polish import polish_narrative
    polished_description = polish_narrative(
        rec.description,
        target_kind="recommendation",
        target_id=str(rec.id),
        catalogue_version=ver or "n/a",
    )
    polished_title = polish_narrative(
        rec.title,
        target_kind="recommendation",
        target_id=f"{rec.id}:title",
        catalogue_version=ver or "n/a",
    )
    # Dependencies (D4 DependencyMap): prerequisites are parsed at ingest;
    # "unlocks" is the read-time inverse — recs in the same run that list THIS
    # rec as a prerequisite. Both empty until re-ingest populates
    # prerequisite_rec_ids (honest contextual-empty in the modal).
    prerequisites = list(rec.prerequisite_rec_ids or [])
    unlock_rows = (
        await session.execute(
            text(
                """
                SELECT rec_id FROM recommendations
                WHERE run_id = (
                    SELECT run_id FROM recommendations
                    WHERE id = CAST(:rid AS uuid)
                )
                  AND :this_rec_id = ANY(prerequisite_rec_ids)
                ORDER BY rec_id
                """
            ),
            {"rid": recommendation_id, "this_rec_id": rec.rec_id},
        )
    ).all()
    unlocks = [u.rec_id for u in unlock_rows]

    payload = RecommendationDetail(
        id=str(rec.id),
        rec_id=rec.rec_id,
        title=polished_title,
        description=polished_description,
        entity_display_id=rec.entity_display_id,
        target_subcap_ids=list(rec.target_subcap_ids or []),
        platform_id=rec.platform_id,
        addressable_offerings=list(rec.addressable_offerings or []),
        uplift_per_pillar=dict(rec.uplift_per_pillar) if rec.uplift_per_pillar else None,
        effort_band=rec.effort_band,
        cited_features=feature_refs,
        cited_constructs=construct_refs,
        cited_agents=agent_refs,
        unresolved_count=unresolved,
        # `runs.ccg_catalog_version` may be NULL on legacy rows — the
        # required-str schema field turned that into a 500 at response
        # build time. Label honestly instead of failing the whole modal.
        catalogue_version=ver or "unversioned",
        dependencies={"prerequisites": prerequisites, "unlocks": unlocks},
        # Migration 048 fields — getattr keeps the legacy column-list
        # fallback path (pre-048 envs) shape-safe.
        feature=getattr(rec, "feature", None),
        phase=getattr(rec, "phase", None),
        root_cause_e_ids=list(getattr(rec, "root_cause_e_ids", None) or []),
        outcomes=(
            dict(rec.outcomes)
            if isinstance(getattr(rec, "outcomes", None), dict) else None
        ),
    )
    return strip_and_respond(payload, view.audience, RecommendationDetail)


async def _resolve_features(
    session, version: str, cited: list[str],
) -> list[CitedReference]:
    if not cited:
        return []
    rows = (
        await session.execute(
            text(
                """
                SELECT feature_name AS name
                FROM ccg_l4_features
                WHERE version = :ver AND feature_name = ANY(:names)
                """
            ),
            {"ver": version, "names": cited},
        )
    ).all()
    known = {r.name for r in rows}
    return [
        CitedReference(
            kind="feature", id=name, resolved=name in known,
            name=name if name in known else None,
        )
        for name in cited
    ]


async def _resolve_constructs(
    session, version: str, cited: list[str],
) -> list[CitedReference]:
    if not cited:
        return []
    rows = (
        await session.execute(
            text(
                """
                SELECT construct_name AS name
                FROM ccg_platform_constructs
                WHERE version = :ver AND construct_name = ANY(:names)
                """
            ),
            {"ver": version, "names": cited},
        )
    ).all()
    known = {r.name for r in rows}
    return [
        CitedReference(
            kind="construct", id=name, resolved=name in known,
            name=name if name in known else None,
        )
        for name in cited
    ]


async def _resolve_agents(
    session, version: str, cited: list[str],
) -> list[CitedReference]:
    if not cited:
        return []
    rows = (
        await session.execute(
            text(
                """
                SELECT agent_id, agent_name
                FROM ccg_agentforce_agents
                WHERE version = :ver AND agent_id = ANY(:ids)
                """
            ),
            {"ver": version, "ids": cited},
        )
    ).all()
    known = {r.agent_id: r.agent_name for r in rows}
    return [
        CitedReference(
            kind="agent", id=agent_id,
            resolved=agent_id in known,
            name=known.get(agent_id),
        )
        for agent_id in cited
    ]


# ── D4 RecommendationModal "AE notes" — durable per-recommendation note ─────
#
# One shared team note per (client, recommendation), keyed by
# UNIQUE(entity_id, rec_id). Per the operator mandate the note PERSISTS
# across sessions AND across users — every AE sees + overwrites the same
# note; `rec_id` is the HUMAN id ("REC-04") so the note survives a
# re-ingest that mints a new recommendations.id uuid.
#
# FLAGGED FOR FUTURE SYNTHESIS: `recommendation_notes` is the persisted
# INPUT for a FUTURE Gemini/ML recalibration pass. The note is captured +
# persisted here; recalibrating findings / scores / roadmap in light of it
# is DELIBERATELY NOT implemented — per the operator guardrail that must be
# a deep Gemini/ML impact simulation, not a deterministic stub. See
# app/models/recommendation_notes.py + migration 057.
async def _resolve_entity_id(session, display_id: str) -> str:
    """display_id → entity uuid (str). 404 when the entity doesn't exist."""
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
    return str(ent.id)


def _note_out(row) -> RecommendationNoteOut:
    return RecommendationNoteOut(
        note=row.note_md,
        author_email=row.author_email,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


@router.get(
    "/entities/{display_id}/recommendations/{rec_id}/note",
    response_model=RecommendationNoteOut,
)
async def get_recommendation_note(
    display_id: str,
    rec_id: str,
    _user: AeUserDep,
    session: SessionDep,
) -> RecommendationNoteOut:
    """The durable AE note for (entity, rec_id).

    Returns the persisted note, or an EMPTY note object
    ``{note:"", author_email:null, updated_at:null}`` when none exists —
    the modal expects a shape, so a missing note is NOT a 404. An unknown
    entity IS a 404 (bad path, not an empty note)."""
    entity_id = await _resolve_entity_id(session, display_id)
    row = (
        await session.execute(
            text(
                """
                SELECT note_md, author_email, updated_at
                FROM recommendation_notes
                WHERE entity_id = CAST(:eid AS uuid) AND rec_id = :rid
                """
            ),
            {"eid": entity_id, "rid": rec_id},
        )
    ).first()
    if row is None:
        return RecommendationNoteOut(note="", author_email=None, updated_at=None)
    return _note_out(row)


@router.put(
    "/entities/{display_id}/recommendations/{rec_id}/note",
    response_model=RecommendationNoteOut,
)
async def put_recommendation_note(
    display_id: str,
    rec_id: str,
    body: RecommendationNoteIn,
    user: AeUserDep,
    session: SessionDep,
) -> RecommendationNoteOut:
    """Upsert the shared AE note for (entity, rec_id).

    A blank/whitespace note DELETES the row (returning the empty note
    object). Otherwise INSERT … ON CONFLICT(entity_id, rec_id) DO UPDATE,
    stamping ``author_email`` from the current user and ``updated_at=NOW()``.
    404 when the entity doesn't exist."""
    entity_id = await _resolve_entity_id(session, display_id)
    # Blank/whitespace clears the note; the raw text is stored otherwise
    # (internal markdown/whitespace preserved for an exact round-trip).
    if not body.note.strip():
        await session.execute(
            text(
                "DELETE FROM recommendation_notes "
                "WHERE entity_id = CAST(:eid AS uuid) AND rec_id = :rid"
            ),
            {"eid": entity_id, "rid": rec_id},
        )
        await session.commit()
        return RecommendationNoteOut(note="", author_email=None, updated_at=None)
    row = (
        await session.execute(
            text(
                """
                INSERT INTO recommendation_notes
                  (entity_id, rec_id, note_md, author_email, created_at, updated_at)
                VALUES
                  (CAST(:eid AS uuid), :rid, :note, :author, NOW(), NOW())
                ON CONFLICT (entity_id, rec_id) DO UPDATE SET
                  note_md = EXCLUDED.note_md,
                  author_email = EXCLUDED.author_email,
                  updated_at = NOW()
                RETURNING note_md, author_email, updated_at
                """
            ),
            {
                "eid": entity_id, "rid": rec_id,
                "note": body.note, "author": user.email,
            },
        )
    ).first()
    await session.commit()
    return _note_out(row)
