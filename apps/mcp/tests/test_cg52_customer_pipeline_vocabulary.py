"""CG-52 — prose a customer is served names no pipeline tool.

Build owner, 2026-10-07: "It is the customer view that lacks heatmap details
for most clients … Ensure no recurrence." The serve layer deletes any customer
field naming a pipeline term; producers had written "An Exa search found…"
into 118 of 4,341 cell syntheses across eight promoted clients, so those
drawers served empty to the customer. Refused here, at submit, so the
producer writes the sentence a customer can read.
"""
from __future__ import annotations

from dma_mcp import validation2 as V
from dma_mcp.gates import GATES


def test_the_gate_is_registered_and_blocks():
    assert "CG-52" in GATES
    assert GATES["CG-52"][-1] == "block"


def test_a_tool_name_in_a_cell_synthesis_is_refused():
    payload = {"cell_evidence": {"cells": [
        {"subcap_id": "P1C1.1.1", "synthesis": "An Exa search found no published strategy."},
        {"subcap_id": "P1C1.1.2", "synthesis": "The strategic plan names three goals."}]}}
    out = V._check_customer_pipeline_vocabulary("heatmap", payload)
    assert [r["gate_id"] for r in out] == ["CG-52"]
    assert out[0]["path"] == "heatmap.cell_evidence.cells[0].synthesis"
    assert "'Exa'" in out[0]["message"] and out[0]["severity"] == "block"


def test_clean_prose_and_unserved_keys_pass():
    payload = {"cell_evidence": {"cells": [
        {"subcap_id": "P1C1.1.1", "synthesis": "A search of the newsroom found no strategy.",
         "sources_searched": ["Exa web search 2026-10-07"], "provenance": "declared"}],
        "r_layer": {"counter": "Tavily NOT_RUN"}},
        "alerts": {"alerts": [{"justification": "Exa"}]}}
    assert V._check_customer_pipeline_vocabulary("heatmap", payload) == []


def test_other_pages_are_checked_on_narrative_and_empty_state_only():
    payload = {"findings": {"findings": [{"body": "Exa shows"}],
                            "narrative_thread": "Five findings, one story.",
                            "empty_state": {"reason": "Clay scan was NOT_RUN for this run."}}}
    out = V._check_customer_pipeline_vocabulary("overview", payload)
    assert [r["path"] for r in out] == ["overview.findings.empty_state.reason"]
    # the whole Context page is customer-withheld
    assert V._check_customer_pipeline_vocabulary(
        "context", {"timeline": {"narrative_thread": "Exa found it"}}) == []


def test_the_reasons_are_capped_but_the_total_is_stated():
    cells = [{"subcap_id": f"P1C1.1.{i}", "synthesis": f"Exa result {i}"} for i in range(12)]
    out = V._check_customer_pipeline_vocabulary("heatmap", {"cell_evidence": {"cells": cells}})
    assert len(out) == 8 and "12 field(s)" in out[0]["message"]
