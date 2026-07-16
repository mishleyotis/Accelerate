"""Other-surface composers (nlp/composer.py) — findings (Surface 2), platform
(Surface 9), why-now (Surface 11). All read the same EntityState as the cards,
are graded by the same rubric, and must be thesis-first / support-checked. A
platform that addresses no in-scope evidenced anchor earns no card.
"""
from __future__ import annotations

import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")

from app.services.nlp.composer import (
    compose_exec,
    compose_findings,
    compose_platform,
    compose_why_now,
)
from app.services.nlp.entity_knowledge import Capability, EntityState
from app.services.nlp.grader import grade
from app.services.nlp.knowledge import EntityKnowledge, Evidence
from app.services.nlp.storyline import derive_thesis


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
    ]
    platforms = [
        # addresses a real in-scope evidenced anchor → earns a card
        {"platform_id": "salesforce", "fit_score": 90.0, "readiness_index": "green",
         "addressable_subcap_ids": ["P4C1.4.1"], "fit_breakdown": None, "sequence_rank": 1},
        # addresses only a subcap with no evidenced anchor → must be dropped
        {"platform_id": "ncino", "fit_score": 80.0, "readiness_index": "amber",
         "addressable_subcap_ids": ["P9C9.9.9"], "fit_breakdown": None, "sequence_rank": 2},
    ]
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


def test_compose_findings_thesis_first_and_graded() -> None:
    st = _state()
    findings = compose_findings(st, k=4)
    assert findings, "expected findings from evidenced anchors"
    names = {c.name.lower() for c in st.capabilities}
    leads = set()
    for f in findings:
        assert f.surface == "finding"
        assert f.title.lower() not in names          # thesis, not the bare label
        assert grade(f, st).passed, (f.title, grade(f, st).hard_fails)
        leads.add(f.what[:60].lower())
    assert len(leads) == len(findings)               # deduped by lead fact


def test_compose_platform_drops_platform_with_no_evidenced_anchor() -> None:
    st = _state()
    cards = compose_platform(st, k=5)
    assert cards, "salesforce addresses P4C1.4.1 → one platform card"
    # ncino addresses only P9C9.9.9 (no evidenced anchor) → never emitted
    assert all("ncino" not in c.title.lower() for c in cards)
    assert cards[0].surface == "platform"
    assert "Salesforce" in cards[0].title
    assert grade(cards[0], st).passed


def test_compose_why_now_is_time_bound() -> None:
    st = _state()
    signals = compose_why_now(st, k=3)
    assert signals
    for s in signals:
        assert s.surface == "why_now"
        # the dated hook from the fixture's why-now signal — present exactly ONCE
        # (the urgency clause is not doubled onto the finding's so_what)
        assert s.so_what.lower().count("before the 2026") == 1
        assert grade(s, st).passed


def test_compose_exec_leads_with_thesis_and_grades() -> None:
    st = _state()
    th = derive_thesis(st)
    findings = compose_findings(st, k=3, thesis=th)
    ex = compose_exec(st, th, findings)
    assert ex.surface == "exec"
    assert th.headline[:24] in ex.title            # leads with the client thesis
    assert grade(ex, st).passed
    # threads the findings' evidence + names a concrete Salesforce system
    assert ex.e_ids and any(s in ex.so_what for s in
                            ("Salesforce", "Data Cloud", "MuleSoft", "Agentforce"))


def test_compose_findings_thesis_orders_matching_pillars_first() -> None:
    st = _state()
    # a thesis pinned to P2 should surface the P2 finding ahead of P4
    from app.services.nlp.storyline import Thesis
    th = Thesis(kind="modernize", headline="H", through_line="t", play="p",
                pillars=["P2"])
    findings = compose_findings(st, k=4, thesis=th)
    pillars = [f.anchor_subcap[:2] for f in findings]
    assert pillars and pillars[0] == "P2"
