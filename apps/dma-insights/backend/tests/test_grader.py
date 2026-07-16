"""L3 rubric grader (nlp/grader.py) — the measurable gold bar. A gold-shaped
insight card PASSES all HARD gates + the weighted bar; the template/misattributed/
out-of-scope/one-liner shapes FAIL the exact parameter with a repair hint the
refine loop consumes. Lexical tier (no torch) so the contract holds in CI.
"""
from __future__ import annotations

import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")

from app.services.nlp.entity_knowledge import Capability, EntityState
from app.services.nlp.grader import Item, grade
from app.services.nlp.knowledge import EntityKnowledge, Evidence


def _state() -> EntityState:
    evidence = [
        Evidence("E-mdm", "Master data management is fragmented across 4 core systems; there is no golden record, so the same customer appears differently in each.", tier=1, year=2026, owned=True),
        Evidence("E-peer", "Peer benchmark: FCSA reports a Net Promoter Score of 60, top of the cohort.", tier=2, year=2025, owned=False),
        Evidence("E-geo", "Geographic portfolio distribution: Indiana 22.3%, Ohio 19.7%.", tier=3, year=2024, owned=True),
    ]
    caps = [
        Capability("P4C1.4.1", "Master Data Management", 1.5, 3.0, -1.5, "P4", "P4C1",
                   "Master data is fragmented across 4 systems.", "T1", True, ["E-mdm"]),
        Capability("P2C3.2.IC1", "AI Claims Estimation", 1.0, 2.75, -1.75, "P2", "P2C3",
                   "", "T2", False, []),
    ]
    return EntityState(
        run_id="r", entity_id="e", name="Test Bank", subvertical="RB",
        catalog_version="v7.0", capabilities=caps, knowledge=EntityKnowledge(evidence),
        firmographics={}, platforms=[], tech_stack=[], scqa=None, top_findings=[],
        why_now_signals=[], na_subcap_ids=set(),
        _by_subcap={c.subcap_id: c for c in caps},
        _excerpt_by_eid={e.e_id: e.text for e in evidence},
        _catalogue_names={c.name.lower() for c in caps},
    )


def _gold_card() -> Item:
    return Item(
        surface="insight_card",
        title="Fragmented master data blocks the single customer view",
        what=("Master data management is fragmented across 4 core systems. "
              "The same customer is represented differently in each, so a "
              "unified golden record is the opportunity that unlocks a single "
              "customer view. That view is what every cross-sell play depends on."),
        why="The fragmentation caps the P2C4 cross-sell category and the P4C1 data foundation together.",
        so_what=("Deploy Salesforce Data Cloud to unify the 4 systems into one "
                 "golden record before the next core conversion."),
        anchor_subcap="P4C1.4.1", e_ids=["E-mdm"], is_top=True,
    )


def test_gold_card_passes() -> None:
    g = grade(_gold_card(), _state())
    assert g.passed, (g.hard_fails, g.repairs)
    assert not g.hard_fails
    assert g.grade >= 75


def test_out_of_scope_anchor_fails_g0() -> None:
    it = _gold_card()
    it.anchor_subcap = "P2C3.2.IC1"      # NA for a retail bank
    g = grade(it, _state())
    assert "G0" in g.hard_fails
    assert "out-of-scope" in g.repairs["G0"]


def test_bare_subcap_title_fails_g1() -> None:
    it = _gold_card()
    it.title = "Master Data Management"   # a bare catalogue label, not a thesis
    g = grade(it, _state())
    assert not g.weighted["G1"]
    assert "catalogue" in g.repairs["G1"]


def test_misattributed_citation_fails_g2() -> None:
    it = _gold_card()
    it.e_ids = ["E-geo"]                  # geography row, not master-data support
    g = grade(it, _state())
    assert "G2" in g.hard_fails


def test_template_oneliner_fails_multiple() -> None:
    it = Item(
        surface="insight_card",
        title="Master Data Management",
        what="Make Master Data Management a near-term focus for Test Bank.",
        why="", so_what="Make Master Data Management a near-term focus.",
        anchor_subcap="P4C1.4.1", e_ids=[], is_top=True,
    )
    g = grade(it, _state())
    assert not g.passed
    assert not g.weighted["G1"]            # bare label
    assert not g.weighted["G8"]            # template skeleton
    assert "C1" in g.hard_fails            # one-liner
    assert "G2" in g.hard_fails            # no evidence


def test_so_what_missing_system_fails_g4() -> None:
    it = _gold_card()
    it.so_what = "Improve the data foundation soon."   # no named system
    g = grade(it, _state())
    assert not g.weighted["G4"]
    assert "named-system" in g.repairs["G4"]
