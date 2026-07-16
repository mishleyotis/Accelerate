"""Recommendation detail schema — drives D4's RecommendationModal."""
from __future__ import annotations

from pydantic import BaseModel, Field


class RecommendationNoteIn(BaseModel):
    """PUT body for the per-recommendation AE note. A blank/whitespace
    ``note`` DELETES the persisted row (see the PUT endpoint)."""

    note: str = Field(default="", max_length=20000)


class RecommendationNoteOut(BaseModel):
    """The durable, team-shared AE note for a (client, recommendation).

    ``note`` is "" when none is persisted (the GET endpoint returns an
    empty note object rather than 404 — the UI expects a shape, not a
    miss). ``author_email`` is the AE who last saved; ``updated_at`` is an
    ISO-8601 string (or null when there is no note)."""

    note: str = ""
    author_email: str | None = None
    updated_at: str | None = None


class CitedReference(BaseModel):
    """A single cited reference (feature / platform construct / agent).

    `resolved` tells the frontend whether the cited string ACTUALLY
    exists in the catalogue. Cited refs that don't resolve are surfaced
    so the AE knows the rec was generated with weaker grounding (and
    the analyst can decide whether to ship it).
    """
    kind: str        # "feature" | "construct" | "agent"
    id: str          # the cited string (e.g. "AF-LoanOriginator-01")
    resolved: bool
    name: str | None = None


class RecDependencies(BaseModel):
    """D4 DependencyMap: sibling recommendations that gate or are gated by
    this one. `prerequisites` are parsed at ingest from the source
    recommendation_validation.json; `unlocks` is the read-time inverse.
    Both empty (honest contextual-empty) until the corpus is re-ingested."""
    prerequisites: list[str] = Field(default_factory=list)
    unlocks: list[str] = Field(default_factory=list)


class RecommendationDetail(BaseModel):
    id: str
    rec_id: str
    title: str
    description: str
    entity_display_id: str
    target_subcap_ids: list[str] = Field(default_factory=list)
    platform_id: str | None = None
    addressable_offerings: list[str] = Field(default_factory=list)
    uplift_per_pillar: dict[str, float] | None = None
    effort_band: str | None = None
    cited_features: list[CitedReference] = Field(default_factory=list)
    cited_constructs: list[CitedReference] = Field(default_factory=list)
    cited_agents: list[CitedReference] = Field(default_factory=list)
    unresolved_count: int = 0
    catalogue_version: str
    dependencies: RecDependencies = Field(default_factory=RecDependencies)
    # Migration 048 (Part 7.2 — recommendations_detail.json / REC-NN.json
    # ingest). All additive — None/empty until re-ingest fills them.
    #
    # The concrete platform feature the rec ships (distinct from title).
    feature: str | None = None
    # Sequencing phase from the source rec files; feeds the multi-phase
    # roadmap (effort-band bucketing stays the fallback).
    phase: int | None = None
    # E-IDs grounding the rec's root cause — the modal's restored
    # "Root-cause evidence" tab.
    root_cause_e_ids: list[str] = Field(default_factory=list)
    # Quantified expected outcomes: {time, effort, metric, peer}.
    outcomes: dict | None = None
