"""L3 composer + refine loop (nlp/composer.py, nlp/refine.py). The deterministic
composer must author a card that PASSES the grader from a well-evidenced anchor,
skip an unevidenced/NA anchor (return None), and the refine loop must return a
PASS via the deterministic path (no Gemini) for the well-evidenced case.
Lexical tier (no torch) so it holds in CI.
"""
from __future__ import annotations

import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")

from app.services.nlp.composer import compose_card
from app.services.nlp.entity_knowledge import Capability, EntityState
from app.services.nlp.grader import grade
from app.services.nlp.knowledge import EntityKnowledge, Evidence
from app.services.nlp.refine import refine_card


def _state() -> EntityState:
    evidence = [
        Evidence("E-mdm", "Master data management is fragmented across 4 core systems, so the same customer is represented differently in each of the bank's platforms.", tier=1, year=2026, owned=True),
        Evidence("E-cx", "The mobile banking experience is a single unified app with modern journeys.", tier=2, year=2026, owned=True),
    ]
    caps = [
        Capability("P4C1.4.1", "Master Data Management", 1.5, 3.0, -1.5, "P4", "P4C1",
                   "Master data management is fragmented across 4 core systems.", "T1", True, ["E-mdm"]),
        Capability("P2C2.1.1", "Digital Servicing Journeys", 3.0, 2.5, 0.5, "P2", "P2C2",
                   "The mobile experience is a unified modern app.", "T1", True, ["E-cx"]),
        Capability("P2C3.2.IC1", "AI Claims Estimation", 1.0, 2.75, -1.75, "P2", "P2C3",
                   "", "T2", False, []),   # NA / unevidenced
    ]
    platforms = [{"platform_id": "salesforce", "fit_score": 90.0, "readiness_index": "green",
                  "addressable_subcap_ids": ["P4C1.4.1"], "fit_breakdown": None, "sequence_rank": 1}]
    return EntityState(
        run_id="r", entity_id="e", name="Test Bank", subvertical="RB",
        catalog_version="v7.0", capabilities=caps, knowledge=EntityKnowledge(evidence),
        firmographics={}, platforms=platforms, tech_stack=[], scqa=None, top_findings=[],
        why_now_signals=[{"so_what": "Engage before the 2026 core conversion sets the roadmap."}],
        na_subcap_ids=set(),
        _by_subcap={c.subcap_id: c for c in caps},
        _excerpt_by_eid={e.e_id: e.text for e in evidence},
        _catalogue_names={c.name.lower() for c in caps},
    )


def test_composer_authors_a_passing_card() -> None:
    st = _state()
    cap = st._by_subcap["P4C1.4.1"]
    sib = st._by_subcap["P2C2.1.1"]
    item = compose_card(st, cap, siblings=[sib])
    assert item is not None
    g = grade(item, st)
    assert g.passed, (g.hard_fails, g.repairs)
    # thesis title, not the bare capability name
    assert item.title.lower() != "master data management"
    # grounded + support-checked
    assert item.e_ids == ["E-mdm"]


def test_composer_skips_unevidenced_na_anchor() -> None:
    st = _state()
    cap = st._by_subcap["P2C3.2.IC1"]
    assert compose_card(st, cap) is None


def test_refine_reaches_pass_deterministically() -> None:
    st = _state()
    cap = st._by_subcap["P4C1.4.1"]
    sib = st._by_subcap["P2C2.1.1"]
    item, g, telem = refine_card(st, cap, siblings=[sib])
    assert item is not None and g is not None
    assert g.passed, (g.hard_fails, g.repairs)
    assert telem["path"] == "deterministic"   # no Gemini needed


def test_refine_skips_unevidenced() -> None:
    st = _state()
    item, _g, telem = refine_card(st, st._by_subcap["P2C3.2.IC1"])
    assert item is None
    assert telem["skipped"] == "unevidenced_anchor"


def test_pick_fact_skips_person_roster_and_meta_prefers_topical() -> None:
    from app.services.nlp.composer import _pick_fact
    cap = Capability("P4C1.1.1", "Enterprise Data Strategy", 3.0, 2.0, 1.0, "P4",
                     "P4C1", "unified data platform strategy", "T1", True, ["E-x"])
    # a name + parenthetical + person-role lead is skipped
    person = "Carey (Stone Point Senior Principal) serves as a director of the firm."
    # an executive-title roster line is skipped
    roster = "Jennifer Martin is EVP Human Resources with 30 years of experience."
    # analyst-workflow meta is skipped
    meta = "2025 Annual Report released — to be fetched in next batch for scoring depth."
    # two capability facts: the data-strategy one must win on topical overlap
    off = "The bank operates a single unified mobile app for retail customers today."
    on = "The enterprise data platform provides one unified data strategy across the estate."
    got = _pick_fact([person, roster, meta, off, on], cap)
    assert "Carey" not in got and "EVP" not in got and "next batch" not in got
    assert "data" in got and "strategy" in got   # topical winner, not the mobile-app line


def test_pick_fact_first_usable_when_no_topical_overlap() -> None:
    from app.services.nlp.composer import _pick_fact
    cap = Capability("P9C9.9.9", "Quantum Ledger", 3.0, 2.0, 1.0, "P9", "P9C9",
                     "", "T1", True, ["E-x"])
    a = "The firm runs a modern payments rail across all regions."
    b = "The firm maintains a large branch network in three states."
    assert _pick_fact([a, b], cap) == a   # neither overlaps → first usable
