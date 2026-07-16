"""Schemas for entities, runs, dashboard, overview surfaces."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class TopPlatform(BaseModel):
    """Best-fit platform for an entity's latest run — the entity card's
    top-OSS chip ("SF 82"). Sourced from a LATERAL over `platform_scores`
    ORDER BY fit_score DESC LIMIT 1, so it is the single highest-fit
    platform area. `short` is the wireframe abbreviation (SF/DB/TBL/…)
    from `app.services.platform_display`."""
    platform_id: str
    short: str
    fit_score: float


class EntitySummary(BaseModel):
    id: str
    display_id: str
    name: str
    domain: str | None = None
    subvertical: str | None = None
    lobs: list[str] = Field(default_factory=list)
    status: Literal["ACTIVE", "ARCHIVED", "MERGED", "PENDING_REVIEW"]
    last_run_at: datetime | None = None
    last_run_request_id: str | None = None
    owner_email: EmailStr | None = None
    owner_name: str | None = None
    updated_at: datetime
    # Per-run summary fields the dashboard + directory cards render —
    # without these, every entity card showed empty pillar bars and a
    # generic "BUILDING" badge regardless of actual run state. Computed
    # over the latest run's `subcap_scores` (per-pillar mean) so the card
    # mirrors what the overview page shows for the same entity.
    last_run_status: str | None = None
    data_source: str | None = None
    in_progress: bool = False
    pillar_scores: dict[str, float] | None = None
    overall_score: float | None = None
    subcap_count: int | None = None
    # 2026-06-06 QA-M4: per-entity open alerts count. Pre-fix the
    # frontend Dashboard + Directory hard-coded `open_alerts: 0` for
    # every entity card, so the orange alert chip never appeared even
    # when the alerts table had open rows for that entity. Now sourced
    # from a LATERAL count(*) against `alerts WHERE closed_at IS NULL`
    # in the list endpoint -- defaults to 0 when no alerts exist.
    open_alerts: int = 0
    # Migration 039: latest run's official assessment date (directory
    # "sorted by date" + card date chips). NULL → consumers fall back to
    # last_run_at (the ingest completion timestamp).
    assessment_date: date | None = None
    # Prototype parity (2026-06-13): entity-card footer + Active-runs card.
    # `hq` is firmographics.hq_address (the " · HQ" suffix after the
    # subvertical label). `top_platform` is the best-fit platform chip.
    # `current_batch` is the coarse Setup→Final pill index (1..6) for an
    # IN_PROGRESS run, derived from the run/ops status; NULL for completed
    # runs (the Active-runs card only renders pills for in-progress runs).
    hq: str | None = None
    top_platform: TopPlatform | None = None
    current_batch: int | None = None

    model_config = ConfigDict(from_attributes=True)


class EntityListResponse(BaseModel):
    items: list[EntitySummary]
    total: int
    owner_filter: Literal["me", "all"]


class RunSummary(BaseModel):
    id: str
    request_id: str
    status: Literal["IN_PROGRESS", "ACTIVE", "SUPERSEDED", "STALE", "FAILED", "PENDING_REVIEW"]
    # Must mirror the CHECK constraint in alembic/versions/021_runs_drive_backfill.py.
    # 2026-05-29 audit: the schema previously rejected DRIVE_BACKFILL +
    # BOT_REQUEST that the writers (historical_backfill.py + bot loop)
    # actually persist — every dashboard/overview/runs response 500'd
    # for any historical-backfill run.
    data_source: Literal[
        "DRIVE_PARSE",
        "DRIVE_BACKFILL",
        "PROJECT_API",
        "MANUAL_BACKFILL",
        "BOT_REQUEST",
    ]
    evidence_mode: Literal["public", "hybrid"]
    ccg_catalog_version: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    # 2026-06-05 QA finding 8: ClientRunsPage renders a Score column.
    # Pre-fix the page cast `(r as { overall_score?: number }).overall_score`
    # against a RunSummary that didn't have the field -- every score
    # rendered as `—`. overall_score is the AVG(score) over subcap_scores
    # for the run, computed in the routers that build RunSummary (same
    # derivation as EntitySummary.overall_score).
    overall_score: float | None = None
    # 2026-06-09 prototype parity: the Runs table's 7th column is "Subcaps"
    # (the count of subcap_scores rows for the run), not the catalogue
    # version. COUNT(*) over the same subcap_scores join as overall_score.
    subcap_count: int | None = None
    # Migration 039 (QA 2026-06-11): the wireframe RUN DATE is the
    # assessment date, not the ingest wall-clock that started_at carries.
    # NULL for pre-039 REQ-hex rows the repair script couldn't derive —
    # consumers fall back to started_at and may flag the provenance via
    # assessment_date_source (run_manifest | run_id | package_manifest).
    assessment_date: date | None = None
    assessment_date_source: str | None = None

    model_config = ConfigDict(from_attributes=True)


class RunListResponse(BaseModel):
    items: list[RunSummary]
    active_run_id: str | None = None


class DashboardTile(BaseModel):
    kind: Literal[
        "active_runs",
        "my_clients",
        "open_alerts",
        "recent_completions",
        "data_health",
        "catalogue_version",
        # 2026-06-06 QA-M5: count of insight_cards bound to ACTIVE
        # runs. Frontend Dashboard KPI was reading data.insight_count
        # via cast; the field didn't exist, so the card always rendered
        # "—". Now backed by a real query on insight_cards.
        "insight_count",
        # 2026-06-13 prototype parity: the wireframe's 4-KPI strip is
        # [Active assessments / Open alerts / Insight cards / Avg maturity].
        # `assessment_count` = DISTINCT ACTIVE entities with an ACTIVE run;
        # `avg_maturity` = mean of per-entity latest-run overall (float).
        # Both were computed client-side before (a reduce over the entities
        # list) — moving them server-side makes the KPIs non-stale + the
        # startup-data snapshot match the live API exactly.
        "assessment_count",
        "avg_maturity",
    ]
    label: str
    # avg_maturity is a float (e.g. 2.64); the other kinds are int counts
    # or the catalogue version string.
    value: int | float | str
    delta: int | None = None
    last_refreshed_at: datetime


class DashboardResponse(BaseModel):
    scope: Literal["mine", "all"]
    tiles: list[DashboardTile]
    active_runs: list[RunSummary]


class EntityOverviewResponse(BaseModel):
    entity: EntitySummary
    run: RunSummary | None
    scqa: dict | None = None
    why_now_signals: list[dict] = Field(default_factory=list)
    top_findings: list[dict] = Field(default_factory=list)
    firmographics: dict | None = None
    pillar_scores: list[dict] = Field(default_factory=list)
    # `narrative` is None when no Assessment_Report DOCX is present.
    # When present, populated from document_sections via section_routing.
    narrative: dict | None = None
    # `evidence_freshness` is the per-entity rollup from
    # services/evidence_staleness.rollup_freshness — populated when
    # the entity has ≥1 evidence_index row.
    evidence_freshness: dict | None = None
    # `intelligence_profile` is the persistent per-customer rollup
    # surfaced as the "Persistent intelligence" card on D1.
    # None until customer_intelligence.recompute_profile has run.
    intelligence_profile: dict | None = None
    # `parser_warnings` from the most recent run on this entity. The
    # earlier UI hid parser_warnings inside Admin → Import Audit only
    # (which AEs can't access). Surfacing them on D1 lets the AE see
    # at-a-glance that "this run was parsed with N warnings" before
    # drawing conclusions from potentially incomplete data.
    # Shape: `{"<warning_key>": "<details>", ...}` — flat dict.
    # None when no warnings were emitted; absent in audience=customer
    # responses (stripped by audience_strip).
    parser_warnings: dict | None = None
    # `overall_score` is the weighted mean of pillar scores. Computed
    # server-side so the D1 ScoreRing has a deterministic value across
    # surfaces (directory card + overview ring + scorecard export
    # MUST agree). Computed even when pillar_scores has gaps so the
    # client can still render a single canonical number.
    overall_score: float | None = None
    # C11 (2026-06-07): analyst's assumptions register sourced from
    # the package (Calprivate JSON + Nicola CSV; other folders ship
    # nothing -> empty list). Persisted to `runs.assumptions_register`
    # JSONB (migration 030); the D1 ClientOverview "Assumptions"
    # footer card renders the rows so AE can answer "we assumed X
    # because Y" on sales calls.
    assumptions_register: list[dict] = Field(default_factory=list)
    # Migration 045 (Part 4.6 "Evidence & benchmarks" cards). All three
    # are run-scoped JSONB written by derive_evidence_surfaces; None
    # until the deriver has run — the frontend keeps honest-empty.
    #   evidence_summary  → EvidenceTierCard histogram
    #     {total_items, total_facts, tiers{T1..T8}, claims{}, signals{}}
    #   coverage_stats    → CoverageByPillarCard
    #     {overall_pct, by_pillar[{pillar, pct, subcaps, scored}], gate_pct}
    #   uncertainty_bands → CeilingEstimateCard (ceiling + band +
    #     modifiers/rationale composed from real facts)
    evidence_summary: dict | None = None
    coverage_stats: dict | None = None
    uncertainty_bands: dict | None = None
    # FinancialTrajectoryCard's normalized series {currency, unit, fy[],
    # series{...}, headline, events[]} — shaped by the shared financial
    # normalization engine (Part 4.6/8.4). None until derived.
    financial_trajectory: dict | None = None
    # SentimentCard's normalized shape {employee[], customer[],
    # industry_avg, b2b_b2c_gap} — distinct from the raw
    # firmographics.sentiment blob. None until derived. The card is
    # internal-audience only (frontend hides it on customer view).
    sentiment: dict | None = None
    # Source-misattribution badge — stamped by the shared contamination
    # twin (startup_enrich.apply_contamination_badge) on BOTH serve paths
    # (live route + offline pack patcher) so a confidently-wrong
    # assessment never renders unflagged and qa_pack_parity stays clean.
    # Shape: {source_misattribution: 'A'|'B', misattribution_markers:
    # {foreign_tickers[], foreign_runid_tokens[], foreign_entities[]}}.
    # None when the snapshot is clean.
    data_quality: dict | None = None
