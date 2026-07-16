"""Drift response schema for the /patterns/{entity}/drift endpoint."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

DriftBucket = Literal[
    "critical_low", "below", "nominal", "above", "critical_high",
    "cohort_insufficient", "entity_missing",
]


class SubcapDriftOut(BaseModel):
    subcap_id: str
    pillar: str
    bucket: DriftBucket
    drift_score: float | None = None
    entity_score: float | None = None
    peer_median: float | None = None
    peer_n: int


class PillarDriftOut(BaseModel):
    pillar: str
    drift_score: float | None = None
    subcap_count: int
    by_bucket: dict[str, int] = Field(default_factory=dict)


class DriftReportOut(BaseModel):
    entity_display_id: str
    cohort_insufficient_count: int = 0
    entity_missing_count: int = 0
    overall_drift: float | None = None
    pillar_drifts: list[PillarDriftOut] = Field(default_factory=list)
    subcap_drifts: list[SubcapDriftOut] = Field(default_factory=list)
