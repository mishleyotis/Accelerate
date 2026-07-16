"""Tests for the catalogue loader parsers + validators using a synthetic
in-memory workbook (so we don't depend on a real v7.0 xlsx being present).
"""
from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import Workbook

# Make the workers/ package importable for tests.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workers.ccg_loader.parsers import (  # noqa: E402
    derive_l1_id,
    parse_capability_map,
    parse_maturity_bands,
    parse_value_chain,
    slug,
)
from workers.ccg_loader.validators import (  # noqa: E402
    validate_fk_closure,
    validate_pillar_totals,
    validate_value_chain_subverticals,
)

# ---------- helpers ----------

def make_wb_with_sheet(title: str, headers: list[str], rows: list[list]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(headers)
    for r in rows:
        ws.append(r)
    return wb


# ---------- parser tests ----------

class TestSlug:
    def test_lowercase_and_separators(self) -> None:
        assert slug("Customer Identity & Auth") == "customer-identity-auth"

    def test_strip_leading_trailing(self) -> None:
        assert slug("  !! Hello world !!  ") == "hello-world"


class TestDeriveL1Id:
    def test_format(self) -> None:
        assert derive_l1_id("P1C1", "Strategy & Vision") == "P1C1::strategy-vision"


class TestParseCapabilityMap:
    def test_minimal_workbook(self) -> None:
        headers = [
            "Category ID", "Category", "L1 Capability", "SubCap ID",
            "SubCap Name", "Description", "Solution Type", "Tier",
        ]
        rows = [
            ["P1C1", "Strategy & Vision", "Digital Strategy",
             "P1C1.1.1", "Vision Setting", "Sets the vision",
             "Traditional", "T1"],
            ["P1C1", "Strategy & Vision", "Digital Strategy",
             "P1C1.1.2", "OKR Cascade", "OKRs from vision",
             "Hybrid", "T1"],
            ["P1C2", "Risk & Compliance", "Risk Posture",
             "P1C2.1.1", "Risk Inventory", "Inventory of risks",
             "Traditional", "T1"],
            ["P1C2", "Risk & Compliance", "Risk Posture",
             "P1C2.1.1-T2-CIB", "Risk Inventory — CIB", "CIB variant",
             "Traditional", "T2-CIB"],
        ]
        wb = make_wb_with_sheet("2_Capability_Map", headers, rows)
        res = parse_capability_map(wb.active, "v7.0", "P1")

        # Categories: 2 unique
        cats = [r for r in res.rows if r["__target__"] == "ccg_categories"]
        assert {c["category_id"] for c in cats} == {"P1C1", "P1C2"}

        # L1: 2 unique (one per category here)
        l1s = [r for r in res.rows if r["__target__"] == "ccg_l1_capabilities"]
        assert len(l1s) == 2

        # Subcaps: 4 rows
        subcaps = [r for r in res.rows if r["__target__"] == "ccg_subcaps"]
        assert {s["subcap_id"] for s in subcaps} == {
            "P1C1.1.1", "P1C1.1.2", "P1C2.1.1", "P1C2.1.1-T2-CIB",
        }
        # T2 variant carries the right tier
        t2 = next(s for s in subcaps if s["subcap_id"] == "P1C2.1.1-T2-CIB")
        assert t2["tier"] == "T2-CIB"

    def test_canonical_l1_id_preferred_when_present(self) -> None:
        headers = [
            "Category ID", "Category", "L1 Capability", "L1_ID", "SubCap ID",
            "SubCap Name", "Description", "Solution Type", "Tier",
        ]
        rows = [
            ["P1C1", "Strategy", "Digital Strategy", "L1-STRAT-001",
             "P1C1.1.1", "Vision Setting", "...", "Traditional", "T1"],
        ]
        wb = make_wb_with_sheet("2_Capability_Map", headers, rows)
        res = parse_capability_map(wb.active, "v7.0", "P1")

        l1s = [r for r in res.rows if r["__target__"] == "ccg_l1_capabilities"]
        # The canonical L1_ID wins over the derived slug (resolved decision 7).
        assert l1s[0]["l1_id"] == "L1-STRAT-001"

    def test_unknown_solution_type_falls_back_with_warning(self) -> None:
        headers = ["Category ID", "Category", "L1 Capability", "SubCap ID",
                   "SubCap Name", "Description", "Solution Type", "Tier"]
        rows = [["P1C1", "Strategy", "Digital Strategy", "P1C1.1.1",
                 "X", "...", "Headlesss",  # typo
                 "T1"]]
        wb = make_wb_with_sheet("2_Capability_Map", headers, rows)
        res = parse_capability_map(wb.active, "v7.0", "P1")
        subcap = next(r for r in res.rows if r["__target__"] == "ccg_subcaps")
        assert subcap["solution_type"] == "Traditional"
        assert any(w["kind"] == "unknown_solution_type" for w in res.warnings)


class TestParseMaturityBands:
    def test_basic(self) -> None:
        headers = ["SubCap ID", "Band", "Narrative", "Features"]
        rows = [
            ["P1C1.1.1", "M1", "ad-hoc", "no formal vision"],
            ["P1C1.1.1", "M3", "established AI-assisted", "AI tools support vision"],
            ["P1C1.1.1", "M9", "bogus band", "ignored"],
        ]
        wb = make_wb_with_sheet("3_Maturity_Scoring_Bands", headers, rows)
        res = parse_maturity_bands(wb.active, "v7.0", "P1")
        assert len(res.rows) == 2
        assert any(r["band"] == "M1" for r in res.rows)
        assert any(r["band"] == "M3" for r in res.rows)
        assert any(w["kind"] == "bad_band_row" for w in res.warnings)


class TestParseValueChain:
    def test_long_form_emission(self) -> None:
        headers = ["SubCap ID", "RB", "CU", "CIB"]
        rows = [
            ["P1C1.1.1", "▌Sales │ Onboarding", "▌Sales", None],
            ["P1C1.1.2", "▌Service", None, "▌Sales │ Trading │ Post-Trade"],
        ]
        wb = make_wb_with_sheet("21_Value_Chain_Mapping", headers, rows)
        res = parse_value_chain(wb.active, "v7.0", "P1")

        # Long-form: (subcap_id, subvertical) per non-null cell
        rows_out = res.rows
        assert {(r["subcap_id"], r["subvertical_code"]) for r in rows_out} == {
            ("P1C1.1.1", "RB"),
            ("P1C1.1.1", "CU"),
            ("P1C1.1.2", "RB"),
            ("P1C1.1.2", "CIB"),
        }
        cib = next(r for r in rows_out
                   if r["subcap_id"] == "P1C1.1.2" and r["subvertical_code"] == "CIB")
        assert cib["value_chain_stages"] == ["Sales", "Trading", "Post-Trade"]


# ---------- validator tests ----------

class TestValidators:
    def test_pillar_totals_pass_when_exact(self) -> None:
        # Synthesize 851 subcaps with the right per-pillar distribution
        from workers.ccg_loader.validators import EXPECTED_PILLAR_SUBCAP_COUNTS

        subcaps = []
        for pillar, count in EXPECTED_PILLAR_SUBCAP_COUNTS.items():
            for i in range(count):
                subcaps.append({"subcap_id": f"{pillar}C1.1.{i+1}"})
        report = validate_pillar_totals(subcaps)
        assert report.ok, report.failed
        assert "total_subcap_count" in report.passed

    def test_pillar_totals_fail_on_short_pillar(self) -> None:
        subcaps = [{"subcap_id": f"P1C1.1.{i+1}"} for i in range(204)]  # 1 short
        report = validate_pillar_totals(subcaps)
        assert not report.ok
        assert any(f["gate"] == "pillar_subcap_count.P1" for f in report.failed)

    def test_fk_closure_no_orphans(self) -> None:
        subcaps = [{"subcap_id": "P1C1.1.1"}, {"subcap_id": "P1C1.1.2"}]
        refs = ["P1C1.1.1", "P1C1.1.1", "P1C1.1.2"]
        report = validate_fk_closure(subcaps, refs)
        assert report.ok

    def test_fk_closure_with_orphans(self) -> None:
        subcaps = [{"subcap_id": "P1C1.1.1"}]
        refs = ["P1C1.1.1", "P9C9.9.9", "P8C1.1.1"]
        report = validate_fk_closure(subcaps, refs)
        assert not report.ok
        failed = report.failed[0]
        assert failed["orphan_count"] == 2

    def test_value_chain_unknown_subvertical_warns_not_fails(self) -> None:
        vc = [
            {"subcap_id": "P1C1.1.1", "subvertical_code": "RB"},
            {"subcap_id": "P1C1.1.1", "subvertical_code": "WX"},  # unknown
        ]
        report = validate_value_chain_subverticals(vc)
        # Unknown subverticals are warnings, not failures (resolved decision 8).
        assert report.ok
        assert any(w["new_codes"] == ["WX"] for w in report.warnings)
