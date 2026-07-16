"""D4 Platform card response schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PlatformState = Literal[
    "READY", "PENDING_REVIEW", "INSUFFICIENT_EVIDENCE", "RECOMPUTE_NEEDED"
]
ReadinessLight = Literal["green", "amber", "red"]


class PrereqCheckOut(BaseModel):
    name: str
    required_subcap_id: str
    threshold: float
    status: Literal["MET", "PARTIAL", "UNMET", "MISSING"]
    current_score: float | None = None
    note: str | None = None


class PlatformCard(BaseModel):
    platform_id: str
    display_name: str
    pillar: str
    fit_score: float
    readiness_index: ReadinessLight
    state: PlatformState
    addressable_subcap_ids: list[str] = Field(default_factory=list)
    prereq_checks: list[PrereqCheckOut] = Field(default_factory=list)
    conversation_starter: str | None = None  # legacy single-string join
    # The prototype's 3 distinct starter cards (08_pages_d.js:206) —
    # deterministic template-fill, one entry per starter, [] when the
    # platform has no addressable subcaps.
    conversation_starters: list[str] = Field(default_factory=list)
    # Validated Gemini platform story (enrich_corpus warm sweep, pro model)
    # read back from vertex_synthesis_cache — an UPLIFT over the
    # deterministic starters, never a replacement. None when cold/unwarmed.
    story_md: str | None = None
    story_source: str | None = None  # "vertex" when story_md is cache-read
    # Migration 053 (Part 7.1 fit engine v2). All additive — None until
    # the v2 engine persists rows on `platform_scores`.
    #
    # Per-factor contributions {opportunity, readiness, interconnect,
    # absent_boost, ...} + top contributing subcaps + their E-IDs —
    # the fit-tile drilldown drawer (factor bars + evidence chips).
    fit_breakdown: dict | None = None
    # Position in the prerequisite DAG across platforms+recs ("what
    # unlocks what") — consumed by SCQA Answer + roadmap phasing.
    sequence_rank: int | None = None
    # Prototype fit-tile badges (Part 7.4): count of confirmed-ABSENT
    # taxonomy rows addressable by this platform, and the top-2
    # contributing subcap names. None until the Part 9 taxonomy /
    # fit v2 derivations land.
    absent_count: int | None = None
    top_subcap_names: list[str] | None = None
    # Evidence ladder (Part 7.1): the E-IDs grounding this card — the union
    # of its addressable subcaps' evidence (direct link → category roll-up →
    # run-level), so a card carries real citations wherever the entity has
    # any evidence. Empty ONLY for a truly evidence-less entity (honest).
    evidence_ids: list[str] = Field(default_factory=list)
    # Serve-side twin of the offline patcher's _enrich_platforms rung:
    # startup_enrich.compose_opportunity_md over this card's OWN serialized
    # fields. None for INSUFFICIENT_EVIDENCE / no addressable surface
    # (honest blank — the patcher skips those too). 2026-07-04: its absence
    # was 40 of 240 qa_pack_parity structural findings on a fresh regen DB.
    opportunity_md: str | None = None
    # 2026-07-06 platform-reasoning mandate — both deterministic
    # (parsed_skipped_llm class), composed from engine state + the
    # entity's OWN evidence:
    #
    # Evidence-rich "where the entity stands on this platform" story:
    # verbatim-quoted excerpts with E-IDs, stack position (in-use /
    # greenfield, evidence-corrected), scale context, top opportunity
    # areas. None when the card has no addressable surface.
    narrative_md: str | None = None
    # Ranked Zennify opportunity areas [{category_id, name, opportunity,
    # subcap_ids, subcap_names, e_ids}] — the per-entity opportunity map.
    opportunity_areas: list[dict] = Field(default_factory=list)
    # Platform v3 deterministic dossier (platform_dossier.compose_dossier) —
    # the evidence-rich narrative floor: three structured sections (readiness
    # now / opportunity / why-this-sequence) that back story_md and drive the
    # D4 dossier panel. All additive/optional so legacy packs + the frontend
    # keep parsing when absent (cold pack ⇒ None ⇒ today's layout).
    dossier: dict | None = None
    # Per-composed-sentence audit chain: [{claim, source_kind, e_ids}] — the
    # traceability mandate ("every issue flagged is QA'd").
    narrative_provenance: list[dict] = Field(default_factory=list)


class PlatformsResponse(BaseModel):
    entity_display_id: str
    run_request_id: str | None = None
    cards: list[PlatformCard]
    pillar_offerings: dict[str, list[str]] = Field(default_factory=dict)
    # Narrative from the Assessment_Report DOCX — recommendations +
    # roadmap + gap_prioritization prose. None when no DOCX ingested.
    narrative: dict | None = None
