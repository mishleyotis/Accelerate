"""Grader-compatible entity state built from the exported startup-data pack.

The L3 grader (``nlp.grader.grade``) and the Tab-09 rubric
(``nlp.rubric100.score_item``) normally read the DB-backed
``entity_knowledge.EntityState``. This module duck-types the same surface from
the 14 per-client JSON files in ``startup-data/clients/<display_id>/`` so the
graded QA instrument runs against the shipped pack with no database:

  * ``heatmap.json``   -> Capability rows (id, label, score, peer_median,
    peer_gap) with ``narrative.per_subcap_md`` as the rationale;
  * ``evidence.json``  -> ``knowledge.Evidence`` rows (cleaned excerpts,
    tiers, years, ownership) backing ``knowledge.challenge``;
  * ``overview.json``  -> entity name, why_now_signals, top_findings, and the
    pillar/overall score set used by consistency checks.

Attribute contract (everything ``grader.grade`` touches): ``in_scope()``,
``capability()``, ``capabilities``, ``catalogue_subcap_names``,
``evidence_excerpt()``, ``why_now_signals``, ``knowledge``.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from app.services.nlp.entity_knowledge import Capability
from app.services.nlp.evidence_hygiene import clean_excerpt
from app.services.nlp.knowledge import EntityKnowledge, Evidence, classify_owned

_TIER_RE = re.compile(r"T(\d+)")
_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _tier_rank(tier: object) -> int:
    m = _TIER_RE.search(str(tier or ""))
    return min(int(m.group(1)), 8) if m else 8


def _year_of(published: object) -> int | None:
    m = _YEAR_RE.search(str(published or ""))
    return int(m.group(0)) if m else None


@dataclass
class PackState:
    """Duck-typed EntityState over one exported pack client."""
    display_id: str
    name: str
    subvertical: str | None
    capabilities: list[Capability]
    knowledge: EntityKnowledge
    why_now_signals: list[dict]
    top_findings: list[dict]
    all_score_values: set[float]
    _excerpts: dict[str, str] = field(default_factory=dict)
    _caps_by_id: dict[str, Capability] = field(default_factory=dict)
    na_subcap_ids: set[str] = field(default_factory=set)

    def in_scope(self, subcap_id: str | None) -> bool:
        return subcap_id not in self.na_subcap_ids

    def capability(self, subcap_id: str | None) -> Capability | None:
        if not subcap_id:
            return None
        cap = self._caps_by_id.get(subcap_id)
        if cap is not None:
            return cap
        # category-level anchors ("P4C1") resolve to the widest-gap member cell
        prefix = str(subcap_id).split("_")[0].rstrip(".")
        members = [c for c in self.capabilities
                   if c.subcap_id.startswith(prefix + ".") or c.category == prefix]
        if not members:
            return None
        return min(members, key=lambda c: (c.peer_gap if c.peer_gap is not None else 0.0))

    def evidence_excerpt(self, e_id: str | None) -> str | None:
        return self._excerpts.get(e_id or "")

    @property
    def catalogue_subcap_names(self) -> set[str]:
        return {c.name.lower() for c in self.capabilities if c.name}


def _load(clients_dir: str, display_id: str, fname: str) -> dict:
    path = os.path.join(clients_dir, display_id, fname)
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    with open(path) as fh:
        return json.load(fh)


def _optional(clients_dir: str, display_id: str, fname: str) -> dict:
    try:
        return _load(clients_dir, display_id, fname)
    except FileNotFoundError:
        return {}


def load_pack_state(clients_dir: str, display_id: str) -> PackState:
    overview = _load(clients_dir, display_id, "overview.json")
    heatmap = _load(clients_dir, display_id, "heatmap.json")
    evidence = _load(clients_dir, display_id, "evidence.json")

    entity = overview.get("entity") or {}
    name = entity.get("name") or display_id
    per_subcap_md = ((heatmap.get("narrative") or {}).get("per_subcap_md")) or {}

    caps: list[Capability] = []
    score_values: set[float] = set()
    for cell in heatmap.get("cells") or []:
        cid = cell.get("id")
        if not cid:
            continue
        score = cell.get("score")
        peer_median = cell.get("peer_median")
        peer_gap = cell.get("peer_gap")
        if peer_gap is None and score is not None and peer_median is not None:
            peer_gap = round(score - peer_median, 2)
        for v in (score, peer_median):
            if isinstance(v, int | float):
                score_values.add(round(float(v), 2))
        if isinstance(peer_gap, int | float):
            score_values.add(round(abs(float(peer_gap)), 2))
        caps.append(Capability(
            subcap_id=cid,
            name=cell.get("label") or cid,
            score=float(score) if score is not None else 0.0,
            peer_median=peer_median,
            peer_gap=peer_gap,
            pillar=cid[:2],
            category=cid.split(".")[0],
            rationale=per_subcap_md.get(cid, "") or "",
            tier=None,
            in_scope=True,
            evidence_ids=list(cell.get("enrichment_evidence_ids") or []),
        ))

    excerpts: dict[str, str] = {}
    ev_rows: list[Evidence] = []
    caps_by_id = {c.subcap_id: c for c in caps}
    for item in evidence.get("items") or []:
        e_id = item.get("e_id")
        if not e_id:
            continue
        text = clean_excerpt(item.get("excerpt") or "") or (item.get("excerpt") or "")
        excerpts[e_id] = text
        ev_rows.append(Evidence(
            e_id=e_id, text=text, tier=_tier_rank(item.get("tier")),
            year=_year_of(item.get("published_date")),
            owned=classify_owned(text, entity_name=name),
        ))
        for sid in item.get("linked_subcap_ids") or []:
            cap = caps_by_id.get(sid)
            if cap is not None and e_id not in cap.evidence_ids:
                cap.evidence_ids.append(e_id)

    # category / pillar / value-chain aggregates are run-computed values a
    # narrative may legitimately quote (SCQA cites category scores and gaps)
    for agg in ("heatmap_category.json", "heatmap_pillar.json",
                "heatmap_value_chain.json"):
        for cell in _optional(clients_dir, display_id, agg).get("cells") or []:
            for k in ("score", "peer_median"):
                if isinstance(cell.get(k), int | float):
                    score_values.add(round(float(cell[k]), 2))
            if isinstance(cell.get("peer_gap"), int | float):
                score_values.add(round(abs(float(cell["peer_gap"])), 2))

    if isinstance(overview.get("overall_score"), int | float):
        score_values.add(round(float(overview["overall_score"]), 2))
    for row in overview.get("pillar_scores") or []:
        if isinstance(row, dict):
            for k in ("score", "peer_median"):
                if isinstance(row.get(k), int | float):
                    score_values.add(round(float(row[k]), 2))

    # A difference of two run values ("trails the median of 3.2 by 1.2")
    # is itself run-computed provenance — add bounded pairwise deltas.
    vals = sorted(score_values)
    for i, a in enumerate(vals):
        for b in vals[i + 1:]:
            delta = round(b - a, 2)
            if 0.05 <= delta <= 5.0:
                score_values.add(delta)
                score_values.add(round(delta, 1))

    return PackState(
        display_id=display_id,
        name=name,
        subvertical=entity.get("subvertical") or heatmap.get("subvertical"),
        capabilities=caps,
        knowledge=EntityKnowledge(ev_rows),
        why_now_signals=list(overview.get("why_now_signals") or []),
        top_findings=list(overview.get("top_findings") or []),
        all_score_values=score_values,
        _excerpts=excerpts,
        _caps_by_id=caps_by_id,
    )
