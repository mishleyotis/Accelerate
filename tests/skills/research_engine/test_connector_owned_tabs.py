"""The three connector-owned tabs are PRELIM sections, with a real gate.

Measured 2026-10-05 (Susser Bank): Focus_Areas, Issue_Register and
Tech_Peer_Deployments had no owner before HANDOFF — no PRELIM section, no
line in the connector brief — and the one gate at HANDOFF (after the whole
research budget was spent) took a free-text reason, which let the issue
register be declared empty by a pass that said, in the reason, that no
regulator's enforcement database had been queried.
"""
from __future__ import annotations

import pytest

from engine import brief, completeness as K, ledger as L, prelim
from fixtures import close_prelim, new_run

SHEETS = {"focus_areas": "Focus_Areas", "issues": "Issue_Register",
          "peer_deployments": "Tech_Peer_Deployments"}


def test_the_three_tabs_are_prelim_sections_that_open_when_empty(tmp_path):
    run = new_run(tmp_path, prelim=False)
    st = prelim.state(run.open())
    for key in SHEETS:
        assert key in st["open"], key
    assert prelim.OWNS_SHEET.keys() >= SHEETS.keys()


def test_a_closed_fixture_closes_them_through_the_real_gate(tmp_path):
    run = new_run(tmp_path)                        # close_prelim ran
    st = prelim.state(run.open())
    assert not st["open"], st["open"]
    status = {s["section"]: s["status"] for s in st["sections"]}
    assert status["focus_areas"] == "RESEARCHED"
    assert status["peer_deployments"] == "RESEARCHED"
    assert status["issues"] == "DECLARED"


@pytest.mark.parametrize("section", list(SHEETS))
def test_declaring_a_tab_empty_needs_connector_searches(tmp_path, section):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    ladder = ("searched the regulator registries, the client's site and the "
              "news archive on 2026-10-05 and found nothing naming the entity")
    with pytest.raises(prelim.PrelimRefusal, match="--facet"):
        prelim.declare(wb, section, ladder=ladder)
    with pytest.raises(K.CompletenessRefusal, match="connector"):
        K.declare(wb, SHEETS[section], ladder)
    facet = prelim.SHEET_FACET[SHEETS[section]]
    # Two web searches are not enough: one must go through a connector.
    for q in ("q one", "q two"):
        L.append_search(wb, subcap=[], facet=facet, query=q, tool="web_search",
                        hits=1, kept=0, prelim=True, actor="enrichment-connector-specialist")
    with pytest.raises(prelim.PrelimRefusal):
        prelim.declare(wb, section, ladder=ladder)
    L.append_search(wb, subcap=[], facet=facet, query="q three", tool="tavily",
                    hits=3, kept=0, prelim=True, actor="enrichment-connector-specialist")
    out = prelim.declare(wb, section, ladder=ladder)
    assert out["status"] == "DECLARED" and out["sheet_declared"] == SHEETS[section]
    st = {s["section"]: s["status"] for s in prelim.state(wb)["sections"]}
    assert st[section] == "DECLARED"


def test_a_reason_without_searches_leaves_the_section_open(tmp_path):
    # The Susser shape: a completeness reason recorded before this gate.
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    import json
    wb.set_metadata("empty_sheet_reasons", json.dumps(
        {"Issue_Register": "searched the news and found nothing at all, honest"}))
    sec = {s["section"]: s for s in prelim.state(wb)["sections"]}["issues"]
    assert sec["status"] == "OPEN" and "not connector-backed" in sec["detail"]


def test_a_cell_less_connector_search_is_prelim_not_relay():
    assert L._search_scope({"SubCap_ID": "", "Tool": "exa"}) == "PRELIM"
    assert L._search_scope({"SubCap_ID": "P1C1.1.1", "Tool": "exa"}) == "RELAY"


def test_the_sheet_facets_need_prelim(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    with pytest.raises(L.LedgerRefusal):
        L.append_search(wb, subcap=["P1C1.1.1"], facet="issues", query="q",
                        tool="exa", hits=0, kept=0)


def test_the_connector_brief_owes_the_three_tabs(tmp_path):
    run = new_run(tmp_path / "r", prelim=False)
    b = brief.prelim_brief(run.open(), run=run, out_dir=tmp_path / "p")
    owed = set(b["orchestrator"]["owed"])
    assert owed >= set(SHEETS), owed
    text = open(b["orchestrator"]["prompt_file"]).read()
    assert "--facet" in text and "engine.profile issue" in text


def test_completeness_text_report_prints_every_verdict(tmp_path, capsys):
    run = new_run(tmp_path)
    assert K.main(["check", "--run", run.run_id, "--root", str(run.root)]) in (0, 1)
    assert "tabs populated" in capsys.readouterr().out
