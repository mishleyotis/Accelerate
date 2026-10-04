"""The customer projection is checked against the internal one (RC-08).

MEASURED 2026-10-04 on SWBC (gold audit, HM-03): 24 customer drawers kept a
"In discovery conversations…" synthesis over zero served items, six of them
thin:false, after the discovery evidence was withheld whole. Every gate ran
on the internal body; the redaction tests looked only for leaks. Nothing
fired.

`packages/shared/customer_projection.check_page` is the check, shared by this
suite (over real `redact_section` output) and by
scripts/audit_promoted_client.py (over served bodies, nightly). These tests
build the customer projection the way the API does and run the check on it.

Fixture rows are SHAPED like the measured ones and carry no client text.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from dma_api.redaction import redact_section                      # noqa: E402
from customer_projection import blockers, check_page              # noqa: E402

EXCERPT = ("The institution describes one customer record per line of "
           "business, with no shared profile across them.")


def _item(e_id, origin, attribution=None):
    return {"e_id": e_id, "origin": origin, "source_name": "Discovery notes",
            "source_url": None, "excerpt": EXCERPT, "claim_type": "FACT",
            "tier": "T2", "customer_attribution": attribution}


def _cell(sid, items, thin=False):
    return {"subcap_id": sid, "synthesis": "In discovery conversations the "
            "client described separate records per line.",
            "e_ids": [i["e_id"] for i in items], "grounded_on": len(items),
            "thin": thin, "items": items}


def _bodies(cells):
    internal = {"cells": cells}
    cust, _ = redact_section("heatmap", "cell_evidence",
                             copy.deepcopy(internal), [], "customer")
    intl, _ = redact_section("heatmap", "cell_evidence",
                             copy.deepcopy(internal), [], "internal")
    wrap = lambda d: {"sections": {"cell_evidence": {"data": d,
                                                     "data_source": "producer"}}}
    return wrap(intl), wrap(cust)


def test_swbc_shape_drawers_arguing_over_nothing_are_named():
    cells = [_cell(f"P4C1.{n}.1", [_item(f"E-CC-{n}", "internal")])
             for n in range(1, 25)]
    intl, cust = _bodies(cells)
    found = blockers(check_page("heatmap", intl, cust))
    named = [f for f in found if f["code"] == "CP-ARGUED-DRAWER-EMPTY"]
    assert len(named) == 24
    assert all("thin:false" in f["message"] for f in named)


def test_a_drawer_regrounded_on_a_shareable_span_passes():
    cells = [_cell("P4C1.1.1", [_item("E-CC-1", "internal"),
                                _item("E-CC-2", "internal",
                                      attribution="Client statement, "
                                                  "discovery conversations")])]
    intl, cust = _bodies(cells)
    assert blockers(check_page("heatmap", intl, cust)) == []


def test_a_list_emptied_without_a_documented_withholding_is_a_hole():
    intl = {"sections": {"focus_areas": {"data": {"areas": [{"fa_id": "FA-1"}]}}}}
    cust = {"sections": {"focus_areas": {"data": {"areas": []}}}}
    codes = [f["code"] for f in check_page("heatmap", intl, cust)]
    assert codes == ["CP-SECTION-EMPTIED"]

    intl = {"sections": {"techstack": {"data": {
        "items": [{"status": "INFERRED"}], "layers": [{"layer": "OPS"}]}}}}
    cust = {"sections": {"techstack": {"data": {"items": [],
                                                "layers": [{"layer": "OPS"}]}}}}
    assert check_page("techstack", intl, cust) == [], "D4 is documented"


def test_a_stated_withholding_is_not_a_hole():
    intl = {"sections": {"thought_leadership": {"data": {"entries": [{"x": 1}]}}}}
    cust = {"sections": {"thought_leadership": {
        "data": None, "data_source": "withheld",
        "empty_state": {"kind": "withheld_for_audience"}}}}
    assert check_page("overview", intl, cust) == []


def test_dangling_chips_against_the_served_evidence_index():
    intl = {"sections": {"insights": {"data": {"cards": [
        {"ic_id": "IC-1", "supporting_e_ids": ["E-CC-1", "E-CC-2"]}]}}}}
    cust = copy.deepcopy(intl)
    found = check_page("insights", intl, cust, served_evidence_ids={"E-CC-1"})
    assert [f["code"] for f in found] == ["CP-DANGLING-CHIP"]
    assert "E-CC-2" in found[0]["message"]


def test_the_audit_script_runs_the_same_check(tmp_path):
    cells = [_cell("P4C1.1.1", [_item("E-CC-1", "internal")])]
    intl, cust = _bodies(cells)
    (tmp_path / "heatmap_internal.json").write_text(json.dumps(intl))
    (tmp_path / "heatmap_customer.json").write_text(json.dumps(cust))
    r = subprocess.run([sys.executable,
                        str(ROOT / "scripts" / "audit_promoted_client.py"),
                        "--from-dir", str(tmp_path), "--json"],
                       capture_output=True, text=True, timeout=120)
    findings = json.loads(r.stdout)["findings"]
    assert any(f["code"] == "CP-ARGUED-DRAWER-EMPTY" for f in findings), \
        r.stdout[:2000]
    assert r.returncode == 1
