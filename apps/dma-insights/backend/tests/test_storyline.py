"""L4 storyline spine (nlp/storyline.derive_thesis). The per-client thesis is
DERIVED from that client's own dominant signals — the analyst's scqa when
present, else competitor footholds / M&A intensity / dominant gap-strength
pillar. Different inputs must yield different theses (never one global shape).
"""
from __future__ import annotations

import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")

from app.services.nlp.entity_knowledge import Capability, EntityState
from app.services.nlp.knowledge import EntityKnowledge, Evidence
from app.services.nlp.storyline import derive_thesis


def _state(*, caps, tech_stack=None, firmographics=None, scqa=None,
           subvertical="RB") -> EntityState:
    evidence = [Evidence(f"E-{i}", f"Grounded fact number {i} about the estate and its systems.",
                         tier=1, year=2026, owned=True) for i in range(1, 5)]
    return EntityState(
        run_id="r", entity_id="e", name="Test Bank", subvertical=subvertical,
        catalog_version="v7.0", capabilities=caps, knowledge=EntityKnowledge(evidence),
        firmographics=firmographics or {}, platforms=[], tech_stack=tech_stack or [],
        scqa=scqa, top_findings=[], why_now_signals=[], na_subcap_ids=set(),
        _by_subcap={c.subcap_id: c for c in caps},
        _excerpt_by_eid={e.e_id: e.text for e in evidence},
        _catalogue_names={c.name.lower() for c in caps})


def _cap(sid, pillar, score, gap, ev=("E-1",)):
    return Capability(sid, f"Cap {sid}", score, score - gap, gap, pillar,
                      sid.rsplit(".", 2)[0], f"rationale for {sid}", "T1", True, list(ev))


def test_analyst_scqa_is_the_preferred_spine() -> None:
    caps = [_cap("P4C1.1.1", "P4", 2.0, -1.0)]
    th = derive_thesis(_state(caps=caps, scqa={
        "answer": "An 18-month, 3-phase platform consolidation roadmap advances the "
                  "client from 3.05 to 3.5+ maturity via MuleSoft then Data Cloud."}))
    assert th.kind == "analyst"
    assert "18-month" in th.headline and th.signals["source"] == "scqa"


def test_competitor_foothold_yields_defense_thesis() -> None:
    # a REAL Salesforce competitor (ServiceNow) + a customer-facing gap; nCino is
    # a Salesforce ISV (runs ON SF) and cores like Fiserv are not CRM rivals, so
    # neither triggers defense — the de-skew that dropped 85/95 -> a real signal.
    caps = [_cap("P4C2.1.1", "P4", 3.5, 1.0), _cap("P2C1.1.1", "P2", 2.0, -1.0)]
    th = derive_thesis(_state(caps=caps, tech_stack=["ServiceNow", "nCino", "Salesforce"]))
    assert th.kind == "competitive_defense"
    assert "ServiceNow" in th.headline and "nCino" not in th.headline


def test_many_acquisitions_yields_post_ma_thesis() -> None:
    caps = [_cap("P4C1.1.1", "P4", 2.5, -0.5)]
    firm = {"narrative_md": "The firm grew through acquisition after acquisition; "
            "an M&A strategy of 59 acquisitions built the platform via merger."}
    th = derive_thesis(_state(caps=caps, firmographics=firm))
    assert th.kind == "post_ma"
    assert "unify" in th.headline.lower()


def test_data_gap_pillar_yields_greenfield_thesis() -> None:
    caps = [_cap("P4C1.1.1", "P4", 1.5, -1.5), _cap("P4C2.1.1", "P4", 2.0, -1.0)]
    th = derive_thesis(_state(caps=caps))
    assert th.kind == "greenfield_lob"
    assert "data and technology" in th.headline


def test_strength_dominant_yields_expand_thesis() -> None:
    caps = [_cap("P2C1.1.1", "P2", 4.0, 1.5), _cap("P2C2.1.1", "P2", 3.8, 1.0),
            _cap("P1C1.1.1", "P1", 3.0, 0.5)]
    th = derive_thesis(_state(caps=caps))
    assert th.kind == "expand_strength"


def test_theses_are_distinct_across_clients() -> None:
    a = derive_thesis(_state(caps=[_cap("P4C1.1.1", "P4", 1.5, -1.5)]))
    b = derive_thesis(_state(caps=[_cap("P2C1.1.1", "P2", 4.0, 1.5)],
                             tech_stack=["ServiceNow"]))
    assert a.kind != b.kind and a.headline != b.headline
