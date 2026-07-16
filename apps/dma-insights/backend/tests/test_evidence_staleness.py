"""Tests for the evidence staleness / freshness banding service.

State-transition coverage matrix (per scope §4 — all 4+1 bands):

  - current → test_band_current
  - aging   → test_band_aging
  - dated   → test_band_dated
  - stale   → test_band_stale (and test_three_year_boundary)
  - undated → test_band_undated_when_both_null
"""
from __future__ import annotations

from datetime import date

from app.services.evidence_staleness import (
    bundle_stale_pct,
    compute_band,
    is_stale,
    rollup_freshness,
)

TODAY = date(2026, 5, 23)


class TestBand:
    def test_band_current(self) -> None:
        assert compute_band(
            published_date=date(2025, 11, 1),
            recency_months=None, today=TODAY,
        ) == "current"

    def test_band_aging(self) -> None:
        assert compute_band(
            published_date=date(2024, 6, 1),
            recency_months=None, today=TODAY,
        ) == "aging"

    def test_band_dated(self) -> None:
        assert compute_band(
            published_date=date(2023, 11, 1),
            recency_months=None, today=TODAY,
        ) == "dated"

    def test_band_stale(self) -> None:
        # 2022-01-01 is > 3 years before 2026-05-23
        assert compute_band(
            published_date=date(2022, 1, 1),
            recency_months=None, today=TODAY,
        ) == "stale"

    def test_band_undated_when_both_null(self) -> None:
        assert compute_band(
            published_date=None, recency_months=None, today=TODAY,
        ) == "undated"

    def test_band_via_recency_months(self) -> None:
        assert compute_band(
            published_date=None, recency_months=8, today=TODAY,
        ) == "current"
        assert compute_band(
            published_date=None, recency_months=37, today=TODAY,
        ) == "stale"

    def test_band_or_semantics_match_sql_when_both_signals_present(self) -> None:
        """Regression for the Python-vs-SQL drift caught 2026-05-26.

        The SQL trigger (migration 018) uses OR semantics: either an
        old published_date OR a fresh recency_months promotes the band
        to "current". The earlier Python helper had an if/else giving
        published_date absolute priority — a row with pd=2020 + rm=5
        rendered as "stale" on the Python side but "current" on the
        SQL side. Surfaces (banner percentages, bundle_stale_pct) and
        the per-row chip would disagree.

        These cases lock the contract so a future Python refactor
        cannot silently re-break the parity.
        """
        # Old publish, fresh recency → SQL says current
        assert compute_band(
            published_date=date(2020, 1, 1), recency_months=5, today=TODAY,
        ) == "current"
        # Old publish, moderately fresh recency → SQL says aging
        assert compute_band(
            published_date=date(2020, 1, 1), recency_months=18, today=TODAY,
        ) == "aging"
        # Old publish, dated recency → SQL says dated
        assert compute_band(
            published_date=date(2020, 1, 1), recency_months=30, today=TODAY,
        ) == "dated"
        # Both old → stale (no false-promotion)
        assert compute_band(
            published_date=date(2020, 1, 1), recency_months=60, today=TODAY,
        ) == "stale"
        # Fresh publish, stale recency → current (publish-side fresh wins too)
        assert compute_band(
            published_date=date(2026, 1, 1), recency_months=60, today=TODAY,
        ) == "current"


class TestIsStale:
    def test_three_year_boundary(self) -> None:
        # 2023-05-23 itself is NOT stale (exactly 3 years).
        assert is_stale(
            published_date=date(2023, 5, 23), recency_months=None, today=TODAY,
        ) is False
        # 2023-05-22 IS stale (3 years + 1 day).
        assert is_stale(
            published_date=date(2023, 5, 22), recency_months=None, today=TODAY,
        ) is True

    def test_recency_months_path(self) -> None:
        assert is_stale(
            published_date=None, recency_months=36, today=TODAY,
        ) is False
        assert is_stale(
            published_date=None, recency_months=37, today=TODAY,
        ) is True


class TestRollup:
    def test_aggregates_band_counts(self) -> None:
        rows = [
            {"published_date": date(2026, 1, 1), "recency_months": None},
            {"published_date": date(2025, 1, 1), "recency_months": None},
            {"published_date": date(2024, 1, 1), "recency_months": None},
            {"published_date": date(2022, 1, 1), "recency_months": None},
            {"published_date": None, "recency_months": None},
        ]
        roll = rollup_freshness(rows, today=TODAY)
        assert roll.current_count == 1
        assert roll.aging_count == 1
        assert roll.dated_count == 1
        assert roll.stale_count == 1
        assert roll.undated_count == 1
        assert roll.total == 5
        assert roll.oldest_published_date == date(2022, 1, 1)
        assert roll.stale_pct == 20.0
        assert roll.median_age_months is not None

    def test_stress_100_rows(self) -> None:
        # Synthesize 100 evidence rows spanning 2018..2026; the year
        # buckets exercise all 4 bands.
        rows = []
        # 9 years * 12 rows = 108 -> take first 100.
        for year in range(2018, 2027):
            for _ in range(12):
                rows.append({
                    "published_date": date(year, 6, 1),
                    "recency_months": None,
                })
        rows = rows[:100]
        roll = rollup_freshness(rows, today=TODAY)
        assert roll.total == 100
        assert roll.stale_count > 0
        # Stale = anything published before 2023-05-23 → years 2018..2022
        # = roughly half the rows.
        assert roll.stale_count >= 40
        assert 30 <= roll.stale_pct <= 70

    def test_empty_input(self) -> None:
        roll = rollup_freshness([], today=TODAY)
        assert roll.total == 0
        assert roll.stale_pct == 0.0
        assert roll.median_age_months is None
        assert roll.oldest_published_date is None


class TestBundleStalePct:
    def test_above_40_triggers_disclaimer_metadata(self) -> None:
        bundle = [
            {"published_date": date(2022, 1, 1), "recency_months": None},
            {"published_date": date(2021, 1, 1), "recency_months": None},
            {"published_date": date(2026, 1, 1), "recency_months": None},
        ]
        pct = bundle_stale_pct(bundle, today=TODAY)
        # 2 of 3 = 66.67%
        assert pct > 40.0

    def test_zero_when_empty(self) -> None:
        assert bundle_stale_pct([], today=TODAY) == 0.0
