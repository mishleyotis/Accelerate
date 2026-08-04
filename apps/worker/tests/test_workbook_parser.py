"""Stage 1.3 QA bullets as tests, on a SANITIZED synthetic workbook built
in-test (modeled on the real Claude-DMA shape; no client data in the repo):

- Every score row carries a source cell and all four grain ids.
- A missing score is skipped, never defaulted to zero.
- scored_cells is stamped and differs from catalogue cells where toggles
  applied (toggled-out variants are not observations).
"""
import sys
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.workbook_parser import parse_scoring_workbook


@pytest.fixture()
def synthetic_workbook(tmp_path):
    wb = openpyxl.Workbook()
    sc = wb.active
    sc.title = "2_Scorecard"
    sc["A1"] = "Maturity Scorecard"
    sc["A4"] = "Overall Effective Score"
    sc["A5"] = 2.4517
    sc["A14"] = "Subcapability scorecard"
    sc.append([])  # r15 placeholder; real header written below
    hdr = ["Pillar", "Pillar_Category", "L1_Capability", "Sub_Cap_ID", "Sub_Cap_Name",
           "Tier", "Works", "Fails", "Value", "Contradicts", "Corroborates",
           "Diagnostic_Score", "Evidence_Quality", "Descriptor_Fit_Level",
           "Descriptor_Fit_Rationale", "Contradiction_Check", "Final_Maturity_Override",
           "Override_Rationale", "Effective_Score"]
    for i, h in enumerate(hdr, 1):
        sc.cell(row=15, column=i, value=h)
    rows = [
        # scored
        ("Pillar 1", "Strategy", "Decisions", "P1C1.1.1", "Fake Board Packs", "T1",
         3, 2, 2, 3, 4, 2.65, 2.8, 3.0, "M2-ish", "Checked", None, None, 2.97),
        # attempted, unscored (ladder ran, nothing found) -> observation
        ("Pillar 2", "CX", "Onboarding", "P2C1.1.2", "Fake Onboarding", "T1",
         None, None, None, None, None, None, None, None, None, None, None, None, None),
        # toggled-out sub-vertical variant -> excluded, not an observation
        ("Pillar 2", "CX", "Channels", "P2C2.9.CU1", "Fake CU Variant", "T2",
         None, None, None, None, None, None, None, None, None, None, None, None, None),
        # unparseable score cell -> observation, row skipped
        ("Pillar 4", "Data", "Quality", "P4C1.2.1", "Fake Data Quality", "T1",
         2, 2, 1, 2, 2, 1.9, 2.0, 2.0, "M2", "Checked", None, None, "n/a"),
    ]
    for r in rows:
        sc.append(list(r))

    a = wb.create_sheet("3_Assessment")
    a["A1"] = "Diagnostic Assessment"
    ahdr = ["Question_ID", "Pillar", "Pillar_Category", "L1_Capability", "Sub_Cap_ID",
            "Sub_Cap_Name", "Tier", "Facet", "Weight", "Diagnostic_Question",
            "Curve_Placement_Guide", "Why_It_Matters", "Internal_Evidence_to_Request",
            "Public_Evidence_to_Inspect", "Public_Search_Probes", "Public_Visibility",
            "Discovery_Notes", "Evidence_References", "Facet_Maturity_Score",
            "Evidence_Quality", "Contradiction_Status", "Assessor_Rationale"]
    for i, h in enumerate(ahdr, 1):
        a.cell(row=4, column=i, value=h)
    a.append(["P1C1.1.1-W", "Pillar 1", "Strategy", "Decisions", "P1C1.1.1",
              "Fake Board Packs", "T1", "Works", 0.3, "q", "g", "w", "i", "p", "s",
              "v", "n", "E-C001, E-C002", 3.0, 4.0, "None", "Solid packs"])
    a.append(["P1C1.1.1-F", "Pillar 1", "Strategy", "Decisions", "P1C1.1.1",
              "Fake Board Packs", "T1", "Fails", 0.2, "q", "g", "w", "i", "p", "s",
              "v", "n", "E-C001", 2.0, 3.0, "None", "Some gaps"])
    a.append(["P2C1.1.2-W", "Pillar 2", "CX", "Onboarding", "P2C1.1.2",
              "Fake Onboarding", "T1", "Works", 0.3, "q", "g", "w", "i", "p", "s",
              "v", "n", None, None, None, None, "NO_EVIDENCE - ladder run"])
    a.append(["P2C2.9.CU1-W", "Pillar 2", "CX", "Channels", "P2C2.9.CU1",
              "Fake CU Variant", "T2", "Works", 0.3, "q", "g", "w", "i", "p", "s",
              "v", None, None, None, None, None, None])
    a.append(["P4C1.2.1-W", "Pillar 4", "Data", "Quality", "P4C1.2.1",
              "Fake Data Quality", "T1", "Works", 0.3, "q", "g", "w", "i", "p", "s",
              "v", "n", "E-C009", 2.0, 2.0, "None", "ok"])
    path = tmp_path / "synthetic_scoring_workbook.xlsx"
    wb.save(path)
    return str(path)


def test_every_score_row_carries_source_cell_and_all_four_grain_ids(synthetic_workbook):
    p = parse_scoring_workbook(synthetic_workbook)
    assert p.scored_cells == 1
    s = p.scores[0]
    assert s.subcap_id == "P1C1.1.1" and s.score == Decimal("2.97")
    assert s.source_cell == "2_Scorecard!S16"
    assert (s.pillar_id, s.category_id, s.capability_id) == ("P1", "P1C1", "P1C1.1")
    assert s.evidence_refs == ["E-C001", "E-C002"]
    assert len(s.facets) == 2 and s.facets[0].source_cell.startswith("3_Assessment!S")


def test_missing_score_is_skipped_never_zeroed_and_observed(synthetic_workbook):
    p = parse_scoring_workbook(synthetic_workbook)
    assert all(s.score is not None for s in p.scores)          # nothing defaulted
    missing = [o for o in p.observations if o.kind == "missing_score"]
    assert [o.subcap_id for o in missing] == ["P2C1.1.2"]
    unparseable = [o for o in p.observations if o.kind == "unparseable_cell"]
    assert [o.subcap_id for o in unparseable] == ["P4C1.2.1"]


def test_toggled_out_variant_is_not_an_observation(synthetic_workbook):
    p = parse_scoring_workbook(synthetic_workbook)
    assert p.toggled_out == ["P2C2.9.CU1"]
    assert all(o.subcap_id != "P2C2.9.CU1" for o in p.observations)
    # scored_cells (1) < the 4 catalogue rows present — the toggle explains it
    assert p.scored_cells < 4


def test_composite_read_from_its_cell_raw(synthetic_workbook):
    p = parse_scoring_workbook(synthetic_workbook)
    assert p.composite == Decimal("2.4517")                    # raw; rounded ONCE at persist
    assert p.composite_source_cell == "2_Scorecard!A5"
