"""Pure-logic helpers for the cross_entity_patterns worker.

A "pattern" = a sub-capability that recurs across >= `min_entities` entities
of the same subvertical+catalogue cohort, from two signals:
  - subcap_gap:  >= N entities score BELOW their peer median on that subcap
                 (`subcap_scores.peer_gap < 0`).
  - issue_theme: >= N entities have an OPEN issue touching that subcap
                 (`issue_register`, `resolved_on IS NULL`).

State transitions:
  cohort entities < min_entities
    → a single "insufficient_data" marker (entity_count=N, affected=all);
      the endpoint renders the honest "needs >= N cohort entities" state.
  no recurring subcap
    → [] (honest empty — the tab shows the contextual empty state).
  a subcap that is both a recurring gap AND a recurring issue
    → two rows (distinct pattern_type), keyed by the same subcap_id.

Pure-logic only. Live DB IO is in live.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median


@dataclass(frozen=True)
class GapRow:
    entity_id: str
    subcap_id: str
    peer_gap: float


@dataclass(frozen=True)
class IssueRow:
    entity_id: str
    subcap_id: str
    severity: str


@dataclass
class Pattern:
    pattern_type: str            # subcap_gap | issue_theme | insufficient_data
    pattern_key: str
    pattern_label: str
    primary_subcap_id: str | None
    entity_count: int
    affected_entity_ids: list[str]
    severity_mix: dict[str, int] = field(default_factory=dict)
    median_peer_gap: float | None = None
    sample_subcap_ids: list[str] = field(default_factory=list)


def _name(names: dict[str, str], subcap_id: str) -> str:
    return names.get(subcap_id) or subcap_id


def compute_patterns(
    *,
    entity_ids: set[str],
    gaps: list[GapRow],
    issues: list[IssueRow],
    names: dict[str, str] | None = None,
    min_entities: int = 3,
) -> list[Pattern]:
    """End-to-end pure pipeline → 0..N Pattern rows ready to persist."""
    names = names or {}
    cohort_n = len(entity_ids)
    if cohort_n < min_entities:
        return [
            Pattern(
                pattern_type="insufficient_data",
                pattern_key="cohort",
                pattern_label=(
                    f"Insufficient cohort — {cohort_n} of "
                    f">= {min_entities} entities"
                ),
                primary_subcap_id=None,
                entity_count=cohort_n,
                affected_entity_ids=sorted(entity_ids),
            )
        ]

    out: list[Pattern] = []

    # ── subcap_gap: entities scoring below peer median, per subcap ──────────
    gap_by_subcap: dict[str, dict[str, float]] = {}
    for g in gaps:
        if g.peer_gap < 0 and g.entity_id in entity_ids:
            cur = gap_by_subcap.setdefault(g.subcap_id, {})
            # keep the most-negative gap per (subcap, entity)
            if g.entity_id not in cur or g.peer_gap < cur[g.entity_id]:
                cur[g.entity_id] = g.peer_gap
    for subcap_id in sorted(gap_by_subcap):
        ents = gap_by_subcap[subcap_id]
        if len(ents) >= min_entities:
            out.append(Pattern(
                pattern_type="subcap_gap",
                pattern_key=subcap_id,
                pattern_label=(
                    f"{_name(names, subcap_id)} — below peer median in "
                    f"{len(ents)} entities"
                ),
                primary_subcap_id=subcap_id,
                entity_count=len(ents),
                affected_entity_ids=sorted(ents),
                median_peer_gap=round(median(ents.values()), 2),
                sample_subcap_ids=[subcap_id],
            ))

    # ── issue_theme: entities with an OPEN issue touching the subcap ────────
    issue_by_subcap: dict[str, dict[str, list[str]]] = {}
    for i in issues:
        if i.entity_id in entity_ids:
            sev = (i.severity or "").strip().lower() or "unknown"
            issue_by_subcap.setdefault(i.subcap_id, {}).setdefault(
                i.entity_id, []).append(sev)
    for subcap_id in sorted(issue_by_subcap):
        ents = issue_by_subcap[subcap_id]
        if len(ents) >= min_entities:
            sev_mix: dict[str, int] = {}
            for sevs in ents.values():
                for s in sevs:
                    sev_mix[s] = sev_mix.get(s, 0) + 1
            out.append(Pattern(
                pattern_type="issue_theme",
                pattern_key=subcap_id,
                pattern_label=(
                    f"{_name(names, subcap_id)} — open issues in "
                    f"{len(ents)} entities"
                ),
                primary_subcap_id=subcap_id,
                entity_count=len(ents),
                affected_entity_ids=sorted(ents),
                severity_mix=sev_mix,
                sample_subcap_ids=[subcap_id],
            ))

    return out
