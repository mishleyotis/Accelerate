"""ET-10 — a FACT rests on a T1 or T2 source.

Measured 28-09-2026 (QA audit F-J04-004, regression seed 2): on the staged
goeasy heatmap 77 of 285 cited rows labelled FACT carried tier T3 or T4,
because the research CLI typed FACT by default and no gate compared label
with tier. The engine's ledger now refuses that shape at the write; this
is the submit-time twin over the rows `get_evidence` resolved, so a
package produced by an older engine cannot promote it either.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.gates import GATES
from dma_mcp.validation2 import _check_fact_tier


def _row(e_id, tier, label):
    return {"e_id": e_id, "stored_id": e_id, "excerpt": "x" * 80,
            "tier": tier, "claim_type": label,
            "published_date": "2025-03-01", "recency_band": "CURRENT"}


def test_a_fact_on_t3_is_refused_and_the_reason_names_the_row_and_the_rule():
    out = _check_fact_tier([_row("E-GSY-010", "T3", "FACT")],
                           {"E-GSY-010": "cell_evidence"})
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "ET-10" and r["severity"] == "block"
    assert r["path"] == "cell_evidence.e_ids"
    assert "E-GSY-010" in r["message"] and "T3" in r["message"]
    assert "T1 or T2" in r["message"]


def test_facts_on_t1_and_t2_and_any_label_but_fact_on_t3_pass():
    rows = [_row("E-1", "T1", "FACT"), _row("E-2", "T2", "FACT"),
            _row("E-3", "T3", "INFERENCE"), _row("E-4", "T4", "HYPOTHESIS"),
            _row("E-5", "T5", "CEILING_ESTIMATE")]
    cited = {r["e_id"]: "evidence" for r in rows}
    assert _check_fact_tier(rows, cited) == []


def test_an_untiered_fact_is_refused_too():
    out = _check_fact_tier([_row("E-9", None, "FACT")], {"E-9": "evidence"})
    assert len(out) == 1 and "untiered" in out[0]["message"]


def test_every_offending_row_is_named_once():
    rows = [_row(f"E-{i}", "T3", "FACT") for i in range(5)]
    cited = {r["e_id"]: "cell_evidence" for r in rows}
    out = _check_fact_tier(rows, cited)
    assert sorted(o["message"].split()[0] for o in out) == sorted(
        r["e_id"] for r in rows)


def test_et10_is_registered_in_the_gate_census_with_the_five_field_shape():
    assert "ET-10" in GATES
    name, plain, what, why, on_fail = GATES["ET-10"]
    assert on_fail == "block" and plain is None
    assert "T1" in what and "T2" in what
