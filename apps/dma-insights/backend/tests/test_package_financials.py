"""D5 financial-trajectory + sentiment parsers.

Pins the multi-year CSV → financials_view-shaped dict (headline series +
per-metric latest values), the sentiment CSV → {sources:[…]}, and the
end-to-end fill onto firmographics for a real package (both columns were
never written before, so D5 chart + grid were dead corpus-wide).
"""
from __future__ import annotations

from pathlib import Path

from app.services.context_extras import financials_view
from app.services.parsers.package_financials import (
    load_financial_trends,
    load_sentiment,
    parse_financial_trends_csv,
    parse_sentiment_csv,
)

_BASE = Path(__file__).resolve().parents[1] / "tests/fixtures/dma_packages_batches"


def test_financial_trends_csv_real() -> None:
    p = next(iter(sorted(_BASE.glob("batch_*/**/A[0-9]*Financial_Trends.csv"))), None)
    if p is None:
        import pytest
        pytest.skip("no financial_trends fixture")
    fh = parse_financial_trends_csv(p)
    assert "series" in fh and len(fh["series"]) >= 2
    # series years are real and monotonic-ish; values numeric
    yrs = sorted(int(y) for y in fh["series"])
    assert all(2000 <= y <= 2030 for y in yrs)
    assert all(isinstance(v, float) for v in fh["series"].values())
    # financials_view turns it into a renderable {years, series, metrics}
    view = financials_view(fh)
    assert view and view["years"] == yrs
    assert view["series"]["value"]
    assert "metrics" in view  # per-metric latest values


def test_sentiment_csv_real() -> None:
    p = next(iter(sorted(_BASE.glob("batch_*/**/A[0-9]*sentiment*.csv"))), None)
    if p is None:
        import pytest
        pytest.skip("no sentiment fixture")
    s = parse_sentiment_csv(p)
    assert s["sources"]
    first = s["sources"][0]
    assert "source" in first
    # at least one of the descriptive fields was captured
    assert any(k in first for k in ("rating", "trend", "themes", "signal"))


def test_financial_trends_headline_prefers_total_assets(tmp_path: Path) -> None:
    p = tmp_path / "A3_Financial_Trends.csv"
    p.write_text(
        "Metric,2022,2023,2024,Source,Tier\n"
        "Asset Growth YoY (%),18.6%,17.5%,9.8%,X,T1\n"
        "Total Assets ($B),5.17,5.84,6.41,X,T1\n"
    )
    fh = parse_financial_trends_csv(p)
    # headline series should be Total Assets, not Asset Growth
    assert fh["series"] == {"2022": 5.17, "2023": 5.84, "2024": 6.41}
    assert "Asset Growth YoY (%)" in fh  # other metric surfaced as scalar


def test_sentiment_parse_shape(tmp_path: Path) -> None:
    p = tmp_path / "A9_sentiment_data.csv"
    p.write_text(
        "Source,Rating,Volume,Key_Themes,Trend,Capability_Signal\n"
        "Glassdoor,4.1/5,120,\"Culture, Comp\",Stable,P1C4 strong\n"
    )
    s = parse_sentiment_csv(p)
    assert len(s["sources"]) == 1
    e = s["sources"][0]
    assert e["source"] == "Glassdoor" and e["rating"] == "4.1/5"
    assert e["trend"] == "Stable" and e["signal"] == "P1C4 strong"


def test_load_empty(tmp_path: Path) -> None:
    assert load_financial_trends(tmp_path) == {}
    assert load_sentiment(tmp_path) == {}


def test_e2e_firm_carries_financials_and_sentiment() -> None:
    """A package shipping A#_financial_trends.csv + A#_sentiment_data.csv
    should attach both to firmographics (persisted → D5 chart + grid)."""
    from app.services.parsers.dma_package import parse_package

    target = None
    for p in sorted(_BASE.glob("batch_*/*")):
        if not p.is_dir():
            continue
        if list(p.glob("**/A[0-9]*[Ss]entiment*.csv")) and list(
            p.glob("**/A[0-9]*Financial_Trends.csv")
        ):
            target = p
            break
    if target is None:
        import pytest
        pytest.skip("no package with both A# csvs")
    pkg = parse_package(target)
    assert pkg.firmographics is not None
    assert pkg.firmographics.financial_highlights.get("series")
    assert pkg.firmographics.sentiment.get("sources")


# ── derive_financials prose-mining magnitude guards (Compeer QA) ──────────


def test_year_series_stray_mention_never_shadows_table_row() -> None:
    """Compeer 2026-07-06 QA regression: a stray inline "net income
    (2024) $480M" bullet consumed the year before the real two-column
    (Total Assets | Net Income) table row, and its lone $480M then
    landed in the ASSETS column — charting FY2024 at $0.48B for a $33B
    institution. The richer row (more populated $-columns) must win the
    year, restoring the true magnitudes."""
    from app.scripts.derive_financials import _year_series_full

    blob = (
        "Highlights: record net income (2024)\t$480M adjusted (E-005).\n"
        "Financial trajectory (Total Assets, Net Income):\n"
        "2023\t$31.9B\t$395M\n"
        "2024\t$32.3B\t$480M\n"
        "2025\t$33.1B\t$520M\n"
    )
    import pytest

    ni, ta = _year_series_full(blob)
    assert ta == pytest.approx({2023: 31.9e9, 2024: 32.3e9, 2025: 33.1e9})
    assert ni == pytest.approx({2023: 395e6, 2024: 480e6, 2025: 520e6})


def test_plausibility_guard_drops_mixed_magnitude_two_point_series() -> None:
    """Two points 50x+ apart cannot both be real for one balance-sheet
    metric, and with only two there is no majority to vote the outlier
    out — the series is honestly dropped, never charted as a cliff."""
    from app.scripts.derive_financials import _plausible_series

    assert _plausible_series({2024: 480e6, 2025: 33.1e9}) == {}
    # ≥3 points: the median votes the parse-error outlier out.
    assert _plausible_series(
        {2023: 31.9e9, 2024: 480e6, 2025: 33.1e9},
    ) == {2023: 31.9e9, 2025: 33.1e9}
    # A real, plausible series passes through untouched.
    assert _plausible_series({2023: 31.9e9, 2025: 33.1e9}) == {
        2023: 31.9e9, 2025: 33.1e9,
    }
