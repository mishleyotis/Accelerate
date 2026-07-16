"""D3 Heatmap response schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ZoomLevel = Literal["pillar", "category", "capability", "subcap"]
ViewMode = Literal["standard", "focus", "value_chain"]


class HeatmapCell(BaseModel):
    """One renderable cell.

    `id` shape depends on zoom level:
      - pillar      → "P1" .. "P4"
      - category    → "P1C1"
      - capability  → "P1C1::strategy-vision" (l1_id)
      - subcap      → "P1C1.1.1" (canonical, post-alias) or "P1C1.1.1-T2-RB"
    """
    id: str
    label: str
    parent_id: str | None = None
    score: float | None = None
    band: str | None = None
    peer_median: float | None = None
    peer_gap: float | None = None
    is_thin_evidence: bool = False
    cap_applied: bool = False
    cap_reason: str | None = None
    issue_count: int = 0
    aliased_from: str | None = None  # set when CatalogueResolver bridged the id
    # AI enrichment flag (set when the cell has an active `ai_enrichments`
    # row joined on subcap_id). Drives the "AI" pill the heatmap renders
    # in the cell corner. evidence_ids are the E-IDs that grounded the
    # enrichment (so the EvidenceDrawer can show them).
    has_enrichment: bool = False
    enrichment_evidence_ids: list[str] = Field(default_factory=list)
    # Batch 3 (2026-06-07): data_source flags how this cell's score
    # was sourced. Values:
    #   `direct`            -- scoring workbook emitted this subcap directly
    #   `shallow_broadcast` -- score broadcast from a category-level row
    #                          via the catalogue_alias_bridge; UI shows
    #                          "broadcast from {parent_category_id}"
    #                          disclosure on the cell.
    #   `llm_extracted`     -- subcap_narrative_extractor pulled this from
    #                          the pillar deep-dive DOCX section.
    #   `heuristic_fallback` -- LLM unavailable; template-fill.
    # `parent_category_id` is populated only when data_source ==
    # 'shallow_broadcast' and points to the category whose score we
    # inherited.
    data_source: str = "direct"
    parent_category_id: str | None = None


class ValueChainBucket(BaseModel):
    """value_chain mode groups cells by value-chain stage(s) per subvertical."""
    stage: str
    cell_ids: list[str]


class HeatmapResponse(BaseModel):
    entity_display_id: str
    run_request_id: str | None = None
    # `run_status` lets the FE differentiate ACTIVE / PENDING_REVIEW /
    # IN_PROGRESS so the empty-state can point operators at the right
    # remediation (load catalogue, wait for bot, etc.).
    run_status: str | None = None
    zoom: ZoomLevel
    view_mode: ViewMode
    subvertical: str | None = None
    peer_overlay: bool
    issue_overlay: bool
    cells: list[HeatmapCell]
    value_chain_buckets: list[ValueChainBucket] = Field(default_factory=list)
    catalogue_version: str
    warnings: list[str] = Field(default_factory=list)
    # `narrative` is None when no Assessment_Report DOCX was ingested.
    narrative: dict | None = None
