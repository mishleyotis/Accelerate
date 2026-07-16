"""D4 StairstepCurve response schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StairStepOut(BaseModel):
    rec_id: str
    title: str
    pillar: str
    score_before: float = Field(..., ge=0.0, le=5.0)
    score_after: float = Field(..., ge=0.0, le=5.0)
    uplift: float = Field(..., ge=0.0)


class StairstepResponse(BaseModel):
    entity_display_id: str
    run_request_id: str | None = None
    steps_by_pillar: dict[str, list[StairStepOut]] = Field(default_factory=dict)
    current_by_pillar: dict[str, float] = Field(default_factory=dict)
    end_score_by_pillar: dict[str, float] = Field(default_factory=dict)
    target_band_score: float = 4.0
    empty_state: Literal["no-gaps", "no-recs", "no-applicable-uplift"] | None = None
    # Names the coarser signal that placed the client on the curve when the
    # run carried no scored subcaps ("pillar_scores" | "overall_maturity"),
    # else None when per-subcap scores drove the position.
    position_source: str | None = None
