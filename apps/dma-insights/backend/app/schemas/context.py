"""D5 Context + Tech stack schemas."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class TimelineEventOut(BaseModel):
    id: str
    event_date: date
    kind: str
    title: str
    body: str | None = None
    source_url: str | None = None
    e_id: str | None = None
    # Migration 047 (Part 8.2 NLP event pipeline). All additive — None/
    # empty on rows persisted before the re-derivation.
    #
    # Polarity-classified event signal (native to the claim, not
    # inferred from kind) — drives the dot colour on the timeline.
    signal: str | None = None
    # day | month | quarter | year | publish_fallback — the frontend
    # jitters/clusters dots by precision so fallback-date pile-ups
    # stop reading as real same-day bursts.
    date_precision: str | None = None
    # Multi-value evidence anchors; supersedes the scalar `e_id` (kept
    # for compatibility) once populated.
    evidence_e_ids: list[str] = Field(default_factory=list)
    # Capability links for the EventDetail cap-impact chips.
    subcap_ids: list[str] = Field(default_factory=list)


class IssueRegisterOut(BaseModel):
    """One ingested `issue_register` row, surfaced on the D5 Context issue
    Gantt (wireframe `InteractiveGantt` / `IssueDetail`). `status` is derived
    from `resolved_on` so the frontend can colour OPEN vs RESOLVED bars without
    a second query."""

    id: str
    issue_id: str
    title: str
    severity: str
    rationale: str | None = None
    opened_on: date | None = None
    resolved_on: date | None = None
    status: Literal["OPEN", "RESOLVED"] = "OPEN"
    linked_subcap_ids: list[str] = Field(default_factory=list)
    # Evidence anchors mined at read time from the rationale's inline
    # [E-###] citations (2026-07-06) — lets IssueDetail / the regulatory
    # enforcement drilldown open the exact evidence rows the issue text
    # quotes. [] when the rationale cites nothing; additive, never
    # fabricated.
    evidence_e_ids: list[str] = Field(default_factory=list)
    # ── DMA-impact attribution (2026-07-06, additive — old packs keep
    # rendering). `kind` is always 'client' on this AE-facing DTO (the
    # router filters assessment-QA rows out) but is carried so exports
    # stay self-describing; `dma_impact` is the one-line grounded
    # attribution composed from the row's own fields; `caps` maps
    # P-codes to the cap level the issue imposes ("P1C2" → 3.0 renders
    # as a "P1C2 @ M3.0" chip).
    kind: str = "client"
    dma_impact: str | None = None
    caps: dict[str, float] = Field(default_factory=dict)


class AcquisitionOut(BaseModel):
    """One acquisition/M&A event for the D5 Context acquisitions panel,
    derived from `timeline_events` rows whose `kind = 'acquisition'`.

    The frame fields (Part 8.3) are all Optional — the acquisition NER
    rewrite fills them from the acquirer+target frame; legacy rows keep
    only the title/body/e_id shape and the panel degrades gracefully.
    """

    id: str
    event_date: date
    title: str
    body: str | None = None
    source_url: str | None = None
    e_id: str | None = None
    # Structured acquisition frame (prototype ACQ shape). `status` is
    # one of announced | closed | integrating when present; `amount`
    # is the verbatim deal size string (e.g. "$50M") — no fabricated
    # normalization.
    target: str | None = None
    acquirer: str | None = None
    amount: str | None = None
    status: str | None = None
    announced_on: date | None = None
    closed_on: date | None = None
    details: str | None = None


class ContextResponse(BaseModel):
    entity_display_id: str
    run_request_id: str | None = None
    timeline_events: list[TimelineEventOut] = Field(default_factory=list)
    # B-2: ingested issue register (already persisted via package_persist) —
    # surfaced first-class for the D5 issue Gantt.
    issue_register: list[IssueRegisterOut] = Field(default_factory=list)
    # B-4: acquisitions derived from timeline_events kind='acquisition'.
    acquisitions: list[AcquisitionOut] = Field(default_factory=list)
    firmographics: dict | None = None  # already audience-stripped server-side
    # B-3: multi-year financial series ({years, series}) lifted from the
    # firmographics.financial_highlights JSONB when present. None → skeleton.
    financials: dict | None = None
    sentiment: dict | None = None
    # Individual peer roster — named comparators + per-category scores + overall
    # (grounded in 06_peers). Best-effort; empty when the package ships none.
    peers: list[dict] = Field(default_factory=list)
    # `narrative` carries trend-analysis + issue-register prose when the
    # Assessment_Report DOCX was ingested. None otherwise → skeleton.
    narrative: dict | None = None


class TechStackEntryOut(BaseModel):
    id: str
    tech_id: str
    vendor: str
    product: str
    # Prototype alias for `product` (the product distinct from the vendor) +
    # the platform link. `status` is the honest 4-state read-model enum
    # (Part 9.1): CONFIRMED (deployment asserted by the source inventory OR
    # T1-T3 evidence), INFERRED (technographic/job/press detection without
    # confirming evidence), CLAIMED (only T4-T5 marketing-tier evidence),
    # ABSENT (server-generated scored-platform-family gap row), plus
    # CONFIRMED_REMOVED (decommissioned). Stored DETECTED rows are mapped at
    # the boundary in services/techstack_read.derive_status.
    product_name: str
    layer: Literal["foundation", "platform", "application", "intelligence"]
    status: Literal[
        "CONFIRMED", "INFERRED", "CLAIMED", "ABSENT", "CONFIRMED_REMOVED",
    ]
    l3_id: str | None = None
    source: str
    evidence_e_ids: list[str] = Field(default_factory=list)
    linked_subcap_ids: list[str] = Field(default_factory=list)
    # NULL for synthesized ABSENT gap rows (nothing was ever detected).
    detected_at: datetime | None = None
    # ── Part 9 prototype fields (all derived read-side, never fabricated) ──
    # Real deployment date mined via nlp.dates from the detection evidence
    # text ("2023-04" / "2025-Q3" / "2021"). None when the evidence carries
    # no date — the UI then labels the ingest timestamp "Detected", not
    # "Since".
    since: str | None = None
    # Clean one-line descriptor composed from real fields (product,
    # evidence count, addressable subcaps) — never the raw source cell.
    note: str | None = None
    # Share of cohort entities (same subvertical when the cohort has tech
    # data, else the whole corpus) carrying the same canonical tech/family.
    peer_coverage: float | None = None
    # True on ABSENT gap rows whose platform family addresses scored
    # sub-capabilities in the active run (catalogue-grounded).
    primary_gap: bool = False
    # Prototype layer ladder L1-L5. L1 Strategy is restored where the
    # catalogue implies it (dominant linked-subcap pillar = P1); otherwise
    # the stored layer maps L2-L5 (Operations / Customer / Data / Infra).
    layer_code: str | None = None
    layer_full: str | None = None
    dma_pillar: str | None = None


class TechStackResponse(BaseModel):
    entity_display_id: str
    items: list[TechStackEntryOut]
    last_synced_at: datetime | None = None
    # Taxonomy triage (Part 9.1): engineering signals (languages/frameworks/
    # OS — proof the entity builds software, NOT platform rows) and the
    # unknown-vendor review queue are persisted but excluded from `items`.
    engineering_signal_count: int = 0
    engineering_signals: list[str] = Field(default_factory=list)
    review_queue_count: int = 0


class TechPeerDeployment(BaseModel):
    """One named cohort peer for the detail page's peer-deployment card."""

    name: str
    has_tech: bool


class TechSubcapImpact(BaseModel):
    """One addressed sub-capability with its real run score — the grounded
    replacement for the wireframe's fabricated baseline→target deltas."""

    subcap_id: str
    name: str | None = None
    score: float | None = None
    peer_median: float | None = None
    thin: bool = False


class TechStackDetailResponse(BaseModel):
    entry: TechStackEntryOut
    linked_subcap_ids: list[str]
    evidence_e_ids: list[str]
    peer_adoption_count: int
    # Part 9 detail extras — cohort share + named peers (real cohort
    # entities with an adoption flag), per-subcap impact rows, and the
    # grounded gap-zone bullets for ABSENT rows.
    peer_coverage: float | None = None
    cohort_size: int | None = None
    cohort_label: str | None = None
    peer_names: list[TechPeerDeployment] = Field(default_factory=list)
    impacts: list[TechSubcapImpact] = Field(default_factory=list)
    gap_zones: list[str] = Field(default_factory=list)
