"""D6 Health + Alerts schemas."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class AlertOut(BaseModel):
    id: str
    kind: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    title: str
    body: str
    linked_subcap_ids: list[str] = Field(default_factory=list)
    linked_e_ids: list[str] = Field(default_factory=list)
    opened_at: datetime
    closed_at: datetime | None = None
    resolution: str | None = None
    age_days: int
    # 2026-06-05 QA finding 9: AlertsPage needs the entity display_id
    # to navigate to the client view. Pre-fix the page tried to derive
    # an entity slug from `linked_subcap_ids[0][:6]` (e.g. P3C1.7 ->
    # 'P3C1.7' -> navigate('/clients/P3C1.7/heatmap')) which is
    # obviously not an entity id; the navigation 404'd every time.
    entity_id: str | None = None
    entity_display_id: str | None = None
    # Migration 040 (alerts producer): the wireframe health/alerts tables
    # render the evidence n/3 mini-bar, the recommended-action mono chip
    # (PROXY_ESCALATION / TIER_UPGRADE) and the proxy-searched flag.
    # NULL for manually-raised alert kinds.
    evidence_count: int | None = None
    recommended_action: str | None = None
    proxy_searched: bool | None = None
    entity_name: str | None = None
    # 2026-07-02 (plan Part 11.2): the AlertsPage "Waived" tab shows each
    # waived alert WITH its operator rationale (the ≥50-char note the
    # waive action requires). Latest waive-action note; NULL for alerts
    # that were never waived.
    waive_note: str | None = None


class AlertListResponse(BaseModel):
    items: list[AlertOut]
    open_count: int


class SafeguardGateOut(BaseModel):
    gate_id: str
    status: Literal["PASS", "PARTIAL", "FAIL", "DEFERRED"]
    detail: str | None = None
    evaluated_at: datetime


class EvidenceAgeOut(BaseModel):
    """One row for the D6 Health "Age" tab. `freshness_band` is the
    SQL-side authority (`evidence_index.freshness_band` STORED generated
    column) — the frontend renders the band directly rather than
    recomputing an age threshold."""

    e_id: str
    source_name: str
    # None = source stated no canonical tier (migration 059).
    tier: int | None = None
    published_date: date | None = None
    recency_months: int | None = None
    freshness_band: Literal["current", "aging", "dated", "stale", "undated"]


class CapsAppliedOut(BaseModel):
    """One row of `caps_applied_log` table surfaced on D6 Health Gates
    tab. Sources from `07_governance/caps_applied_log.csv` (per the
    C10 v2-QA win 2026-06-07). Renders as a sortable cap-events table
    showing why specific subcap scores were ceiling-capped."""

    log_id: str
    subcap_id: str
    cap_type: str | None = None
    trigger_condition: str | None = None
    cap_ceiling: str | None = None
    trigger_evidence: list[str] = Field(default_factory=list)
    affected_categories: list[str] = Field(default_factory=list)
    severity: str | None = None
    date_applied: str | None = None
    recalc_verified: str | None = None


class QaVerdictOut(BaseModel):
    """C5 (2026-06-07): one verdict from `qa_verdict.json` /
    `L1_qa_verdict.json` / `Layer1_qa_verdict.json` / `GOV_qa_verdict.json`.

    `verdict` is the headline value (`PASS`, `PASS_WITH_NOTES`,
    `FAIL`, etc.) — distinct shapes across L1 and L2 verdict files.
    Rendered on the D6 Gates tab as a top-of-tab "QA verdict chain"
    card so analysts can see the L1->L2 escalation.
    """
    verdict: str | None = None
    recommendation: str | None = None
    verdict_basis: str | None = None
    governance_skill_version: str | None = None


class AuditLogsOut(BaseModel):
    """C7 (2026-06-07): bot governance audit logs envelope.

    Surfaces the bot's actual reasoning chain (CoT decision paths) +
    contradiction adjudication on D6 Health "Audit" tab. Analyst-only.
    Empty when the package shipped no audit log files (3 of 5 real
    fixtures; only Nicola + Odlum ship at least one component).
    """
    reasoning_chain: list[dict] = Field(default_factory=list)
    contradictions: list[dict] = Field(default_factory=list)


class HealthResponse(BaseModel):
    entity_display_id: str
    run_request_id: str | None = None
    thin_evidence_subcap_ids: list[str] = Field(default_factory=list)
    safeguard_gates: list[SafeguardGateOut] = Field(default_factory=list)
    alerts: list[AlertOut] = Field(default_factory=list)
    # B-5: per-evidence freshness for the Age tab (STORED freshness_band).
    evidence_age: list[EvidenceAgeOut] = Field(default_factory=list)
    # C10 (2026-06-07): cap-event log surfacing why subcap scores were
    # ceiling-capped. Renders on the Gates tab as a sortable table.
    # Empty list when the package shipped no `caps_applied_log.csv`
    # (WSFS-shape; equivalent semantics in subcap_scores.caps_applied).
    caps_applied: list[CapsAppliedOut] = Field(default_factory=list)
    # C5 (2026-06-07): 2-stage QA verdict chain. Both fields are nullable
    # because not every package ships both verdicts:
    #   Odlum + Calprivate : both L1 + L2 (escalation chain visible).
    #   Alma / WSFS / Nicola: only L2 (qa_verdict_l1 = null).
    qa_verdict_l1: QaVerdictOut | None = None
    qa_verdict_l2: QaVerdictOut | None = None
    # C7 (2026-06-07): bot reasoning chain + contradiction adjudication
    # (D6 Health "Audit" tab; Analyst-only role gate). `null` when the
    # package shipped no audit logs.
    audit_logs: AuditLogsOut | None = None
    # Data-gaps + evidence-registry preface from the DOCX. None = no DOCX.
    narrative: dict | None = None


class AlertActionRequest(BaseModel):
    action: Literal["acknowledge", "waive", "escalate", "close"]
    note: str | None = None


class CrossEntityPatternOut(BaseModel):
    """One recurring cross-entity pattern (D6 Health "Patterns" tab).

    `pattern_type` is subcap_gap | issue_theme. `entity_count` is how many
    cohort entities share it; this entity is always one of them.
    """
    pattern_type: str
    pattern_key: str
    pattern_label: str
    primary_subcap_id: str | None = None
    entity_count: int
    severity_mix: dict[str, int] = Field(default_factory=dict)
    median_peer_gap: float | None = None
    sample_subcap_ids: list[str] = Field(default_factory=list)


class HealthPatternsResponse(BaseModel):
    entity_display_id: str
    run_request_id: str | None = None
    subvertical: str | None = None
    catalogue_version: str | None = None
    patterns: list[CrossEntityPatternOut] = Field(default_factory=list)
    # full | no_cohort | insufficient_data | no_active_run
    state: str


class GlobalPatternOut(BaseModel):
    """One fleet-wide recurring pattern for the AlertsPage "Patterns" tab
    (plan Part 11.2). Same worker output as `CrossEntityPatternOut`
    (`cross_entity_patterns`, written nightly by the cross_entity_patterns
    worker) but WITHOUT an anchor entity: the global tab lists every
    pattern with the affected entity names so an Analyst can spot cohort
    themes without opening a client first.
    """
    pattern_type: str
    pattern_key: str
    pattern_label: str
    subvertical: str
    catalogue_version: str
    primary_subcap_id: str | None = None
    entity_count: int
    severity_mix: dict[str, int] = Field(default_factory=dict)
    median_peer_gap: float | None = None
    sample_subcap_ids: list[str] = Field(default_factory=list)
    affected_entity_names: list[str] = Field(default_factory=list)


class GlobalPatternsResponse(BaseModel):
    items: list[GlobalPatternOut] = Field(default_factory=list)
    # full | insufficient_data | empty  — `insufficient_data` when the
    # worker ran but every cohort was below its minimum N; `empty` when
    # the worker has never written rows (honest empty state, no promises).
    state: str
