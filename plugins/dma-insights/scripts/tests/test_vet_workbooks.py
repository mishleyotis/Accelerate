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
