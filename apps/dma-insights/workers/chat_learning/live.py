"""chat_learning live IO. Joins chat_feedback to its parent assistant
message (and that message's preceding user question), groups by surface,
clusters via service.rollup_signals, persists chat_learning_signals.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import text

from app.database import get_sessionmaker
from workers.chat_learning.service import FeedbackSample, rollup_signals


async def run(*, since: str | None = None) -> dict:
    sm = get_sessionmaker()
    summary = {"samples_seen": 0, "signals_written": 0}
    now = datetime.now(tz=UTC)
    async with sm() as session:
        rows = await _fetch_feedback_with_context(session, since=since)
        summary["samples_seen"] = len(rows)
        # Build question_lookup for exemplars
        question_lookup = {r["message_id"]: r["user_question"] for r in rows}
        samples = [
            FeedbackSample(
                message_id=r["message_id"],
                surface=r["surface"],
                embedding=r["embedding"] or [],
                rating=r["rating"],
                cited_evidence_ids=r["cited_evidence_ids"] or [],
                validators_passed=bool(r["validators_passed"]),
                created_at=r["created_at"],
            )
            for r in rows
        ]
        signals = rollup_signals(samples, now=now, question_lookup=question_lookup)
        # Replace prior rollups for clean state.
        await session.execute(text("DELETE FROM chat_learning_signals"))
        for sig in signals:
            await session.execute(
                text(
                    """
                    INSERT INTO chat_learning_signals
                        (surface, prompt_centroid, exemplar_question,
                         retrieval_quality, response_quality, effectiveness,
                         sample_count, preferred_evidence_ids)
                    VALUES
                        (:surface,
                         CASE WHEN :centroid_len > 0
                              THEN CAST(:centroid AS vector)
                              ELSE NULL END,
                         :exemplar, :rq, :respq, :eff, :n,
                         CAST(:eids AS varchar[]))
                    """
                ),
                {
                    "surface": sig.surface,
                    "centroid": "[" + ",".join(str(x) for x in sig.prompt_centroid) + "]",
                    "centroid_len": len(sig.prompt_centroid),
                    "exemplar": sig.exemplar_question,
                    "rq": sig.retrieval_quality,
                    "respq": sig.response_quality,
                    "eff": sig.effectiveness,
                    "n": sig.sample_count,
                    "eids": sig.preferred_evidence_ids,
                },
            )
        summary["signals_written"] = len(signals)
        await session.commit()
    print(json.dumps(summary, indent=2))
    return summary


async def _fetch_feedback_with_context(
    session, *, since: str | None,
) -> list[dict]:
    sql = """
        SELECT m.id::text AS message_id,
               s.surface AS surface,
               (SELECT m2.content_markdown FROM chat_messages m2
                  WHERE m2.session_id = m.session_id AND m2.role = 'user'
                    AND m2.created_at < m.created_at
                  ORDER BY m2.created_at DESC LIMIT 1) AS user_question,
               m.embedding AS embedding,
               f.rating AS rating,
               m.cited_evidence_ids AS cited_evidence_ids,
               m.validators_passed AS validators_passed,
               f.created_at AS created_at
        FROM chat_feedback f
        JOIN chat_messages m ON m.id = f.message_id
        JOIN chat_sessions s ON s.id = m.session_id
        WHERE m.role = 'assistant'
    """
    params: dict = {}
    if since:
        sql += " AND f.created_at >= :since"
        params["since"] = since
    rows = (await session.execute(text(sql), params)).all()
    out = []
    for r in rows:
        emb = list(r.embedding) if r.embedding is not None else None
        out.append({
            "message_id": r.message_id,
            "surface": r.surface,
            "user_question": r.user_question or "",
            "embedding": emb,
            "rating": int(r.rating),
            "cited_evidence_ids": list(r.cited_evidence_ids or []),
            "validators_passed": bool(r.validators_passed),
            "created_at": r.created_at,
        })
    return out
