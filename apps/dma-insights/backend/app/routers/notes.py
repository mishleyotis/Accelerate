"""AE notes endpoints — rec-card / roadmap-item notes + recalibration.

New prototype feature (2026-07-06, migration 057). The RecommendationModal
(which also fronts roadmap-item drilldowns — roadmap chips open the rec
modal) gains an "AE notes" tab:

  GET  /api/v1/entities/{display_id}/notes?target_kind=&target_id=
  POST /api/v1/entities/{display_id}/notes
  PATCH /api/v1/notes/{note_id}                (status / body)
  GET  /api/v1/notes/{note_id}/assessment      (latest simulation)
  POST /api/v1/notes/{note_id}/assessment:run  (ANALYST+ re-run)
  GET  /api/v1/admin/note-assessments          (ADMIN review queue)
  POST /api/v1/admin/note-assessments/{id}:review

All note writes are auth-gated AE+ (CUSTOMER is 403). A note with
``recalibrate=true`` triggers the Gemini impact SIMULATION
(services/ae_notes.run_impact_assessment) best-effort inside the same
request — the note write NEVER fails on a simulation failure; the
assessment row records the honest status (SIMULATED / PENDING / FAILED)
with full provenance. Nothing on this surface mutates scores.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep, require_admin, require_analyst
from app.services.ae_notes import (
    NOTE_STATUSES,
    NOTE_TARGET_KINDS,
    run_impact_assessment,
)

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1", tags=["ae-notes"])

NoteTargetKind = Literal["recommendation", "roadmap_phase", "insight_card"]
NoteStatus = Literal["ACTIONED", "PENDING", "SUPERSEDED"]


def _require_uuid(value: str, *, what: str) -> str:
    """404 (not 500) on a malformed id: the SQL below CASTs to uuid, and an
    unparseable path segment must read as 'no such row', never a DB error
    (the every-GET-route no-5xx regression net probes /notes/x/assessment)."""
    import uuid as _uuid
    try:
        return str(_uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{what} {value!r} not found",
        ) from None


class NoteIn(BaseModel):
    target_kind: NoteTargetKind
    target_id: str = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1, max_length=8000)
    status: NoteStatus = "PENDING"
    sf_opp_id: str | None = Field(default=None, max_length=64)
    recalibrate: bool = False


class NotePatch(BaseModel):
    body: str | None = Field(default=None, min_length=1, max_length=8000)
    status: NoteStatus | None = None


class NoteOut(BaseModel):
    id: str
    target_kind: str
    target_id: str
    author_email: str
    author_role: str
    status: str
    body: str
    sf_opp_id: str | None = None
    recalibrate: bool = False
    created_at: datetime
    # Latest assessment status for the recalibration chip
    # (None = no recalibration requested on this note).
    assessment_status: str | None = None


class NoteListResponse(BaseModel):
    entity_display_id: str
    items: list[NoteOut] = Field(default_factory=list)


class AssessmentOut(BaseModel):
    id: str
    note_id: str
    status: str
    assessment_md: str | None = None
    impact: dict | None = None
    model: str | None = None
    grounding_evidence_ids: list[str] = Field(default_factory=list)
    validators_passed: bool = False
    failure_reason: str | None = None
    created_at: datetime
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


async def _resolve_entity(session, display_id: str):
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
    return ent


def _require_ae_plus(user) -> None:
    """AE+ gate for note writes (CUSTOMER may read nothing here either —
    the notes segment is internal field intelligence)."""
    from app.auth import role_at_least

    if not role_at_least(user.role, "AE"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"role '{user.role}' insufficient (needs AE+)",
        )


@router.get("/entities/{display_id}/notes", response_model=NoteListResponse)
async def list_notes(
    display_id: str,
    user: CurrentUserDep,
    session: SessionDep,
    target_kind: NoteTargetKind | None = None,
    target_id: str | None = None,
) -> NoteListResponse:
    _require_ae_plus(user)
    ent = await _resolve_entity(session, display_id)
    where = "n.entity_id = :eid AND n.deleted_at IS NULL"
    params: dict = {"eid": ent.id}
    if target_kind:
        where += " AND n.target_kind = :tk"
        params["tk"] = target_kind
    if target_id:
        where += " AND n.target_id = :tid"
        params["tid"] = target_id
    rows = (
        await session.execute(
            text(
                f"""
                SELECT n.id, n.target_kind, n.target_id, n.author_email,
                       n.author_role, n.status, n.body, n.sf_opp_id,
                       n.recalibrate, n.created_at,
                       (
                         SELECT a.status FROM ae_note_assessments a
                         WHERE a.note_id = n.id
                         ORDER BY a.created_at DESC LIMIT 1
                       ) AS assessment_status
                FROM ae_notes n
                WHERE {where}
                ORDER BY n.created_at DESC
                """
            ),
            params,
        )
    ).all()
    return NoteListResponse(
        entity_display_id=display_id,
        items=[_note_out(r) for r in rows],
    )


def _note_out(r) -> NoteOut:
    return NoteOut(
        id=str(r.id),
        target_kind=r.target_kind,
        target_id=r.target_id,
        author_email=r.author_email,
        author_role=r.author_role,
        status=r.status,
        body=r.body,
        sf_opp_id=r.sf_opp_id,
        recalibrate=bool(r.recalibrate),
        created_at=r.created_at,
        assessment_status=getattr(r, "assessment_status", None),
    )


@router.post(
    "/entities/{display_id}/notes",
    response_model=NoteOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_note(
    display_id: str,
    body: NoteIn,
    user: CurrentUserDep,
    session: SessionDep,
) -> NoteOut:
    _require_ae_plus(user)
    ent = await _resolve_entity(session, display_id)
    run_row = (
        await session.execute(
            text(
                "SELECT id FROM runs WHERE entity_id = :eid AND status = 'ACTIVE' "
                "ORDER BY completed_at DESC NULLS LAST LIMIT 1"
            ),
            {"eid": ent.id},
        )
    ).first()
    row = (
        await session.execute(
            text(
                """
                INSERT INTO ae_notes
                  (entity_id, run_id, target_kind, target_id, author_email,
                   author_role, status, body, sf_opp_id, recalibrate)
                VALUES
                  (CAST(:eid AS uuid), CAST(:rid AS uuid), :tk, :tid,
                   :email, :role, :status, :body, :sf, :recal)
                RETURNING id, target_kind, target_id, author_email,
                          author_role, status, body, sf_opp_id, recalibrate,
                          created_at
                """
            ),
            {
                "eid": str(ent.id),
                "rid": str(run_row.id) if run_row else None,
                "tk": body.target_kind,
                "tid": body.target_id,
                "email": user.email,
                "role": user.role,
                "status": body.status,
                "body": body.body,
                "sf": body.sf_opp_id,
                "recal": body.recalibrate,
            },
        )
    ).first()
    await session.commit()

    assessment_status: str | None = None
    if body.recalibrate:
        # Best-effort simulation — the note write already committed; any
        # failure here lands as an honest FAILED/PENDING assessment row.
        try:
            result = await run_impact_assessment(
                session,
                note_id=str(row.id),
                entity_id=str(ent.id),
                target_kind=body.target_kind,
                target_id=body.target_id,
                note_body=body.body,
            )
            await session.commit()
            assessment_status = result.get("status")
        except Exception as e:
            log.warning("ae_notes.assessment_failed", note_id=str(row.id),
                        err=str(e)[:200])
            import contextlib
            with contextlib.suppress(Exception):
                await session.rollback()
            assessment_status = None

    out = _note_out(row)
    out.assessment_status = assessment_status
    return out


@router.patch("/notes/{note_id}", response_model=NoteOut)
async def patch_note(
    note_id: str,
    patch: NotePatch,
    user: CurrentUserDep,
    session: SessionDep,
) -> NoteOut:
    _require_ae_plus(user)
    note_id = _require_uuid(note_id, what="note")
    if patch.body is None and patch.status is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="nothing to update — pass body and/or status",
        )
    row = (
        await session.execute(
            text(
                """
                UPDATE ae_notes
                SET body = COALESCE(:body, body),
                    status = COALESCE(:status, status),
                    updated_at = NOW()
                WHERE id = CAST(:nid AS uuid) AND deleted_at IS NULL
                RETURNING id, target_kind, target_id, author_email,
                          author_role, status, body, sf_opp_id, recalibrate,
                          created_at
                """
            ),
            {"nid": note_id, "body": patch.body, "status": patch.status},
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"note {note_id} not found",
        )
    await session.commit()
    return _note_out(row)


@router.get("/notes/{note_id}/assessment", response_model=AssessmentOut)
async def get_note_assessment(
    note_id: str,
    user: CurrentUserDep,
    session: SessionDep,
) -> AssessmentOut:
    _require_ae_plus(user)
    note_id = _require_uuid(note_id, what="note")
    row = (
        await session.execute(
            text(
                """
                SELECT id, note_id, status, assessment_md, impact, model,
                       grounding_evidence_ids, validators_passed,
                       failure_reason, created_at, reviewed_by, reviewed_at
                FROM ae_note_assessments
                WHERE note_id = CAST(:nid AS uuid)
                ORDER BY created_at DESC LIMIT 1
                """
            ),
            {"nid": note_id},
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no assessment for note {note_id}",
        )
    return _assessment_out(row)


def _assessment_out(row) -> AssessmentOut:
    # Validated-Gemini-only: unvalidated raw payloads stay internal — the
    # response only carries impact/assessment_md when validators passed.
    validated = bool(row.validators_passed)
    return AssessmentOut(
        id=str(row.id),
        note_id=str(row.note_id),
        status=row.status,
        assessment_md=row.assessment_md if validated else None,
        impact=(dict(row.impact) if validated and isinstance(row.impact, dict) else None),
        model=row.model,
        grounding_evidence_ids=list(row.grounding_evidence_ids or []),
        validators_passed=validated,
        failure_reason=row.failure_reason,
        created_at=row.created_at,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


@router.post(
    "/notes/{note_id}/assessment:run",
    response_model=AssessmentOut,
    dependencies=[Depends(require_analyst)],
)
async def rerun_note_assessment(
    note_id: str,
    _user: CurrentUserDep,
    session: SessionDep,
) -> AssessmentOut:
    """ANALYST+ retry — e.g. after a PENDING (Gemini-unavailable) first
    attempt, or when new evidence landed."""
    note_id = _require_uuid(note_id, what="note")
    note = (
        await session.execute(
            text(
                """
                SELECT id, entity_id, target_kind, target_id, body
                FROM ae_notes
                WHERE id = CAST(:nid AS uuid) AND deleted_at IS NULL
                """
            ),
            {"nid": note_id},
        )
    ).first()
    if note is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"note {note_id} not found",
        )
    await run_impact_assessment(
        session,
        note_id=str(note.id),
        entity_id=str(note.entity_id),
        target_kind=note.target_kind,
        target_id=note.target_id,
        note_body=note.body,
    )
    await session.commit()
    return await _latest_assessment(session, note_id)


async def _latest_assessment(session, note_id: str) -> AssessmentOut:
    row = (
        await session.execute(
            text(
                """
                SELECT id, note_id, status, assessment_md, impact, model,
                       grounding_evidence_ids, validators_passed,
                       failure_reason, created_at, reviewed_by, reviewed_at
                FROM ae_note_assessments
                WHERE note_id = CAST(:nid AS uuid)
                ORDER BY created_at DESC LIMIT 1
                """
            ),
            {"nid": note_id},
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"no assessment for note {note_id}",
        )
    return _assessment_out(row)


class AssessmentReviewIn(BaseModel):
    verdict: Literal["REVIEWED"] = "REVIEWED"


@router.get(
    "/admin/note-assessments",
    dependencies=[Depends(require_admin)],
)
async def list_note_assessments(
    _user: CurrentUserDep,
    session: SessionDep,
    status_filter: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """ADMIN review queue — newest first, optionally filtered by status."""
    where = "1=1"
    params: dict = {"lim": max(1, min(int(limit), 200))}
    if status_filter:
        where = "a.status = :st"
        params["st"] = status_filter
    rows = (
        await session.execute(
            text(
                f"""
                SELECT a.id, a.note_id, a.status, a.assessment_md,
                       a.validators_passed, a.failure_reason, a.created_at,
                       a.reviewed_by, a.reviewed_at,
                       n.target_kind, n.target_id, n.body AS note_body,
                       n.author_email, e.display_id
                FROM ae_note_assessments a
                JOIN ae_notes n ON n.id = a.note_id
                JOIN entities e ON e.id = n.entity_id
                WHERE {where}
                ORDER BY a.created_at DESC
                LIMIT :lim
                """
            ),
            params,
        )
    ).all()
    return [
        {
            "id": str(r.id),
            "note_id": str(r.note_id),
            "status": r.status,
            "assessment_md": r.assessment_md if r.validators_passed else None,
            "validators_passed": bool(r.validators_passed),
            "failure_reason": r.failure_reason,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "reviewed_by": r.reviewed_by,
            "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            "target_kind": r.target_kind,
            "target_id": r.target_id,
            "note_body": r.note_body,
            "author_email": r.author_email,
            "entity_display_id": r.display_id,
        }
        for r in rows
    ]


@router.post(
    "/admin/note-assessments/{assessment_id}:review",
    dependencies=[Depends(require_admin)],
)
async def review_note_assessment(
    assessment_id: str,
    body: AssessmentReviewIn,
    user: CurrentUserDep,
    session: SessionDep,
) -> dict:
    """Mark a simulation REVIEWED (human sign-off recorded). Applying any
    actual recalibration remains a separate, explicit admin operation —
    this endpoint records the review, nothing else."""
    assessment_id = _require_uuid(assessment_id, what="assessment")
    row = (
        await session.execute(
            text(
                """
                UPDATE ae_note_assessments
                SET status = 'REVIEWED', reviewed_by = :who, reviewed_at = NOW()
                WHERE id = CAST(:aid AS uuid) AND status = 'SIMULATED'
                RETURNING id, status, reviewed_by, reviewed_at
                """
            ),
            {"aid": assessment_id, "who": user.email},
        )
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"assessment {assessment_id} not found or not in SIMULATED "
                "state (only validated simulations can be reviewed)"
            ),
        )
    await session.commit()
    return {
        "id": str(row.id),
        "status": row.status,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
    }


# Re-exported for tests that assert the closed vocabularies match the
# migration CHECK constraints.
__all__ = [
    "AssessmentOut",
    "NOTE_STATUSES",
    "NOTE_TARGET_KINDS",
    "NoteIn",
    "NoteListResponse",
    "NoteOut",
    "router",
]
