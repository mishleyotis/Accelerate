"""The duplicate-evidence rule: duplicate BY CONTENT, never by id alone.

Owner adjudication 2026-08-20, from the first live vetting: evidence ids
are unique per client, and one id cited from many tabs is a reference —
43 false REFUSEs said otherwise and blocked a clean package. What refuses
is one id DEFINED twice with DIFFERENT content in a register tab.
"""
import sys
from pathlib import Path

import pytest

openpyxl = pytest.importorskip("openpyxl")

VET_DIR = (Path(__file__).resolve().parents[2]
           / "skills" / "dma-surface-production" / "scripts")
sys.path.insert(0, str(VET_DIR))
import vet_workbooks as vw  # noqa: E402


def _workbook(tmp_path, register_rows, reference_rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Evidence_Master"
    ws.append(["evidence_id", "source_name", "excerpt"])
    for row in register_rows:
        ws.append(row)
    ref = wb.create_sheet("P1_Subcap_Scoring")
    ref.append(["cell_id", "score", "evidence_id"])
    for row in reference_rows:
        ref.append(row)
    wb.create_sheet("Run_Metadata").append(["key", "value", "note"])
    wb.create_sheet("Recommendations").append(["rec", "why", "who"])
    path = tmp_path / "scoring.xlsx"
    wb.save(path)
    return path


def _vet(path):
    vw.findings.clear()
    vw.vet_scoring(path)
    return list(vw.findings)


def test_cross_tab_references_are_never_a_finding(tmp_path):
    path = _workbook(
        tmp_path,
        register_rows=[["E-001", "NCUA call report", "a real excerpt"]],
        reference_rows=[["P1C1.1", 3.2, "E-001"],
                        ["P1C1.2", 2.8, "E-001"],
                        ["P1C2.1", 4.0, "E-001"]])
    found = _vet(path)
    assert not any("evidence id" in msg for lvl, msg in found
                   if lvl == "REFUSE"), found


def test_identical_redefinition_warns_and_names_the_client_prefix(tmp_path):
    path = _workbook(
        tmp_path,
        register_rows=[["E-001", "NCUA call report", "a real excerpt"],
                       ["E-001", "NCUA call report", "a real excerpt"]],
        reference_rows=[["P1C1.1", 3.2, "E-001"]])
    found = _vet(path)
    assert not any("evidence id" in m for lvl, m in found if lvl == "REFUSE")
    warn = [m for lvl, m in found if lvl == "WARN" and "identical" in m]
    assert warn and "prefix" in warn[0]


def test_conflicting_redefinition_refuses_by_name(tmp_path):
    path = _workbook(
        tmp_path,
        register_rows=[["E-002", "annual report", "one excerpt"],
                       ["E-002", "press release", "a different excerpt"]],
        reference_rows=[["P1C1.1", 3.2, "E-002"]])
    found = _vet(path)
    refuse = [m for lvl, m in found
              if lvl == "REFUSE" and "DIFFERENT content" in m]
    assert refuse and "E-002" in refuse[0]


# ── which *score* columns are maturity scores (Houlihan Lokey, 2026-08-22) ──
#
# The range check matched any header containing "score" and refused the
# package for "26 score(s) outside 1.0–5.0". The 26 were `Subcaps_Scored`,
# a COUNT of sub-capabilities scored (14–25), and `Priority_Score`, a
# recommendation ranking on its own scale (6.0–7.05). Neither is a maturity
# score; neither was dirty; production halted anyway. Across 111 corpus
# clients there are 130 distinct *score* headers, so the substring alone was
# never going to separate them.


def _scoring_book(tmp_path, header, values, tab="Category_Detail"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = tab
    ws.append(["cell_id", "label", header])
    for i, v in enumerate(values):
        ws.append([f"P1C1.{i + 1}", "Some capability", v])
    for extra in ("Evidence_Master", "Run_Metadata", "Recommendations"):
        wb.create_sheet(extra).append(["a", "b", "c"])
    path = tmp_path / "scoring.xlsx"
    wb.save(path)
    return path


def _levels(findings):
    return {lvl for lvl, _ in findings}


@pytest.mark.parametrize("header,values", [
    ("Subcaps_Scored", [14, 15, 20, 21, 23, 25]),      # a count
    ("Priority_Score", [6.0, 6.25, 6.3, 6.45, 7.05]),  # its own scale
    ("ERS_Score", [7.5, 8.0, 9.25]),                   # evidence strength
    ("Score_Delta", [-1.5, 0.75, 2.0]),                # a difference
    ("Max_Score", [5.0, 5.0, 5.0]),                    # the ceiling
    ("Weighted_Score", [12.4, 18.0]),                  # score x weight
    ("Scored_Count", [16, 22]),                        # a count
    ("Target_Score", [7, 8]),                          # an aspiration
])
def test_a_column_named_like_a_score_but_measuring_something_else(
        tmp_path, header, values):
    findings = _vet(_scoring_book(tmp_path, header, values))
    assert "REFUSE" not in _levels(findings), (
        f"{header} must not refuse the package: {findings}")
    assert any(header in msg for _, msg in findings), (
        "the decision to skip the column has to be visible, not silent")


def test_a_real_maturity_score_out_of_range_still_refuses(tmp_path):
    """The negative control. If this ever stops refusing, the exclusion list
    has eaten the check it was meant to make precise."""
    findings = _vet(_scoring_book(tmp_path, "Score", [3.2, 4.1, 6.4, 2.0]))
    assert "REFUSE" in _levels(findings)
    assert any("outside 1.0" in msg for _, msg in findings)


def test_a_clean_maturity_score_column_passes_quietly(tmp_path):
    findings = _vet(_scoring_book(tmp_path, "Score", [1.0, 2.5, 3.2, 5.0]))
    assert "REFUSE" not in _levels(findings)


def test_a_maturity_column_with_no_in_range_value_is_a_wrong_column(tmp_path):
    """A column where EVERY value is out of range is a header this script
    failed to recognise, not a package with every measurement wrong. Saying
    "26 scores are dirty" about a count sends the reader to fix the data
    instead of the vocabulary — which is exactly what happened."""
    findings = _vet(_scoring_book(tmp_path, "GCBC_Score", [40, 55, 61]))
    assert "REFUSE" not in _levels(findings)
    assert any("not a maturity score" in msg for _, msg in findings)


@pytest.mark.parametrize("header", [
    "score", "final_score", "raw_score", "prior_score", "score_1_to_5",
    "pre_cap_score", "post_cap_score", "overall_score", "category_score",
])
def test_the_measured_maturity_headers_are_still_checked(header):
    """The corpus's real 1–5 columns, by frequency. Excluding one of these
    by accident would silently stop range-checking the actual scores."""
    assert vw.is_maturity_score_column(header)


@pytest.mark.parametrize("header", [
    "subcaps_scored", "priority_score", "ers_score", "score_delta",
    "max_score", "target_score", "weighted_score", "score_rationale",
    "categories_scored", "scored/total", "peer_score",
])
def test_the_measured_non_maturity_headers_are_excluded(header):
    assert not vw.is_maturity_score_column(header)
