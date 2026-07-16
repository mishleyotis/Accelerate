"""Pillar → offering router. Selects which Zennify offerings get D4 cards
for each pillar of an entity's run, using `ccg_offering_subcap_matrix`
counts per pillar.

Per the plan:
  - P1 (Strategy)    → strategy/governance offerings + GRC/risk data products
  - P2 (Engagement)  → Marketing Cloud, Service Cloud, Personalization data products
  - P3 (Operations)  → Intelligent Process Automation Suite + Compliance Surveillance
  - P4 (Data & AI)   → Data Cloud, Databricks, Alation/Collibra, Cybersecurity

The router never recommends an offering with zero matrix rows touching the
entity's gap profile.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OfferingSubcapLink:
    offering_id: str
    subcap_id: str
    pillar: str  # 'P1' | 'P2' | 'P3' | 'P4'


@dataclass
class GapSubcap:
    subcap_id: str
    pillar: str
    severity: str  # critical | high | medium | low
    gap_size: float  # target - current; > 0 means there is room to improve


@dataclass
class PillarRoutingResult:
    pillar: str
    offerings: list[str]  # ranked by total addressable gap


def route_offerings_per_pillar(
    *,
    catalogue_links: list[OfferingSubcapLink],
    entity_gaps: list[GapSubcap],
    pillars: tuple[str, ...] = ("P1", "P2", "P3", "P4"),
) -> list[PillarRoutingResult]:
    # Build {(pillar, offering_id): set of subcap_ids covered by both
    #                                catalogue + this entity's gap profile}
    coverage: dict[tuple[str, str], list[float]] = {}
    gaps_by_subcap = {g.subcap_id: g for g in entity_gaps if g.gap_size > 0}
    for link in catalogue_links:
        gap = gaps_by_subcap.get(link.subcap_id)
        if gap is None or gap.pillar != link.pillar:
            continue
        coverage.setdefault((link.pillar, link.offering_id), []).append(gap.gap_size)

    out: list[PillarRoutingResult] = []
    for pillar in pillars:
        candidates = [
            (off, sum(gaps))
            for (p, off), gaps in coverage.items()
            if p == pillar
        ]
        candidates.sort(key=lambda x: x[1], reverse=True)
        out.append(
            PillarRoutingResult(
                pillar=pillar, offerings=[off for off, _ in candidates]
            )
        )
    return out
