"""Chat sessions + feedback router.

State transitions:
  GET /sessions/:id where session.user_id != current user
    → 403; chat history is per-user-private
  DELETE /sessions/:id
    → soft delete (deleted_at = NOW()); subsequent GET returns 404
  POST /feedback with rating=-1 + better_answer
    → row recorded; adversarial-learning rollup picks it up at next
      worker run and boosts preferred_evidence_ids for the cluster
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import text

from app.deps import CurrentUserDep, SessionDep
from app.schemas.chat import (
    ChatFeedbackRequest,
    ChatFeedbackResponse,
    ChatMessageOut,
    ChatSessionDetailResponse,
    ChatSessionListResponse,
    ChatSessionSummary,
)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_sessions(
    user: CurrentUserDep,
    session: SessionDep,
    entity_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> ChatSessionListResponse:
    sql = """
        SELECT s.id::text AS id, s.surface, s.entity_id::text AS entity_id,
               s.page_context, s.started_at, s.last_message_at,
               (SELECT COUNT(*) FROM chat_messages m WHERE m.session_id = s.id)
                   AS message_count,
               (SELECT m2.content_markdown FROM chat_messages m2
                  WHERE m2.session_id = s.id AND m2.role = 'user'
                  ORDER BY m2.created_at ASC LIMIT 1) AS last_question
        FROM chat_sessions s
        WHERE s.user_id = CAST(:uid AS uuid)
          AND s.deleted_at IS NULL
    """
    params: dict[str, object] = {"uid": user.user_id, "lim": limit}
    if entity_id is not None:
        sql += " AND s.entity_id = CAST(:eid AS uuid)"
        params["eid"] = entity_id
    sql += " ORDER BY s.last_message_at DESC LIMIT :lim"

    rows = (await session.execute(text(sql), params)).all()
    items = [
        ChatSessionSummary(
            id=r.id,
            surface=r.surface,
            entity_id=r.entity_id,
            page_context=r.page_context or {},
            started_at=r.started_at,
            last_message_at=r.last_message_at,
            message_count=int(r.message_count or 0),
            last_question=r.last_question,
        )
        for r in rows
    ]
    return ChatSessionListResponse(items=items)


@router.get("/sessions/{session_id}", response_model=ChatSessionDetailResponse)
async def get_session(
    session_id: str,
    user: CurrentUserDep,
    session: SessionDep,
) -> ChatSessionDetailResponse:
    sess = (
        await session.execute(
            text(
                """
                SELECT s.id::text AS id, s.user_id::text AS uid,
                       s.surface, s.entity_id::text AS entity_id,
                       s.page_context, s.started_at, s.last_message_at,
                       s.deleted_at
                FROM chat_sessions s
                WHERE s.id = CAST(:sid AS uuid)
                """
            ),
            {"sid": session_id},
        )
    ).first()
    if sess is None or sess.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="session not found")
    if sess.uid != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="not your session")

    msgs = (
        await session.execute(
            text(
                """
                SELECT id::text, role, content_markdown,
                       cited_evidence_ids, cited_subcap_ids,
                       model, validators_passed, created_at
                FROM chat_messages
                WHERE session_id = CAST(:sid AS uuid)
                ORDER BY created_at ASC
                """
            ),
            {"sid": session_id},
        )
    ).all()
    return ChatSessionDetailResponse(
        id=sess.id,
        surface=sess.surface,
        entity_id=sess.entity_id,
        page_context=sess.page_context or {},
        started_at=sess.started_at,
        last_message_at=sess.last_message_at,
        messages=[
            ChatMessageOut(
                id=m.id,
                role=m.role,
                content_markdown=m.content_markdown,
                cited_evidence_ids=list(m.cited_evidence_ids or []),
                cited_subcap_ids=list(m.cited_subcap_ids or []),
                model=m.model,
                validators_passed=m.validators_passed,
                created_at=m.created_at,
            )
            for m in msgs
        ],
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    user: CurrentUserDep,
    session: SessionDep,
) -> Response:
    row = (
        await session.execute(
            text(
                """
                UPDATE chat_sessions
                SET deleted_at = NOW()
                WHERE id = CAST(:sid AS uuid)
                  AND user_id = CAST(:uid AS uuid)
                  AND deleted_at IS NULL
                RETURNING id::text
                """
            ),
            {"sid": session_id, "uid": user.user_id},
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="session not found")
    await session.commit()
    return Response(status_code=204)


@router.post(
    "/messages/{message_id}/feedback",
    response_model=ChatFeedbackResponse,
)
async def post_feedback(
    message_id: str,
    body: ChatFeedbackRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> ChatFeedbackResponse:
    # Verify the message belongs to a session this user owns.
    owner = (
        await session.execute(
            text(
                """
                SELECT s.user_id::text AS uid
                FROM chat_messages m
                JOIN chat_sessions s ON s.id = m.session_id
                WHERE m.id = CAST(:mid AS uuid)
                """
            ),
            {"mid": message_id},
        )
    ).first()
    if owner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="message not found")
    if owner.uid != user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="not your message")

    row = (
        await session.execute(
            text(
                """
                INSERT INTO chat_feedback
                    (message_id, user_id, rating, unhelpful_reason,
                     free_text, better_answer)
                VALUES
                    (CAST(:mid AS uuid), CAST(:uid AS uuid),
                     :rating, :reason, :ft, :ba)
                RETURNING id::text, created_at
                """
            ),
            {
                "mid": message_id,
                "uid": user.user_id,
                "rating": body.rating,
                "reason": body.unhelpful_reason,
                "ft": body.free_text,
                "ba": body.better_answer,
            },
        )
    ).first()
    await session.commit()

    # ── Synthesis-cache feedback invalidation ─────────────────────────
    # A 👎 with `unhelpful_reason='hallucinated'` invalidates ONLY the
    # specific cache row that produced this hallucinated answer. Sibling
    # rows untouched. Next equivalent question re-synthesizes.
    #
    # State branches:
    #   negative_hallucinated → invalidate the single row tied to
    #                           message → cache_id mapping
    #   negative_other_reason → no cache invalidation (the reranker
    #                           handles soft signal via chat_learning)
    #   neutral_or_positive  → no invalidation
    #   cache_module_missing  → log + continue (feedback row already
    #                           persisted; learning still happens via
    #                           the nightly chat_learning rollup)
    if body.rating == -1 and (body.unhelpful_reason or "") == "hallucinated":
        try:
            from sqlalchemy import text as _text

            from app.services.synthesis_cache_db import safe_mark_invalidated
            from app.services.synthesis_orchestrator import (
                build_invalidation_for_feedback,
            )
            # The chat_messages row may carry a cache_row_id pointer if
            # the assistant turn was synthesized via the orchestrator.
            # We probe the column existence-tolerantly so this works
            # even when the schema hasn't been bumped yet.
            # retrieval_bundle is a JSONB array; the rag router appends
            # a {"kind":"_meta","ref_id":"cache_row_id","cache_row_id":...}
            # entry at the end. We scan the array for that marker.
            cache_row_q = await session.execute(
                _text(
                    """
                    SELECT (item->>'cache_row_id') AS cache_row_id
                    FROM chat_messages,
                         jsonb_array_elements(COALESCE(retrieval_bundle,
                                                       '[]'::jsonb)) item
                    WHERE chat_messages.id = CAST(:mid AS uuid)
                      AND item->>'kind' = '_meta'
                      AND item->>'ref_id' = 'cache_row_id'
                    LIMIT 1
                    """
                ),
                {"mid": message_id},
            )
            crow = cache_row_q.first()
            cache_row_id = (
                crow.cache_row_id if crow and crow.cache_row_id else None
            )
            if cache_row_id:
                spec = build_invalidation_for_feedback(cache_row_id)
                safe_mark_invalidated(spec)
        except Exception:
            # Defense in depth — feedback row already committed; never
            # raise from the invalidation side-effect.
            pass

    return ChatFeedbackResponse(
        id=row.id,
        message_id=message_id,
        rating=body.rating,
        created_at=row.created_at or datetime.now(tz=UTC),
    )
