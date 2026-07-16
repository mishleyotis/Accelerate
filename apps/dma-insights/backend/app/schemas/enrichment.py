"""AI enrichment schemas — read shape exposed to /heatmap, /insights, etc.

State transitions:
  target row has no active (non-superseded) ai_enrichments row
    → response omits the `ai_enrichment` field entirely.
  catalogue_version bump
    → the prior enrichment is marked superseded; the new row becomes the
      active record returned by the read API.
  validators_passed = False
    → enrichment_text is the deterministic template fallback; UI badge
      MUST show "fallback" instead of "AI-enriched".
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class AiEnrichmentOut(BaseModel):
    id: str
    target_kind: Literal["subcap_score", "insight_card", "recommendation", "entity"]
    target_id: str
    surface: str
    enrichment_text: str
    grounding_evidence_ids: list[str] = Field(default_factory=list)
    grounding_subcap_ids: list[str] = Field(default_factory=list)
    model: str
    catalogue_version: str
    validators_passed: bool
    confidence: float | None = None
    created_at: datetime


class ArchetypeMatch(BaseModel):
    archetype_label: str
    subvertical: str
    catalogue_version: str
    distance: float
    defining_subcap_ids: list[str] = Field(default_factory=list)
    sample_count: int
    silhouette_score: float | None = None


class ArchetypeResponse(BaseModel):
    closest: ArchetypeMatch | None = None
    all_archetypes: list[ArchetypeMatch] = Field(default_factory=list)
    insufficient_data: bool = False


class RunHistoryItem(BaseModel):
    request_id: str
    parent_request_id: str | None = None
    status: str
    catalogue_version: str
    completed_at: datetime | None = None
    started_at: datetime | None = None
    subcap_count: int = 0
    evidence_count: int = 0
    score_delta_vs_parent: float | None = None
    # Migration 039: the run-selector pill renders the assessment date
    # (falls back to completed_at when NULL for pre-039 REQ-hex rows).
    assessment_date: date | None = None


class RunHistoryResponse(BaseModel):
    entity_id: str
    items: list[RunHistoryItem]
    parent_chain: list[str] = Field(default_factory=list)


class VertexBudgetSurfaceUsage(BaseModel):
    surface: str
    tokens: int
    estimated_usd: float


class VertexBudgetUserUsage(BaseModel):
    user_email: str
    tokens: int
    estimated_usd: float


class VertexBudgetResponse(BaseModel):
    period: str
    spent_usd: float
    budget_usd: float
    pct_used: float
    top_surfaces: list[VertexBudgetSurfaceUsage] = Field(default_factory=list)
    top_users: list[VertexBudgetUserUsage] = Field(default_factory=list)


class PendingReviewItem(BaseModel):
    kind: Literal["run", "entity", "import_file"]
    id: str
    display_id: str | None = None
    title: str
    detail: str | None = None
    created_at: datetime
    entity_id: str | None = None
    entity_name: str | None = None


class PendingReviewResponse(BaseModel):
    items: list[PendingReviewItem]
    counts_by_kind: dict[str, int] = Field(default_factory=dict)
