"""Embedder live IO path — connects the pure service helpers in service.py
to real DB reads (SQLAlchemy async) and the Vertex SDK.

Called from main.py when --dry-run is NOT set.
"""
from __future__ import annotations

import sys

# NB: `datetime` here is the CLASS — `datetime.UTC` does not exist (the
# 2026-07-05 regen replica caught every `--since` invocation crashing
# with AttributeError behind the soft step, so embeddings never baked).
# UTC must come from the MODULE namespace.
from datetime import UTC, date, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_sessionmaker
from app.services.vertex_client import get_vertex_client
from workers.embedder.service import (
    ArtifactKind,
    EmbedBatchResult,
    EmbedCandidate,
    batchify,
    build_evidence_text,
    build_insight_text,
    build_recommendation_text,
    is_valid_vector,
    stitch_mixed_batch,
)


async def _fetch_evidence_candidates(
    session: AsyncSession, model_version: str, run_id: str | None, since: date | None
) -> list[EmbedCandidate]:
    """Fetch evidence_index rows that don't already have an embedding."""
    base = """
        SELECT ei.id::text, ei.source_name, ei.claim_type,
               COALESCE(ei.excerpt, '') AS excerpt
        FROM evidence_index ei
        WHERE NOT EXISTS (
            SELECT 1 FROM evidence_embeddings ee
            WHERE ee.evidence_id = ei.id AND ee.model_version = :mv
        )
    """
    params: dict = {"mv": model_version}
    if run_id:
        base += " AND ei.run_id = :run_id"
        params["run_id"] = run_id
    if since:
        base += " AND ei.created_at >= :since"
        params["since"] = datetime(since.year, since.month, since.day, tzinfo=UTC)
    rows = (await session.execute(text(base), params)).fetchall()
    return [
        EmbedCandidate(
            kind="evidence",
            id=r.id,
            text=build_evidence_text(
                source_name=r.source_name,
                claim_type=r.claim_type or "claim",
                excerpt=r.excerpt,
            ),
        )
        for r in rows
    ]


async def _fetch_insight_candidates(
    session: AsyncSession, model_version: str, run_id: str | None, since: date | None
) -> list[EmbedCandidate]:
    base = """
        SELECT ic.id::text, ic.title, ic.what_text, ic.why_text, ic.so_what_text
        FROM insight_cards ic
        WHERE NOT EXISTS (
            SELECT 1 FROM insight_embeddings ie
            WHERE ie.insight_card_id = ic.id AND ie.model_version = :mv
        )
    """
    params: dict = {"mv": model_version}
    if run_id:
        base += " AND ic.run_id = :run_id"
        params["run_id"] = run_id
    if since:
        base += " AND ic.created_at >= :since"
        params["since"] = datetime(since.year, since.month, since.day, tzinfo=UTC)
    rows = (await session.execute(text(base), params)).fetchall()
    return [
        EmbedCandidate(
            kind="insight",
            id=r.id,
            text=build_insight_text(
                title=r.title or "",
                what_text=r.what_text or "",
                why_text=r.why_text or "",
                so_what_text=r.so_what_text or "",
            ),
        )
        for r in rows
    ]


async def _fetch_recommendation_candidates(
    session: AsyncSession, model_version: str, run_id: str | None, since: date | None
) -> list[EmbedCandidate]:
    # `description` is the only prose column on recommendations (NOT NULL
    # since migration 004) — the old COALESCE also named `rationale` and
    # `outcome`, columns that NEVER existed, so this query raised
    # UndefinedColumnError while BUILDING candidates and took the whole
    # embed run down with it (zero vectors of ANY kind ever written).
    # Caught by the 2026-07-05 regen replica right after the datetime.UTC
    # fix let execution reach this line.
    base = """
        SELECT r.id::text, r.title, COALESCE(r.description, '') AS description
        FROM recommendations r
        WHERE NOT EXISTS (
            SELECT 1 FROM recommendation_embeddings re
            WHERE re.recommendation_id = r.id AND re.model_version = :mv
        )
    """
    params: dict = {"mv": model_version}
    if run_id:
        base += " AND r.run_id = :run_id"
        params["run_id"] = run_id
    if since:
        base += " AND r.created_at >= :since"
        params["since"] = datetime(since.year, since.month, since.day, tzinfo=UTC)
    rows = (await session.execute(text(base), params)).fetchall()
    return [
        EmbedCandidate(
            kind="recommendation",
            id=r.id,
            text=build_recommendation_text(
                title=r.title or "",
                description=r.description or "",
            ),
        )
        for r in rows
    ]


async def _persist_batch(session: AsyncSession, result: EmbedBatchResult) -> int:
    """UPSERT one batch of vectors into the appropriate *_embeddings table.
    Returns the count of rows written."""
    if not result.ids:
        return 0

    table_map: dict[ArtifactKind, tuple[str, str, str]] = {
        "evidence": ("evidence_embeddings", "evidence_id", "evidence_index"),
        "insight": ("insight_embeddings", "insight_card_id", "insight_cards"),
        "recommendation": ("recommendation_embeddings", "recommendation_id", "recommendations"),
    }
    table, id_col, _ = table_map[result.kind]

    rows = []
    for artifact_id, text_body, vec in zip(result.ids, result.texts, result.vectors, strict=True):
        if not is_valid_vector(vec):
            continue
        rows.append((artifact_id, vec, text_body, result.model_version))

    if not rows:
        return 0

    # Build a VALUES clause for the batch UPSERT. CAST(... AS ...) not
    # `::` — SQLAlchemy text() does NOT recognise a bindparam immediately
    # followed by `::` (the lookahead rejects `:id_0::uuid`), so the raw
    # `:id_0` reached Postgres → `syntax error at or near ":"`. And the
    # INSERT names 5 columns — created_at must be supplied (NOW()).
    placeholders = ", ".join(
        f"(CAST(:id_{i} AS uuid), CAST(:vec_{i} AS vector), :text_{i}, :mv_{i}, NOW())"
        for i in range(len(rows))
    )
    params: dict = {}
    for i, (artifact_id, vec, text_body, mv) in enumerate(rows):
        params[f"id_{i}"] = artifact_id
        params[f"vec_{i}"] = f"[{','.join(str(v) for v in vec)}]"
        params[f"text_{i}"] = text_body
        params[f"mv_{i}"] = mv

    sql = f"""
        INSERT INTO {table} ({id_col}, embedding, embedded_text, model_version, created_at)
        VALUES {placeholders}
        ON CONFLICT ({id_col}) DO UPDATE
          SET embedding = EXCLUDED.embedding,
              embedded_text = EXCLUDED.embedded_text,
              model_version = EXCLUDED.model_version,
              created_at = NOW()
    """
    await session.execute(text(sql), params)
    return len(rows)


async def embed_run(
    *,
    run_id: str | None,
    since: date | None,
    batch_size: int,
    model_version: str,
) -> int:
    """Fetch candidates, call Vertex, persist embeddings. Returns total count written."""
    vertex = get_vertex_client()
    sm = get_sessionmaker()
    total = 0

    async with sm() as session:
        candidates: list[EmbedCandidate] = []
        candidates += await _fetch_evidence_candidates(session, model_version, run_id, since)
        candidates += await _fetch_insight_candidates(session, model_version, run_id, since)
        candidates += await _fetch_recommendation_candidates(session, model_version, run_id, since)

        if not candidates:
            print("embedder: no candidates found (all already embedded)", flush=True)
            return 0

        print(f"embedder: {len(candidates)} candidates across 3 artifact kinds", flush=True)
        # The SQL fetchers above ARE the selection: their NOT EXISTS
        # subqueries dedup against *_embeddings and they build the
        # EmbedCandidate text. The service-layer select_candidates()
        # (a per-kind dict filter with a keyword-only signature) never
        # fit this path — the call crashed with TypeError the moment
        # the 2026-07-05 fixes let execution reach it, killing every
        # embed run at 11,334 candidates.
        batches = batchify(candidates, batch_size=batch_size)

        for i, batch in enumerate(batches):
            texts = [c.text for c in batch]
            try:
                vectors = await vertex.embed(texts)
            except Exception as exc:
                print(f"embedder: batch {i+1} Vertex call failed: {exc}", file=sys.stderr, flush=True)
                continue

            # A batch can SPAN artifact kinds (the three fetchers append
            # one flat list); persistence is per-kind, so stitch each
            # kind-group separately (stitch_mixed_batch) and persist all
            # groups before the commit.
            results = stitch_mixed_batch(
                batch=batch,
                vectors=vectors,
                model_version=model_version,
            )
            written = 0
            for result in results:
                written += await _persist_batch(session, result)
            await session.commit()
            total += written
            kinds = ", ".join(r.kind for r in results)
            print(
                f"embedder: batch {i+1}/{len(batches)} "
                f"({kinds}) → {written} rows written",
                flush=True,
            )
            # Mid-run counter flush so the admin pill shows progress.
            try:
                from workers._runner import get_current_tracker
                ex = get_current_tracker()
                if ex is not None:
                    ex.update(rows_added=total)
            except Exception:
                pass

    return total
