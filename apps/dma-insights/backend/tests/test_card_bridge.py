"""Composer→card bridge (nlp/card_bridge.py). compose_gold_cards must turn the
PASS composer items into InsightCardRows with clean, curated citations and a
valid severity, capped and ranked — the highest-priority derive rung.
"""
from __future__ import annotations

import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")

from app.services.nlp.card_bridge import _severity, compose_gold_cards
from app.services.nlp.entity_knowledge import Capability, EntityState
from app.services.nlp.knowledge import EntityKnowledge, Evidence


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
    return EntityState(
        run_id="r", entity_id="e", name="Test Bank", subvertical="RB",
        catalog_version="v7.0", capabilities=caps, knowledge=EntityKnowledge(evidence),
        firmographics={}, platforms=[], tech_stack=[], scqa=None, top_findings=[],
        why_now_signals=[{"so_what": "Engage before the 2026 core conversion sets the roadmap."}],
        na_subcap_ids=set(),
        _by_subcap={c.subcap_id: c for c in caps},
        _excerpt_by_eid={e.e_id: e.text for e in evidence},
        _catalogue_names={c.name.lower() for c in caps},
    )


def test_compose_gold_cards_emits_clean_insight_card_rows() -> None:
    cards = compose_gold_cards(_state())
    assert cards, "expected at least one PASS gold card"
    for c in cards:
        assert c.ic_id.startswith("GLD")
        assert c.severity in {"critical", "high", "medium", "low"}
        assert c.title and c.what_text and c.linked_subcap_id
        # citations are clean + de-annotated (no comma/colon/INT- cruft)
        for e in c.linked_e_ids:
            assert "," not in e and ":" not in e and not e.startswith("INT-")


def test_severity_bounds() -> None:
    gap = Capability("P1C1.1.1", "X", 1.5, 3.0, -1.5, "P1", "P1C1", "", "T1", True, [])
    strength = Capability("P1C1.1.2", "Y", 4.0, 3.0, 1.0, "P1", "P1C1", "", "T1", True, [])
    assert _severity(gap, is_top=True) == "critical"
    assert _severity(gap, is_top=False) == "high"
    assert _severity(strength, is_top=True) == "medium"
    assert _severity(strength, is_top=False) == "low"
