"""Per-segment grade scorecard (app/scripts/grade_scorecard.py) — the pure
scoring + aggregation core. A composer-authored gold card must grade PASS; a
bare-subcap-name ladder card must grade FAIL; aggregation must split gold vs
ladder per subvertical.
"""
from __future__ import annotations

import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")

from app.scripts.grade_scorecard import aggregate, grade_run
from app.services.nlp.card_bridge import compose_gold_cards
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


def test_grade_run_passes_gold_fails_bare_ladder_card() -> None:
    st = _state()
    gold = compose_gold_cards(st)
    assert gold, "fixture should yield at least one gold card"
    rows = [g.model_dump() for g in gold]
    # a bare-subcap-name ladder card with no grounding — must fail the rubric
    rows.append({
        "ic_id": "INS-01", "severity": "high", "title": "Master Data Management",
        "what_text": "Make Master Data Management a near-term focus.",
        "why_text": "", "so_what_text": "", "linked_subcap_id": "P4C1.4.1",
        "linked_e_ids": [],
    })
    grades = grade_run(st, rows)
    by_id = {g.ic_id: g for g in grades}
    assert all(g.passed for g in grades if g.is_gold)
    assert by_id["INS-01"].passed is False and not by_id["INS-01"].is_gold


def test_aggregate_splits_gold_and_ladder_by_segment() -> None:
    st = _state()
    rows = [g.model_dump() for g in compose_gold_cards(st)]
    rows.append({"ic_id": "INS-01", "severity": "high", "title": "X",
                 "what_text": "y", "why_text": "", "so_what_text": "",
                 "linked_subcap_id": "P4C1.4.1", "linked_e_ids": []})
    grades = grade_run(st, rows)
    segs = aggregate([("RB", grades), ("RB", grades)])
    seg = segs["RB"]
    assert seg.n_clients == 2
    assert seg.gold_total == 2 * sum(1 for g in grades if g.is_gold)
    assert seg.ladder_total == 2
    assert seg.gold_pass == seg.gold_total          # all gold pass
    assert seg.gold_pass_rate == 1.0
    assert seg.ladder_pass == 0                       # the bare card fails
