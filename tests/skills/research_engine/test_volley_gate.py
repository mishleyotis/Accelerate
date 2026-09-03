"""An empty cell EARNS its emptiness: five volleys fired, a ladder, a declaration.

REPORTED 2026-09-03 by the engagement owner: "The major issue is some subcaps
are marked as no evidence without any enrichment efforts. Also, limited
evidence is consolidated in most runs making the entire assessment very
evidence deficient and not even looking at the 5 volley structure and related
DQ set."

Measured on the reference package itself (Golden 1, gold_reference.json): 307
searches for 690 subcaps; `fails` fired 3 times, `value` 10, `corroborates` 14.
The protocol had said "every volley fires or is NOT_RUN with a reason" since
AUD-0017 and NOTHING measured it for a cell that never reached synthesis —
`absence_unsearched` cleared on one logged query, and `dq_gaps` ran only after
`if not synthesised: continue`.

Three things now hold, and each is a test below:

  volleys_incomplete        BLOCKING — every askable facet of every cell in the
                            category has a logged search for THAT cell
  absence_undeclared_empty  BLOCKING — a cell with no evidence closes only as a
                            DECLARED absence (`engine.cli absence`), which itself
                            refuses while a volley is unfired or a ladder rung
                            names an unfired query
  the card and the worklist name the facets still owed, and serve a half-fired
                            cell before a new one
"""
from __future__ import annotations

import pytest

from engine import floors_gate, orient
from engine import ledger as L
from engine.ledger import LedgerRefusal
from fixtures import (bank_evidence, declare_absent, fire_volleys,
                      good_synthesis, new_run, synthesise)


def _one_query(wb, cell, facet="works"):
    L.append_search(wb, subcap=cell, facet=facet, tool="web_search",
                    query=f'"Acme Credit Union" {cell} rollout', hits=0, kept=0,
                    outcome="no hits")


def test_a_category_of_worked_and_declared_cells_passes(tmp_path):
    """The gate must be satisfiable by doing the work — evidence where there is
    some, a declared absence where there is none."""
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cells = wb.selected_subcaps()
    for cell in cells[:5]:
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell, n=5)))
    declare_absent(wb, cells[5])
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]
    assert v["volleys_incomplete"] == []
    assert v["absence_undeclared_empty"] == []


def test_one_shallow_query_does_not_close_a_cell(tmp_path):
    """The reported shape: one `works` query, four volleys never fired, the
    row left at NO_EVIDENCE. Both new terms name the cell."""
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cells = wb.selected_subcaps()
    for cell in cells[:5]:
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell, n=3)))
    _one_query(wb, cells[5])
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "FAIL"
    assert "volleys_incomplete" in v["blocking"]
    assert "absence_undeclared_empty" in v["blocking"]
    hit = [x for x in v["volleys_incomplete"] if x["subcap"] == cells[5]]
    assert hit and set(hit[0]["missing"]) == {"fails", "value", "contradicts", "corroborates"}
    assert cells[5] in v["absence_undeclared_empty"]
    # and the cell that was never searched at all is still its own finding
    assert not v["absence_unsearched"], "one query IS a search; a different term owns that"


def test_an_evidenced_cell_still_owes_its_volleys(tmp_path):
    """Rich evidence on `works` is not a reason to skip `fails` — it is the
    reason `fails` matters. A synthesised cell with one volley fired blocks."""
    run = new_run(tmp_path, n=3)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    _one_query(wb, cell)
    eids = [L.append_evidence(
        wb, source_name=f"src {i}", source_url=f"https://s{i}.example/x",
        tier="T2", subcaps=[cell], published="2025-06-01",
        excerpt=("Alkami digital banking went live in Q3 2024 and reached 47 "
                 f"percent member adoption within ninety days, restated at {50+i} "
                 "percent in the 2025 report.")) for i in range(3)]
    synthesise(wb, cell, good_synthesis(cell, eids))
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert any(x["subcap"] == cell for x in v["volleys_incomplete"])
    assert "volleys_incomplete" in v["blocking"]


def test_declaring_an_absence_refuses_while_a_volley_is_unfired(tmp_path):
    run = new_run(tmp_path, n=2)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    _one_query(wb, cell)
    with pytest.raises(LedgerRefusal, match="volley\\(s\\) never fired"):
        L.declare_absence(
            wb, cell, actor="research-p1c1-producer",
            ladder=[{"rung": "direct", "query": f'"Acme Credit Union" {cell} rollout'}],
            proxy_log="hunted the leadership_title proxy across the site and LinkedIn; nothing",
            what_was_hunted="a public artefact naming the capability at Acme; nothing came back")


def test_declaring_an_absence_refuses_a_ladder_rung_nobody_fired(tmp_path):
    run = new_run(tmp_path, n=2)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    fire_volleys(wb, cell, n=0)
    with pytest.raises(LedgerRefusal, match="never saw|owed"):
        L.declare_absence(
            wb, cell, actor="research-p1c1-producer",
            ladder=[{"rung": "direct", "query": "a query that was never logged anywhere"},
                    {"rung": "proxy", "query": "another query nobody fired"}],
            proxy_log="hunted the leadership_title proxy across the site and LinkedIn; nothing",
            what_was_hunted="a public artefact naming the capability at Acme; nothing came back")


def test_declaring_an_absence_refuses_a_cell_that_holds_evidence(tmp_path):
    run = new_run(tmp_path, n=2)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    bank_evidence(wb, cell, n=2)
    with pytest.raises(LedgerRefusal, match="carries evidence"):
        L.declare_absence(wb, cell, actor="x", ladder=[], proxy_log="x" * 50,
                          what_was_hunted="y" * 50)


def test_a_declared_absence_is_closed_and_recorded(tmp_path):
    run = new_run(tmp_path, n=2)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    out = declare_absent(wb, cell)
    assert set(out["rungs"]) == {"direct", "proxy"}
    row = wb.scoring_row(cell)
    assert str(row["Absence_Claimed"]).upper() == "YES"
    assert row["Claim_Label"] == "HYPOTHESIS"
    assert str(row["DQ_Fails"]).startswith("NO_FINDING after")
    assert L.actor_for(wb, cell, "absence") == "research-p1c1-producer"
    wl = L.worklist(wb, "P1C1")
    assert cell in wl["closed"] and cell in wl["declared_absent"]
    assert cell not in wl["pending"]


def test_the_worklist_tells_a_half_fired_cell_from_an_untouched_one(tmp_path):
    run = new_run(tmp_path, n=3)
    wb = run.open()
    a, b, c = wb.selected_subcaps()
    _one_query(wb, a)                 # in_volley
    fire_volleys(wb, b, n=0)          # searched_empty: all fired, nothing registered
    wl = L.worklist(wb, "P1C1")
    assert a in wl["in_volley"]
    assert b in wl["searched_empty"]
    assert c in wl["pending"]


def test_orient_serves_the_half_fired_cell_before_a_new_one(tmp_path):
    run = new_run(tmp_path, n=3)
    wb = run.open()
    a, b, c = wb.selected_subcaps()
    _one_query(wb, b)
    out = orient.orient(wb, "P1C1", qa_dir=run.qa_dir)
    assert out["next_card"]["id"] == b, out["do_first"]
    assert out["next_card"]["volleys"]["missing"] == ["fails", "value", "contradicts", "corroborates"]
    assert out["next_card"]["name"], "the card names the subcapability"
    assert any("SOME volleys" in d for d in out["do_first"])
    assert out["clean"] is False


def test_orient_serves_a_fully_fired_empty_cell_in_declare_mode(tmp_path):
    run = new_run(tmp_path, n=2)
    wb = run.open()
    a, b = wb.selected_subcaps()
    fire_volleys(wb, a, n=0)
    out = orient.orient(wb, "P1C1", qa_dir=run.qa_dir)
    assert out["next_card"]["id"] == a
    assert out["next_card"]["mode"] == "declare"
    assert "engine.cli absence" in out["next_card"]["close_by"]


def test_the_card_names_the_proxy_class_the_template_expects(tmp_path):
    run = new_run(tmp_path, n=1)
    wb = run.open()
    out = orient.orient(wb, "P1C1", qa_dir=run.qa_dir)
    assert out["next_card"]["proxy_class_if_absent"] in (
        "leadership_title", "regulator_filing", "org_talent", "ecosystem_vendor",
        "artifact_disclosure", "behavioral_delivery")


def test_a_single_tool_absence_is_advisory_not_blocking(tmp_path):
    run = new_run(tmp_path, n=1)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    fire_volleys(wb, cell, n=0, tool="web_search")        # one tool only
    L.declare_absence(
        wb, cell, actor="research-p1c1-producer",
        ladder=[{"rung": "direct", "query": f'"Acme Credit Union" {cell} rollout OR "went live"'},
                {"rung": "proxy", "query": f'"Acme Credit Union" {cell} regulator OR analyst OR rating'}],
        proxy_log="hunted the regulator_filing proxy — NCUA and DFPI registries — nothing names it",
        what_was_hunted="a public artefact naming the capability at Acme across five volleys; nothing")
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert "absence_single_tool" in v["advisory"]
    assert "absence_single_tool" not in v["blocking"]
    assert "absence_undeclared_empty" not in v["blocking"]
    assert "volleys_incomplete" not in v["blocking"]


def test_the_reference_package_would_fail_the_volley_gate():
    """gold_reference.json records the Golden 1 search facets; the gate is
    stricter than the reference on exactly this point by the owner's
    instruction, and the pin says so."""
    import json
    from engine.template import TEMPLATES_DIR
    gold = json.loads((TEMPLATES_DIR / "gold_reference.json").read_text())
    facets = gold["workbook"]["search_facets"]
    assert facets["fails"] < gold["workbook"]["subcaps"]
    assert any("volley" in line for line in gold["_readme"])
