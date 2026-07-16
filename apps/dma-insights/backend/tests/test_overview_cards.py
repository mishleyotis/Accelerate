"""Unit tests for the D1 card projections (overview_cards)."""
from app.services.overview_cards import financial_trajectory_card, sentiment_card


def test_financial_trajectory_from_structured_lines():
    fh = {
        "lines": [
            "Total assets: 2023 $34.2B → 2024 $38.3B → 2025 $40.8B",
            "Deposits: 2023 $27.4B → 2024 $31.0B",
        ],
        "cagr_3yr": "9.5%",
    }
    out = financial_trajectory_card(fh)
    assert out is not None
    assert out["fy"] == [2023, 2024, 2025]
    assert out["series"]["total_assets"] == [34.2, 38.3, 40.8]
    assert out["unit"] == "B"
    assert out["cagr"] == "9.5%"


def test_financial_trajectory_chart_needs_two_points():
    # A single period can't form a chart series, but the real financial value
    # is still surfaced as a highlights card (not an empty state).
    single = financial_trajectory_card({"lines": ["Total assets: 2024 $10B"]})
    assert single is not None
    assert single["fy"] == []                       # no chart
    assert single["highlights"][0]["label"] == "Total assets"
    assert single["highlights"][0]["value"] == 10.0
    # Truly-empty inputs still return None (honest empty state).
    assert financial_trajectory_card({}) is None
    assert financial_trajectory_card(None) is None
    assert financial_trajectory_card({"trend_period": "3yr"}) is None


def test_financial_trajectory_highlights_from_cagr_and_keyed_metrics():
    # CAGR-only prose → a highlights card carrying the CAGR (no series).
    cagr_only = financial_trajectory_card(
        {"lines": ["3-Year Asset CAGR (2022-2025): 9.4%"]})
    assert cagr_only is not None and cagr_only["fy"] == []
    assert cagr_only["cagr"] == "9.4%"
    # unit-in-key single-year metrics ("Revenue ($B)": "5.1 (2024)").
    keyed = financial_trajectory_card(
        {"Revenue ($B)": "5.1 (2024)", "Premium Placed ($B)": "47 (2024)"})
    assert keyed is not None
    labels = {h["label"]: h["value"] for h in keyed["highlights"]}
    assert labels.get("Revenue") == 5.1
    # bare money string ("$3.7B", no year) → a highlight tile.
    bare = financial_trajectory_card({"total_assets": "$3.7B"})
    assert bare is not None and bare["highlights"][0]["value"] == 3.7


def test_sentiment_card_passthrough_shape():
    sent = {
        "employee": [{"metric": "Overall", "scale": 5, "score": 4.2, "source": "Glassdoor"}],
        "customer": None,
        "b2b_b2c_gap": False,
        "industry_avg": 3.7,
    }
    out = sentiment_card(sent)
    assert out is not None
    assert out["employee"][0]["score"] == 4.2
    assert out["customer"] == []          # None coerced to list
    assert out["industry_avg"] == 3.7


def test_sentiment_card_empty_when_no_cohort():
    assert sentiment_card({"employee": None, "customer": None}) is None
    assert sentiment_card(None) is None


def test_trajectory_card_trusts_persisted_guarded_trajectory_first():
    # The guarded trajectory (from derive_financials.build_trajectory) is
    # persisted under `trajectory`; the Overview card must render it verbatim
    # so it agrees with the D5 Context chart by construction.
    fh = {
        "trajectory": {
            "currency": "USD", "unit": "B", "fy": ["FY2021", "FY2022"],
            "series": {"total_assets": [29.5, 30.8]}, "events": [],
        },
        "series": {"2020": 999},  # would otherwise diverge if trusted
        "series_metric": "total_assets",
    }
    card = financial_trajectory_card(fh)
    assert card["fy"] == ["FY2021", "FY2022"]
    assert card["series"]["total_assets"] == [29.5, 30.8]


def test_trajectory_card_ignores_empty_persisted_trajectory():
    # An empty persisted trajectory must fall through to the existing
    # structured-series / prose-mining behaviour, not short-circuit to None.
    fh = {
        "trajectory": {"fy": [], "series": {}},
        "series": {"2021": 30.0, "2022": 31.0},
    }
    card = financial_trajectory_card(fh)
    assert card is not None
    assert card["fy"] == [2021, 2022]


def test_financial_trajectory_card_prefers_persisted_guarded_trajectory():
    """Compeer divergence (2026-07-06 deploy review): context charted the
    persisted 5-year trajectory while the Overview card re-derived from the
    raw metric-keyed `series` and fell to the highlights variant. The
    persisted (guarded, unit-normalized) trajectory must win outright."""
    persisted = {
        "currency": "USD", "unit": "B",
        "fy": ["FY2021", "FY2022", "FY2023"],
        "series": {"total_assets": [29.5, 30.8, 32.1]},
        "headline": "$32.1B assets · FY2023",
        "events": [], "anomalies": [],
    }
    fh = {
        "trajectory": persisted,
        # metric-keyed (NOT year-keyed) series that the old path choked on
        "series": {"value": [385000000.0, 420000000.0]},
        "lines": ["tier 1 risk based pct: 12.0"],
    }
    out = financial_trajectory_card(fh)
    assert out is not None
    assert out["fy"] == ["FY2021", "FY2022", "FY2023"]
    assert out["series"]["total_assets"] == [29.5, 30.8, 32.1]

    # an empty/degenerate persisted trajectory must NOT short-circuit
    assert financial_trajectory_card(
        {"trajectory": {"fy": [], "series": {}}, "lines": []}) is None
