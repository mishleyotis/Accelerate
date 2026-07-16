"""Tests for the cross_entity_patterns service (pure logic, no DB)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workers.cross_entity_patterns.service import (  # noqa: E402
    GapRow,
    IssueRow,
    compute_patterns,
)


def _gaps(spec: dict[str, list[tuple[str, float]]]) -> list[GapRow]:
    """spec: subcap_id -> [(entity_id, peer_gap), ...]."""
    return [
        GapRow(entity_id=eid, subcap_id=sid, peer_gap=gap)
        for sid, rows in spec.items()
        for eid, gap in rows
    ]


def test_insufficient_cohort_marker():
    res = compute_patterns(entity_ids={"e1", "e2"}, gaps=[], issues=[])
    assert len(res) == 1
    assert res[0].pattern_type == "insufficient_data"
    assert res[0].entity_count == 2
    assert sorted(res[0].affected_entity_ids) == ["e1", "e2"]


def test_subcap_gap_requires_three_entities():
    eids = {"e1", "e2", "e3"}
    gaps = _gaps({
        "P2C1": [("e1", -0.5), ("e2", -1.0), ("e3", -0.3)],  # 3 → pattern
        "P3C2": [("e1", -0.2), ("e2", -0.4)],                # 2 → none
    })
    res = compute_patterns(entity_ids=eids, gaps=gaps, issues=[],
                           names={"P2C1": "Journey Mapping"})
    gap_patterns = [p for p in res if p.pattern_type == "subcap_gap"]
    assert len(gap_patterns) == 1
    p = gap_patterns[0]
    assert p.pattern_key == "P2C1"
    assert p.entity_count == 3
    assert "Journey Mapping" in p.pattern_label
    assert p.median_peer_gap == -0.5  # median of [-1.0, -0.5, -0.3]
    assert sorted(p.affected_entity_ids) == ["e1", "e2", "e3"]


def test_positive_gap_ignored():
    eids = {"e1", "e2", "e3"}
    gaps = _gaps({"P1C1": [("e1", 0.5), ("e2", 0.2), ("e3", 1.0)]})
    res = compute_patterns(entity_ids=eids, gaps=gaps, issues=[])
    assert [p for p in res if p.pattern_type == "subcap_gap"] == []


def test_issue_theme_with_severity_mix():
    eids = {"e1", "e2", "e3", "e4"}
    issues = [
        IssueRow("e1", "P4C3", "critical"),
        IssueRow("e2", "P4C3", "high"),
        IssueRow("e3", "P4C3", "high"),
        IssueRow("e4", "P1C1", "low"),  # only 1 entity → no pattern
    ]
    res = compute_patterns(entity_ids=eids, gaps=[], issues=issues,
                           names={"P4C3": "Integration"})
    themes = [p for p in res if p.pattern_type == "issue_theme"]
    assert len(themes) == 1
    p = themes[0]
    assert p.pattern_key == "P4C3"
    assert p.entity_count == 3
    assert p.severity_mix == {"critical": 1, "high": 2}


def test_subcap_with_both_gap_and_issue_yields_two_rows():
    eids = {"e1", "e2", "e3"}
    gaps = _gaps({"P2C1": [("e1", -0.5), ("e2", -0.6), ("e3", -0.7)]})
    issues = [
        IssueRow("e1", "P2C1", "high"), IssueRow("e2", "P2C1", "medium"),
        IssueRow("e3", "P2C1", "high"),
    ]
    res = compute_patterns(entity_ids=eids, gaps=gaps, issues=issues)
    assert sorted(p.pattern_type for p in res) == ["issue_theme", "subcap_gap"]
    assert all(p.pattern_key == "P2C1" for p in res)


def test_entities_outside_cohort_excluded():
    eids = {"e1", "e2", "e3"}  # e9 is NOT in the cohort
    gaps = _gaps({"P2C1": [("e1", -0.5), ("e2", -0.6), ("e9", -0.7)]})
    res = compute_patterns(entity_ids=eids, gaps=gaps, issues=[])
    # only e1, e2 count → 2 < 3 → no pattern
    assert [p for p in res if p.pattern_type == "subcap_gap"] == []
