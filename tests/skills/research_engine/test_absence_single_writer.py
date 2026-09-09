"""An empty cell closes ONE way — and every reader can prove it.

Owner, 2026-09-03 (issue 1): "some subcaps are marked as no evidence without
any enrichment efforts … not even looking at the 5 volley structure and
related DQ set." Reproduced before the fix (scratchpad repro, same day):

  * `engine.memory note --kind absence` + `consolidate` set Absence_Claimed
    on a cell with ZERO Search_Log rows, and `is_declared_absent` said True;
  * `append_search(subcap=None, facet=None, tool="my-made-up-tool")` landed;
  * `assessment.open_stage(force=True)` opened scoring on an ungated run;
  * `validator.validate` passed a workbook where every cell was NO_EVIDENCE;
  * the strip dropped Absence_Claimed / Proxy_Log / Negative_Ladder.

Each of those is a test below, inverted.
"""
from __future__ import annotations

import json

import pytest

from engine import assessment as A
from engine import contract as C
from engine import floors_gate
from engine import handoff
from engine import ledger as L
from engine import memory as M
from engine import strip_working_area as STRIP
from engine import validator

from fixtures import (CAT, bank_evidence, declare_absent, fire_volleys,
                      good_synthesis, new_run, researched_run, synthesise)


# ── the flag has one writer ──────────────────────────────────────────────

def test_the_absence_flag_has_one_writer(tmp_path):
    """A flag written by anything but `declare_absence` is not an absence."""
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    wb.set_scoring(cell, {"Absence_Claimed": "YES",
                          "Proxy_Log": "a ladder somebody typed by hand"})
    row = wb.scoring_row(cell)
    assert L.is_declared_absent(row, wb) is False
    assert cell not in L.declared_absences(wb)
    v = floors_gate.run(wb, CAT, qa_dir=run.qa_dir)
    assert cell in v["absence_undeclared_empty"]
    fails = validator.validate(wb.path, run_id="R-TEST-1")
    assert any(f["rule"] == 8 and "Provenance 'absence' row" in f["detail"]
               for f in fails), fails
    # and the worklist does not count it closed
    wl = L.worklist(wb, CAT)
    assert cell not in wl["closed"] and cell not in wl["declared_absent"]


def test_a_notebook_absence_stages_the_ladder_and_leaves_the_declaration_to_the_cli(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    M.note(run, category=CAT, subcap=cell, facet="works", kind="absence",
           ladder="proxy: hunted the leadership_title class across the site and "
                  "LinkedIn; nothing names an owner for the capability")
    res = M.consolidate(run, CAT)
    wb = run.open()
    row = wb.scoring_row(cell)
    assert "proxy:" in str(row.get("Proxy_Log"))
    assert str(row.get("Absence_Claimed") or "").upper() != "YES"
    assert L.is_declared_absent(row, wb) is False
    assert any("undeclared" in str(x) for x in json.dumps(res).split(","))
    prov = [r for r in wb.rows("Provenance")
            if r.get("SubCap_ID") == cell and r.get("Step") == "enrichment"]
    assert prov and "NOT declared" in str(prov[0]["Detail"])


def test_a_synthesis_cannot_declare_an_absence_on_an_empty_cell(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[1]
    fire_volleys(wb, cell, n=0)
    rec = good_synthesis(cell, [])
    rec.update({"Absence_Claimed": "YES",
                "Proxy_Log": "hunted the proxy class across five volleys and two rungs"})
    with pytest.raises(L.LedgerRefusal, match="engine.cli absence"):
        L.append_synthesis(wb, cell, rec, actor="research-p1c1-producer")
    assert str(wb.scoring_row(cell).get("Absence_Claimed") or "") == ""


def test_the_declared_absence_is_the_one_that_counts(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path, n=6, absent=1)
    absent = cells[-1]
    row = wb.scoring_row(absent)
    assert L.is_declared_absent(row, wb)
    assert absent in L.declared_absences(wb)
    assert L.actor_for(wb, absent, "absence") == "research-p1c1-producer"
    assert validator.validate(wb.path, run_id="R-TEST-1") == []


# ── the volleys, the primary question, the enrichment connector ──────────

def test_an_unfired_primary_question_blocks_the_category(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    for facet in C.FACETS:                        # five volleys, no primary
        L.append_search(wb, subcap=cell, facet=facet, query=f'"Acme" {facet} q',
                        tool="web_search", hits=0, kept=0)
    v = floors_gate.run(wb, CAT, qa_dir=run.qa_dir)
    assert cell in v["primary_unfired"]
    assert "primary_unfired" in v["blocking"]
    assert "primary_unfired" not in floors_gate.ADVISORY_TERMS


def test_declaring_an_absence_refuses_while_the_primary_question_is_unfired(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    for facet in C.FACETS:
        L.append_search(wb, subcap=cell, facet=facet, query=f'"Acme" {facet} q',
                        tool="exa", hits=0, kept=0)
    with pytest.raises(L.LedgerRefusal, match="primary diagnostic question"):
        L.declare_absence(
            wb, cell, actor="research-p1c1-producer",
            ladder=[{"rung": "direct", "query": '"Acme" works q'},
                    {"rung": "proxy", "query": '"Acme" corroborates q'}],
            proxy_log="hunted the leadership_title proxy class across the site "
                      "and LinkedIn and the annual report; nothing names one",
            what_was_hunted="a public artefact naming the capability at Acme "
                            "across five volleys and two rungs; nothing about Acme")


def test_an_absence_with_no_enrichment_connector_is_refused(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    fire_volleys(wb, cell, n=0)                   # primary + five, web_search only
    with pytest.raises(L.LedgerRefusal, match="enrichment connector"):
        L.declare_absence(
            wb, cell, actor="research-p1c1-producer",
            ladder=[{"rung": "direct",
                     "query": f'"Acme Credit Union" {cell} rollout OR "went live"'},
                    {"rung": "proxy",
                     "query": f'"Acme Credit Union" {cell} regulator OR analyst OR rating'}],
            proxy_log="hunted the leadership_title proxy class across the site "
                      "and LinkedIn and the annual report; nothing names one",
            what_was_hunted="a public artefact naming the capability at Acme "
                            "across five volleys and two rungs; nothing about Acme")
    v = floors_gate.run(wb, CAT, qa_dir=run.qa_dir)
    assert any(f["subcap"] == cell for f in v["absence_single_tool"])
    assert "absence_single_tool" in v["blocking"]


def test_an_enrichment_tool_unlocks_the_declaration(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    out = declare_absent(wb, cell)                # fixture fires one `exa` query
    assert "exa" in out["tools"]
    v = floors_gate.run(wb, CAT, qa_dir=run.qa_dir)
    assert not any(f["subcap"] == cell for f in v["absence_single_tool"])
    assert cell not in v["absence_undeclared_empty"]


def test_the_ai_overlay_is_measured_and_advisory(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    fire_volleys(wb, cell, n=0)
    v = floors_gate.run(wb, CAT, qa_dir=run.qa_dir)
    assert any(f["subcap"] == cell for f in v["ai_overlay_unsearched"])
    assert "ai_overlay_unsearched" in floors_gate.ADVISORY_TERMS
    assert "ai_overlay_unsearched" not in v["blocking"]
    vs = L.volley_status(wb, cell)
    assert vs["primary_fired"] == 1
    assert set(vs["ai_fired"]) == set(C.AI_FACETS)


# ── the Search_Log vocabulary ────────────────────────────────────────────

def test_an_unknown_tool_is_refused(tmp_path):
    wb = new_run(tmp_path, n=2).open()
    cell = wb.selected_subcaps()[0]
    with pytest.raises(L.LedgerRefusal, match="not one of"):
        L.append_search(wb, subcap=cell, facet="works", query='"Acme" q',
                        tool="my-made-up-tool", hits=1, kept=1)


def test_a_search_with_no_cell_and_no_facet_is_refused_unless_prelim(tmp_path):
    wb = new_run(tmp_path, n=2).open()
    with pytest.raises(L.LedgerRefusal, match="--prelim"):
        L.append_search(wb, subcap=None, facet=None, query='"Acme" who is the CEO',
                        tool="web_search", hits=1, kept=1)
    n = L.append_search(wb, subcap=None, facet=None, query='"Acme" who is the CEO',
                        tool="web_search", hits=1, kept=1, prelim=True)
    assert n >= 1


# ── scoring has no back door ─────────────────────────────────────────────

def test_open_has_no_force(tmp_path):
    run = new_run(tmp_path, n=4)
    wb = run.open()
    with pytest.raises(TypeError):
        A.open_stage(wb, run.qa_dir, force=True)
    with pytest.raises(A.ScoringRefusal, match="There is no --force"):
        A.open_stage(wb, run.qa_dir)
    with pytest.raises(SystemExit) as e:
        A.main(["open", "--run", "R-TEST-1", "--root", str(run.root), "--force"])
    assert e.value.code == 2


def test_a_forged_absence_flag_cannot_be_scored(tmp_path):
    from fixtures import scored_run
    run, wb, cells, ev = scored_run(tmp_path, n=6, absent=1)
    # a row nobody researched, flagged by hand after scoring opened
    victim = cells[0]
    wb.set_scoring(victim, {"Evidence_IDs": C.NO_EVIDENCE, "Absence_Claimed": "YES",
                            "Dominant_Claim": ""})
    with pytest.raises(A.ScoringRefusal, match="absence was never declared"):
        A.score(wb, victim, score=2.0, confidence="LOW",
                rationale=("[EVIDENCE] none — [CEILING] the no-evidence cap of 2.0 "
                           "applies; this row was flagged absent by hand and carries "
                           "no ladder, no volleys and no declaration, so a score "
                           "here would be a score on nothing at all."),
                actor="scoring-p1-producer", ai_applicability="NONE",
                data_dependency="none", data_readiness="UNKNOWN")


def test_rule8_fires_on_an_undeclared_empty_row_at_the_assessment_stage(tmp_path):
    from fixtures import scored_run
    run, wb, cells, ev = scored_run(tmp_path, n=6, absent=1)
    assert validator.validate(wb.path, run_id="R-TEST-1", expect_scores=True) == []
    wb.set_scoring(cells[0], {"Evidence_IDs": C.NO_EVIDENCE})
    fails = validator.validate(wb.path, run_id="R-TEST-1", expect_scores=True)
    assert any(f["rule"] == 8 and "undeclared" in f["detail"] for f in fails), fails


# ── the ladder outlives the strip ────────────────────────────────────────

def test_the_handoff_carries_the_absence_ladder(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path, n=6, absent=1)
    doc = handoff.build(wb, qa_dir=run.qa_dir, strict=False)
    rec = next(r for r in doc["subcap_records"] if r["subcap_id"] == cells[-1])
    assert rec["state"] == "declared_absent"
    assert rec["absence"]["negative_ladder"] and rec["absence"]["proxy_log"]
    assert rec["absence"]["declared_by"] == "research-p1c1-producer"
    assert all(r["absence"] is None for r in doc["subcap_records"]
               if r["subcap_id"] != cells[-1])


def test_the_strip_refuses_while_a_declared_absence_has_no_surviving_ladder(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path, n=6, absent=1)
    doc = handoff.build(wb, qa_dir=run.qa_dir, strict=False)
    hp = tmp_path / "handoff.json"
    hp.write_text(json.dumps(doc))
    ok = STRIP.survives_elsewhere(wb.path, hp)
    assert ok == []
    for r in doc["subcap_records"]:
        r["absence"] = None
    hp.write_text(json.dumps(doc))
    missing = STRIP.survives_elsewhere(wb.path, hp)
    assert "Negative_Ladder" in missing and "Proxy_Log" in missing
    with pytest.raises(SystemExit, match="Negative_Ladder"):
        STRIP.strip(str(wb.path), handoff=str(hp), out=str(tmp_path / "s.xlsx"))


# ── the run-level density floor ──────────────────────────────────────────

def test_a_run_thinner_than_golden_1_cannot_open_scoring(tmp_path):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cells = wb.selected_subcaps()
    # one row on two cells, four honest absences: far below 1.05 rows per
    # subcap and 64% evidenced — the Golden 1 floors
    for cell in cells[:2]:
        bank_evidence(wb, cell, n=1)
    for cell in cells[2:]:
        declare_absent(wb, cell)
    d = floors_gate.run_density(wb)
    assert d["met"] is False
    assert any("thinner than the Golden 1" in s for s in d["shortfall"])
    assert any("Golden 1's own coverage" in s for s in d["shortfall"])
    assert d["floors"]["source"] == "gold_reference.json"
    pre = A.research_ready(wb, run.qa_dir)
    assert any("thinner than the Golden 1" in p for p in pre)


def test_the_density_floors_are_read_from_the_gold_reference():
    import json as _json
    from engine import template
    g = _json.loads((template.TEMPLATES_DIR / "gold_reference.json").read_text())["workbook"]
    f = floors_gate.density_floors()
    assert f["rows_per_subcap"] == pytest.approx(g["evidence_rows"] / g["subcaps"])
    assert f["evidenced_share"] == pytest.approx(g["subcaps_with_evidence"] / g["subcaps"])
