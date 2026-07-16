"""AppPayloadV1 — the Claude project's ingest contract.

The project posts to POST /api/v1/ingest/assessment with this shape when an
assessment run finishes. Mirrors the canonical SCQA / subcap-scores / evidence
/ insights / recommendations layout from PRD §02 and Backend Schema v2.0.

Stricter than the workbook parser's tolerance: ingest from the project is
expected to be schema-clean (the Claude project owns this contract).
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SubcapScoreIn(BaseModel):
    subcap_id: str = Field(..., pattern=r"^P[1-4]C\d+\.\d+\.\d+(?:-T2-[A-Z]{2,3})?$")
    score: float = Field(..., ge=1.0, le=5.0)
    band: Literal["M1", "M2", "M3", "M4", "M5"]
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    rationale: str | None = None
    peer_median: float | None = Field(None, ge=1.0, le=5.0)
    peer_gap: float | None = None
    is_thin_evidence: bool = False
    cap_applied: bool = False
    cap_reason: str | None = None
    platform_tags: list[str] = Field(default_factory=list)


class EvidenceItemIn(BaseModel):
    e_id: str = Field(..., pattern=r"^E-\d+$")
    source_name: str
    source_url: str | None = None
    excerpt: str = Field(..., min_length=1)
    claim_type: str
    tier: int = Field(..., ge=1, le=8)
    recency_months: int | None = None
    published_date: date | None = None
    linked_subcap_ids: list[str] = Field(default_factory=list)


class InsightCardIn(BaseModel):
    ic_id: str = Field(..., pattern=r"^IC-\d+$")
    severity: Literal["critical", "high", "medium", "low"]
    title: str
    what_text: str
    why_text: str
    so_what_text: str
    linked_subcap_id: str
    linked_e_ids: list[str] = Field(default_factory=list)


class RecommendationIn(BaseModel):
    rec_id: str = Field(..., pattern=r"^REC-\d+$")
    title: str
    description: str
    target_subcap_ids: list[str] = Field(default_factory=list)
    platform_id: str | None = None
    addressable_offerings: list[str] = Field(default_factory=list)
    cited_l4_features: list[str] = Field(default_factory=list)
    cited_constructs: list[str] = Field(default_factory=list)
    cited_agents: list[str] = Field(default_factory=list)
    uplift_per_pillar: dict[str, float] | None = None
    effort_band: Literal["small", "medium", "large", "xl"] | None = None


class FocusAreaIn(BaseModel):
    name: str
    source_quote: str
    source_path: str
    page_number: int | None = None
    financial_reference: str | None = None
    involved_subcap_ids: list[str] = Field(default_factory=list)


class IssueIn(BaseModel):
    issue_id: str
    title: str
    severity: Literal["critical", "high", "medium", "low"]
    rationale: str | None = None
    opened_on: date | None = None
    resolved_on: date | None = None
    linked_subcap_ids: list[str] = Field(default_factory=list)
    source_path: str | None = None


class TimelineEventIn(BaseModel):
    event_date: date
    kind: str
    title: str
    body: str | None = None
    source_url: str | None = None
    e_id: str | None = None


class TechStackEntryIn(BaseModel):
    tech_id: str
    vendor: str
    product: str
    layer: Literal["foundation", "platform", "application", "intelligence"]
    status: str
    source: str
    evidence_e_ids: list[str] = Field(default_factory=list)
    linked_subcap_ids: list[str] = Field(default_factory=list)


class FirmographicsIn(BaseModel):
    aum_usd: float | None = None
    revenue_usd: float | None = None
    headcount: int | None = None
    hq_address: str | None = None
    primary_regulator: str | None = None
    leadership: list[dict] | None = None
    thought_leadership: list[dict] | None = None


class ScqaIn(BaseModel):
    situation: str
    complication: str
    question: str
    answer: str


class AppPayloadV1(BaseModel):
    """The complete envelope the Claude project posts back."""

    model_config = ConfigDict(extra="ignore")

    payload_version: Literal["v1"] = "v1"
    request_id: str = Field(..., pattern=r"^REQ-[0-9A-F]{8}$")
    parent_request_id: str | None = Field(None, pattern=r"^REQ-[0-9A-F]{8}$")
    ccg_catalog_version: str = Field(default="v7.0")

    entity_name: str
    entity_domain: str | None = None
    entity_subvertical: str | None = None
    entity_lobs: list[str] = Field(default_factory=list)

    firmographics: FirmographicsIn | None = None
    scqa: ScqaIn
    why_now_signals: list[dict] = Field(default_factory=list)
    top_findings: list[dict] = Field(default_factory=list)

    subcap_scores: list[SubcapScoreIn]
    evidence: list[EvidenceItemIn]
    insights: list[InsightCardIn]
    recommendations: list[RecommendationIn]
    focus_areas: list[FocusAreaIn] = Field(default_factory=list)
    issue_register: list[IssueIn] = Field(default_factory=list)
    timeline_events: list[TimelineEventIn] = Field(default_factory=list)
    tech_stack: list[TechStackEntryIn] = Field(default_factory=list)


class IngestAck(BaseModel):
    request_id: str
    run_id: str
    status: Literal["ACTIVE"]
    superseded_run_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
