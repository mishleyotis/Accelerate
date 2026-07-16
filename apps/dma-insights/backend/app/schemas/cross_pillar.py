"""Cross-pillar response schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class ThemeClusterOut(BaseModel):
    theme: str
    story_count: int
    target_pillars: dict[str, int] = Field(default_factory=dict)
    origin_capabilities: list[str] = Field(default_factory=list)


class CrossPillarResponse(BaseModel):
    entity_display_id: str
    catalogue_version: str
    total_stories: int
    themes: list[ThemeClusterOut] = Field(default_factory=list)


class CrossPillarStoryOut(BaseModel):
    """One cross-pillar story instance, scoped to this entity.

    Surfaces on D5 Context. Each row corresponds to a `ccg_cross_pillar_stories`
    catalogue row that touches one of the entity's scored subcaps.
    """
    story_key: str
    origin_pillar: str
    origin_subcap_id: str
    origin_capability: str | None = None
    target_pillar: str
    themes: list[str] = Field(default_factory=list)
    subcaps_touched: list[str] = Field(default_factory=list)
    sample_subcap_names: list[str] = Field(default_factory=list)
    # Heuristic "Why this matters" — derived from the entity's actual
    # gap profile (subcaps scored below the median get prepended).
    why_this_matters: str | None = None


class CrossPillarStoryListResponse(BaseModel):
    entity_display_id: str
    catalogue_version: str
    pillar_filter: str | None = None
    total: int
    stories: list[CrossPillarStoryOut] = Field(default_factory=list)
    # State-transition label for the endpoint:
    #   full_match | no_subverticals_match | catalogue_version_drift
    state: str
