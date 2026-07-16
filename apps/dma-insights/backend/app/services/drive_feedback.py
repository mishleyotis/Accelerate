"""Phase 0 feedback loop — writes the 5 PRD §17 feedback files back
to the entity's source Drive folder after every successful ingest.

Per PRD v3.0 §17. Triggered from
`parsers.package_persist.publish_post_commit` as a sibling call to
the Pub/Sub publish. Best-effort: Drive API failures DO NOT block the
ingest. Every state surfaces an audit_log row (best-effort) so the
operator can trace why a feedback file did or didn't land.

Files emitted (each independently re-tryable):
  - thin_evidence_feedback.json     — subcaps with evidence_count < 2
  - evidence_freshness_alerts.json  — evidence flagged dated/stale/undated
  - tech_inference_handoff.json     — synthesised tech rows for re-validation
  - narrative_overrides.json        — AE-curated narrative edits to respect
  - waiver_decisions.json           — Admin-granted cap-bypass decisions

State branches (returned in `FeedbackWriteResult.state`):
  - drive_folder_unknown   → entity has no recorded drive_folder_id;
                             we never have a target to upload to; skip.
  - drive_perms_missing    → 403 on upsert → SA lost write access;
                             surfaces a typed error_kind so the
                             operator can re-grant in the Drive UI.
  - upload_failed          → at least one upload returned 4xx/5xx;
                             `failed` lists the file names; `written`
                             lists the names that did succeed.
  - upload_ok              → every file accepted by Drive.
  - dry_run                → caller passed dry_run=True; no IO.
  - dev_skip               → env not in (prod, staging); no IO. Local
                             developers don't need to hit real Drive.

The 5 compute_* helpers below are pure SQL→Pydantic transforms — no
Drive imports — so they can be unit-tested without GCP credentials.
The upload helpers are mockable via the `drive_service` param
(defaults to `build_drive_service()` from the live wrapper).
"""
from __future__ import annotations

import io
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.drive_feedback import (
    EvidenceFreshnessAlerts,
    FeedbackWriteResult,
    FreshnessAlertRow,
    NarrativeOverrideRow,
    NarrativeOverrides,
    TechInferenceHandoff,
    TechInferenceRow,
    ThinEvidenceFeedback,
    ThinEvidenceRow,
    WaiverDecisions,
    WaiverRow,
)

log = logging.getLogger("drive.feedback")

# ── Computed-feedback builders (pure SQL → Pydantic) ───────────────────


async def compute_thin_evidence(
    session: AsyncSession,
    *,
    run_id: str,
    entity_id: str,
    threshold: int = 2,
) -> ThinEvidenceFeedback:
    """One row per subcap whose persisted evidence count is below
    threshold. Reads from subcap_scores joined to the per-subcap
    evidence counts already maintained by the dedup engine."""
    rows = (
        await session.execute(
            text(
                """
                SELECT
                  s.subcap_id,
                  COALESCE(s.category_id, LEFT(s.subcap_id, 4)) AS category_id,
                  LEFT(s.subcap_id, 2) AS pillar_id,
                  s.score,
                  s.confidence,
                  s.is_thin_evidence,
                  COALESCE(ec.evidence_count, 0) AS evidence_count
                FROM subcap_scores s
                LEFT JOIN (
                    SELECT subcap_mapping, COUNT(*) AS evidence_count
                    FROM evidence_index ei
                    JOIN evidence_run_links rl ON rl.evidence_id = ei.id
                    CROSS JOIN LATERAL unnest(ei.subcap_mappings) AS subcap_mapping
                    WHERE rl.run_id = :rid
                    GROUP BY subcap_mapping
                ) ec ON ec.subcap_mapping = s.subcap_id
                WHERE s.run_id = :rid
                  AND s.is_thin_evidence = TRUE
                ORDER BY s.subcap_id
                """
            ),
            {"rid": run_id},
        )
    ).mappings().all()

    items: list[ThinEvidenceRow] = []
    for r in rows:
        items.append(
            ThinEvidenceRow(
                subcap_id=r["subcap_id"],
                category_id=r["category_id"],
                pillar_id=r["pillar_id"],
                score=float(r["score"] or 0),
                evidence_count=int(r["evidence_count"]),
                confidence=str(r["confidence"]) if r["confidence"] is not None else None,
                suggested_action=_suggest_action(
                    r["score"], int(r["evidence_count"]), r["confidence"]
                ),
                rationale=(
                    f"persisted evidence_count={r['evidence_count']} < "
                    f"threshold={threshold}"
                ),
            )
        )

    return ThinEvidenceFeedback(
        run_id=run_id,
        entity_id=entity_id,
        completed_at=datetime.now(tz=UTC),
        state="empty" if not items else "generated",
        threshold=threshold,
        items=items,
    )


def _suggest_action(
    score: float | None, evidence_count: int, confidence: Any
) -> str:
    """Pure mapping from observed state to bot guidance. Keep simple —
    the bot does the heavy lifting; we just surface intent.
    """
    if evidence_count == 0:
        return "request_client_artifact"
    if (score or 0) >= 4.0:
        # High score with thin evidence → most suspicious; deeper research.
        return "research_deeper"
    if str(confidence or "").upper() in ("LOW", "MEDIUM"):
        return "downgrade_confidence"
    return "mark_as_proxy"


async def compute_freshness_alerts(
    session: AsyncSession,
    *,
    run_id: str,
    entity_id: str,
) -> EvidenceFreshnessAlerts:
    """One row per evidence flagged dated / stale / undated. Reads
    `freshness_band` (Postgres STORED generated column from migration
    018) so the bot sees the exact same band the UI does.
    """
    rows = (
        await session.execute(
            text(
                """
                SELECT
                  ei.e_id,
                  ei.source_name,
                  ei.source_url,
                  ei.tier,
                  ei.published_date,
                  ei.recency_months,
                  ei.freshness_band,
                  ei.subcap_mappings
                FROM evidence_index ei
                JOIN evidence_run_links rl ON rl.evidence_id = ei.id
                WHERE rl.run_id = :rid
                  AND ei.freshness_band IN ('dated', 'stale', 'undated')
                ORDER BY
                  CASE ei.freshness_band
                    WHEN 'stale'   THEN 1
                    WHEN 'dated'   THEN 2
                    WHEN 'undated' THEN 3
                    ELSE 4
                  END,
                  ei.e_id
                """
            ),
            {"rid": run_id},
        )
    ).mappings().all()

    summary_rows = (
        await session.execute(
            text(
                """
                SELECT ei.freshness_band, COUNT(*) AS n
                FROM evidence_index ei
                JOIN evidence_run_links rl ON rl.evidence_id = ei.id
                WHERE rl.run_id = :rid
                GROUP BY ei.freshness_band
                """
            ),
            {"rid": run_id},
        )
    ).mappings().all()
    summary = {
        "current": 0, "aging": 0, "dated": 0, "stale": 0, "undated": 0,
    }
    for row in summary_rows:
        band = row["freshness_band"] or "undated"
        summary[band] = int(row["n"])

    items = [
        FreshnessAlertRow(
            evidence_id=r["e_id"],
            source_name=r["source_name"] or "(unnamed)",
            source_url=r["source_url"],
            # None = source stated no canonical tier (honest-absent);
            # the old else-5 fabricated a mid-scale tier for display.
            tier=int(r["tier"]) if r["tier"] is not None else None,
            published_date=str(r["published_date"]) if r["published_date"] else None,
            recency_months=(
                int(r["recency_months"]) if r["recency_months"] is not None else None
            ),
            freshness_band=r["freshness_band"] or "undated",
            subcap_mappings=list(r["subcap_mappings"] or []),
        )
        for r in rows
    ]

    return EvidenceFreshnessAlerts(
        run_id=run_id,
        entity_id=entity_id,
        completed_at=datetime.now(tz=UTC),
        state="empty" if not items else "generated",
        stale_threshold_months=36,
        summary=summary,
        items=items,
    )


async def compute_tech_handoff(
    session: AsyncSession,
    *,
    run_id: str,
    entity_id: str,
) -> TechInferenceHandoff:
    """One row per tech_stack entry that we synthesised vs observed
    directly. `inference_source` is the discriminant column; rows
    with `inference_source != 'explorium_direct'` surface as
    candidates for the bot to re-validate.
    """
    try:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT
                      vendor,
                      product,
                      category,
                      COALESCE(confidence, 0.5) AS confidence,
                      COALESCE(inference_source, 'unknown') AS inference_source,
                      COALESCE(evidence_ids, ARRAY[]::TEXT[]) AS evidence_ids
                    FROM tech_stack
                    WHERE run_id = :rid
                      AND COALESCE(inference_source, '') != 'explorium_direct'
                    ORDER BY vendor, product
                    """
                ),
                {"rid": run_id},
            )
        ).mappings().all()
    except Exception:
        # Schema older than the tech_stack inference_source column —
        # skip gracefully (the bot just won't get the handoff).
        rows = []

    items = [
        TechInferenceRow(
            vendor=r["vendor"] or "(unknown)",
            product=r["product"],
            category=r["category"],
            confidence=float(r["confidence"]),
            inferred_from=[r["inference_source"]],
            evidence_ids=list(r["evidence_ids"] or []),
        )
        for r in rows
    ]

    return TechInferenceHandoff(
        run_id=run_id,
        entity_id=entity_id,
        completed_at=datetime.now(tz=UTC),
        state="empty" if not items else "generated",
        items=items,
    )


async def compute_narrative_overrides(
    session: AsyncSession,
    *,
    entity_id: str,
) -> NarrativeOverrides:
    """One row per AE-curated narrative override stored against this
    entity. Returns empty `items` until the narrative-edit panel ships.
    """
    items: list[NarrativeOverrideRow] = []
    try:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT section_kind, surface, pillar_id, subcap_id,
                           override_text, set_by, set_at, rationale
                    FROM narrative_overrides
                    WHERE entity_id = :eid
                      AND retracted_at IS NULL
                    ORDER BY set_at DESC
                    """
                ),
                {"eid": entity_id},
            )
        ).mappings().all()
        for r in rows:
            items.append(
                NarrativeOverrideRow(
                    section_kind=r["section_kind"],
                    surface=r["surface"],
                    pillar_id=r["pillar_id"],
                    subcap_id=r["subcap_id"],
                    override_text=r["override_text"],
                    set_by=r["set_by"],
                    set_at=r["set_at"],
                    rationale=r["rationale"],
                )
            )
    except Exception:
        # Table may not exist yet — first-cut feedback file is empty
        # but `state=empty` so the bot still knows the channel is alive.
        pass

    return NarrativeOverrides(
        entity_id=entity_id,
        completed_at=datetime.now(tz=UTC),
        state="empty" if not items else "generated",
        items=items,
    )


async def compute_waiver_decisions(
    session: AsyncSession,
    *,
    entity_id: str,
) -> WaiverDecisions:
    """One row per active admin-granted waiver for this entity."""
    items: list[WaiverRow] = []
    try:
        rows = (
            await session.execute(
                text(
                    """
                    SELECT waiver_id, scope, target_id, issue_id, reason,
                           granted_by, granted_at, expires_at, cap_ceiling
                    FROM waivers
                    WHERE entity_id = :eid
                      AND (expires_at IS NULL OR expires_at > NOW())
                      AND revoked_at IS NULL
                    ORDER BY granted_at DESC
                    """
                ),
                {"eid": entity_id},
            )
        ).mappings().all()
        for r in rows:
            items.append(
                WaiverRow(
                    waiver_id=str(r["waiver_id"]),
                    scope=r["scope"],
                    target_id=r["target_id"],
                    issue_id=r["issue_id"],
                    reason=r["reason"],
                    granted_by=r["granted_by"],
                    granted_at=r["granted_at"],
                    expires_at=r["expires_at"],
                    cap_ceiling=(
                        float(r["cap_ceiling"]) if r["cap_ceiling"] is not None else None
                    ),
                )
            )
    except Exception:
        # waivers table not deployed yet; surface empty channel.
        pass

    return WaiverDecisions(
        entity_id=entity_id,
        completed_at=datetime.now(tz=UTC),
        state="empty" if not items else "generated",
        items=items,
    )


# ── Drive upsert (mockable) ────────────────────────────────────────────


# Type alias for the injected uploader: (folder_id, name, json_bytes) → file_id.
DriveUpserter = Callable[[str, str, bytes], Awaitable[str]]


async def _default_upsert(
    folder_id: str, name: str, body: bytes
) -> str:
    """Default uploader: upsert via the Drive v3 API. Mockable via the
    `drive_upserter` param to write_feedback_files."""
    from googleapiclient.http import MediaIoBaseUpload  # type: ignore[import-untyped]

    from app.services.drive_client import build_drive_service

    service = build_drive_service()
    # Look for an existing file with the same name in this folder. We
    # use update-if-exists / create-if-not so the file_id is stable
    # across runs (bot can reference the same Drive URL).
    q = (
        f"name = '{name}' and '{folder_id}' in parents and trashed = false"
    )
    existing = service.files().list(
        q=q, fields="files(id,name)", pageSize=1,
    ).execute()
    files = existing.get("files", [])
    media = MediaIoBaseUpload(
        io.BytesIO(body), mimetype="application/json", resumable=False,
    )
    if files:
        fid = files[0]["id"]
        service.files().update(
            fileId=fid, media_body=media,
        ).execute()
        return fid
    created = service.files().create(
        body={"name": name, "parents": [folder_id]},
        media_body=media, fields="id",
    ).execute()
    return created["id"]


# ── Orchestrator ───────────────────────────────────────────────────────


async def write_feedback_files(
    *,
    session: AsyncSession,
    db_run_id: str,
    entity_id: str,
    drive_folder_id: str | None,
    env: str = "prod",
    dry_run: bool = False,
    drive_upserter: DriveUpserter | None = None,
) -> FeedbackWriteResult:
    """Build + upload the 5 PRD §17 feedback files.

    `env` gates real IO: only `prod` / `staging` reach Drive. Local /
    test envs short-circuit to `dev_skip` so devs don't need
    Application Default Credentials.

    `dry_run=True` builds the envelopes but skips the upload — used by
    the upcoming Admin → "Preview feedback files" surface.

    `drive_upserter` is the injectable upload function; defaults to
    the live Drive v3 update-or-create wrapper above. Tests inject
    a mock.

    See module docstring for the full state-branch contract.
    """
    if drive_folder_id is None:
        return FeedbackWriteResult(state="drive_folder_unknown")
    if env not in ("prod", "staging"):
        return FeedbackWriteResult(state="dev_skip")

    # ── Build the 5 envelopes ────────────────────────────────────────
    files: dict[str, Any] = {}
    try:
        files["thin_evidence_feedback.json"] = await compute_thin_evidence(
            session, run_id=db_run_id, entity_id=entity_id,
        )
        files["evidence_freshness_alerts.json"] = await compute_freshness_alerts(
            session, run_id=db_run_id, entity_id=entity_id,
        )
        files["tech_inference_handoff.json"] = await compute_tech_handoff(
            session, run_id=db_run_id, entity_id=entity_id,
        )
        files["narrative_overrides.json"] = await compute_narrative_overrides(
            session, entity_id=entity_id,
        )
        files["waiver_decisions.json"] = await compute_waiver_decisions(
            session, entity_id=entity_id,
        )
    except Exception as e:
        log.warning(
            "feedback.compute_failed run_id=%s err=%s",
            db_run_id, str(e)[:200],
        )
        return FeedbackWriteResult(
            state="upload_failed", error_kind=type(e).__name__,
            error_message=str(e)[:200],
        )

    if dry_run:
        return FeedbackWriteResult(
            state="dry_run", written=list(files.keys()),
        )

    upserter = drive_upserter or _default_upsert

    written: list[str] = []
    failed: list[str] = []
    first_error: Exception | None = None
    perms_missing = False
    for name, envelope in files.items():
        try:
            body = json.dumps(
                envelope.model_dump(by_alias=True, mode="json"),
                indent=2,
            ).encode("utf-8")
            await upserter(drive_folder_id, name, body)
            written.append(name)
        except Exception as e:
            failed.append(name)
            if first_error is None:
                first_error = e
            # 403 / PermissionDenied — surface specifically so operators
            # can re-share the folder with the SA without sifting logs.
            kind = type(e).__name__
            msg = str(e)
            if "403" in msg or "permission" in msg.lower() or kind in (
                "PermissionDenied", "Forbidden",
            ):
                perms_missing = True
            log.warning(
                "feedback.upload_failed run_id=%s name=%s err=%s",
                db_run_id, name, msg[:200],
            )

    if not failed:
        return FeedbackWriteResult(state="upload_ok", written=written)
    if perms_missing and not written:
        return FeedbackWriteResult(
            state="drive_perms_missing", written=written, failed=failed,
            error_kind=type(first_error).__name__ if first_error else None,
            error_message=str(first_error)[:200] if first_error else None,
        )
    return FeedbackWriteResult(
        state="upload_failed", written=written, failed=failed,
        error_kind=type(first_error).__name__ if first_error else None,
        error_message=str(first_error)[:200] if first_error else None,
    )
