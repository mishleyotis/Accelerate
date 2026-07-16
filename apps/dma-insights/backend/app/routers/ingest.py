"""POST /api/v1/ingest/assessment — the Claude project's callback endpoint.

Behavior (per plan ④):
  1. Validate AppPayloadV1.
  2. Look up the in-progress run by `request_id`.
     - If found → upsert payload, flip status to ACTIVE, supersede any
       prior ACTIVE run for the same entity.
     - If not found → create a fresh run with `data_source=PROJECT_API`,
       mark assignment source as `bot_request_oob` (next sheet_poller
       cycle reconciles).
  3. Resolve subcap IDs through CatalogueResolver against the run's
     `ccg_catalog_version`; record `source_subcap_id` + `alias_resolved_from`
     when a translation was applied.
  4. Trigger embedder (post-commit hook → Pub/Sub) and Gemini cache warm.

Auth contract (2026-05-28 audit fix):
  - Bot bearer (Authorization: Bearer <dma_bot_api_key>) — the canonical
    path for the Claude project's webhook callback.
  - OR admin session cookie (dma_session, role=ADMIN) — lets operators
    replay an ingest manually from a curl/Postman session without
    having to retrieve the bearer secret from Secret Manager.
  Either path is sufficient; both flow through the same /assessment
  handler. The dependency is fail-closed: missing both → 401.
"""
from __future__ import annotations

import hmac
import json

import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import text

from app.config import get_settings
from app.deps import SessionDep
from app.schemas.ingest import AppPayloadV1, IngestAck
from app.schemas.package import normalize_tier as _norm_tier
from app.services.catalogue_resolver import CatalogueResolver, SubcapNotFound

log = structlog.get_logger()

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


async def _verify_project_token(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> None:
    """Accept EITHER bot bearer OR admin cookie. Fail-closed if neither.

    Order of precedence:
      1. If `Authorization: Bearer <dma_bot_api_key>` matches → ok.
      2. Else if cookie `dma_session` resolves to a role=ADMIN user → ok.
      3. Else 401. Local dev (settings.dma_bot_api_key empty) still
         falls through to the legacy "no-op" branch for parity with
         the previous behaviour -- the prod-readiness guard refuses
         to boot env=prod without a real bot key, so this branch can't
         leak in prod.
    """
    settings = get_settings()
    expected = (settings.dma_bot_api_key or "").strip()

    # Local dev — empty configured key means auth is disabled.
    if not expected:
        return

    # Path 1: bot bearer.
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization.split(" ", 1)[1].strip()
        # 2026-05-28 audit fix: constant-time compare via
        # hmac.compare_digest. The previous `provided == expected`
        # short-circuited at the first mismatched byte, leaking a
        # timing side-channel an attacker could use to extract the
        # bot API key one character at a time. The /rag/answer
        # bearer at app/routers/rag.py:90 already uses
        # compare_digest; this brings ingest into parity.
        if hmac.compare_digest(provided, expected):
            return
        # Wrong bearer is hard-rejected. Don't fall through to cookie
        # auth, otherwise a leaked-but-stale bearer + a valid cookie
        # would silently succeed and the structlog wouldn't capture
        # the bearer mismatch.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid bearer token"
        )

    # Path 2: admin session cookie.
    cookie = request.cookies.get("dma_session")
    if cookie:
        try:
            from app.services.jwt_service import verify_token
            payload = verify_token(cookie)
            role = (payload.get("role") or "").upper()
            if role == "ADMIN":
                log.info(
                    "ingest.assessment.admin_cookie_auth",
                    actor_email=payload.get("email"),
                )
                return
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="ingest replay requires ADMIN role",
            )
        except HTTPException:
            raise
        except Exception:
            # JWT verify failure -- fall through to the generic 401.
            pass

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="bearer token or admin session required",
    )


@router.post(
    "/assessment",
    response_model=IngestAck,
    dependencies=[Depends(_verify_project_token)],
)
async def ingest_assessment(
    payload: AppPayloadV1,
    session: SessionDep,
) -> IngestAck:
    warnings: list[str] = []

    # 1. Resolve / create entity row.
    entity_row = (
        await session.execute(
            text(
                """
                INSERT INTO entities (
                    name, display_id, domain, subvertical, lobs, status
                ) VALUES (
                    :name, :display_id, :domain, :sv, :lobs, 'ACTIVE'
                )
                ON CONFLICT (display_id) DO UPDATE
                SET name = EXCLUDED.name,
                    domain = EXCLUDED.domain,
                    subvertical = EXCLUDED.subvertical,
                    lobs = EXCLUDED.lobs,
                    updated_at = NOW()
                RETURNING id
                """
            ),
            {
                "name": payload.entity_name,
                "display_id": _display_id_for(payload.entity_name),
                "domain": payload.entity_domain,
                "sv": payload.entity_subvertical,
                "lobs": payload.entity_lobs,
            },
        )
    ).first()
    assert entity_row is not None
    entity_id = entity_row.id

    # 2. Match in-progress run by request_id (idempotent).
    existing_run = (
        await session.execute(
            text(
                "SELECT id, status, entity_id FROM runs "
                "WHERE request_id = :rid FOR UPDATE"
            ),
            {"rid": payload.request_id},
        )
    ).first()

    if existing_run is not None:
        run_id = existing_run.id
        # JSONB columns need a pre-serialized string + explicit CAST when
        # bound through asyncpg — passing a raw dict/list raises
        # `'list'/'dict' object has no attribute 'encode'` mid-execute.
        # Same pattern as parsers/package_persist.py for top_findings /
        # why_now / parser_warnings.
        await session.execute(
            text(
                """
                UPDATE runs
                SET status='ACTIVE',
                    scqa = CAST(:scqa AS JSONB),
                    why_now_signals = CAST(:why_now AS JSONB),
                    top_findings = CAST(:top_findings AS JSONB),
                    completed_at = NOW(),
                    updated_at = NOW(),
                    ccg_catalog_version = :ver
                WHERE id = :rid
                """
            ),
            {
                "scqa": json.dumps(payload.scqa.model_dump()) if payload.scqa else None,
                "why_now": json.dumps(payload.why_now_signals or []),
                "top_findings": json.dumps(payload.top_findings or []),
                "ver": payload.ccg_catalog_version,
                "rid": run_id,
            },
        )
    else:
        # Out-of-band: project posted with an unknown request_id.
        warnings.append("bot_request_oob: created run without prior request envelope")
        new_run = (
            await session.execute(
                text(
                    """
                    INSERT INTO runs (
                        entity_id, request_id, data_source, evidence_mode,
                        status, ccg_catalog_version, scqa, why_now_signals,
                        top_findings, started_at, completed_at, parent_request_id
                    ) VALUES (
                        :eid, :rid, 'PROJECT_API', 'public', 'ACTIVE',
                        :ver, CAST(:scqa AS JSONB),
                        CAST(:why_now AS JSONB),
                        CAST(:top_findings AS JSONB),
                        NOW(), NOW(), :prid
                    )
                    RETURNING id
                    """
                ),
                {
                    "eid": entity_id,
                    "rid": payload.request_id,
                    "ver": payload.ccg_catalog_version,
                    # Same JSONB encoding contract as the UPDATE branch above.
                    "scqa": json.dumps(payload.scqa.model_dump()) if payload.scqa else None,
                    "why_now": json.dumps(payload.why_now_signals or []),
                    "top_findings": json.dumps(payload.top_findings or []),
                    "prid": payload.parent_request_id,
                },
            )
        ).first()
        assert new_run is not None
        run_id = new_run.id

    # 3. Supersede any other ACTIVE runs for this entity.
    superseded = (
        await session.execute(
            text(
                """
                UPDATE runs
                SET status='SUPERSEDED', superseded_by_run_id = :new_run
                WHERE entity_id = :eid
                  AND status = 'ACTIVE'
                  AND id <> :new_run
                RETURNING id
                """
            ),
            {"eid": entity_id, "new_run": run_id},
        )
    ).all()
    superseded_ids = [str(r.id) for r in superseded]

    # 4. Insert subcap_scores via resolver.
    resolver = CatalogueResolver(session)
    for sc in payload.subcap_scores:
        resolved = await resolver.resolve_subcap(
            sc.subcap_id, payload.ccg_catalog_version
        )
        if isinstance(resolved, SubcapNotFound):
            warnings.append(f"unresolved_subcap:{sc.subcap_id}")
            continue
        source_id = sc.subcap_id if resolved.was_aliased else None
        await session.execute(
            text(
                """
                INSERT INTO subcap_scores (
                    run_id, entity_id, subcap_id, source_subcap_id,
                    alias_resolved_from, score, band, confidence, rationale,
                    peer_median, peer_gap, is_thin_evidence, cap_applied,
                    cap_reason, platform_tags
                ) VALUES (
                    :rid, :eid, :sid, :src, :alias_from, :score, :band,
                    :conf, :rat, :pm, :pg, :thin, :cap, :cap_reason, :tags
                )
                ON CONFLICT (run_id, subcap_id) DO UPDATE SET
                    score = EXCLUDED.score,
                    band = EXCLUDED.band,
                    confidence = EXCLUDED.confidence,
                    rationale = EXCLUDED.rationale,
                    peer_median = EXCLUDED.peer_median,
                    peer_gap = EXCLUDED.peer_gap,
                    is_thin_evidence = EXCLUDED.is_thin_evidence,
                    cap_applied = EXCLUDED.cap_applied,
                    cap_reason = EXCLUDED.cap_reason,
                    platform_tags = EXCLUDED.platform_tags
                """
            ),
            {
                "rid": run_id,
                "eid": entity_id,
                "sid": resolved.subcap_id,
                "src": source_id,
                "alias_from": resolved.aliased_from_version,
                "score": sc.score,
                "band": sc.band,
                "conf": sc.confidence,
                "rat": sc.rationale,
                "pm": sc.peer_median,
                "pg": sc.peer_gap,
                "thin": sc.is_thin_evidence,
                "cap": sc.cap_applied,
                "cap_reason": sc.cap_reason,
                "tags": sc.platform_tags,
            },
        )

    # 5. Bulk-insert evidence_index.
    #
    # SQLAlchemy `session.execute(text(...), [list_of_dicts])` issues
    # a SINGLE round-trip for the whole batch instead of one per row.
    # The earlier per-row loop took O(N) round-trips for a 700-evidence
    # package — roughly 30s wall time at 40 ms median per round-trip.
    # Bulk shape brings the same package under 1s.
    if payload.evidence:
        await session.execute(
            text(
                """
                INSERT INTO evidence_index (
                    run_id, entity_id, e_id, source_name, source_url,
                    excerpt, claim_type, tier, recency_months,
                    published_date, linked_subcap_ids
                ) VALUES (
                    :rid, :eid, :e_id, :sname, :surl, :exc, :ct, :tier,
                    :rec, :pub, :linked
                )
                ON CONFLICT (run_id, e_id) DO UPDATE SET
                    source_name = EXCLUDED.source_name,
                    source_url = EXCLUDED.source_url,
                    excerpt = EXCLUDED.excerpt,
                    claim_type = EXCLUDED.claim_type,
                    tier = EXCLUDED.tier,
                    recency_months = EXCLUDED.recency_months,
                    published_date = EXCLUDED.published_date,
                    linked_subcap_ids = EXCLUDED.linked_subcap_ids
                """
            ),
            [
                {
                    "rid": run_id, "eid": entity_id,
                    "e_id": ev.e_id, "sname": ev.source_name,
                    "surl": ev.source_url, "exc": ev.excerpt,
                    # normalize_tier: canonical taxonomy [1,7] or NULL — the API
                    # contract still accepts 1..8, but 8 is not a real
                    # source tier (migration 055) and stores as NULL.
                    "ct": ev.claim_type, "tier": _norm_tier(ev.tier),
                    "rec": ev.recency_months, "pub": ev.published_date,
                    "linked": ev.linked_subcap_ids,
                }
                for ev in payload.evidence
            ],
        )

    # 6. Insights + Recommendations — same bulk pattern.
    if payload.insights:
        await session.execute(
            text(
                """
                INSERT INTO insight_cards (
                    run_id, entity_id, ic_id, severity, title,
                    what_text, why_text, so_what_text,
                    linked_subcap_id, linked_e_ids
                ) VALUES (
                    :rid, :eid, :ic, :sev, :title, :what, :why, :so_what,
                    :sid, :eids
                )
                ON CONFLICT (run_id, ic_id) DO UPDATE SET
                    severity = EXCLUDED.severity,
                    title = EXCLUDED.title,
                    what_text = EXCLUDED.what_text,
                    why_text = EXCLUDED.why_text,
                    so_what_text = EXCLUDED.so_what_text,
                    linked_subcap_id = EXCLUDED.linked_subcap_id,
                    linked_e_ids = EXCLUDED.linked_e_ids
                """
            ),
            [
                {
                    "rid": run_id, "eid": entity_id,
                    "ic": ic.ic_id, "sev": ic.severity, "title": ic.title,
                    "what": ic.what_text, "why": ic.why_text,
                    "so_what": ic.so_what_text, "sid": ic.linked_subcap_id,
                    "eids": ic.linked_e_ids,
                }
                for ic in payload.insights
            ],
        )

    if payload.recommendations:
        await session.execute(
            text(
                """
                INSERT INTO recommendations (
                    run_id, entity_id, rec_id, title, description,
                    target_subcap_ids, platform_id, addressable_offerings,
                    cited_l4_features, cited_constructs, cited_agents,
                    uplift_per_pillar, effort_band
                ) VALUES (
                    :rid, :eid, :rec, :title, :desc, :tgts, :platform,
                    :offers, :feats, :constructs, :agents,
                    CAST(:uplift AS JSONB), :effort
                )
                ON CONFLICT (run_id, rec_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    target_subcap_ids = EXCLUDED.target_subcap_ids,
                    platform_id = EXCLUDED.platform_id,
                    addressable_offerings = EXCLUDED.addressable_offerings,
                    cited_l4_features = EXCLUDED.cited_l4_features,
                    cited_constructs = EXCLUDED.cited_constructs,
                    cited_agents = EXCLUDED.cited_agents,
                    uplift_per_pillar = EXCLUDED.uplift_per_pillar,
                    effort_band = EXCLUDED.effort_band
                """
            ),
            [
                {
                    "rid": run_id, "eid": entity_id,
                    "rec": rec.rec_id, "title": rec.title,
                    "desc": rec.description,
                    "tgts": rec.target_subcap_ids,
                    "platform": rec.platform_id,
                    "offers": rec.addressable_offerings,
                    "feats": rec.cited_l4_features,
                    "constructs": rec.cited_constructs,
                    "agents": rec.cited_agents,
                    # uplift_per_pillar is JSONB — must be a json.dumps'd
                    # string under asyncpg or the execute crashes with
                    # `'dict' object has no attribute 'encode'`.
                    "uplift": json.dumps(rec.uplift_per_pillar) if rec.uplift_per_pillar else None,
                    "effort": rec.effort_band,
                }
                for rec in payload.recommendations
            ],
        )

    # 7. Focus areas — written to the `focus_areas` table (schema after
    # migration 023: `title`, `verbatim_quote`, `source_path`,
    # `page_number`, `involved_subcap_ids`). FocusAreaIn still carries
    # the legacy v6 field names (`name`, `source_quote`,
    # `financial_reference`) for back-compat with the Claude project's
    # payload; we translate at persist time.
    # 2026-05-28 audit fix (F-203): previously the parser extracted
    # focus_areas into `AppPayloadV1.focus_areas` but no persistence
    # path wrote them to the DB. Heatmap + context routers query the
    # `focus_areas` table; every cell rendered "no focus areas" even
    # when the payload contained them.
    if payload.focus_areas:
        for fa in payload.focus_areas:
            if fa.financial_reference:
                warnings.append(
                    f"focus_area_financial_reference_dropped:{fa.name}"
                )
        await session.execute(
            text(
                """
                INSERT INTO focus_areas (
                    run_id, entity_id, title, verbatim_quote,
                    source_path, page_number, involved_subcap_ids
                ) VALUES (
                    :rid, :eid, :title, :vq, :sp, :pn, :ids
                )
                ON CONFLICT DO NOTHING
                """
            ),
            [
                {
                    "rid": run_id, "eid": entity_id,
                    "title": fa.name,
                    "vq": fa.source_quote,
                    "sp": fa.source_path,
                    "pn": fa.page_number,
                    "ids": fa.involved_subcap_ids,
                }
                for fa in payload.focus_areas
            ],
        )

    await session.commit()

    # ── Pub/Sub fan-out + synthesis-cache invalidation ────────────────
    # Best-effort post-commit side-effects. Both internally swallow
    # every exception so the ack response is never delayed by an
    # audit-layer or Pub/Sub outage.
    #
    # State branches:
    #   pubsub_ok + invalidate_ok    → embedder fires; cache rows stale
    #   pubsub_fail + invalidate_ok  → next embedder run picks up via
    #                                   nightly watermark sweep; cache
    #                                   still invalidated this turn
    #   pubsub_ok + invalidate_fail  → cache stays warm; new run still
    #                                   indexed for retrieval
    #   both_fail                    → all reconciled by next scheduler
    #                                   cycle; ack still succeeds
    try:
        from app.services.parsers.package_persist import publish_post_commit
        await publish_post_commit(
            db_run_id=str(run_id),
            entity_id=entity_id,
            request_id=payload.request_id,
            ccg_catalog_version=payload.ccg_catalog_version,
            is_rerun=bool(superseded_ids),
            parent_request_id=None,
        )
        # 2026-05-29 QA audit P1 fix — direct dispatch of the derived-
        # data workers so the assessment-ingest path also populates
        # section_embeddings + customer_intelligence_profiles. Without
        # this, /ingest/assessment runs were Pub/Sub-publishing into
        # a topic with no subscriber.
        try:
            from app.services.post_commit_workers import (
                dispatch_post_commit_workers,
            )
            await dispatch_post_commit_workers(
                session, run_id=str(run_id), entity_id=entity_id,
            )
        except Exception as e:
            log.warning(
                "ingest.post_commit_worker_dispatch_failed",
                err=str(e), request_id=payload.request_id,
            )
    except Exception as e:
        log.warning(
            "ingest.post_commit_fanout_failed",
            err=str(e), request_id=payload.request_id,
        )

    return IngestAck(
        request_id=payload.request_id,
        run_id=str(run_id),
        status="ACTIVE",
        superseded_run_ids=superseded_ids,
        warnings=warnings,
    )


def _display_id_for(name: str) -> str:
    """Stable short ID from the entity name. Deterministic; ingest is idempotent."""
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (slug[:24] or "entity") + "-001"
