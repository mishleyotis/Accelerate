"""D2 Insights schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InsightCardOut(BaseModel):
    id: str
    ic_id: str
    severity: Literal["critical", "high", "medium", "low"]
    title: str
    what_text: str
    why_text: str
    so_what_text: str
    linked_subcap_id: str
    linked_e_ids: list[str] = Field(default_factory=list)
    # Counter-signals: E-IDs that DISAGREE with the headline insight.
    # The app's job is to argue, not just claim. An insight without
    # counter-signals is either (a) genuinely uncontested (rare), or
    # (b) under-evidenced. The UI renders a "But also..." section when
    # this is non-empty; renders "No counter-signals identified" when
    # empty. Either way, the AE sees the model's homework.
    #
    # Backfilled NULL for legacy rows (migration 023, future). For
    # now, defaults to [] so existing tests pass and the field is
    # always present in the response.
    counter_e_ids: list[str] = Field(default_factory=list)
    # Confidence band: "high" / "medium" / "low" — distinct from the
    # numeric `confidence` (legacy schema). UI shows a chip with a
    # tooltip explaining the band's rule:
    #   high   = ≥ 3 evidence rows, all tier ≥ 4
    #   medium = ≥ 2 evidence rows OR mixed tier
    #   low    = single evidence row OR tier ≤ 2
    confidence_band: Literal["high", "medium", "low"] | None = None
    # The recommendation this insight was DERIVED from — the faithful single
    # link for the "Linked recommendation" callout. NULL until re-ingest
    # (populated at parse time by insights_from_recommendations).
    source_rec_id: str | None = None
    # Recommendations targeting the same capability (subcap join, prefix-
    # aware). Works on existing data with no re-ingest; the frontend uses
    # source_rec_id when present and falls back to related_rec_ids[0].
    related_rec_ids: list[str] = Field(default_factory=list)
    # Migration 046 (Part 5.1 interconnection mining). All additive —
    # empty/None on rows persisted before the re-derivation.
    #
    # `affects` is the multi-value, cross-pillar subcap set this card
    # touches (the modal's affects chips → heatmap navigation). The
    # legacy single `linked_subcap_id` stays the anchor.
    affects: list[str] = Field(default_factory=list)
    # Implicated platform_ids — card platform badge + "Linked" tab.
    platforms: list[str] = Field(default_factory=list)
    # Mined links [{kind, target_id, note, e_ids}]: counter-evidence,
    # related recs, tech-stack absences, sibling cards sharing evidence.
    interconnections: list[dict] = Field(default_factory=list)
    # Short classification label for grouping/filters (e.g. "Data
    # foundations"). None until re-derivation fills it.
    theme: str | None = None
    # Presentation twins of the offline pack patcher (_enrich_insights):
    # pure functions of linked_subcap_id / severity computed with the SAME
    # startup_enrich helpers. Serving them keeps qa_pack_parity's key-set
    # diff clean against the patched pack (2026-07-04: their absence was
    # 180 of 240 structural findings on a fresh regen DB) — the patcher's
    # fill-if-missing then becomes a no-op on freshly exported packs.
    pillar: str | None = None
    flag: Literal["CRITICAL", "OPPORTUNITY", "MONITOR"] | None = None


class InsightListResponse(BaseModel):
    entity_display_id: str
    run_request_id: str | None = None
    items: list[InsightCardOut]
    # Per-pillar deep-dive prose from the Assessment_Report DOCX, when
    # the DOCX was ingested. None = no DOCX → skeleton fallback in UI.
    narrative: dict | None = None


class EvidenceDrawerItem(BaseModel):
    id: str
    e_id: str
    source_name: str
    source_url: str | None = None
    excerpt: str
    claim_type: str
    # None = the source stated no canonical tier (honest-absent;
    # migration 059) — the UI renders an em-dash instead of an invented tier.
    tier: int | None = None
    # Age in months at ingest time (evidence_index.recency_months — column
    # has existed since migration 004 but was never served). Drives the
    # prototype's per-row recency string; the freshness badge stays the
    # published_date-derived band. Additive: None on older baked packs.
    recency_months: int | None = None
    published_date: str | None = None
    linked_subcap_ids: list[str] = Field(default_factory=list)


class EvidenceDrawerResponse(BaseModel):
    entity_display_id: str
    run_request_id: str | None = None
    filter_subcap_id: str | None = None
    filter_min_tier: int
    # Exact E-ID lookup echo (2026-07-06): set when the drawer was opened
    # from a citation click (?e_id=…) — None for scope-filtered loads.
    filter_e_id: str | None = None
    # E-IDs the opener cited (`?e_ids=` echo). Rows for these are unioned
    # into `items` regardless of subcap/tier filters. Additive — [] when
    # the drawer was opened without a citation list (incl. the baked pack).
    filter_e_ids: list[str] = Field(default_factory=list)
    items: list[EvidenceDrawerItem]
