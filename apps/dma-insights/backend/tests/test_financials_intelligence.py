"""Consultant-grade financial-derive intelligence (audit bugs 1-6).

Every input string here is VERBATIM from the named real DMA package
(`tests/fixtures/dma_packages_batches`) so the assertions prove the bug is
fixed on the client's own package text, never on a synthetic stand-in. The
absolute rule under test: never fabricate — an absent value stays absent, a
parent's figure is never the client's, a quarterly print is never annual.
"""
from app.scripts.derive_financials import (
    _mine_highlights,
    _progression_series,
    _stated_cagr,
    build_trajectory,
)
from app.services.nlp import quantities as q
from app.services.overview_cards import financial_trajectory_card

# ── Farm Credit Mid America (batch_15) — the AR "5-Year Financial Progression"
#    table + the SCQA banner sentence that leaked $48.9B into FY2020. ──────────
FCMA_PROSE = (
    "Earning Asset Owned & Managed (EAOM) growing from approximately $29B in "
    "FY 2020 to $48.9B current (H1 2026), representing a compound annual growth "
    "rate of 11.2% — materially above US agricultural lending system growth. "
    "5-Year Financial Progression [E-001, T1]: Period EAOM Net Income ACLL "
    "Provision YoY Growth FY 2020 ~$29B ~$385M stable baseline FY 2021 ~$32B "
    "~$430M stable +10.3% FY 2022 ~$36B ~$475M stable +12.5% FY 2023 ~$40.8B "
    "(post-Midsouth merger April 1) ~$545M stable +13.3% FY 2024 $44.1B $600.4M "
    "(record) stable +8.1% H1 2026 $48.9B (in-period) +38.4% YoY +10.9% "
    "annualized Key Financial Signals: • Record profitability: FY 2024 net "
    "income of $600.4M is the highest in cooperative history"
)


def test_fcma_year_slotting_binds_each_value_to_its_labelled_fy() -> None:
    """Bug 3: the $48.9B 'current' banner must NOT occupy FY2020; the AR table's
    labelled rows win over the SCQA 'from $29B in FY 2020 to $48.9B' phrase."""
    primary, ni, meta = _progression_series(FCMA_PROSE)
    assert round(primary[2020] / 1e9, 1) == 29.0     # NOT 48.9 (the banner)
    assert round(primary[2024] / 1e9, 1) == 44.1
    assert round(primary[2026] / 1e9, 1) == 48.9     # H1 2026 keeps its OWN year
    # net income filled at every labelled FY (2023 was dropped before the fix)
    assert round(ni[2023] / 1e6) == 545
    assert round(ni[2024] / 1e6, 1) == 600.4
    # per-row drivers become fy-keyed events (bug 4) — no trailing-section bleed
    assert meta["events"][2023].startswith("post-Midsouth")
    assert 2026 not in meta["events"]


def test_fcma_prefers_stated_cagr_and_events_align_to_series_fy() -> None:
    """Bug 4: chart the report's STATED CAGR (11.2%, labelled to the metric),
    never a recomputed 0% off the mis-slotted series; events key to the fy."""
    assert _stated_cagr(FCMA_PROSE) == (11.2, "assets")
    primary, ni, meta = _progression_series(FCMA_PROSE)
    traj = build_trajectory(
        ta_series=primary, ni_series=ni, branches=None, regulator="FCA",
        geography=None, headcount=None, source="report_prose", anchor_usd=48.9e9,
        size_tier="large", max_fy=2027, stated_cagr=_stated_cagr(FCMA_PROSE),
        events_by_fy=meta["events"])
    assert traj["series"]["total_assets"][0] == 29.0
    assert "11.2% assets CAGR" in traj["headline"]
    assert traj["cagr"] == "11.2%"
    fys = {e["fy"] for e in traj["events"]}
    assert {"FY2023", "FY2024"} <= fys and "FY2026" not in fys


# ── Capital Farm Credit (batch_12) — evidence findings, verbatim. ─────────────
CFC_TEXT = (
    "The cooperative's financial strength—$13.17B in loans, BBB Fitch rating "
    "with Stable outlook, Aa3 parent rating—provides a solid foundation. "
    "CFC total loans: $13.17B (Q2 2025), up from $12.99B (Dec 2024). "
    "Debt-to-equity: 5.90:1. Credit quality: 95.6% acceptable. "
    "March 2025: $111.5M cash patronage + $78.1M allocated equities = $189.6M "
    "total for 2024. $2.9B returned since 2006. "
    "Fitch affirmed Capital Farm Credit at BBB, Outlook Stable (Dec 2025). "
    "Farm Credit Bank of Texas rated Aa3 by Moody's (2017-2025), Stable outlook. "
    "FCBT Q1 2025 net income $51.6M (+5.3% YoY). Total assets $39.5B."
)


def test_capital_farm_partial_trend_yields_highlights_not_null() -> None:
    """Bug 1: a PARTIAL 5-yr trend must not blank the card — loans / patronage /
    credit quality / ratings surface as the highlights + ratings variant."""
    hl = _mine_highlights(CFC_TEXT)
    assert round(hl["loans"] / 1e9, 2) == 13.17
    assert round(hl["patronage"] / 1e6, 1) == 189.6      # annual total, NOT $2.9B
    assert hl["credit_quality_pct"] == 95.6
    assert hl["ratings"]["Fitch"].startswith("BBB")      # NOT Aa3
    assert hl["ratings"]["Moody's"].startswith("Aa3")


def test_capital_farm_never_attributes_the_parents_balance_sheet() -> None:
    """Never fabricate: FCBT's $39.5B assets / $51.6M Q1 net income are the
    PARENT's — they must not be mislabelled as Capital Farm's own figures."""
    hl = _mine_highlights(CFC_TEXT)
    assert "total_assets" not in hl                      # $39.5B (FCBT) guarded out
    assert "net_income" not in hl                        # $51.6M Q1 (FCBT) guarded out


def test_capital_farm_card_renders_highlights_and_ratings() -> None:
    fh = {**_mine_highlights(CFC_TEXT), "size_tier": "Large ($10B-$50B)"}
    card = financial_trajectory_card(fh)
    assert card is not None and card["fy"] == []         # highlights variant, no chart
    labels = {h["label"] for h in card["highlights"]}
    assert {"Loans", "Patronage", "Credit quality"} <= labels
    assert card["ratings"]["Fitch"].startswith("BBB")


# ── Alliant Insurance (batch_03, SV7→IB broker) — A3 revenue trend. ───────────
def test_broker_charts_revenue_series_not_total_assets() -> None:
    """Bug 2/6: an insurance broker's scale metric is REVENUE. The A3 revenue
    series must chart under the `revenue` key at $B scale — never coerced into
    total_assets (which the unit-guard then rescaled to ~0 'K')."""
    revenue = {2021: 2.0, 2022: 3.0, 2023: 4.0, 2024: 5.1}   # A3 $B figures
    traj = build_trajectory(
        ta_series=revenue, ni_series={}, branches=None, regulator="State DOI",
        geography=None, headcount=14000, source="trends_csv", anchor_usd=None,
        size_tier="mega", max_fy=2027, primary_key="revenue")
    assert traj is not None
    assert "total_assets" not in traj["series"]
    assert traj["series"]["revenue"] == [2.0, 3.0, 4.0, 5.1]
    assert traj["unit"] == "B"
    assert "revenue" in traj["headline"]
    # the card passes a >=2yr broker trajectory straight through (bug 6)
    card = financial_trajectory_card({"trajectory": traj})
    assert card["series"]["revenue"] == [2.0, 3.0, 4.0, 5.1]


# ── quantities.py number / period parsing (bug 5). ────────────────────────────
def test_comma_grouped_integer_is_one_token() -> None:
    """Bug 5a: "1,253" is a single integer, never truncated to 253."""
    out = q.extract_metrics("the bank operates 1,253 branches")
    assert out[0]["metric"] == "branches" and out[0]["value"] == 1253.0


def test_quarterly_revenue_is_not_labelled_annual() -> None:
    """Bug 5b: a Q# print must be rejected when the annual figure is wanted."""
    assert q.is_quarterly("Q2 2025") is True
    assert q.pick_annual_revenue_usd("Revenue of $1.9B in Q2 2025") is None
    assert q.pick_annual_revenue_usd("Revenue of $5.1B in 2024") == 5.1e9


def test_size_tier_band_edge_is_not_a_point_estimate() -> None:
    """Bug 5c: "Large ($10B-$50B)" is a band; neither edge is a point figure."""
    assert q.is_size_tier_band("Large ($10B-$50B)") is True
    usd = [m for m in q.extract_metrics("size tier: Large ($10B-$50B)")
           if m["unit"] == "usd"]
    assert usd == []
    # a real growth range is NOT a tier band — both endpoints survive
    grow = [m["value"] for m in q.extract_metrics("revenue grew from $2.0B to $5.1B")
            if m["unit"] == "usd"]
    assert grow == [2.0e9, 5.1e9]


# ── regression guards: the default bank path is unchanged. ────────────────────
def test_bank_total_assets_path_unchanged() -> None:
    traj = build_trajectory(
        ta_series={2021: 29.5e9, 2022: 30.8e9, 2023: 32.1e9}, ni_series=None,
        branches=None, regulator=None, geography=None, headcount=None,
        source="t", anchor_usd=33.2e9)
    assert traj["series"]["total_assets"] == [29.5, 30.8, 32.1]
    assert "assets" in traj["headline"]


def test_no_progression_table_returns_empty() -> None:
    """Scattered prose (no clustered >=3-row table) must not fabricate a
    series — the caller falls back to the looser positional parser."""
    primary, ni, meta = _progression_series(
        "Assets were strong in 2024. Net income rose. See 2023 and 2022 filings.")
    assert primary == {} and ni == {}
