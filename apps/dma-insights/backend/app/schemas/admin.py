"""Admin surface schemas."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: Literal["ADMIN", "ANALYST", "AE", "CUSTOMER"]
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class UserListResponse(BaseModel):
    items: list[UserOut]


class UpdateRoleRequest(BaseModel):
    role: Literal["ADMIN", "ANALYST", "AE", "CUSTOMER"]


class BuildQaGateOut(BaseModel):
    id: str
    stage: str
    gate_id: str
    category: str
    description: str
    acceptance_criteria: str
    status: Literal["PENDING", "PASS", "PARTIAL", "FAIL", "DEFERRED"]
    evidence_url: str | None = None
    evaluated_at: datetime | None = None
    git_sha: str | None = None


class BuildQaResponse(BaseModel):
    items: list[BuildQaGateOut]
    summary: dict[str, int] = Field(default_factory=dict)


class CatalogueRunOut(BaseModel):
    id: str
    version: str
    status: Literal["STAGING", "AWAITING_APPROVAL", "APPLIED", "REJECTED"]
    loader_started_at: datetime
    loader_finished_at: datetime | None = None
    source_files: list[dict] = Field(default_factory=list)
    parse_warnings: list[dict] = Field(default_factory=list)
    validation_report: dict | None = None
    diff_vs_prior_version: dict | None = None


class CatalogueQueueResponse(BaseModel):
    awaiting_approval: list[CatalogueRunOut]
    recent_applied: list[CatalogueRunOut]


class AssignmentQueueRow(BaseModel):
    entity_id: str
    entity_display_id: str
    entity_name: str
    source: str
    source_ref: str | None = None
    confidence: float | None = None
    assigned_at: datetime
    proposed_user_email: EmailStr | None = None
    proposed_user_name: str | None = None
    reason: str


class AssignmentQueueResponse(BaseModel):
    pending: list[AssignmentQueueRow]


class ImportFileOut(BaseModel):
    id: str
    filename: str
    file_kind: str
    status: Literal["DETECTED", "PROCESSING", "OK", "PENDING_REVIEW", "FAILED", "SKIPPED"]
    parser_warnings: dict | list | None = None
    drive_file_id: str
    drive_modified_time: datetime | None = None
    processed_at: datetime | None = None
    created_at: datetime
    entity_display_id: str | None = None
    run_request_id: str | None = None


class ImportAuditResponse(BaseModel):
    items: list[ImportFileOut]
    counts_by_status: dict[str, int]


# ───────────────────────────────────────────────────────────────────
# job_executions — admin "trigger a worker" endpoints (migration 020)
# ───────────────────────────────────────────────────────────────────


class JobExecuteRequest(BaseModel):
    mode: str | None = None
    args: dict | None = None
    entity_id: str | None = None


class JobExecutionOut(BaseModel):
    id: str
    job_name: str
    mode: str | None = None
    status: Literal["running", "succeeded", "failed", "cancelled"]
    trigger_source: str
    triggered_by_email: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
    duration_sec: float | None = None
    entity_id: str | None = None
    # Counters (all optional — populated by the worker as it progresses)
    folders_seen: int | None = None
    folders_new: int | None = None
    folders_changed: int | None = None
    files_parsed: int | None = None
    files_skipped: int | None = None
    files_errored: int | None = None
    rows_added: int | None = None
    rows_updated: int | None = None
    rows_deleted: int | None = None
    parser_warnings: dict | list | None = None
    stderr_tail: str | None = None
    error_message: str | None = None
    # Computed for UI
    result_summary: str = ""
    error_count: int = 0
    # Cloud Logging deep link — present only when the row was actually
    # dispatched to a Cloud Run Job (cloud_run_execution_name set).
    # The admin UI renders this as a "View logs" link in the row's
    # action menu so the operator can jump straight from a stuck/failed
    # job to the worker's stdout/stderr without manually building the
    # Cloud Logging filter URL.
    logs_url: str | None = None


class JobExecutionListResponse(BaseModel):
    items: list[JobExecutionOut]


class JobRegistryEntry(BaseModel):
    job_name: str
    modes: list[str]
    default_mode: str
    description: str


class JobRegistryResponse(BaseModel):
    jobs: list[JobRegistryEntry]


# ───────────────────────────────────────────────────────────────────
# Per-entity import audit drilldown (Defect 4)
# ───────────────────────────────────────────────────────────────────


class ImportAuditSummary(BaseModel):
    """Live tile counts for the Import Audit page."""
    last_crawl_at: datetime | None = None
    candidates_processed: int = 0
    files_imported: int = 0
    files_excluded: int = 0
    files_awaiting_review: int = 0
    files_errored: int = 0


class ImportAuditEntityRow(BaseModel):
    """One row per entity that has ever been ingested."""
    entity_id: str
    entity_display_id: str
    entity_name: str
    latest_run_completed_at: datetime | None = None
    runs_count: int = 0
    latest_status: str | None = None
    dedup_audit_count: int = 0
    enrichment_count: int = 0


class ImportAuditByEntityResponse(BaseModel):
    items: list[ImportAuditEntityRow]
    # 2026-05-29 QA audit P1: the endpoint is self-healing for optional
    # audit/enrichment tables — `dedup_audit` missing → warning + count=0;
    # `ai_enrichments` legacy shape → warning + legacy count. Core
    # `entities`/`runs` missing escalates to 503 instead of a warning.
    warnings: list[str] = []


class ImportAuditEntityRunRow(BaseModel):
    run_id: str
    request_id: str
    status: str
    completed_at: datetime | None = None
    parent_request_id: str | None = None
    evidence_count: int = 0
    embedding_count: int = 0


class ImportAuditEntityJobRow(BaseModel):
    id: str
    job_name: str
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    duration_sec: float | None = None


class ImportAuditEntityDetailResponse(BaseModel):
    entity_id: str
    entity_display_id: str
    entity_name: str
    runs: list[ImportAuditEntityRunRow]
    job_executions: list[ImportAuditEntityJobRow]


# ---------------------------------------------------------------------------
# Prompt-quality rollup (consumer of services/prompt_quality.py)
# ---------------------------------------------------------------------------

class PromptQualityVersionRow(BaseModel):
    """One row per (surface, prompt_template_version) — read by the
    Admin → Prompt Quality table."""

    surface: str
    prompt_template_version: str
    total_responses: int
    total_hallucinations: int
    hallucination_rate: float
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    is_active_version: bool


class PromptQualitySurfaceRow(BaseModel):
    """Collapsed (one row per surface) view of the rollup."""

    surface: str
    versions_observed: int
    active_version: str | None = None
    total_responses: int
    total_hallucinations: int
    hallucination_rate: float
    estimated_cost_usd: float


class PromptQualityVersionDiffRow(BaseModel):
    """Pairwise candidate-vs-baseline diff between consecutive
    prompt_template_versions recorded for a surface."""

    surface: str
    baseline_version: str
    candidate_version: str
    baseline_hallucination_rate: float
    candidate_hallucination_rate: float
    rate_delta: float
    baseline_responses: int
    candidate_responses: int
    verdict: Literal[
        "candidate_better", "candidate_worse", "tie", "insufficient_data",
    ]


class PromptQualityResponse(BaseModel):
    """Top-level response — by_surface for the budget tile,
    by_version for the table, version_diffs for the side panel."""

    by_surface: list[PromptQualitySurfaceRow] = Field(default_factory=list)
    by_version: list[PromptQualityVersionRow] = Field(default_factory=list)
    version_diffs: list[PromptQualityVersionDiffRow] = Field(default_factory=list)
    window_days: int | None = None
