"""Live IO path for intelligence_recompute.

Wires the pure-logic service helpers to SQLAlchemy (read runs +
evidence + existing profile), Vertex (Pro summary + embedding), and the
``customer_intelligence_profiles`` UPSERT.

State branches mirror service.classify_worker_state — see that
docstring for the full matrix.
"""
from __future__ import annotations

import json as _json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_sessionmaker
from app.services.customer_intelligence import compute_profile
from app.services.vertex_client import get_vertex_client
from workers.intelligence_recompute.service import (
    EvidenceRow,
    ExistingProfile,
    SummaryDecision,
    assemble_snapshots,
    build_recompute_payload,
    call_vertex_summary,
    classify_worker_state,
    deterministic_template_summary,
    should_skip,
    validate_summary_citations,
)

log = logging.getLogger(__name__)


async def _load_existing(session: AsyncSession, *, entity_id: str) -> ExistingProfile | None:
    row = (
        await session.execute(
            text(
                """
                SELECT computed_for_run_id::text AS computed_for_run_id,
                       catalogue_version,
                       (intelligence_summary_md IS NOT NULL) AS summary_present
                FROM customer_intelligence_profiles
                WHERE entity_id = CAST(:eid AS uuid)
                """
            ),
            {"eid": entity_id},
        )
    ).first()
    if row is None:
        return None
    return ExistingProfile(
        computed_for_run_id=row.computed_for_run_id,
        catalogue_version=row.catalogue_version,
        summary_present=bool(row.summary_present),
    )


async def _load_runs(session: AsyncSession, *, entity_id: str) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            text(
                """
                SELECT r.id::text                AS run_id,
                       r.request_id              AS request_id,
                       r.completed_at            AS completed_at,
                       r.ccg_catalog_version     AS catalogue_version,
                       (
                         SELECT AVG(score)::float
                           FROM subcap_scores sc
                          WHERE sc.run_id = r.id
                       )                         AS overall_score
                FROM runs r
                WHERE r.entity_id = CAST(:eid AS uuid)
                  AND r.status IN ('ACTIVE', 'SUPERSEDED')
                ORDER BY r.completed_at ASC NULLS LAST
                """
            ),
            {"eid": entity_id},
        )
    ).all()
    return [
        {
            "run_id": r.run_id,
            "request_id": r.request_id,
            "completed_at": r.completed_at,
            "catalogue_version": r.catalogue_version,
            "overall_score": float(r.overall_score or 0.0),
            "pillar_scores": {},   # not yet rolled at this granularity
            "archetype": None,
            "archetype_silhouette": None,
            "theme_tags": [],
            "below_median_subcap_ids": [],
            "tech_stack": [],
        }
        for r in rows
    ]


async def _load_evidence(session: AsyncSession, *, entity_id: str, limit: int = 24) -> list[EvidenceRow]:
    rows = (
        await session.execute(
            text(
                """
                SELECT e_id, tier, COALESCE(excerpt, '') AS excerpt
                FROM evidence_index
                WHERE entity_id = CAST(:eid AS uuid)
                ORDER BY tier ASC, COALESCE(published_date, created_at::date) DESC NULLS LAST
                LIMIT :k
                """
            ),
            {"eid": entity_id, "k": limit},
        )
    ).all()
    return [
        EvidenceRow(e_id=r.e_id, tier=int(r.tier or 8), excerpt=r.excerpt or "")
        for r in rows
    ]


async def _load_entity_name(session: AsyncSession, *, entity_id: str) -> str:
    row = (
        await session.execute(
            text("SELECT name FROM entities WHERE id = CAST(:eid AS uuid)"),
            {"eid": entity_id},
        )
    ).first()
    return row.name if row else "Entity"


async def _upsert_profile(session: AsyncSession, *, payload: dict[str, Any]) -> None:
    """UPSERT one customer_intelligence_profiles row.

    The summary_embedding column is pgvector; we materialise it as
    `[1.0,2.0,...]` only when present, else NULL.
    """
    vec_param: str | None = None
    if payload.get("summary_embedding"):
        vec_param = "[" + ",".join(str(x) for x in payload["summary_embedding"]) + "]"

    await session.execute(
        text(
            """
            INSERT INTO customer_intelligence_profiles (
                entity_id,
                first_dma_at, latest_dma_at, total_runs,
                maturity_history, maturity_velocity,
                archetype_history,
                recurring_themes, emerging_themes,
                persistent_gap_subcap_ids, closed_gap_subcap_ids,
                tech_stack_additions, tech_stack_removals,
                intelligence_summary_md,
                summary_embedding,
                summary_grounding_evidence_ids,
                computed_for_run_id,
                catalogue_version,
                computed_at
            ) VALUES (
                CAST(:eid AS uuid),
                :first_at, :latest_at, :runs,
                CAST(:mh AS jsonb), :vel,
                CAST(:arch AS jsonb),
                :recur, :emerg,
                :pgap, :cgap,
                CAST(:ta AS jsonb), CAST(:tr AS jsonb),
                :smd,
                CASE WHEN CAST(:vec AS text) IS NULL THEN NULL ELSE CAST(:vec AS vector) END,
                :sgei,
                CAST(:crid AS uuid),
                :cv,
                NOW()
            )
            ON CONFLICT (entity_id) DO UPDATE SET
                first_dma_at = EXCLUDED.first_dma_at,
                latest_dma_at = EXCLUDED.latest_dma_at,
                total_runs = EXCLUDED.total_runs,
                maturity_history = EXCLUDED.maturity_history,
                maturity_velocity = EXCLUDED.maturity_velocity,
                archetype_history = EXCLUDED.archetype_history,
                recurring_themes = EXCLUDED.recurring_themes,
                emerging_themes = EXCLUDED.emerging_themes,
                persistent_gap_subcap_ids = EXCLUDED.persistent_gap_subcap_ids,
                closed_gap_subcap_ids = EXCLUDED.closed_gap_subcap_ids,
                tech_stack_additions = EXCLUDED.tech_stack_additions,
                tech_stack_removals = EXCLUDED.tech_stack_removals,
                intelligence_summary_md = EXCLUDED.intelligence_summary_md,
                summary_embedding = EXCLUDED.summary_embedding,
                summary_grounding_evidence_ids = EXCLUDED.summary_grounding_evidence_ids,
                computed_for_run_id = EXCLUDED.computed_for_run_id,
                catalogue_version = EXCLUDED.catalogue_version,
                computed_at = NOW()
            """
        ),
        {
            "eid": payload["entity_id"],
            # asyncpg types these as timestamptz from the column — ISO
            # strings (the JSON-safe payload form) must be parsed here.
            "first_at": _as_dt(payload["first_dma_at"]),
            "latest_at": _as_dt(payload["latest_dma_at"]),
            "runs": payload["total_runs"],
            "mh": _json.dumps(payload["maturity_history"], default=str),
            "vel": payload["maturity_velocity"],
            "arch": _json.dumps(payload["archetype_history"], default=str),
            "recur": list(payload["recurring_themes"]),
            "emerg": list(payload["emerging_themes"]),
            "pgap": list(payload["persistent_gap_subcap_ids"]),
            "cgap": list(payload["closed_gap_subcap_ids"]),
            "ta": _json.dumps(payload["tech_stack_additions"], default=str),
            "tr": _json.dumps(payload["tech_stack_removals"], default=str),
            "smd": payload["intelligence_summary_md"],
            "vec": vec_param,
            "sgei": list(payload["summary_grounding_evidence_ids"]),
            "crid": payload["computed_for_run_id"],
            "cv": payload["catalogue_version"],
        },
    )


def _as_dt(v):
    """ISO-string -> datetime passthrough (asyncpg rejects str for
    timestamptz params); None/datetime pass unchanged."""
    if isinstance(v, str):
        from datetime import datetime
        return datetime.fromisoformat(v)
    return v


async def _log_hallucination(
    session: AsyncSession, *, entity_id: str, fabricated: list[str], summary_text: str,
) -> None:
    """Best-effort alert insert. Never raises — the recompute path must
    still complete even if the alert table is missing."""
    try:
        await session.execute(
            text(
                """
                INSERT INTO gemini_hallucination_alerts
                    (cache_key, surface, entity_id, flags, response_text)
                VALUES
                    (:ck, 'intelligence_summary',
                     CAST(:eid AS uuid),
                     CAST(:flags AS jsonb), :resp)
                """
            ),
            {
                "ck": f"intel:{entity_id[:32]}",
                "eid": entity_id,
                "flags": _json.dumps({"fabricated_e_ids": fabricated}),
                "resp": summary_text[:4000] if summary_text else "",
            },
        )
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("intelligence_recompute: alert insert failed: %s", exc)


async def recompute_entity(*, entity_id: str) -> str:
    """Recompute a single entity's customer_intelligence_profiles row.

    Returns the worker state label (one of the 6 branches in
    service.classify_worker_state). The caller logs this for audit.
    """
    sm = get_sessionmaker()
    async with sm() as session:
        existing = await _load_existing(session, entity_id=entity_id)
        runs = await _load_runs(session, entity_id=entity_id)
        if not runs:
            return "first_time_compute"   # no runs → nothing to do, but emit label

        latest = runs[-1]
        latest_run_id = latest["run_id"]
        latest_catalogue_version = latest["catalogue_version"] or "v7.0"

        if should_skip(
            existing=existing,
            latest_run_id=latest_run_id,
            latest_catalogue_version=latest_catalogue_version,
        ):
            log.info("intelligence_recompute: idempotent_skip entity=%s", entity_id)
            return "idempotent_skip"

        # Build snapshots + deterministic profile.
        snapshots = assemble_snapshots(runs)
        profile = compute_profile(snapshots)
        entity_name = await _load_entity_name(session, entity_id=entity_id)
        evidence = await _load_evidence(session, entity_id=entity_id)

        # Vertex Pro summary (best-effort).
        vertex = get_vertex_client()
        decision: SummaryDecision = await call_vertex_summary(
            entity_name=entity_name,
            profile=profile,
            evidence=evidence,
            vertex_client=vertex,
        )

        # Validator: every cited E-ID must be in the bundle.
        bundled = {e.e_id for e in evidence}
        validator_passed, fabricated = validate_summary_citations(
            cited_evidence_ids=decision.cited_evidence_ids,
            bundled_evidence_ids=bundled,
        )

        # Branch logic mirroring classify_worker_state.
        if decision.summary_status == "vertex_unavailable" or decision.summary_md is None:
            # Vertex cold: fall back to the deterministic, grounded rollup
            # template instead of leaving the summary NULL — every entity's
            # intelligence card must render on deployment (no empty state).
            summary_md = deterministic_template_summary(
                entity_name=entity_name, profile=profile,
            )
            grounding_eids: list[str] = []
            embedding = None
            summary_status = "vertex_unavailable"
        elif not validator_passed:
            # Validator-rejected — log + use deterministic template.
            await _log_hallucination(
                session, entity_id=entity_id,
                fabricated=fabricated, summary_text=decision.summary_md or "",
            )
            summary_md = deterministic_template_summary(
                entity_name=entity_name, profile=profile,
            )
            grounding_eids = []
            embedding = None
            summary_status = "validator_rejected"
        else:
            summary_md = decision.summary_md
            grounding_eids = decision.cited_evidence_ids
            embedding = decision.embedding
            summary_status = (
                "ok" if embedding is not None else "embedding_failed"
            )

        payload = build_recompute_payload(
            entity_id=entity_id,
            entity_name=entity_name,
            catalogue_version=latest_catalogue_version,
            latest_run_id=latest_run_id,
            profile=profile,
            summary=SummaryDecision(
                summary_md=summary_md,
                cited_evidence_ids=grounding_eids,
                summary_status=summary_status,
                embedding=embedding,
            ),
        )
        await _upsert_profile(session, payload=payload)
        await session.commit()

        state = classify_worker_state(
            existing=existing,
            latest_run_id=latest_run_id,
            latest_catalogue_version=latest_catalogue_version,
            vertex_available=summary_status != "vertex_unavailable",
            validator_passed=summary_status != "validator_rejected",
            embedding_succeeded=embedding is not None,
        )
        log.info(
            "intelligence_recompute: entity=%s state=%s runs=%d",
            entity_id, state, len(runs),
        )
        return state
