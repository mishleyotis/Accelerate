"""Value-chain clustering helpers.

The Capability Catalogue ships per-subvertical value-chain mappings
(catalogue tab "21_Value_Chain_Mapping" → `ccg_vc_mapping` table). Each
row pairs a sub-capability with one or more value-chain stages (e.g.
"Market", "Sales", "Back Office Ops, Compliance & Platform") for a
specific sub-vertical (RB, CU, CL, CIB, FC, AM, RIA, IC, IB).

This module is pure — given the (subcap_id, score, stages, l1_id) rows
loaded from the catalogue + scoring tables, it produces:

  - **Stage clusters**: a list of stages, each with the subcaps that
    land in it and the average score for that stage. This drives D3's
    `value_chain` view-mode bucketing.

  - **Capability clusters**: subcaps grouped by their parent capability
    (formerly "L1") so the heatmap's "capability zoom" can render
    consistent groups across the wireframe.

  - **Platform-area clusters**: subcaps grouped by their platform-area
    (formerly "L3"). The frontend renders these as user-friendly
    "platform area" labels, not "L3".

State-branch contract (per cluster):
  - subcap is missing a score → it still appears in the cluster
    (rendered as `—` by the UI) but is excluded from the average.
  - cluster has only-null scores → average is null (UI shows "—").
  - subcap is mapped to multiple stages → it appears in EACH stage's
    cluster (the UI shows it more than once on purpose so the AE sees
    the cross-stage involvement).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class SubcapForCluster:
    subcap_id: str
    score: float | None
    stages: list[str]                    # value-chain stages (zero or more)
    capability_id: str | None = None     # parent capability (formerly l1_id)
    capability_name: str | None = None
    platform_area_id: str | None = None  # formerly l3_id, kept ID for FK
    platform_area_name: str | None = None
    subcap_name: str | None = None


@dataclass
class StageCluster:
    stage: str
    subcap_ids: list[str] = field(default_factory=list)
    average_score: float | None = None
    cell_count: int = 0
    scored_cell_count: int = 0


@dataclass
class CapabilityCluster:
    capability_id: str
    capability_name: str
    subcap_ids: list[str] = field(default_factory=list)
    average_score: float | None = None


@dataclass
class PlatformAreaCluster:
    platform_area_id: str
    platform_area_name: str
    subcap_ids: list[str] = field(default_factory=list)
    average_score: float | None = None


def _avg(scores: list[float | None]) -> float | None:
    nums = [s for s in scores if s is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def cluster_by_stage(subcaps: Iterable[SubcapForCluster]) -> list[StageCluster]:
    """Group subcaps by value-chain stage. A subcap mapped to multiple
    stages contributes to each one independently."""
    buckets: dict[str, list[SubcapForCluster]] = {}
    for sc in subcaps:
        for stage in sc.stages:
            buckets.setdefault(stage, []).append(sc)
    out: list[StageCluster] = []
    for stage in sorted(buckets.keys()):
        members = buckets[stage]
        scores = [m.score for m in members]
        out.append(
            StageCluster(
                stage=stage,
                subcap_ids=sorted(m.subcap_id for m in members),
                average_score=_avg(scores),
                cell_count=len(members),
                scored_cell_count=sum(1 for s in scores if s is not None),
            )
        )
    return out


def cluster_by_capability(
    subcaps: Iterable[SubcapForCluster],
) -> list[CapabilityCluster]:
    """Group subcaps by their parent capability (the catalogue's
    capability layer — formerly called L1)."""
    buckets: dict[str, list[SubcapForCluster]] = {}
    names: dict[str, str] = {}
    for sc in subcaps:
        if sc.capability_id is None:
            continue
        buckets.setdefault(sc.capability_id, []).append(sc)
        names[sc.capability_id] = sc.capability_name or sc.capability_id
    out: list[CapabilityCluster] = []
    for cap_id in sorted(buckets.keys()):
        members = buckets[cap_id]
        out.append(
            CapabilityCluster(
                capability_id=cap_id,
                capability_name=names[cap_id],
                subcap_ids=sorted(m.subcap_id for m in members),
                average_score=_avg([m.score for m in members]),
            )
        )
    return out


def cluster_by_platform_area(
    subcaps: Iterable[SubcapForCluster],
) -> list[PlatformAreaCluster]:
    """Group subcaps by their platform area (the catalogue's platform
    layer — formerly called L3). Subcaps that span multiple platform
    areas appear once per area."""
    buckets: dict[str, list[SubcapForCluster]] = {}
    names: dict[str, str] = {}
    for sc in subcaps:
        if sc.platform_area_id is None:
            continue
        buckets.setdefault(sc.platform_area_id, []).append(sc)
        names[sc.platform_area_id] = sc.platform_area_name or sc.platform_area_id
    out: list[PlatformAreaCluster] = []
    for area_id in sorted(buckets.keys()):
        members = buckets[area_id]
        out.append(
            PlatformAreaCluster(
                platform_area_id=area_id,
                platform_area_name=names[area_id],
                subcap_ids=sorted(m.subcap_id for m in members),
                average_score=_avg([m.score for m in members]),
            )
        )
    return out
