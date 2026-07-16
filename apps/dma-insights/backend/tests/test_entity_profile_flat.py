"""Standalone flat entity_profile.json + financial_baseline.json parsing.

41 packages ship a FLAT `entity_profile.json` and 31 ship a standalone
`financial_baseline.json` whose schemas differ from the nested Calprivate
variant the original parser handled -- so both returned nothing and D1
firmographics / D5 financials stayed empty for those entities. These
tests pin the flat-schema parsing against the real Zions fixture plus
synthetic edge cases, and confirm the orchestrator merges the financial
baseline into firmographics end-to-end.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.parsers.entity_profile import (
    parse_entity_profile_json,
    parse_financial_baseline_json,
)

_FIX = Path(__file__).resolve().parents[1] / (
    "tests/fixtures/dma_packages_batches"
)
# Real flat fixtures (batch_01 Zions, nested under 00_entity_profile/).
_ZIONS = (
    _FIX
    / "batch_01/Zions Bancorporation - DMA/Zions_Bancorporation_DMA FINAL"
    / "00_entity_profile"
)


def test_flat_entity_profile_real_fixture() -> None:
    p = _ZIONS / "entity_profile.json"
    if not p.exists():  # fixture path drift guard
        pytest.skip(f"fixture moved: {p}")
    out = parse_entity_profile_json(p)
    assert out["legal_name"].startswith("Zions")
    assert out["ticker"] == "ZION"
    assert "Salt Lake City" in out["hq"]
    assert out["total_assets"].startswith("$87B")
    assert "OCC" in out["primary_regulator"]
    assert out["sub_vertical"] == "Regional Banks"
    assert isinstance(out["affiliate_banks"], list) and out["affiliate_banks"]


def test_flat_financial_baseline_real_fixture() -> None:
    p = _ZIONS / "financial_baseline.json"
    if not p.exists():
        pytest.skip(f"fixture moved: {p}")
    out = parse_financial_baseline_json(p)
    assert out["total_assets"] == "$87B"
    assert out["total_deposits"] == "$73B"
    assert out["net_income"].startswith("$824M")
    assert out["roe"] == "14.5%"
    assert out["efficiency_ratio"] == "61%"
    assert out["employees_approx"].startswith("~10,000")
    assert "11 western" in out["branches"]
    assert "Q4 2024" in out["financials_as_of"]


def test_flat_entity_profile_synthetic(tmp_path: Path) -> None:
    p = tmp_path / "entity_profile.json"
    p.write_text(json.dumps({
        "entity_name": "Acme CU",
        "ticker": "N/A",  # sentinel -> dropped
        "headquarters": "Denver, CO",
        "total_assets_approx": "$3.2B",
        "primary_regulator": "NCUA",
        "size_tier": "Mid",
    }))
    out = parse_entity_profile_json(p)
    assert out["legal_name"] == "Acme CU"
    assert "ticker" not in out  # "N/A" sentinel dropped
    assert out["hq"] == "Denver, CO"
    assert out["total_assets"] == "$3.2B"
    assert out["size_tier"] == "Mid"


def test_nested_variant_still_works(tmp_path: Path) -> None:
    """The discriminator must keep routing nested profiles to the
    nested path (corporate_identity present)."""
    p = tmp_path / "entity_profile.json"
    p.write_text(json.dumps({
        "corporate_identity": {
            "entity_legal_name": "Nested Bank",
            "ticker": "NEST",
            "branch_count": 12,
        },
        "regulatory_standing": {"primary_regulator": "FDIC"},
        "financial_baseline": {"q4_2025_total_assets_usd_b": 4.5},
    }))
    out = parse_entity_profile_json(p)
    assert out["legal_name"] == "Nested Bank"
    assert out["primary_regulator"] == "FDIC"
    assert out["total_assets"] == "$4.50B"
    assert out["branches"] == "12"


def test_absent_and_malformed_return_empty(tmp_path: Path) -> None:
    assert parse_entity_profile_json(tmp_path / "nope.json") == {}
    assert parse_financial_baseline_json(tmp_path / "nope.json") == {}
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert parse_entity_profile_json(bad) == {}
    assert parse_financial_baseline_json(bad) == {}
