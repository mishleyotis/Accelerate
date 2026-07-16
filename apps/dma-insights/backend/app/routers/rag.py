"""RAG read API — what the Claude project queries when generating a new DMA.

Auth: the legacy /evidence + /peer_band + /embed endpoints use a Bearer
key (Secret Manager `dma-insights-rag-api-key`) — server-to-server only.
The newer /answer endpoint uses the session JWT (UI-facing).

State transitions:
  /answer with page_context.entity_id = None
    → cohort_mode = "catalogue_only"; no per-entity grounding
  /answer with session_id = None
    → router creates a new chat_sessions row before answering
  /answer where the surface's per-day rate limit is exceeded
    → returns 429 + a template "rate-limited" answer
  /answer where validator rejects the LLM output
    → response_text replaced with template fallback;
      gemini_hallucination_alerts row created
"""
from __future__ import annotations

import contextlib
import hashlib
import hmac
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import text

from app.config import get_settings
from app.deps import CurrentUserDep, SessionDep, get_redis
from app.schemas.chat import (
    CitationChip,
    RagAnswerRequest,
    RagAnswerResponse,
)
from app.schemas.rag import (
    RagEmbedRequest,
    RagEmbedResponse,
    RagEvidenceItem,
    RagEvidenceResponse,
    RagPeerBandResponse,
)
from app.services.chat_persistence import (
    MessagePayload,
    append_message,
    create_session,
    list_recent_messages,
    load_session_for_user,
)
from app.services.grounding_contract import refusal_answer, should_refuse
from app.services.rag_answer import (
    RATE_LIMITS_PER_DAY,
    SURFACE_CACHE_TTL,
    GroundingBundle,
    LearningCluster,
    RetrievedItem,
    apply_learning_signal,
    cache_key_for_answer,
    cap_bundle_by_tokens,
    cohort_from_profile,
    daily_rate_limit_key,
    extract_citations,
    extract_section_citations,
    fallback_answer,
    merge_bundles,
    model_for_style,
    pick_best_cluster,
)
from app.services.rag_cohort import EntityProfile, RagCohortRouter

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])


async def _verify_rag_key(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> None:
    settings = get_settings()
    expected = settings.rag_api_bearer_key
    if not expected:
        # Local dev: open access. Production CI checks this is set in Secret Manager.
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="bearer token required"
        )
    # Constant-time comparison defends against byte-by-byte timing attacks
    # on the bearer token (an attacker measuring response latency could
    # otherwise brute-force the key one character at a time).
    provided = authorization.split(" ", 1)[1].strip()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token"
        )


@router.get(
    "/evidence",
    response_model=RagEvidenceResponse,
    dependencies=[Depends(_verify_rag_key)],
)
async def rag_evidence(
    session: SessionDep,
    subcap_id: str = Query(...),
    subvertical: str | None = None,
    lobs: str | None = None,
    cross_vertical: str = Query("auto"),
    min_tier: int = Query(1, ge=1, le=8),
    max_age_months: int = Query(24, ge=1, le=120),
    top_k: int = Query(20, ge=1, le=100),
) -> RagEvidenceResponse:
    redis = await get_redis()
    router_svc = RagCohortRouter(session, redis=redis)
    profile = EntityProfile(
        entity_id=None,
        subvertical=subvertical,
        lobs=[s.strip() for s in (lobs or "").split(",") if s.strip()],
    )
    cohort = await router_svc.select(profile, cross_vertical=cross_vertical)

    # Build subvertical filter from the cohort weights map. For single mode,
    # only the single subvertical scores 1.0; for cross_vertical, every
    # adjacency entry contributes its weight.
    weight_clause = _weight_clause_for_cohort(cohort.weights, cohort.lobs)
    if not weight_clause:
        return RagEvidenceResponse(
            cohort_mode=cohort.mode,
            n=0,
            insufficient_cohort=True,
            items=[],
        )

    rows = (
        await session.execute(
            text(
                f"""
                WITH cohort_scored AS (
                    SELECT
                        ev.e_id,
                        ent.name AS entity_name,
                        :subcap_id AS subcap_id,  -- request anchor
                        ev.source_name,
                        ev.excerpt,
                        ev.tier,
                        ev.claim_type,
                        ev.published_date,
                        ev.source_url,
                        {weight_clause} AS cohort_match
                    FROM evidence_index ev
                    JOIN entities ent ON ent.id = ev.entity_id
                    JOIN runs r ON r.id = ev.run_id
                    WHERE :subcap_id = ANY(ev.linked_subcap_ids)
                      -- NULL tier = unstated (migration 055): treated as
                      -- weakest, retrievable only when the caller allows
                      -- the loosest band (the default min_tier=1 does).
                      AND COALESCE(ev.tier, 8) <= :min_tier_max
                      AND r.status = 'ACTIVE'
                      AND (ev.published_date IS NULL
                           OR ev.published_date >= NOW() - (
                                INTERVAL '1 month' * :max_age_months))
                )
                SELECT *
                FROM cohort_scored
                WHERE cohort_match > 0
                ORDER BY cohort_match DESC, tier ASC, published_date DESC NULLS LAST
                LIMIT :top_k
                """
            ),
            {
                "subcap_id": subcap_id,
                "min_tier_max": 9 - min_tier,  # tier_max-input is the *worst* allowed; lower-tier = better
                "max_age_months": max_age_months,
                "top_k": top_k,
                **_weight_params(cohort.weights, cohort.lobs),
            },
        )
    ).all()

    items = [
        RagEvidenceItem(
            e_id=row.e_id,
            entity_name=row.entity_name,
            subcap_id=row.subcap_id,
            source_name=row.source_name,
            excerpt=row.excerpt,
            tier=row.tier,
            claim_type=row.claim_type,
            published_date=row.published_date,
            source_url=row.source_url,
            cohort_match=float(row.cohort_match),
        )
        for row in rows
    ]
    return RagEvidenceResponse(
        cohort_mode=cohort.mode,
        n=cohort.n_estimated,
        insufficient_cohort=cohort.n_estimated < 3,
        items=items,
    )


@router.get(
    "/peer_band",
    response_model=RagPeerBandResponse,
    dependencies=[Depends(_verify_rag_key)],
)
async def rag_peer_band(
    session: SessionDep,
    subvertical: str = Query(...),
    subcap_id: str = Query(...),
) -> RagPeerBandResponse:
    row = (
        await session.execute(
            text(
                """
                SELECT median, p25, p75, n
                FROM peer_benchmarks
                WHERE subvertical = :sv AND subcap_id = :sid
                ORDER BY computed_at DESC
                LIMIT 1
                """
            ),
            {"sv": subvertical, "sid": subcap_id},
        )
    ).first()
    if row is None or row.n < 3:
        # Cross-vertical fallback
        xv = (
            await session.execute(
                text(
                    """
                    SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY score) AS median,
                           COUNT(*) AS n
                    FROM subcap_scores sc
                    JOIN runs r ON r.id = sc.run_id
                    WHERE r.status = 'ACTIVE' AND sc.subcap_id = :sid
                    """
                ),
                {"sid": subcap_id},
            )
        ).first()
        return RagPeerBandResponse(
            insufficient_cohort=True,
            n=row.n if row is not None else 0,
            median=row.median if row is not None else None,
            fallback="cross_vertical_median",
            n_xv=int(xv.n) if xv else 0,
        )
    return RagPeerBandResponse(
        insufficient_cohort=False,
        n=int(row.n),
        median=float(row.median),
        p25=float(row.p25) if row.p25 is not None else None,
        p75=float(row.p75) if row.p75 is not None else None,
    )


@router.post(
    "/embed",
    response_model=RagEmbedResponse,
    dependencies=[Depends(_verify_rag_key)],
)
async def rag_embed(body: RagEmbedRequest) -> RagEmbedResponse:
    from app.services.vertex_client import get_vertex_client

    embeddings = await get_vertex_client().embed(body.texts)
    return RagEmbedResponse(
        model_version=body.model_version,
        embeddings=embeddings,
    )


# ---------- internal helpers ----------

def _weight_clause_for_cohort(
    weights: dict[str, float], lobs: list[str]
) -> str:
    """Build a SQL CASE expression that scores each row by cohort_match."""
    if not weights:
        return ""
    parts: list[str] = []
    for code, _w in weights.items():
        if code == "__lob_overlap__":
            parts.append("WHEN ent.lobs && CAST(:rag_lobs AS varchar[]) "
                         "THEN :rag_w___lob_overlap__")
        else:
            parts.append(f"WHEN ent.subvertical = :rag_sv_{code} THEN :rag_w_{code}")
    return "CASE " + " ".join(parts) + " ELSE 0 END"


def _weight_params(
    weights: dict[str, float], lobs: list[str]
) -> dict[str, object]:
    params: dict[str, object] = {"rag_lobs": lobs}
    for code, w in weights.items():
        if code == "__lob_overlap__":
            params["rag_w___lob_overlap__"] = float(w)
        else:
            params[f"rag_sv_{code}"] = code
            params[f"rag_w_{code}"] = float(w)
    return params


# ====================================================================
# /answer — grounded chat endpoint (UI-facing, session-JWT auth)
# ====================================================================


async def _fetch_entity_profile(session, entity_id: str) -> dict | None:
    row = (
        await session.execute(
            text(
                "SELECT id::text AS id, name, subvertical, lobs, "
                "       (SELECT ccg_catalog_version FROM runs r "
                "          WHERE r.entity_id = e.id AND r.status='ACTIVE' "
                "          ORDER BY r.completed_at DESC NULLS LAST LIMIT 1) "
                "          AS catalogue_version "
                "FROM entities e WHERE id = CAST(:eid AS uuid)"
            ),
            {"eid": entity_id},
        )
    ).first()
    if row is None:
        return None
    return {
        "id": row.id,
        "name": row.name,
        "subvertical": row.subvertical,
        "lobs": list(row.lobs or []),
        "catalogue_version": row.catalogue_version,
    }


async def _fetch_grounding_for_entity(
    session, *, entity_id: str, subcap_id: str | None, top_k: int = 12,
) -> list[RetrievedItem]:
    """Top-k evidence rows for an entity (optionally filtered by subcap).
    No embedding search here — that requires a question-embedding round-
    trip via Vertex; we use SQL ordering by tier + recency as a strong
    proxy. Embedding-based reranking is wired separately when the
    embedder has populated evidence_embeddings.
    """
    sql = (
        "SELECT e_id, source_name, claim_type, excerpt, tier, "
        "       linked_subcap_ids, COALESCE(published_date, created_at::date) AS dt "
        "FROM evidence_index "
        "WHERE entity_id = CAST(:eid AS uuid) "
    )
    params: dict[str, object] = {"eid": entity_id, "k": top_k}
    if subcap_id:
        sql += " AND :sub = ANY(linked_subcap_ids) "
        params["sub"] = subcap_id
    sql += " ORDER BY tier ASC, dt DESC NULLS LAST LIMIT :k"
    rows = (await session.execute(text(sql), params)).all()
    items: list[RetrievedItem] = []
    for idx, r in enumerate(rows):
        # Synthetic similarity: tier 1 → 1.0, tier 8 → 0.2; recency
        # tie-broken by order. The post-retrieval token cap uses this.
        sim = max(0.2, 1.05 - 0.1 * (int(r.tier or 1)))
        items.append(
            RetrievedItem(
                kind="evidence",
                ref_id=r.e_id,
                text=f"{r.source_name}: {(r.excerpt or '').strip()}",
                similarity=sim - 0.001 * idx,
                source_label=r.source_name or "",
            )
        )
    return items


async def _fetch_sections_for_entity(
    session, *, entity_id: str, top_k: int = 8,
) -> list[RetrievedItem]:
    """Pull the entity's narrative section rows for the retrieval bundle.

    State branches (5 — matches docstring of merge_bundles consumer):
      table_missing            → exception swallowed; return []
      no_sections_for_entity   → empty list (graceful skeleton fallback)
      sections_recent_run      → returned, weighted into the bundle
      sections_pillar_filtered → reserved for a later route_context expansion
      cross_run_dedup_skipped  → reserved for the dedup overlay (next batch)
    """
    try:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT ds.id::text          AS section_id,
                           ds.section_kind      AS section_kind,
                           ds.heading           AS heading,
                           ds.body              AS body,
                           ds.run_id::text      AS run_id,
                           se.embedding         AS embedding
                    FROM document_sections ds
                    LEFT JOIN section_embeddings se ON se.section_id = ds.id
                    WHERE ds.entity_id = CAST(:eid AS uuid)
                    ORDER BY ds.created_at DESC
                    LIMIT :k
                    """
                ),
                {"eid": entity_id, "k": top_k},
            )
        ).all()
    except Exception:
        return []
    items: list[RetrievedItem] = []
    for r in rows:
        # Pillar extraction from section_kind "pillar_deep_dive_p1" → "P1"
        kind = r.section_kind or ""
        pillar = None
        if "_p1" in kind:
            pillar = "P1"
        elif "_p2" in kind:
            pillar = "P2"
        elif "_p3" in kind:
            pillar = "P3"
        elif "_p4" in kind:
            pillar = "P4"
        # Synthetic similarity until we plug in question-embedding cosine:
        # pillar deep-dive sections rank ahead of generic ones.
        sim = 0.9 if pillar else 0.75
        items.append(
            RetrievedItem(
                kind="section",
                ref_id=f"SEC-{r.section_id[:8]}",
                text=(r.heading or "") + ": " + ((r.body or "").strip()[:600]),
                similarity=sim,
                source_label=r.heading or "section",
                section_kind=kind,
                section_pillar=pillar,
                document_id=r.run_id,
            )
        )
    return items


async def _count_entities_in_subvertical(session, sv: str) -> int:
    row = (
        await session.execute(
            text(
                "SELECT COUNT(*) AS n FROM entities "
                "WHERE subvertical = :sv AND status = 'ACTIVE'"
            ),
            {"sv": sv},
        )
    ).first()
    return int(row.n if row else 0)


async def _check_rate_limit(redis, *, user_id: str, surface: str) -> bool:
    """Returns True if request is allowed, False if over the daily cap.

    Open-fail: if Redis is unavailable we allow the call (audit_log still
    records the surface so abusive patterns are recoverable).
    """
    limit = RATE_LIMITS_PER_DAY.get(surface)
    if not limit:
        return True
    if redis is None:
        return True
    ymd = datetime.now(tz=UTC).strftime("%Y%m%d")
    key = daily_rate_limit_key(user_id=user_id, surface=surface, ymd=ymd)
    try:
        n = await redis.incr(key)
        if n == 1:
            await redis.expire(key, 86_400 + 60)
    except Exception:
        return True
    return n <= limit


async def _audit_log(
    session, *, user_id: str, email: str, surface: str, prompt_hash: str,
    model: str, tokens_out: int, validators_passed: bool, cache_hit: bool,
    learning_signal: dict | None = None,
) -> None:
    """One row per /answer call, regardless of cache/fallback. Cheap and
    invaluable for the vertex-budget surface. Audit must never block the
    user's chat experience — any failure is swallowed."""
    with contextlib.suppress(Exception):
        after = {
            "prompt_hash": prompt_hash,
            "model": model,
            "tokens_out": tokens_out,
            "validators_passed": validators_passed,
            "cache_hit": cache_hit,
        }
        if learning_signal is not None:
            after["learning_signal"] = learning_signal
        await session.execute(
            text(
                """
                INSERT INTO audit_log
                    (actor_user_id, actor_email, action, resource_type,
                     resource_id, after_json)
                VALUES
                    (CAST(:uid AS uuid), :ae, 'rag_answer', 'surface',
                     :surface, CAST(:after AS jsonb))
                """
            ),
            {
                "uid": user_id, "ae": email, "surface": surface,
                "after": _json_dumps(after),
            },
        )


# In-process TTL cache for chat_learning_signals. The reranker reads it
# on every /answer call; in production we re-fetch every 5 min.
_LEARNING_CACHE: dict[str, tuple[float, list[LearningCluster]]] = {}
_LEARNING_TTL_SECONDS = 300.0


async def _fetch_learning_clusters(session, *, surface: str) -> list[LearningCluster]:
    """Load chat_learning_signals rows for one surface, projecting onto
    LearningCluster. TTL-cached to keep latency negligible for the
    common case of many /answer calls per minute.

    Rows missing prompt_centroid are skipped (un-rollupable).
    """
    import time as _t
    now = _t.time()
    cached = _LEARNING_CACHE.get(surface)
    if cached and (now - cached[0]) < _LEARNING_TTL_SECONDS:
        return cached[1]
    try:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT id::text AS cluster_id, surface,
                           prompt_centroid, effectiveness, sample_count,
                           COALESCE(preferred_evidence_ids, '{}'::varchar[])
                               AS preferred_evidence_ids
                    FROM chat_learning_signals
                    WHERE surface = :s
                      AND prompt_centroid IS NOT NULL
                    """
                ),
                {"s": surface},
            )
        ).all()
    except Exception:
        rows = []
    clusters: list[LearningCluster] = []
    for r in rows:
        centroid = r.prompt_centroid
        # pgvector returns Vector objects in asyncpg; force list[float].
        if centroid is None:
            continue
        if hasattr(centroid, "tolist"):
            centroid = centroid.tolist()
        elif isinstance(centroid, str):
            # textual repr "[0.1,0.2,...]" — defensive parse
            try:
                import json as _json
                centroid = _json.loads(centroid)
            except Exception:
                continue
        clusters.append(
            LearningCluster(
                cluster_id=r.cluster_id,
                surface=r.surface,
                centroid=[float(x) for x in centroid],
                effectiveness=float(r.effectiveness or 0.0),
                sample_count=int(r.sample_count or 0),
                preferred_evidence_ids=list(r.preferred_evidence_ids or []),
            )
        )
    _LEARNING_CACHE[surface] = (now, clusters)
    return clusters


async def _embed_question(question: str) -> list[float] | None:
    """One-call Vertex embedding for the user's question. Returns None
    on any failure (offline / no creds) so the reranker degrades to
    no_match cleanly."""
    try:
        from app.services.vertex_client import get_vertex_client
        embs = await get_vertex_client().embed([question])
        if embs and embs[0]:
            return [float(x) for x in embs[0]]
    except Exception:
        pass
    return None


async def _fetch_evidence_text(
    session, *, e_id: str, entity_id: str | None,
) -> RetrievedItem | None:
    """For a pulled-in preferred E-ID, fetch its source_name + excerpt so
    we can drop a real RetrievedItem into the bundle.

    Cohort filter: when entity_id is provided, only return rows owned by
    that entity (cohort_mode=single defense). Cross-entity pulls are
    allowed for cohort_mode=cross_vertical (caller passes entity_id=None).
    """
    sql = "SELECT e_id, source_name, excerpt, entity_id::text AS eid FROM evidence_index WHERE e_id = :e"
    params: dict[str, object] = {"e": e_id}
    if entity_id is not None:
        sql += " AND entity_id = CAST(:ent AS uuid)"
        params["ent"] = entity_id
    sql += " LIMIT 1"
    try:
        row = (await session.execute(text(sql), params)).first()
    except Exception:
        return None
    if row is None:
        return None
    return RetrievedItem(
        kind="evidence",
        ref_id=row.e_id,
        text=f"{row.source_name or ''}: {(row.excerpt or '').strip()}",
        similarity=0.0,
        source_label=row.source_name or "",
    )


def _json_dumps(obj: dict) -> str:
    import json
    return json.dumps(obj, default=str)


class VertexOfflineFallback(Exception):
    """Marker raised by `_generate_via_vertex` when the Vertex call
    fails and the caller has been served a sanitized fallback body.

    Callers MUST catch this and set `fallback_used=True` so the
    answer is NEVER written to Redis or `vertex_synthesis_cache`.
    Earlier code treated the offline body as a normal Vertex return
    and cached it for 15 minutes — meaning operators who fixed
    IAM/model/project still saw "offline mode" until the TTL expired.

    Attributes:
      body: The operator-visible diagnostic body (no secrets).
      kind: Exception class name (e.g. PermissionDenied).
      msg:  Truncated original exception message.
      hint: Operator-actionable fix hint.
    """
    def __init__(self, *, body: str, kind: str, msg: str, hint: str) -> None:
        super().__init__(f"{kind}: {msg[:80]}")
        self.body = body
        self.kind = kind
        self.msg = msg
        self.hint = hint


async def _generate_via_vertex(
    *, prompt: str, model_alias: str, max_paragraphs: int,
) -> tuple[str, int, int]:
    """Live Vertex call. Returns (text, tokens_in, tokens_out).
    On Vertex failure raises `VertexOfflineFallback` with the
    sanitized body + diagnostic — the caller MUST catch and tag
    `fallback_used=True` so the answer is not cached.
    """
    # ERROR HISTORY R1: prior implementation caught Exception silently;
    # operators saw 'offline mode' with no diagnostic. Now we log the
    # underlying error so logs surface the actual root cause (missing
    # roles/aiplatform.user grant, wrong project ID, unreachable
    # endpoint, etc.). Operator reported on 2026-05-24 that the chat
    # showed offline mode continuously with no way to debug.
    try:
        from app.services.vertex_client import GeminiCall, get_vertex_client
        client = get_vertex_client()
        call = GeminiCall(
            surface="rag_answer", model=model_alias, prompt=prompt,
            max_output_tokens=512 if max_paragraphs <= 3 else 1024,
            temperature=0.2,
        )
        chunks: list[str] = []
        async for chunk in client.stream(call):
            chunks.append(chunk)
        text_out = "".join(chunks)
        return text_out, len(prompt) // 4, len(text_out) // 4
    except Exception as exc:
        # Surface the diagnostic — every offline fallback writes a
        # structured log line with the exception kind + message so the
        # operator can grep Cloud Run logs for the root cause. The same
        # diagnostic is ALSO embedded inline below so the operator
        # doesn't need log access to triage from the chat panel.
        import logging as _logging
        _logger = _logging.getLogger("rag.answer")
        kind = type(exc).__name__
        # Common Vertex SDK errors → operator-actionable hints. Order
        # matters: most-specific first so the most useful hint wins.
        msg = str(exc)
        msg_lower = msg.lower()
        if "permission" in msg_lower or "denied" in msg_lower or "403" in msg_lower or "forbidden" in msg_lower:
            hint = (
                "Backend SA missing roles/aiplatform.user. Fix: "
                "gcloud projects add-iam-policy-binding $PROJECT_ID "
                "--member=serviceAccount:dma-insights-backend@$PROJECT_ID."
                "iam.gserviceaccount.com --role=roles/aiplatform.user"
            )
        elif "not found" in msg_lower or "404" in msg_lower or "does not exist" in msg_lower:
            hint = (
                "Model ID not found. Check vertex_flash_model / "
                "vertex_pro_model env vars match a model the project "
                "has access to."
            )
        elif "credentials" in msg_lower or "default" in msg_lower or "authenticate" in msg_lower:
            hint = (
                "Application Default Credentials missing. Confirm Cloud "
                "Run service is using the dma-insights-backend SA "
                "(set via terraform service_account field)."
            )
        elif "project" in msg_lower:
            hint = (
                "Project mismatch. Check VERTEX_PROJECT_ID env var is "
                "set to 'digital-maturity-assessor' (or the active "
                "project ID)."
            )
        else:
            hint = (
                "Unknown Vertex error — grep Cloud Run logs for "
                "'vertex_offline_fallback' to see the full traceback."
            )
        _logger.warning(
            "vertex_offline_fallback surface=rag_answer model=%s kind=%s msg=%s hint=%s",
            model_alias, kind, msg[:240], hint,
        )
        # Honest default body: used verbatim by the caller ONLY when the
        # retrieval bundle had no evidence rows to embed (otherwise the
        # caller composes a "Grounded evidence" list from the bundle —
        # see the VertexOfflineFallback handler in rag_answer()).
        body = (
            "I'm running in offline mode and can't call Vertex right now, "
            "and no grounded evidence was retrieved for this question. "
            "Try narrowing to a specific client or sub-capability.\n\n"
            f"**Diagnostic** ({kind}): {msg[:200]}\n\n"
            f"**Fix**: {hint}"
        )
        # P0 fix (2026-05-28 audit): raise instead of returning a 3-tuple
        # so the caller MUST handle the offline path explicitly. The
        # caller catches `VertexOfflineFallback`, sets `fallback_used=True`,
        # and SKIPS both Redis L1 + L2 cache writes. The prior
        # `return (body, 0, 0)` made the caller treat the offline body
        # as a successful Vertex response with no E-IDs cited, so
        # validators passed, fallback_used stayed False, and the offline
        # message got cached for the surface's TTL (15 min for rag_answer).
        # Operators who fixed IAM/model/project STILL saw "offline mode"
        # until the TTL expired.
        raise VertexOfflineFallback(body=body, kind=kind, msg=msg, hint=hint) from exc


@router.post("/answer", response_model=RagAnswerResponse)
async def rag_answer(
    body: RagAnswerRequest,
    user: CurrentUserDep,
    session: SessionDep,
) -> RagAnswerResponse:
    start = time.monotonic()
    settings = get_settings()
    redis = await get_redis()

    # ---- rate limit ----
    if not await _check_rate_limit(redis, user_id=user.user_id, surface=body.surface):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"daily rate limit reached for surface={body.surface}",
        )

    # ---- entity profile + catalogue version resolution ----
    pc = body.page_context
    # 2026-06-10 chatbot fix: the frontend's page_context.entity_id is
    # the ROUTE value — a display_id slug ("corporate-america-credit-
    # 0001"), not a UUID. Every downstream query CASTs to uuid, so any
    # client-page question 500'd with asyncpg DataError. Resolve slugs
    # to the entity UUID here; real UUIDs pass through untouched.
    if pc.entity_id:
        import uuid as _uuid
        try:
            _uuid.UUID(pc.entity_id)
        except ValueError:
            row = (
                await session.execute(
                    text("SELECT id::text AS id FROM entities "
                         "WHERE display_id = :did"),
                    {"did": pc.entity_id},
                )
            ).first()
            pc = pc.model_copy(update={"entity_id": row.id if row else None})
    entity_profile = None
    catalogue_version = settings.catalogue_default_version
    if pc.entity_id:
        entity_profile = await _fetch_entity_profile(session, pc.entity_id)
        if entity_profile and entity_profile.get("catalogue_version"):
            catalogue_version = entity_profile["catalogue_version"]

    # ---- cohort decision ----
    n_in_cohort = 0
    sv = entity_profile.get("subvertical") if entity_profile else None
    if sv:
        n_in_cohort = await _count_entities_in_subvertical(session, sv)
    cohort_mode, insufficient = cohort_from_profile(
        entity_id=pc.entity_id, subvertical=sv, n_in_cohort=n_in_cohort,
    )

    # ---- retrieve grounding ----
    evidence_items: list[RetrievedItem] = []
    section_items: list[RetrievedItem] = []
    if pc.entity_id:
        evidence_items = await _fetch_grounding_for_entity(
            session, entity_id=pc.entity_id, subcap_id=pc.subcap_id,
        )
        # UNION in document section embeddings so narrative-style
        # questions ("what does the report say about retail banking
        # maturity?") see analyst prose rows alongside evidence rows.
        section_items = await _fetch_sections_for_entity(
            session, entity_id=pc.entity_id,
        )
    raw_items = merge_bundles(evidence_items, section_items=section_items)
    capped_items = cap_bundle_by_tokens(raw_items)

    # ---- adversarial-learning reranking (close the loop) ----
    # If chat_learning_signals has rolled up a high-effectiveness cluster
    # for this surface and the user's question lands close to its
    # centroid, boost preferred_evidence_ids in the bundle (and pull in
    # up to 3 additional preferred items respecting cohort scope).
    learning_signal_dict: dict | None = None
    try:
        clusters = await _fetch_learning_clusters(session, surface=body.surface)
        question_embedding = (
            await _embed_question(body.question) if clusters else None
        )
        cluster, similarity = pick_best_cluster(
            question_embedding=question_embedding,
            clusters=clusters,
            surface=body.surface,
        )
        # Cohort filter: cohort_mode=single → pull-ins must belong to the
        # current entity; otherwise allow any entity (cross_vertical).
        cohort_entity = pc.entity_id if cohort_mode == "single" else None

        async def _factory_for_eid(eid: str) -> RetrievedItem | None:
            return await _fetch_evidence_text(
                session, e_id=eid, entity_id=cohort_entity,
            )

        # apply_learning_signal is sync. Pre-fetch the pull-in items
        # synchronously into a dict so the pure-logic call doesn't need
        # the async factory.
        prefetched: dict[str, RetrievedItem | None] = {}
        if cluster is not None:
            for eid in cluster.preferred_evidence_ids:
                if eid in {i.ref_id for i in capped_items}:
                    continue
                prefetched[eid] = await _factory_for_eid(eid)

        capped_items, signal = apply_learning_signal(
            bundle_items=capped_items,
            cluster=cluster,
            similarity=similarity,
            cohort_eligible_eids=None,  # already filtered via factory
            extra_item_factory=(
                (lambda eid: prefetched.get(eid)) if cluster is not None else None
            ),
        )
        learning_signal_dict = signal.to_dict()
    except Exception:
        # The reranker is best-effort. A failure inside it must never
        # break a /answer call; record reason="error" for audit.
        learning_signal_dict = {"applied": False, "reason": "error",
                                "items_boosted": 0, "items_pulled": 0}

    bundle = GroundingBundle(
        items=capped_items,
        cohort_mode=cohort_mode,
        insufficient_cohort=insufficient,
    )

    # ---- session resolution ----
    session_id = body.session_id
    if session_id:
        sess = await load_session_for_user(
            session, session_id=session_id, user_id=user.user_id,
        )
        if sess is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="session not found or not yours",
            )
    else:
        session_id = await create_session(
            session, user_id=user.user_id,
            entity_id=pc.entity_id,
            surface=body.surface,
            page_context=pc.model_dump(),
            catalogue_version=catalogue_version,
        )

    # ---- conversation tail ----
    tail = await list_recent_messages(session, session_id=session_id, limit=4)
    convo = [(m["role"], m["content_markdown"]) for m in tail]

    # ---- cache lookup ----
    ck = cache_key_for_answer(
        question=body.question, entity_id=pc.entity_id,
        subcap_id=pc.subcap_id, catalogue_version=catalogue_version,
        response_style=body.response_style,
    )
    cache_hit = False
    cached_text: str | None = None
    cached_eids: list[str] = []
    if redis is not None:
        try:
            blob = await redis.get(ck)
            if blob:
                cache_hit = True
                import json as _json
                try:
                    parsed = _json.loads(blob)
                    cached_text = parsed.get("text")
                    cached_eids = parsed.get("eids") or []
                except Exception:
                    cache_hit = False
        except Exception:
            cache_hit = False

    # ---- record the user's turn ----
    user_msg_id = await append_message(
        session,
        MessagePayload(
            session_id=session_id, role="user",
            content_markdown=body.question,
            cited_evidence_ids=[], cited_subcap_ids=[],
        ),
    )
    _ = user_msg_id  # FK target for any later trace links

    # ---- generate (cache hit short-circuits) ----
    model_alias = model_for_style(body.response_style)
    if cache_hit and cached_text is not None:
        answer_text = cached_text
        tokens_in, tokens_out = 0, 0
        validators_passed = True
        fallback_used = False
        cited_eids = cached_eids
        # Bump the L2 cache row's access_count + last_accessed_at so
        # /admin/vertex-budget can compute a meaningful hit_rate. The
        # row id is stashed on the prior assistant turn's
        # retrieval_bundle._meta marker; we don't know which prior
        # turn produced the L1 hit, so we look it up by fingerprint
        # via safe_record_access on the most-recent active row for
        # this (entity, surface, fingerprint).
        try:
            from app.services.synthesis_cache_db import (
                safe_fetch_active,
                safe_record_access,
            )
            from app.services.synthesis_orchestrator import (
                compute_fingerprint,
                hash_grounding_bundle,
                hash_page_context,
            )
            bundle_dicts = [
                {"kind": i.kind, "ref_id": i.ref_id,
                 "similarity": round(i.similarity, 4)}
                for i in bundle.items
            ]
            fp = compute_fingerprint(
                prompt_template_version="rag_answer_v1",
                grounding_bundle_hash=hash_grounding_bundle(bundle_dicts),
                catalogue_version=catalogue_version,
                page_context_hash=hash_page_context({
                    "route": pc.route or "",
                    "entity_id": pc.entity_id or "",
                    "subcap_id": pc.subcap_id or "",
                    "response_style": body.response_style,
                }),
            )
            row = safe_fetch_active(
                "entity" if pc.entity_id else "global",
                pc.entity_id or "global",
                "rag_answer",
                fp,
            )
            if row is not None:
                safe_record_access(row.id)
        except Exception:
            # Defense in depth — L2 access tracking is observability-only.
            pass
    elif not bundle.items and pc.entity_id is not None:
        # Asked for an entity but we have no evidence → deterministic
        # fallback so we never blank-out the UI.
        answer_text = fallback_answer(
            question=body.question, bundle=bundle, reason="no_grounding"
        )
        tokens_in, tokens_out = 0, 0
        validators_passed = True
        fallback_used = True
        cited_eids = []
    elif pc.entity_id is not None and (_refuse := should_refuse(
            body.question, [{"text": i.text} for i in bundle.items]))[0]:
        # Grounding contract pre-call gate (Training Spec Tab 01 §2.3):
        # the bundle cannot honestly answer this — refuse with the G9
        # enrichment offer instead of asking the model to pad. Same
        # zero-token response shape as the no_grounding fallback.
        answer_text = refusal_answer(_refuse[1])
        tokens_in, tokens_out = 0, 0
        validators_passed = True
        fallback_used = True
        cited_eids = []
    else:
        from app.services.rag_answer import build_answer_prompt
        prompt = build_answer_prompt(
            question=body.question, bundle=bundle, style=body.response_style,
            max_paragraphs=body.max_paragraphs, conversation_tail=convo,
        )
        try:
            text_out, tokens_in, tokens_out = await _generate_via_vertex(
                prompt=prompt, model_alias=model_alias,
                max_paragraphs=body.max_paragraphs,
            )
        except VertexOfflineFallback as offline:
            # P0 fix (2026-05-28 audit): Vertex unreachable. Serve the
            # diagnostic body BUT mark fallback_used=True so the cache
            # write blocks below skip the L1 + L2 caches. Once IAM /
            # model / project is fixed, the next /answer call hits
            # Vertex again with no stale cache masking the recovery.
            #
            # Intelligence-layer fix (2026-07 plan Part 10.3): the offline
            # body used to claim "the retrieved evidence is shown above"
            # while showing NONE. Embed the top retrieved bundle rows
            # (title + E-ID + one-line excerpt) under a "Grounded
            # evidence" list and populate `cited_eids` from those rows so
            # the citation chips render — the answer is grounded even
            # when generation is cold. Bundle rows are real retrieved
            # evidence, so citing them fabricates nothing.
            ev_lines: list[str] = []
            offline_cited: list[str] = []
            for item in bundle.items:
                if item.kind != "evidence":
                    continue
                label = item.source_label or "Evidence"
                excerpt = item.text
                # item.text is "{source_name}: {excerpt}" — strip the
                # label prefix so the line reads title · E-ID — excerpt.
                if item.source_label and excerpt.startswith(f"{item.source_label}:"):
                    excerpt = excerpt[len(item.source_label) + 1:]
                excerpt = " ".join(excerpt.split())[:160]
                ev_lines.append(f"- **{label}** · {item.ref_id} — {excerpt}")
                offline_cited.append(item.ref_id)
                if len(ev_lines) >= 5:
                    break
            if ev_lines:
                answer_text = (
                    "Gemini is unreachable right now, so here is the "
                    "grounded evidence retrieved for your question — "
                    "review it directly.\n\n"
                    "**Grounded evidence**\n"
                    + "\n".join(ev_lines)
                    + "\n\n"
                    f"**Diagnostic** ({offline.kind}): {offline.msg[:200]}\n\n"
                    f"**Fix**: {offline.hint}"
                )
                cited_eids = offline_cited
            else:
                answer_text = offline.body
                cited_eids = []
            tokens_in, tokens_out = 0, 0
            validators_passed = False
            fallback_used = True
        else:
            # Validate citations (evidence + section)
            mentioned = extract_citations(text_out)
            mentioned_sections = extract_section_citations(text_out)
            allowed = set(bundle.evidence_e_ids)
            allowed_sections = set(bundle.section_ids)
            fabricated = [e for e in mentioned if e not in allowed]
            fabricated.extend([s for s in mentioned_sections if s not in allowed_sections])
            if fabricated:
                # Persist a hallucination alert + serve fallback. The
                # insert is best-effort: if the alerts table is
                # unreachable we still serve the deterministic fallback
                # so the user isn't blocked.
                with contextlib.suppress(Exception):
                    await session.execute(
                        text(
                            """
                            INSERT INTO gemini_hallucination_alerts
                                (cache_key, surface, entity_id, flags, response_text)
                            VALUES
                                (:ck, :surface,
                                 CASE WHEN :eid = '' THEN NULL ELSE CAST(:eid AS uuid) END,
                                 CAST(:flags AS jsonb), :resp)
                            """
                        ),
                        {
                            "ck": ck[:128], "surface": body.surface,
                            "eid": pc.entity_id or "",
                            "flags": _json_dumps({"fabricated_e_ids": fabricated}),
                            "resp": text_out,
                        },
                    )
                answer_text = fallback_answer(
                    question=body.question, bundle=bundle,
                    reason="validator_rejected",
                )
                validators_passed = False
                fallback_used = True
                cited_eids = []
            elif body.require_citations and bundle.items \
                 and not mentioned and not mentioned_sections:
                # 2026-05-29 audit fix: when caller explicitly requires
                # citations AND the grounding bundle has evidence/sections
                # available, an answer with ZERO citations must fail
                # closed. Prior code only caught FABRICATED citations;
                # a plausible-sounding answer that omitted citations
                # entirely passed as validator-clean.
                with contextlib.suppress(Exception):
                    await session.execute(
                        text(
                            """
                            INSERT INTO gemini_hallucination_alerts
                                (cache_key, surface, entity_id, flags, response_text)
                            VALUES
                                (:ck, :surface,
                                 CASE WHEN :eid = '' THEN NULL ELSE CAST(:eid AS uuid) END,
                                 CAST(:flags AS jsonb), :resp)
                            """
                        ),
                        {
                            "ck": ck[:128], "surface": body.surface,
                            "eid": pc.entity_id or "",
                            "flags": _json_dumps({
                                "missing_citations": True,
                                "bundle_size": len(bundle.items),
                            }),
                            "resp": text_out,
                        },
                    )
                answer_text = fallback_answer(
                    question=body.question, bundle=bundle,
                    reason="citation_required_but_missing",
                )
                validators_passed = False
                fallback_used = True
                cited_eids = []
            else:
                # Bundle-membership (V0) passed. Now run the full DB-backed
                # grounding validator (V1 cited⊆retrieved, V2 mentioned
                # E-/subcap/IC/REC IDs must exist in the DB for this entity,
                # V3 AF-agent IDs must exist). This catches a model that
                # fabricates a subcap/IC/REC/agent ID *in prose* — IDs the
                # bare E-/SEC- citation check above never inspects.
                #
                # Fail-closed contract (matches the two branches above): on
                # ANY flag we serve the deterministic template fallback +
                # write a gemini_hallucination_alerts row + set
                # fallback_used=True so the L1/L2 cache writes are skipped.
                # A validator *error* (DB hiccup, etc.) must NOT 500 the
                # request — it also falls back, conservatively.
                from app.services.grounding_validator import (
                    ValidationFlags,
                    validate_response,
                )

                grounding_flags = ValidationFlags()
                validator_errored = False
                try:
                    grounding_flags = await validate_response(
                        session=session,
                        response_text=text_out,
                        cited_evidence_ids=mentioned,
                        retrieved_bundle_e_ids=bundle.evidence_e_ids,
                        entity_id=pc.entity_id,
                        run_catalog_version=catalogue_version,
                    )
                except Exception:
                    # Deterministic + fail-closed: a validator exception is
                    # treated as a rejection so un-validated Gemini output is
                    # never served to the AE (CLAUDE.md hard rule).
                    validator_errored = True

                # V4 (semantic grounding): catches a fluent paraphrase that
                # reuses NO fabricated ids — which V1-V3 cannot. Runs only when
                # V1-V3 are clean; ABSTAINS offline (no embedding tier), so it
                # never fail-closes an answer merely because embeddings are
                # absent (2026-07-14 audit: V4 was documented but never wired).
                v4_cosine: float | None = None
                v4_failed = False
                if not validator_errored and grounding_flags.is_clean:
                    from app.services.grounding_validator import (
                        semantic_grounding_ok,
                    )
                    _v4_ok, v4_cosine = semantic_grounding_ok(
                        text_out, [i.text for i in bundle.items])
                    v4_failed = not _v4_ok

                if validator_errored or not grounding_flags.is_clean or v4_failed:
                    if validator_errored:
                        alert_flags = {"validator_error": True}
                    elif v4_failed:
                        alert_flags = {
                            "v4_semantic_ungrounded": True,
                            "v4_cosine": (round(v4_cosine, 4)
                                          if v4_cosine is not None else None),
                        }
                    else:
                        alert_flags = grounding_flags.to_dict()
                    with contextlib.suppress(Exception):
                        await session.execute(
                            text(
                                """
                                INSERT INTO gemini_hallucination_alerts
                                    (cache_key, surface, entity_id, flags, response_text)
                                VALUES
                                    (:ck, :surface,
                                     CASE WHEN :eid = '' THEN NULL ELSE CAST(:eid AS uuid) END,
                                     CAST(:flags AS jsonb), :resp)
                                """
                            ),
                            {
                                "ck": ck[:128], "surface": body.surface,
                                "eid": pc.entity_id or "",
                                "flags": _json_dumps(alert_flags),
                                "resp": text_out,
                            },
                        )
                    answer_text = fallback_answer(
                        question=body.question, bundle=bundle,
                        reason="validator_rejected",
                    )
                    validators_passed = False
                    fallback_used = True
                    cited_eids = []
                else:
                    answer_text = text_out
                    validators_passed = True
                    fallback_used = False
                    cited_eids = mentioned

    # ---- cache write (only validator-clean LLM answers) ----
    if not cache_hit and not fallback_used and redis is not None:
        try:
            ttl = SURFACE_CACHE_TTL.get(body.surface, 900)
            import json as _json
            await redis.setex(
                ck, ttl,
                _json.dumps({"text": answer_text, "eids": cited_eids}),
            )
        except Exception:
            pass

    # ---- L2 cache write: vertex_synthesis_cache ─────────────────────
    # Records every validator-clean LLM answer in the Postgres-backed
    # synthesis cache. Powers /admin/vertex-budget aggregations AND
    # the invalidation lifecycle (on next ingest for this entity, the
    # row is marked invalidated_re_synthesized; on hallucination
    # feedback, the single row is invalidated by id).
    #
    # State branches:
    #   l2_write_success → cache_row_id captured, persisted on
    #                       chat_messages.retrieval_bundle for later
    #                       feedback invalidation lookup.
    #   l2_write_skipped → cache_hit (Redis L1 served it; no L2
    #                       refresh needed) OR fallback_used (don't
    #                       cache template fallbacks).
    #   l2_write_failed   → safe wrapper returns None; ingest/answer
    #                       both proceed unaffected.
    cache_row_id: str | None = None
    if not cache_hit and not fallback_used:
        try:
            from app.services.synthesis_cache_db import safe_insert_or_supersede
            from app.services.synthesis_orchestrator import (
                DecisionGate,
                compute_fingerprint,
                hash_grounding_bundle,
                hash_page_context,
            )
            from app.services.vertex_client import resolve_model_id
            # Bundle fingerprint must reflect what we actually grounded on.
            bundle_dicts = [
                {"kind": i.kind, "ref_id": i.ref_id,
                 "similarity": round(i.similarity, 4)}
                for i in bundle.items
            ]
            fp = compute_fingerprint(
                prompt_template_version="rag_answer_v1",
                grounding_bundle_hash=hash_grounding_bundle(bundle_dicts),
                catalogue_version=catalogue_version,
                page_context_hash=hash_page_context({
                    "route": pc.route or "",
                    "entity_id": pc.entity_id or "",
                    "subcap_id": pc.subcap_id or "",
                    "response_style": body.response_style,
                }),
            )
            cache_row_id = safe_insert_or_supersede(
                target_kind="entity" if pc.entity_id else "global",
                target_id=pc.entity_id or "global",
                surface="rag_answer",
                model=model_alias,
                input_fingerprint=fp,
                prompt_template_version="rag_answer_v1",
                grounding_bundle_hash=hash_grounding_bundle(bundle_dicts),
                catalogue_version=catalogue_version,
                output_text=answer_text,
                # source/model_id/synthesized_at = the provenance contract
                # every vertex-backed cache row carries (fallbacks are
                # never cached — the fallback_used guard above — so
                # "vertex" is always true here). Read by the overview
                # merge + the qa_gemini_surfaces deploy assertions.
                output_json={
                    "cited_evidence_ids": cited_eids,
                    "source": "vertex",
                    "model_id": resolve_model_id(model_alias),
                    "synthesized_at": datetime.now(UTC).isoformat(),
                },
                cited_evidence_ids=cited_eids,
                cited_subcap_ids=bundle.subcap_ids,
                validators_passed=validators_passed,
                prompt_tokens=tokens_in,
                completion_tokens=tokens_out,
                latency_ms=int((time.monotonic() - start) * 1000),
                decision_gate=DecisionGate.CACHE_MISS.value,
            )
        except Exception:
            # Defense in depth — every save_* call is itself swallowing;
            # this catches missing-module / import-time issues.
            cache_row_id = None

    # ---- persist assistant turn ----
    bundle_for_persist = [
        {"kind": i.kind, "ref_id": i.ref_id, "similarity": i.similarity}
        for i in bundle.items
    ]
    # Stash the L2 cache row id on the message's retrieval_bundle so
    # the feedback handler can find it for targeted invalidation
    # (see app/routers/chat.py post_feedback "hallucinated" branch).
    if cache_row_id:
        bundle_for_persist.append({
            "kind": "_meta", "ref_id": "cache_row_id",
            "cache_row_id": cache_row_id,
        })
    assistant_msg_id = await append_message(
        session,
        MessagePayload(
            session_id=session_id, role="assistant",
            content_markdown=answer_text,
            cited_evidence_ids=cited_eids,
            cited_subcap_ids=bundle.subcap_ids,
            retrieval_bundle=bundle_for_persist,
            model=model_alias,
            tokens_in=tokens_in, tokens_out=tokens_out,
            latency_ms=int((time.monotonic() - start) * 1000),
            validators_passed=validators_passed,
            hallucination_flags=(
                {"fallback_reason": "validator_rejected"} if fallback_used and not cache_hit
                else None
            ),
        ),
    )

    # ---- audit + commit ----
    prompt_hash = hashlib.sha256(body.question.encode("utf-8")).hexdigest()[:32]
    await _audit_log(
        session, user_id=user.user_id, email=user.email, surface=body.surface,
        prompt_hash=prompt_hash, model=model_alias, tokens_out=tokens_out,
        validators_passed=validators_passed, cache_hit=cache_hit,
        learning_signal=learning_signal_dict,
    )
    await session.commit()

    # ---- build citation chips ----
    chips: list[CitationChip] = []
    eid_to_item = {i.ref_id: i for i in bundle.items if i.kind == "evidence"}
    for eid in cited_eids:
        item = eid_to_item.get(eid)
        if item is not None:
            chips.append(
                CitationChip(
                    e_id=eid, source_name=item.source_label,
                    excerpt=item.text[:280], kind="evidence",
                )
            )
    # Section citation chips (open the section drawer, not EvidenceDrawer).
    cited_section_ids: list[str] = []
    if not cache_hit and not fallback_used:
        cited_section_ids = extract_section_citations(answer_text)
    sec_to_item = {i.ref_id: i for i in bundle.items if i.kind == "section"}
    for sid in cited_section_ids:
        item = sec_to_item.get(sid)
        if item is not None:
            chips.append(
                CitationChip(
                    e_id=sid, source_name=item.source_label,
                    excerpt=item.text[:280],
                    kind="section",
                    section_kind=item.section_kind,
                    section_pillar=item.section_pillar,
                )
            )

    # ---- bundle freshness metadata (per the 3-year staleness mandate) ----
    bundle_stale_pct = 0.0
    stale_disclaimer = ""
    try:
        from datetime import date as _date

        from app.services.evidence_staleness import (
            bundle_stale_pct as _bundle_stale_pct,
        )
        eids_in_bundle = bundle.evidence_e_ids
        if eids_in_bundle:
            freshness_rows = (
                await session.execute(
                    text(
                        """
                        SELECT e_id, published_date, recency_months
                        FROM evidence_index
                        WHERE e_id = ANY(:eids)
                        """
                    ),
                    {"eids": eids_in_bundle},
                )
            ).all()
            bundle_rows = [
                {"published_date": r.published_date,
                 "recency_months": r.recency_months}
                for r in freshness_rows
            ]
            bundle_stale_pct = _bundle_stale_pct(bundle_rows, today=_date.today())
            if bundle_stale_pct > 40.0:
                stale_disclaimer = (
                    "⚠ Most of the evidence behind this answer is more than "
                    "3 years old — read with caution."
                )
    except Exception:  # pragma: no cover — pre-migration deployments
        bundle_stale_pct = 0.0

    latency_ms = int((time.monotonic() - start) * 1000)
    return RagAnswerResponse(
        session_id=session_id,
        message_id=assistant_msg_id,
        answer_markdown=answer_text,
        cited_evidence_ids=cited_eids,
        cited_subcap_ids=bundle.subcap_ids,
        cited_section_ids=cited_section_ids,
        citations=chips,
        confidence=0.7 if validators_passed and not fallback_used else 0.3,
        cohort_mode=cohort_mode,
        insufficient_cohort=insufficient,
        validators_passed=validators_passed,
        fallback_used=fallback_used,
        cache_hit=cache_hit,
        model=model_alias,
        latency_ms=latency_ms,
        learning_signal=learning_signal_dict,
        bundle_stale_pct=bundle_stale_pct,
        stale_disclaimer=stale_disclaimer,
        bundle_section_pct=bundle.section_pct,
    )


@router.post("/answer/stream")
async def rag_answer_stream(
    body: RagAnswerRequest,
    user: CurrentUserDep,
    session: SessionDep,
):
    """SSE variant of /answer. Streams the same response in three events:
      event: token  data: {"text": "..."}
      event: citations  data: {"cited_evidence_ids": [...]}
      event: done   data: {"session_id": "...", "message_id": "..."}

    For initial parity with the JSON endpoint we generate the full response
    first then yield it in word-sized chunks. The structure is the SSE
    contract the frontend expects; the in-flight streaming optimization
    can land later without an API break.
    """
    from fastapi.responses import StreamingResponse

    resp = await rag_answer(body, user, session)

    async def gen():
        # token events
        words = resp.answer_markdown.split(" ")
        chunk_size = 8
        for i in range(0, len(words), chunk_size):
            piece = " ".join(words[i : i + chunk_size])
            yield f"event: token\ndata: {_json_dumps({'text': piece + ' '})}\n\n"
        yield (
            f"event: citations\ndata: "
            f"{_json_dumps({'cited_evidence_ids': resp.cited_evidence_ids, 'citations': [c.model_dump() for c in resp.citations]})}"
            f"\n\n"
        )
        yield (
            f"event: done\ndata: "
            f"{_json_dumps({'session_id': resp.session_id, 'message_id': resp.message_id, 'fallback_used': resp.fallback_used})}"
            f"\n\n"
        )

    return StreamingResponse(gen(), media_type="text/event-stream")
