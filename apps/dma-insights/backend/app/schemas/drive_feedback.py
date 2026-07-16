"""Pydantic shapes for the 5 PRD §17 feedback files written back to
each entity's Drive folder after every successful Phase 0 ingest.

These are the canonical interchange formats — downstream DMA bots
read them on their next run to incorporate Insights-side decisions
(thin-evidence flagging, freshness alerts, etc.) into the next
assessment iteration. Treat as a public schema: every field is
documented, every shape is versioned via `$schema`.

State-branch contract — `state` field on every envelope:
  - generated      → file built normally
  - empty          → no rows met the criteria (file still written so
                     downstream bots can distinguish "no feedback" from
                     "feedback channel broken")
  - skipped        → entity-level skip flag (e.g. waived run)
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# ── thin_evidence_feedback.json ────────────────────────────────────────


class ThinEvidenceRow(BaseModel):
    """One subcap flagged as thin-evidence (< 2 evidence rows)."""

    subcap_id: str
    category_id: str
    pillar_id: str
    score: float
    evidence_count: int
    confidence: str | None = None
    suggested_action: Literal[
        "research_deeper",
        "downgrade_confidence",
        "mark_as_proxy",
        "request_client_artifact",
    ]
    rationale: str


class ThinEvidenceFeedback(BaseModel):
    """Surfaces every subcap whose persisted evidence_count < 2 so the
    next bot run can re-target research at the gaps."""

    schema_: str = Field(
        default="thin_evidence_feedback_v1", alias="$schema"
    )
    run_id: str
    entity_id: str
    completed_at: datetime
    state: Literal["generated", "empty", "skipped"]
    threshold: int = 2
    items: list[ThinEvidenceRow] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── evidence_freshness_alerts.json ─────────────────────────────────────


class FreshnessAlertRow(BaseModel):
    """One evidence row flagged for staleness review."""

    evidence_id: str
    source_name: str
    source_url: str | None = None
    # None = source stated no canonical tier (migration 055).
    tier: int | None = None
    published_date: str | None = None
    recency_months: int | None = None
    freshness_band: Literal[
        "current", "aging", "dated", "stale", "undated"
    ]
    subcap_mappings: list[str] = Field(default_factory=list)


class EvidenceFreshnessAlerts(BaseModel):
    """Per-PRD: every evidence row with freshness_band in
    {dated, stale, undated} surfaces here so the next bot iteration
    can prioritise re-research."""

    schema_: str = Field(
        default="evidence_freshness_alerts_v1", alias="$schema"
    )
    run_id: str
    entity_id: str
    completed_at: datetime
    state: Literal["generated", "empty", "skipped"]
    stale_threshold_months: int = 36
    summary: dict[str, int] = Field(
        default_factory=lambda: {
            "current": 0, "aging": 0, "dated": 0,
            "stale": 0, "undated": 0,
        }
    )
    items: list[FreshnessAlertRow] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── tech_inference_handoff.json ────────────────────────────────────────


class TechInferenceRow(BaseModel):
    """One tech-stack row the parser inferred (vs. observed directly)."""

    vendor: str
    product: str | None = None
    category: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    inferred_from: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class TechInferenceHandoff(BaseModel):
    """Surfaces every tech-stack row we synthesised from evidence (vs.
    pulled directly from Explorium / explicit declaration). The bot can
    then re-validate / promote / discard each on the next run."""

    schema_: str = Field(
        default="tech_inference_handoff_v1", alias="$schema"
    )
    run_id: str
    entity_id: str
    completed_at: datetime
    state: Literal["generated", "empty", "skipped"]
    items: list[TechInferenceRow] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── narrative_overrides.json ───────────────────────────────────────────


class NarrativeOverrideRow(BaseModel):
    """One AE-curated narrative override that should re-apply on the
    next ingest (so the bot doesn't regenerate it)."""

    section_kind: str
    surface: Literal[
        "overview", "insights", "heatmap",
        "platform", "context", "health",
    ]
    pillar_id: str | None = None
    subcap_id: str | None = None
    override_text: str
    set_by: str
    set_at: datetime
    rationale: str | None = None


class NarrativeOverrides(BaseModel):
    """AE-side narrative edits the bot should respect on the next run.
    Empty `items` on first ingest; populated by every subsequent AE
    edit through the (yet-to-be-built) narrative-edit panel."""

    schema_: str = Field(default="narrative_overrides_v1", alias="$schema")
    entity_id: str
    completed_at: datetime
    state: Literal["generated", "empty", "skipped"]
    items: list[NarrativeOverrideRow] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── waiver_decisions.json ──────────────────────────────────────────────


class WaiverRow(BaseModel):
    """One admin-granted waiver — a subcap / pillar / entire-run scope
    decision the bot should respect on subsequent runs."""

    waiver_id: str
    scope: Literal["subcap", "pillar", "category", "entity_run"]
    target_id: str | None = None
    issue_id: str | None = None
    reason: str
    granted_by: str
    granted_at: datetime
    expires_at: datetime | None = None
    cap_ceiling: float | None = None


class WaiverDecisions(BaseModel):
    """Cap-bypass / score-floor waivers an Admin has granted. Bot reads
    on next run to skip the redundant flag."""

    schema_: str = Field(default="waiver_decisions_v1", alias="$schema")
    entity_id: str
    completed_at: datetime
    state: Literal["generated", "empty", "skipped"]
    items: list[WaiverRow] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


# ── Aggregate envelope returned by write_feedback_files ────────────────


class FeedbackWriteResult(BaseModel):
    """State branches surfaced to the caller (publish_post_commit) so
    the audit_log row carries enough diagnostic info.

    State values:
      - drive_folder_unknown  → entity has no recorded drive_folder_id
      - drive_perms_missing   → 403 on upsert (SA lost write access)
      - upload_failed         → 4xx/5xx on at least one file
      - upload_ok             → every file accepted
      - dry_run               → caller passed dry_run=True (no IO)
      - dev_skip              → env=local/test (no Drive call)
    """

    state: Literal[
        "drive_folder_unknown",
        "drive_perms_missing",
        "upload_failed",
        "upload_ok",
        "dry_run",
        "dev_skip",
    ]
    written: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    error_kind: str | None = None
    error_message: str | None = None


class FeedbackRefreshResponse(BaseModel):
    """Result of an entity-scoped feedback-file refresh. `state` is a
    FeedbackWriteResult state OR `no_active_run` (no run to compute from)."""
    entity_display_id: str
    run_request_id: str | None = None
    state: str
    written: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)


class FeedbackRefreshAllItem(BaseModel):
    entity_display_id: str
    state: str
    written: list[str] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)


class FeedbackRefreshAllResponse(BaseModel):
    total: int
    by_state: dict[str, int] = Field(default_factory=dict)
    results: list[FeedbackRefreshAllItem] = Field(default_factory=list)
