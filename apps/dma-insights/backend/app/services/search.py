"""Global quick-search service — the multi-surface palette behind the
TopBar ⌘K popover (prototype `chrome.jsx` SearchPopover).

The prototype searches three surfaces at once and routes every hit to a
real page:
  - entities  → /clients/{display_id}/overview
  - insights  → /clients/{entity}/insights?card={IC-id}
  - evidence  → /clients/{entity}/insights?evidence={E-id}

This pure helper turns raw DB rows (fetched by the router) into
ready-to-render hits with the kind, composed subtitle, route, and icon
the popover expects — so the frontend stays a thin renderer and the
shaping logic is unit-testable without a database. The router owns the
SQL + role scoping; everything here is deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass

# Per-surface caps mirror the prototype (entities 4, insights 3, evidence
# 3) so the popover never grows past a glanceable list.
ENTITY_LIMIT = 4
INSIGHT_LIMIT = 3
EVIDENCE_LIMIT = 3

# Human subvertical labels for the entity subtitle. Mirrors the frontend
# SUBVERTICAL_LABELS so a hit reads "Regional bank", never the raw "RB"
# code. Unknown / missing codes fall through to a generic label.
_SUBVERTICAL_LABEL: dict[str, str] = {
    "RB": "Regional bank",
    "CU": "Credit union",
    "CL": "Commercial lender",
    "FC": "Farm credit institution",
    "REIT": "REIT",
    "RIA": "Wealth / RIA firm",
    "AM": "Asset manager",
    "INSURANCE_CARRIER": "Insurance carrier",
    "INSURANCE_BROKER": "Insurance broker",
    "FINTECH_SAAS": "Fintech / SaaS",
}


@dataclass(frozen=True)
class SearchHit:
    """One ready-to-render search result row."""
    kind: str   # "entity" | "insight" | "evidence"
    title: str
    sub: str
    route: str
    icon: str


def subvertical_label(code: str | None) -> str:
    if not code:
        return "Financial institution"
    return _SUBVERTICAL_LABEL.get(code.upper(), "Financial institution")


def _entity_hit(display_id: str, name: str, subvertical: str | None) -> SearchHit:
    return SearchHit(
        kind="entity",
        title=name,
        sub=subvertical_label(subvertical),
        route=f"/clients/{display_id}/overview",
        icon="users",
    )


def _insight_hit(ic_id: str, title: str, severity: str | None, entity_display_id: str) -> SearchHit:
    flag = (severity or "").upper()
    return SearchHit(
        kind="insight",
        title=title or ic_id,
        sub=f"{ic_id} · {flag}" if flag else ic_id,
        route=f"/clients/{entity_display_id}/insights?card={ic_id}",
        icon="insight",
    )


def _evidence_hit(e_id: str, title: str, tier: str | None, entity_display_id: str) -> SearchHit:
    tier_s = (tier or "").upper()
    return SearchHit(
        kind="evidence",
        title=title or e_id,
        sub=f"{e_id} · {tier_s}" if tier_s else e_id,
        route=f"/clients/{entity_display_id}/insights?evidence={e_id}",
        icon="evidence",
    )


def build_search_results(
    entities: list[tuple[str, str, str | None]],
    insights: list[tuple[str, str, str | None, str]],
    evidence: list[tuple[str, str, str | None, str]],
) -> list[SearchHit]:
    """Compose the concatenated entity → insight → evidence hit list.

    Rows arrive already filtered + ordered by the router's SQL; this
    enforces the per-surface caps and the surface ordering the prototype
    renders (entities first, then insights, then evidence). Hits that
    can't route (a NULL entity join) are dropped so a row never points
    at a dead link.
    """
    hits: list[SearchHit] = []
    for display_id, name, subvertical in entities[:ENTITY_LIMIT]:
        if display_id and name:
            hits.append(_entity_hit(display_id, name, subvertical))
    for ic_id, title, severity, entity_display_id in insights[:INSIGHT_LIMIT]:
        if ic_id and entity_display_id:
            hits.append(_insight_hit(ic_id, title, severity, entity_display_id))
    for e_id, title, tier, entity_display_id in evidence[:EVIDENCE_LIMIT]:
        if e_id and entity_display_id:
            hits.append(_evidence_hit(e_id, title, tier, entity_display_id))
    return hits
