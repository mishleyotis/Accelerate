"""The assessment stage's three tabs, and the stage that says they apply.

WHY THESE EXIST. The app READS all three — `parse_grain_summaries` for
Pillar_Summary and Category_Detail, `parse_recommendations` for
Recommendations — both land server-side, and both already back live gates:
the 0.05 grain tolerance reconciles served figures against the STATED grains,
and CG-39 reads `recommendations_raw`. Nothing ever wrote them, so every
package this engine built landed with zero recommendations and both stated
grains absent.

They could not simply be added, because there was NO STAGE KEY ANYWHERE. The
app inferred the stage from the emptiness of column D; the engine made it a
CLI opinion (`expect_scores`, defaulted False by `assemble.package`); and
`REQUIRED_SHEETS = tuple(SHEETS)` made every declared sheet required at every
stage. Adding three scored tabs to that would have given every research run
three tabs it is FORBIDDEN to fill — contract rule 4 keeps column D empty —
which is the same defect facing the other way.
"""
from __future__ import annotations

import sys

import pytest

from engine import contract as C
from engine import grains as G
from engine import narrative as N
from engine import report_spec as RS
from engine.grains import GrainRefused

from .fixtures import (bank_evidence, good_synthesis, new_run, synthesise)
from .test_report_structure import _rec


def _scored(tmp_path, n=6):
    """A workbook whose column D carries scores — an assessment, not a run
    that has merely finished researching."""
    run = new_run(tmp_path, n=n)
    wb = run.open()
    cells = wb.selected_subcaps()
    for cell in cells:
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell)))
    # score them the way the assessment stage does: column D, one per subcap
    for i, cell in enumerate(cells):
        wb.update_row(cells and "P1_Subcap_Scoring", "SubCap_ID", cell,
                      {"Score": 2 + (i % 3)})
    return run, wb, cells


# ── the stage is a recorded fact, not an inference ───────────────────────

def test_a_new_workbook_records_that_it_is_at_the_research_stage(tmp_path):
    wb = new_run(tmp_path).open()
    assert wb.metadata()["stage"] == "research"
    assert C.stage_of(wb.metadata()) == "research"


def test_an_older_workbook_with_no_stage_key_reads_as_research(tmp_path):
    """A v4 workbook upgraded in place must not read as an assessment with
    three empty tabs."""
    assert C.stage_of({}) == "research"
    assert C.stage_of({"stage": "nonsense"}) == "research"


def test_the_three_grains_belong_to_the_assessment_stage():
    assert set(C.SHEET_STAGE) == {"Pillar_Summary", "Category_Detail",
                                  "Recommendations"}
    assert set(C.SHEET_STAGE.values()) == {"assessment"}


def test_a_research_run_is_not_asked_for_a_grain_it_may_not_produce(tmp_path):
    """Column D is empty at the research stage by contract rule 4, so asking
    a research run for a score grain asks it for something it is forbidden
    to produce."""
    from engine import completeness as K

    wb = new_run(tmp_path).open()
    verdicts = {r["sheet"]: r["verdict"] for r in K.check(wb)["sheets"]}
    for sheet in C.SHEET_STAGE:
        assert verdicts[sheet] == "OUT_OF_STAGE", (sheet, verdicts[sheet])
    assert not any(sheet in b for b in K.check(wb)["blocking"]
                   for sheet in C.SHEET_STAGE)


def test_a_research_workbook_carrying_assessment_rows_is_reported(tmp_path):
    """The other direction is a real problem: a research workbook that
    somehow carries a stated grain is claiming a figure the stage says
    cannot have been struck yet."""
    from engine import completeness as K

    wb = new_run(tmp_path).open()
    wb.append("Pillar_Summary", {"Pillar": "P1", "Pillar_Name": "",
                                 "Score": 3.1, "Weight_Pct": "",
                                 "Peer_Median": ""})
    out = K.check(wb)
    row = next(r for r in out["sheets"] if r["sheet"] == "Pillar_Summary")
    assert row["verdict"] == "AHEAD_OF_STAGE"
    assert any("Pillar_Summary" in b for b in out["blocking"])


def test_the_stage_cannot_be_set_to_assessment_with_no_scores(tmp_path):
    wb = new_run(tmp_path).open()
    with pytest.raises(GrainRefused, match="Column D is what the stage"):
        G.set_stage(wb, "assessment")


# ── the grains themselves ────────────────────────────────────────────────

def test_recompute_refuses_at_the_research_stage(tmp_path):
    run, wb, cells = _scored(tmp_path)
    with pytest.raises(GrainRefused, match="research stage"):
        G.recompute(wb)


def test_the_stated_grains_land_in_the_columns_the_app_reads(tmp_path):
    run, wb, cells = _scored(tmp_path)
    G.set_stage(wb, "assessment")
    out = G.recompute(wb)
    assert out["subcaps_scored"] == len(cells)
    assert out["pillars"] == 1 and out["categories"] >= 1

    pillars = [r for r in wb.rows("Pillar_Summary") if r.get("Pillar")]
    assert [r["Pillar"] for r in pillars] == ["P1"]
    assert pillars[0]["Score"] is not None

    cats = [r for r in wb.rows("Category_Detail") if r.get("Category_ID")]
    assert all(str(r["Category_ID"]).startswith("P1C") for r in cats)
    assert all(r["Pillar"] == "P1" for r in cats)


def test_the_app_parser_reads_the_grains_this_engine_writes(tmp_path):
    """The whole point of using the app's own header spellings."""
    sys.path.insert(0, "/home/user/Accelerate/apps/worker")
    from dma_worker.workbook_parser import parse_grain_summaries

    run, wb, cells = _scored(tmp_path)
    G.set_stage(wb, "assessment")
    G.recompute(wb)

    obs: list = []
    got = parse_grain_summaries(str(run.workbook_path), obs)
    assert got["pillars"], f"the parser read no pillar grain: " \
                           f"{[o.kind for o in obs]}"
    assert got["categories"], f"no category grain: {[o.kind for o in obs]}"
    assert got["pillars"][0]["pillar_id"] == "P1"
    assert got["pillars"][0]["score"] is not None
    assert all(c["category_id"].startswith("P1C") for c in got["categories"])


def test_recompute_refuses_a_workbook_with_no_scores(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    wb.set_metadata("stage", "assessment")     # forced past set_stage
    with pytest.raises(GrainRefused, match="no grain to state"):
        G.recompute(wb)


# ── the recommendations, projected rather than authored ──────────────────

def test_recommendations_project_the_reports_own_rows(tmp_path):
    run, wb, cells = _scored(tmp_path)
    eids = bank_evidence(wb, cells[0])
    sec = next(s for s in RS.SPECS["assessment"].sections
               if s.kind == "recommendation")
    for i in range(3):
        N.write(wb, "assessment", sec.id,
                _rec(sec.id, eids, report="assessment"),
                actor="report-assessment-producer", card=f"R-{i + 1}")
    G.set_stage(wb, "assessment")
    out = G.recommendations(wb)
    assert out["rows"] == 3
    rows = [r for r in wb.rows("Recommendations") if r.get("Rec_ID")]
    assert [r["Rec_ID"] for r in rows] == ["REC-R-1", "REC-R-2", "REC-R-3"]
    assert all(r["Rationale"] for r in rows), "the argument travels with it"


def test_recommendations_refuse_when_the_section_is_unwritten(tmp_path):
    run, wb, cells = _scored(tmp_path)
    G.set_stage(wb, "assessment")
    with pytest.raises(GrainRefused, match="nothing to project"):
        G.recommendations(wb)


def test_the_app_parser_reads_the_recommendations_this_engine_writes(
        tmp_path):
    sys.path.insert(0, "/home/user/Accelerate/apps/worker")
    from dma_worker.workbook_parser import parse_recommendations

    run, wb, cells = _scored(tmp_path)
    eids = bank_evidence(wb, cells[0])
    sec = next(s for s in RS.SPECS["assessment"].sections
               if s.kind == "recommendation")
    N.write(wb, "assessment", sec.id, _rec(sec.id, eids, report="assessment"),
            actor="report-assessment-producer", card="R-1")
    G.set_stage(wb, "assessment")
    G.recommendations(wb)

    obs: list = []
    got = parse_recommendations(str(run.workbook_path), obs)
    assert got, f"the parser read no recommendation: {[o.kind for o in obs]}"
    assert got[0]["rec_id"] == "REC-R-1", got[0]
    assert got[0]["payload"].get("rationale"), got[0]["payload"].keys()


# ── the report section that reads them says so ───────────────────────────

def test_the_assessment_report_names_the_grains_it_reads():
    """H4's grain lock forbids re-deriving a pillar figure by averaging its
    subcaps, so §3 must read what was STATED, not only the subcap sheets."""
    spec = RS.SPECS["assessment"]
    assert "Pillar_Summary" in spec.section("3").inputs
    assert "Category_Detail" in spec.section("3").inputs
    assert "Recommendations" in spec.section("7").inputs


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
