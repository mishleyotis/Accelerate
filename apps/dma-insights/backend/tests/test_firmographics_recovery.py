"""Unit tests for the DB-prose firmographics recovery ladders (2026-07-02).

Pure, stdlib-only extractors that heal the residual founded / hq / geography /
footprint / size_tier / provenance nulls from the entity's OWN persisted prose
(narrative + parsed facts + financial-highlight lines). No DB, no package on
disk — the honest-null contract is that a field with no signal stays NULL.
"""
from __future__ import annotations

from app.scripts import derive_financials as df
from app.services import entity_healing as eh

# ── founded — a founding YEAR behind a founding verb, not a tenure/tech year ──

def test_prose_founded_year_matches_founding_cue():
    assert eh.prose_founded_year("Alma Bank was founded in 2007 to serve") == "2007"
    assert eh.prose_founded_year("Acuity, headquartered in WI. Founded in 1925 as") == "1925"
    assert eh.prose_founded_year("a bank incorporated in 1977, with") == "1977"
    assert eh.prose_founded_year("Established: 2009 (as a merger)") == "2009"


def test_prose_founded_year_rejects_non_founding_years():
    # CEO tenure / tech-adoption years are NOT founding years
    assert eh.prose_founded_year("CEO Mary Phillips (since 2021, named)") is None
    assert eh.prose_founded_year("cloud-first since 2019, AI later") is None
    assert eh.prose_founded_year("90% of whom joined since the 2021 transformation") is None
    assert eh.prose_founded_year("no year at all here") is None


# ── hq — City, ST / City ST / State from a headquartered/based/HQ cue ─────────

def test_prose_hq_location_variants():
    assert eh.prose_hq_location("headquartered in Sheboygan, Wisconsin. Founded") \
        == "Sheboygan, Wisconsin"
    assert eh.prose_hq_location("HQ: Poughkeepsie, NY trajectory_prose") == "Poughkeepsie, NY"
    assert eh.prose_hq_location("HQ Denver CO) financial_highlights") == "Denver CO"
    assert eh.prose_hq_location("A bank with no location cue anywhere") is None


# ── geography — states / region / N states ───────────────────────────────────

def test_prose_geography_states_region_count():
    assert eh.prose_geography("operations across Texas and Ohio today") == "Texas, Ohio"
    assert eh.prose_geography("a Mid-Atlantic community bank") == "Mid-Atlantic"
    assert eh.prose_geography("serving in 17 states nationwide") == "17 states"
    assert eh.prose_geography("no place named at all") is None


# ── footprint — scalar string from phrase / list / geography ─────────────────

def test_derive_footprint_prefers_explicit_then_geography():
    assert eh.derive_footprint(None, "7 states (MI/OH/IN/NV)") == "MI, OH, IN, NV"
    assert eh.derive_footprint("Utah", "no explicit footprint phrase") == "Utah"
    assert eh.derive_footprint(None, "nothing usable") is None


# ── HQ column backfill from parsed_facts (the 47%->covered extraction fix) ──
# Fixtures are the REAL corpus candidate strings the audit surfaced for null-HQ
# clients: a curated hq, an explanatory-clause footprint, a street address, and
# the region/national/multi-state values that must stay footprint (honest-null).

def test_derive_hq_prefers_curated_hq_fact():
    assert eh.derive_hq_address({"hq": "Poughkeepsie, NY"}) == "Poughkeepsie, NY"
    # a street-address HQ is a fine, more-specific value
    assert eh.derive_hq_address(
        {"hq": "150 Hilltop Rd, St. Joseph MI"}) == "150 Hilltop Rd, St. Joseph MI"


def test_derive_hq_trims_explanatory_clause_from_footprint():
    # ccu ships no hq key; footprint leads with the real HQ city + a trailing clause
    assert eh.derive_hq_address(
        {"footprint": "Lake Forest, IL — state-chartered, national digital reach "
                      "(open charter)"}) == "Lake Forest, IL"


def test_derive_hq_mines_prose_when_no_parsed_fact():
    assert eh.derive_hq_address(
        {}, hay="The bank is headquartered in Sheboygan, Wisconsin. Founded 1930.") \
        == "Sheboygan, Wisconsin"


def test_derive_hq_rejects_multistate_footprint_and_national_descriptors():
    # a multi-state footprint is NOT an HQ (stays the footprint, surfaced apart)
    assert eh.derive_hq_address({"footprint": "NY, FL, VT, MA, NJ"}) is None
    # full-state-name lists are ambiguous ("New York" the city vs state) → skip
    assert eh.derive_hq_address({"geography": "New York, Nevada, Pennsylvania"}) is None
    assert eh.derive_hq_address({"footprint": "National (all 50 US states)"}) is None
    assert eh.derive_hq_address({"geography": "Western WA / Puget Sound"}) is None
    assert eh.derive_hq_address({}) is None


def test_derive_hq_reads_structured_dict_hq_fact():
    # virtuity ships hq as a dict {address, primary_city, state, …}
    assert eh.derive_hq_address(
        {"hq": {"address": "Westlake Village, CA / Surprise, AZ",
                "primary_city": "San Diego", "state": "California"}}) \
        == "San Diego, California"


def test_hq_is_plausible_rejects_dict_repr_and_ranking_phrase():
    assert eh.hq_is_plausible("Rockland, MA")
    assert eh.hq_is_plausible("150 Hilltop Rd, St. Joseph MI")     # street address ok
    assert not eh.hq_is_plausible("Texas by asset size")           # a ranking phrase
    assert not eh.hq_is_plausible("{'address': 'Westlake Village, CA'}")  # dict repr
    assert not eh.hq_is_plausible("")
    assert not eh.hq_is_plausible(None)


# ── revenue — annual only; a quarterly (Q#) figure is never labelled annual ──

def test_prose_revenue_accepts_annual():
    assert eh.prose_revenue("FY2024 annual revenue of $3.4B, up 8%") == 3.4e9
    assert eh.prose_revenue("The broker reported $850M in annual revenue.") == 850e6


def test_prose_revenue_rejects_quarterly():
    # Regions symptom: a Q2 figure must NOT become the annual revenue_usd.
    assert eh.prose_revenue("Q2 2025: $1.9B total revenue | +12% YoY") is None
    assert eh.prose_revenue("second quarter revenue of $500M") is None
    assert eh.prose_revenue("quarterly revenue reached $1.2B") is None


# ── assets — a size-tier band edge is never a point estimate ─────────────────

def test_prose_assets_rejects_tier_band_edge_prefers_actual():
    # The upper edge of a "$100B-$200B" tier band (real fixture uses a U+2013
    # en-dash) is NOT the entity's assets; the balance-sheet actual wins.
    text = (
        "Size Tier | Super-Regional ($100B–$200B Assets)\n"  # noqa: RUF001
        "Primary Metric | $157.3B Total Assets (FY2024)\n"
        "NYSE: RF | Birmingham, Alabama | $157.3B Assets"
    )
    assert eh.prose_assets(text) == 157.3e9


def test_prose_assets_band_only_returns_none():
    # A tier band with no balance-sheet actual yields nothing here (the
    # size_tier fallback in prose_primary_metric handles that case, labelled).
    assert eh.prose_assets("Size Tier: Super-Regional ($100B–$200B Assets)") is None  # noqa: RUF001


def test_prose_assets_plain_figure_still_extracts():
    assert eh.prose_assets("The bank holds $4.5B in total assets today.") == 4.5e9


# ── size_tier — assets bands preferred, headcount fallback ───────────────────

def test_derive_size_tier_bands():
    assert eh.derive_size_tier(300e9, None) == "mega"
    assert eh.derive_size_tier(87e9, None) == "large"
    assert eh.derive_size_tier(12e9, None) == "mid-size"
    assert eh.derive_size_tier(3.2e9, None) == "community"
    assert eh.derive_size_tier(None, 15000) == "large"
    assert eh.derive_size_tier(None, 250) == "community"
    assert eh.derive_size_tier(None, None) is None


# ── provenance stamping — every present provenanced fact carries a *_basis ────

def test_stamp_firmographic_provenance_fills_missing_bases():
    pf = {"trend": "ACCELERATING", "cagr": "8%", "cagr_basis": "kept",
          "footprint": "Utah", "aum_usd": 1e9, "website": "https://x.example"}
    added = eh.stamp_firmographic_provenance(pf)
    assert added == 4  # trend, footprint, aum, website (cagr already had a basis)
    assert pf["trend_basis"] and pf["footprint_basis"] and pf["aum_basis"]
    assert pf["cagr_basis"] == "kept"  # idempotent — untouched


def test_stamp_firmographic_provenance_ignores_absent_fields():
    pf = {"legal_name": "X"}
    assert eh.stamp_firmographic_provenance(pf) == 0


# ── strict AUM attribution — only "$N.NB … total assets", never a score number ─

def test_strict_total_assets_requires_attribution():
    assert df._strict_total_assets("REGIONS BANK | $157.3B Total Assets") == 157.3e9
    assert df._strict_total_assets("Total assets of $8.9 billion (E-061)") == 8.9e9
    # a peer-median SCORE is never a balance sheet
    assert df._strict_total_assets("runs at 3.0/5 against a 2.8 peer median") is None
    # a bare cohort figure with no "total assets" is not attributed
    assert df._strict_total_assets("occupies the $8.9B regional bank cohort") is None


def test_parse_usd_amount_units():
    assert df._parse_usd_amount("$3.2B") == 3.2e9
    assert df._parse_usd_amount("$10.23 billion") == 10.23e9
    assert df._parse_usd_amount("not a number") is None
