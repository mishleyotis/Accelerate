"""governance_audit — schema-tolerant reasoning chain + contradiction logs.

D6 Health "Audit" tab. The logs ship under many schemas + folders across
the corpus; these pin the variants that previously parsed to nothing
(reasoning_chain 1/28 → 9/28; contradiction_log found only in
07_governance → recursive).
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.parsers.governance_audit import (
    _split_decision_path,
    parse_governance_audit_logs,
    parse_reasoning_chain,
)

_BASE = Path(__file__).resolve().parents[1] / "tests/fixtures/dma_packages_batches"


def test_split_decision_path() -> None:
    assert _split_decision_path(["a", "b"]) == ["a", "b"]
    assert _split_decision_path("evidence → ceiling → final") == [
        "evidence", "ceiling", "final"
    ]
    assert _split_decision_path("a -> b -> c") == ["a", "b", "c"]
    assert _split_decision_path(None) == []


def test_reasoning_subcap_chains(tmp_path: Path) -> None:
    p = tmp_path / "reasoning_chain_log.json"
    p.write_text(json.dumps({"subcap_chains": [
        {"subcap_id": "P1C1.1.1", "category": "P1C1",
         "decision_path": ["evidence", "ceiling"], "final_score": 3.0},
    ]}))
    rows = parse_reasoning_chain(p)
    assert rows[0].subcap_id == "P1C1.1.1" and rows[0].decision_path == ["evidence", "ceiling"]


def test_reasoning_chains_key_with_arrow_string(tmp_path: Path) -> None:
    p = tmp_path / "reasoning_chain_log.json"
    p.write_text(json.dumps({"chains": [
        {"subcap_id": "P4C3.1.1", "category_id": "P4C3",
         "decision_path": "evidence_mapped → ceiling=4.0 → final=3.5",
         "confidence": "HIGH"},
    ]}))
    rows = parse_reasoning_chain(p)
    assert len(rows) == 1
    assert rows[0].subcap_id == "P4C3.1.1"
    assert rows[0].decision_path == ["evidence_mapped", "ceiling=4.0", "final=3.5"]


def test_reasoning_key_decisions(tmp_path: Path) -> None:
    p = tmp_path / "reasoning_chain_log.json"
    p.write_text(json.dumps({"key_decisions": [
        {"subcap": "P4C2.*_ai", "decision": "Cap at M1.5",
         "evidence": "E-091 (zero AI)", "ceiling": 1.5, "confidence": "HIGH"},
    ]}))
    rows = parse_reasoning_chain(p)
    assert rows[0].subcap_id == "P4C2"  # prefix extracted from wildcard
    assert "Cap at M1.5" in rows[0].decision_path[0]


def test_reasoning_subcap_keyed_dict(tmp_path: Path) -> None:
    p = tmp_path / "reasoning_chain_log.json"
    p.write_text(json.dumps({
        "assessment_id": "X",  # metadata ignored
        "P1C1.1.1": {"decision_path": "evidence→ceiling→final", "final_score": 3.0},
        "P2C3.1.2": {"decision_path": "evidence→caps→final", "confidence": "MED"},
    }))
    rows = parse_reasoning_chain(p)
    assert {r.subcap_id for r in rows} == {"P1C1.1.1", "P2C3.1.2"}


def test_recursive_contradiction_discovery() -> None:
    """contradiction_log.csv lives in 03_scoring_workbook / 08_appendices /
    04_Governance too — the sweep must find it outside 07_governance."""
    target = None
    for p in sorted(_BASE.glob("batch_*/*")):
        if not p.is_dir():
            continue
        hits = list(p.glob("**/contradiction_log.csv"))
        if hits and not any("07_governance" in str(h) for h in hits):
            target = p
            break
    if target is None:
        import pytest
        pytest.skip("no non-07_governance contradiction_log fixture")
    logs = parse_governance_audit_logs(target)
    assert logs is not None and logs.contradictions
