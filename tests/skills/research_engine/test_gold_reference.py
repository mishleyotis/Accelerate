"""The gold gate is calibrated to the reference it names — provably.

`engine/gold_standard.py` has cited this file since it was written
("a floor this gate demands that the Golden 1 package itself would fail is a
floor nobody measured, and is refused by the suite") and the file did not
exist (measured 2026-09-03). The floor it would have caught was live: a flat
60 distinct citations for both reports, while the Golden 1 research report
carries 47. Every threshold the gate demands is asserted here to be AT OR
BELOW what `references/templates/gold_reference.json` records the reference
meeting, and the engine's own artefacts are asserted to pass the gate's
structural checks.
"""
from __future__ import annotations

import json

import pytest

from engine import gold_standard as GS
from engine import report_spec as RS
from engine import reports as R
from engine import template as T

from fixtures import scored_run


@pytest.fixture(scope="module")
def gold() -> dict:
    return json.loads((T.TEMPLATES_DIR / "gold_reference.json").read_text())


def test_every_report_floor_is_at_or_below_what_golden_1_meets(gold):
    for kind in ("research", "assessment"):
        ref = gold["reports"][kind]
        floors = GS.depth_floors(kind)                 # the full-size floors
        assert floors["subcaps"] == gold["workbook"]["subcaps"]
        assert floors["citations"] <= ref["distinct_e_ids"], (kind, floors, ref)
        assert floors["words"] <= ref["words_paragraphs"], (kind, floors, ref)


def test_the_floors_scale_with_the_runs_size_and_never_vanish(gold):
    small = GS.depth_floors("research", subcaps=6)
    full = GS.depth_floors("research")
    assert 1 <= small["citations"] < full["citations"]
    assert small["words"] < full["words"]
    # the word floor never drops below the pinned Doc's own contract
    assert GS.depth_floors("assessment", subcaps=690)["words"] >= \
        RS.SPECS["assessment"].min_words


def test_every_gold_sheet_the_gate_demands_exists_in_the_reference(gold):
    have = set(gold["workbook"]["sheets"])
    assert set(GS.GOLD_SHEETS) <= have, set(GS.GOLD_SHEETS) - have


def test_the_exec_fields_the_gate_demands_fit_the_reference_dashboard(gold):
    assert len(GS.EXEC_FIELDS) <= gold["workbook"]["sheets"]["Executive_Summary"]["rows"]


def test_the_engines_own_coverage_map_passes_the_disclosure_gate(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    findings = GS.workbook_findings(wb.path)
    codes = {f["code"] for f in findings}
    assert "GS-WB-COVERAGE" not in codes, [str(f) for f in findings]
    assert "GS-WB-FINANCIALS" not in codes, [str(f) for f in findings]
    assert "GS-WB-NAMES" not in codes
    assert "GS-WB-SCORES" not in codes


def test_the_engines_own_workbook_emits_no_structural_blank_findings(tmp_path):
    """An engine-built assessment workbook must not fail GS-WB-EMPTY by
    construction: structurally optional blanks (an ABSENT firmographic's
    value, a peer row's quartiles, an issue's cap) are readable states."""
    run, wb, cells, ev = scored_run(tmp_path)
    empties = [str(f) for f in GS.workbook_findings(wb.path) if f["code"] == "GS-WB-EMPTY"]
    assert empties == [], empties


def test_the_renderers_citation_floor_is_the_gold_density(tmp_path, gold):
    run, wb, cells, ev = scored_run(tmp_path)
    n = len(wb.selected_subcaps())
    for key, kind in (("client_research", "research"), ("assessment", "assessment")):
        floor = R.citation_floor(wb, RS.SPECS[key])
        expected = -(-gold["reports"][kind]["distinct_e_ids"] * n // gold["workbook"]["subcaps"])
        assert floor == max(1, expected), (key, floor, expected)
        assert floor == GS.depth_floors(kind, subcaps=n)["citations"]


def test_the_shell_is_the_reference_chrome_and_is_pinned():
    import zipfile
    assert "report_shell.docx" in T.PINNED_FILES
    assert T.REPORT_SHELL.is_file()
    with zipfile.ZipFile(T.REPORT_SHELL) as z:
        names = z.namelist()
    assert any(n.startswith("word/fonts/") for n in names)
    assert "word/header1.xml" in names and "word/footer1.xml" in names
    assert T.pinned_digest()["report_shell.docx"]
