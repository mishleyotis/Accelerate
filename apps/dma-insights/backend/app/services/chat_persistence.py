"""Chat persistence — append-only writes to chat_sessions / chat_messages
/ chat_feedback. The DB owns the conversation log; this module only
holds the pure helpers that build INSERT params + read-shape mappers.

State transitions:
  session_id is None on /answer
    → caller MUST call create_session() first, then append_message()
  session belongs to a different user than the caller
    → load_session_for_user() returns None (router converts to 403)
  feedback rating = -1 with better_answer != None
    → recorded as the adversarial-network "preferred response" signal;
      the nightly chat_learning worker reads these and boosts the
      preferred_evidence_ids for the surrounding cluster.

Pure-logic only. Tests mock the AsyncSession.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class MessagePayload:
    """Inputs for one chat_messages insert."""
    session_id: str
    role: str
    content_markdown: str
    cited_evidence_ids: list[str]
    cited_subcap_ids: list[str]
    retrieval_bundle: list[dict] | None = None
    model: str | None = None
    tokens_in: int | None = None
    tokens_out: int | None = None
    latency_ms: int | None = None
    validators_passed: bool | None = None
    hallucination_flags: dict | None = None


async def create_session(
    session: AsyncSession,
    *,
    user_id: str,
    entity_id: str | None,
    surface: str,
    page_context: dict[str, Any],
    catalogue_version: str,
) -> str:
    """Insert a new chat_sessions row, return the new session_id."""
    row = (
        await session.execute(
            text(
                """
                INSERT INTO chat_sessions
                    (user_id, entity_id, surface, page_context, catalogue_version)
                VALUES
                    (CAST(:uid AS uuid),
                     CASE WHEN :eid = '' THEN NULL ELSE CAST(:eid AS uuid) END,
                     :surface, CAST(:pc AS jsonb), :ver)
                RETURNING id::text
                """
            ),
            {
                "uid": user_id,
                "eid": entity_id or "",
                "surface": surface,
                "pc": json.dumps(page_context or {}),
                "ver": catalogue_version,
            },
        )
    ).first()
    return row.id  # type: ignore[no-any-return]


async def append_message(
    session: AsyncSession, payload: MessagePayload
) -> str:
    """Insert a chat_messages row + update parent session.last_message_at.
    Returns the new message_id."""
    msg = (
        await session.execute(
            text(
                """
                INSERT INTO chat_messages
                    (session_id, role, content_markdown,
                     cited_evidence_ids, cited_subcap_ids,
                     retrieval_bundle, model, tokens_in, tokens_out,
                     latency_ms, validators_passed, hallucination_flags)
                VALUES
                    (CAST(:sid AS uuid), :role, :content,
                     CAST(:eids AS varchar[]), CAST(:subs AS varchar[]),
                     CAST(:bundle AS jsonb), :model, :tin, :tout,
                     :lat, :vp, CAST(:flags AS jsonb))
                RETURNING id::text
                """
            ),
            {
                "sid": payload.session_id,
                "role": payload.role,
                "content": payload.content_markdown,
                "eids": payload.cited_evidence_ids or [],
                "subs": payload.cited_subcap_ids or [],
                "bundle": (
                    json.dumps(payload.retrieval_bundle)
                    if payload.retrieval_bundle is not None
                    else None
                ),
                "model": payload.model,
                "tin": payload.tokens_in,
                "tout": payload.tokens_out,
                "lat": payload.latency_ms,
                "vp": payload.validators_passed,
                "flags": (
                    json.dumps(payload.hallucination_flags)
                    if payload.hallucination_flags is not None
                    else None
                ),
            },
        )
    ).first()
    await session.execute(
        text(
            "UPDATE chat_sessions SET last_message_at = NOW() "
            "WHERE id = CAST(:sid AS uuid)"
        ),
        {"sid": payload.session_id},
    )
    return msg.id  # type: ignore[no-any-return]


async def load_session_for_user(
    session: AsyncSession, *, session_id: str, user_id: str,
) -> dict | None:
    """Return the chat_sessions row IF it belongs to the user, else None.
    Router converts None → 403/404."""
    row = (
        await session.execute(
            text(
                """
                SELECT id::text, user_id::text, entity_id::text,
                       surface, page_context, catalogue_version,
                       started_at, last_message_at, deleted_at
                FROM chat_sessions
                WHERE id = CAST(:sid AS uuid)
                  AND user_id = CAST(:uid AS uuid)
                  AND deleted_at IS NULL
                """
            ),
            {"sid": session_id, "uid": user_id},
        )
    ).first()
    if row is None:
        return None
    return {
        "id": row.id,
        "user_id": row.user_id,
        "entity_id": row.entity_id,
        "surface": row.surface,
        "page_context": row.page_context,
        "catalogue_version": row.catalogue_version,
        "started_at": row.started_at,
        "last_message_at": row.last_message_at,
    }


async def list_recent_messages(
    session: AsyncSession, *, session_id: str, limit: int = 8,
) -> list[dict]:
    """Most-recent N messages in chronological order, used to feed the
    'last 4 turns' context window into the next prompt."""
    rows = (
        await session.execute(
            text(
                """
                SELECT id::text, role, content_markdown
                FROM chat_messages
                WHERE session_id = CAST(:sid AS uuid)
                ORDER BY created_at DESC
                LIMIT :lim
                """
            ),
            {"sid": session_id, "lim": limit},
        )
    ).all()
    rows = list(reversed(rows))
    return [
        {"id": r.id, "role": r.role, "content_markdown": r.content_markdown}
        for r in rows
    ]
