"""`firmographics_parsed_facts` — the parsed_facts selection that decides
which firmographics fields survive ingest into the JSONB bag.

Regression guard for the 2026-06-09 fix: the prior hardcoded 3-key
allowlist (total_assets / employees_approx / branches) silently dropped
every new parser extra (total_deposits, roe, efficiency_ratio,
net_income, sub_vertical, …) before it reached the DB. The selection is
now exclusion-based so future extras persist automatically.
"""
from __future__ import annotations

from app.services.parsers.firmographics_facts import firmographics_parsed_facts


def test_keeps_extras_and_drops_columned_fields() -> None:
    firm_dict = {
        # dedicated-column / specially-handled → excluded
        "hq": "Salt Lake City, Utah",
        "primary_regulator": "OCC",
        "leadership": [{"name": "Jane", "title": "CEO"}],
        "narrative_md": "long prose ...",
        # extras + columnless declared fields → kept
        "legal_name": "Zions Bancorporation, N.A.",
        "ticker": "ZION",
        "total_assets": "$87B",
        "employees_approx": "~10,000",
        "branches": "~400",
        "total_deposits": "$73B",
        "roe": "14.5%",
        "efficiency_ratio": "61%",
        "net_income": "$824M (2024)",
        "sub_vertical": "Regional Banks",
        "size_tier": "Mega (>$50B)",
        "financials_as_of": "Q4 2024",
        "affiliate_banks": ["Zions Bank", "Amegy Bank"],
        # empties → dropped
        "founded": None,
        "cra_rating": "",
        "website": None,
    }
    pf = firmographics_parsed_facts(firm_dict)

    for col in ("hq", "primary_regulator", "leadership", "narrative_md"):
        assert col not in pf, f"{col} owns a column / handler; must not duplicate"
    for empty in ("founded", "cra_rating", "website"):
        assert empty not in pf, f"{empty} is empty; must be dropped"
    for kept in (
        "ticker", "total_assets", "total_deposits", "roe", "efficiency_ratio",
        "net_income", "sub_vertical", "size_tier", "financials_as_of",
        "employees_approx", "branches", "legal_name",
    ):
        assert pf[kept] == firm_dict[kept]
    # list extras survive (JSONB can hold them)
    assert pf["affiliate_banks"] == ["Zions Bank", "Amegy Bank"]


def test_empty_when_all_columned_or_empty() -> None:
    assert firmographics_parsed_facts(
        {"hq": "x", "primary_regulator": "y", "leadership": [], "narrative_md": ""}
    ) == {}
