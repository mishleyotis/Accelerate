"""Pattern recognition response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SimilarInsightOut(BaseModel):
    insight_card_id: str
    ic_id: str
    entity_name: str
    title: str
    severity: str
    linked_subcap_id: str
    cohort_match: float = Field(..., ge=0.0, le=1.0)
    text_similarity: float = Field(..., ge=0.0, le=1.0)
    combined_score: float = Field(..., ge=0.0, le=1.0)


class SimilarInsightsResponse(BaseModel):
    seed_ic_id: str
    cohort_mode: str
    items: list[SimilarInsightOut]


class SimilarRecommendationOut(BaseModel):
    recommendation_id: str
    rec_id: str
    entity_name: str
    title: str
    platform_id: str | None = None
    cohort_match: float = Field(..., ge=0.0, le=1.0)
    text_similarity: float = Field(..., ge=0.0, le=1.0)
    combined_score: float = Field(..., ge=0.0, le=1.0)


class SimilarRecommendationsResponse(BaseModel):
    seed_rec_id: str
    cohort_mode: str
    items: list[SimilarRecommendationOut]


class RecurringSubcapTheme(BaseModel):
    """Aggregated frequency of an insight title (and its severity) across
    the cohort, anchored to a single subcap_id. Useful for D2's "This
    pattern appears on N other entities" affordance.
    """
    title: str
    severity: str
    occurrence_count: int
    sample_entities: list[str] = Field(default_factory=list)


class RecurringSubcapResponse(BaseModel):
    subcap_id: str
    cohort_mode: str
    themes: list[RecurringSubcapTheme]
