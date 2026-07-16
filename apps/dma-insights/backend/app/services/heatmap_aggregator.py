"""Heatmap cell aggregation across the 4 zoom levels.

Plan §⑥ + UI/UX Brief: heatmap renders at 4 depths
  - pillar     (4 cells: P1..P4)
  - category   (16 cells: P1C1..P4C4)
  - capability (~136 cells: l1_id per category)
  - subcap     (~851 cells: subcap_id; T2 variants when toggled)

Pillar / category / capability cells aggregate child scores using the
simple mean (matches the wireframe's "average score" rule). Subcap cells
are leaf and emit raw scores.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SubcapInput:
    subcap_id: str
    score: float
    band: str
    peer_median: float | None
    peer_gap: float | None
    is_thin_evidence: bool
    cap_applied: bool
    cap_reason: str | None
    aliased_from: str | None
    # parent linkage from CatalogueResolver
    pillar_id: str          # 'P1' ... 'P4'
    category_id: str        # 'P1C1' ...
    l1_id: str              # 'P1C1::strategy-vision' etc.
    # display labels
    pillar_name: str = ""
    category_name: str = ""
    l1_name: str = ""
    subcap_name: str = ""
    # Batch 3 (2026-06-07): data_source surfaces the shallow-broadcast
    # disclosure on the heatmap cell. Default 'direct' so legacy
    # call-sites unchanged.
    data_source: str = "direct"
    parent_category_id: str | None = None


@dataclass
class AggregatedCell:
    id: str
    label: str
    parent_id: str | None
    score: float | None
    band: str | None
    peer_median: float | None
    peer_gap: float | None
    is_thin_evidence: bool
    cap_applied: bool
    cap_reason: str | None
    issue_count: int
    aliased_from: str | None
    # Batch 3 (2026-06-07): aggregated data_source. When at subcap
    # zoom, mirrors the source row. When aggregating up, takes the
    # "worst" available source label: any 'shallow_broadcast' child
    # makes the parent 'shallow_broadcast' so the UI disclosure
    # propagates through pillar/category zoom levels.
    data_source: str = "direct"
    parent_category_id: str | None = None


def _score_to_band(score: float) -> str:
    if score >= 4.5:
        return "M5"
    if score >= 3.5:
        return "M4"
    if score >= 2.5:
        return "M3"
    if score >= 1.5:
        return "M2"
    return "M1"


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


@dataclass
class AggregateResult:
    cells: list[AggregatedCell] = field(default_factory=list)


def aggregate_for_zoom(
    subcaps: list[SubcapInput],
    zoom: str,
    *,
    issue_counts_by_subcap: dict[str, int] | None = None,
) -> AggregateResult:
    issue_counts = issue_counts_by_subcap or {}
    if zoom == "subcap":
        return _zoom_subcap(subcaps, issue_counts)
    if zoom == "capability":
        return _zoom_group(subcaps, issue_counts, group_key="l1")
    if zoom == "category":
        return _zoom_group(subcaps, issue_counts, group_key="category")
    if zoom == "pillar":
        return _zoom_group(subcaps, issue_counts, group_key="pillar")
    raise ValueError(f"unknown zoom: {zoom}")


def _zoom_subcap(
    subcaps: list[SubcapInput], issue_counts: dict[str, int]
) -> AggregateResult:
    cells = [
        AggregatedCell(
            id=s.subcap_id,
            label=s.subcap_name or s.subcap_id,
            parent_id=s.l1_id,
            score=s.score,
            band=s.band,
            peer_median=s.peer_median,
            peer_gap=s.peer_gap,
            is_thin_evidence=s.is_thin_evidence,
            cap_applied=s.cap_applied,
            cap_reason=s.cap_reason,
            issue_count=issue_counts.get(s.subcap_id, 0),
            aliased_from=s.aliased_from,
            data_source=s.data_source,
            parent_category_id=s.parent_category_id,
        )
        for s in subcaps
    ]
    cells.sort(key=lambda c: c.id)
    return AggregateResult(cells=cells)


def _aggregate_data_source(kids: list[SubcapInput]) -> tuple[str, str | None]:
    """Roll up data_source for a group of kids.

    Precedence (worst-wins so the UI disclosure propagates up):
      heuristic_fallback > shallow_broadcast > llm_extracted > direct.

    Returns (data_source, parent_category_id). parent_category_id is
    set only when ALL kids share the same parent (typical when a
    single category-level row was broadcast).
    """
    sources = {k.data_source for k in kids}
    if "heuristic_fallback" in sources:
        ds = "heuristic_fallback"
    elif "shallow_broadcast" in sources:
        ds = "shallow_broadcast"
    elif "llm_extracted" in sources:
        ds = "llm_extracted"
    else:
        ds = "direct"
    parent_cats = {
        k.parent_category_id for k in kids if k.parent_category_id
    }
    pcat = (parent_cats.pop() if len(parent_cats) == 1 else None)
    return ds, pcat


def _zoom_group(
    subcaps: list[SubcapInput],
    issue_counts: dict[str, int],
    *,
    group_key: str,
) -> AggregateResult:
    buckets: dict[str, list[SubcapInput]] = {}
    parent_of: dict[str, str | None] = {}
    label_of: dict[str, str] = {}
    for s in subcaps:
        if group_key == "pillar":
            key, parent, label = s.pillar_id, None, s.pillar_name or s.pillar_id
        elif group_key == "category":
            key, parent, label = s.category_id, s.pillar_id, s.category_name or s.category_id
        else:  # l1
            key, parent, label = s.l1_id, s.category_id, s.l1_name or s.l1_id
        buckets.setdefault(key, []).append(s)
        parent_of[key] = parent
        label_of[key] = label

    cells = []
    for key, kids in buckets.items():
        scores = [k.score for k in kids if k.score is not None]
        peers = [k.peer_median for k in kids if k.peer_median is not None]
        avg = _avg(scores)
        avg_peer = _avg(peers)
        agg_ds, agg_pcat = _aggregate_data_source(kids)
        cells.append(
            AggregatedCell(
                id=key,
                label=label_of[key],
                parent_id=parent_of[key],
                score=avg,
                band=_score_to_band(avg) if avg is not None else None,
                peer_median=avg_peer,
                peer_gap=(round(avg - avg_peer, 2) if avg is not None and avg_peer is not None else None),
                is_thin_evidence=any(k.is_thin_evidence for k in kids),
                cap_applied=any(k.cap_applied for k in kids),
                cap_reason=None,
                issue_count=sum(issue_counts.get(k.subcap_id, 0) for k in kids),
                aliased_from=None,
                data_source=agg_ds,
                parent_category_id=agg_pcat,
            )
        )
    cells.sort(key=lambda c: c.id)
    return AggregateResult(cells=cells)
