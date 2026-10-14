"""A quarter, a month or a bare year IS a date, and the engine bands it as
the app does (QA audit F-L11-031, 29-09-2026).

Measured: `ledger.recency_band('2025-Q4')` returned UNVERIFIED — the ledger
parsed ISO dates only — while the page contract (H7) says "'2025-Q4' IS a
date. Resolve to the quarter end", and `apps/mcp/dma_mcp/dates.py` does
exactly that at submit and promote. One filing, two bands.

`engine/dates.py` is the engine's copy of the app's rule (the plugin cannot
import apps/); this file holds the two equal on one case table, so a change
to either names the other.
"""
import importlib.util
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from engine import contract as C
from engine import dates as engine_dates
from engine import ledger as L

REPO = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("app_dates", REPO / "apps" / "mcp" / "dma_mcp" / "dates.py")
app_dates = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app_dates)

CASES = [
    ("2026-07", date(2026, 7, 1)),                 # month -> first day
    ("2025-Q4", date(2025, 12, 31)),               # quarter -> END (the H7 rule)
    ("2025Q1", date(2025, 3, 31)),
    ("2024-q2", date(2024, 6, 30)),
    ("2019", date(2019, 1, 1)),                    # bare year -> 1 January
    ("2026-01-15", date(2026, 1, 15)),
    ("2026-01-15T09:00:00+00:00", date(2026, 1, 15)),
    ("2026-02-30", False),                         # not a date
    ("Q4 2025", False),                            # not an accepted shape
    ("last year", False),
    ("", None),
    (None, None),
    (date(2025, 5, 5), date(2025, 5, 5)),
    (datetime(2025, 5, 5, 12, tzinfo=timezone.utc), date(2025, 5, 5)),
]


@pytest.mark.parametrize("value, expected", CASES, ids=[str(c[0]) for c in CASES])
def test_the_engine_resolves_every_shape_exactly_as_the_app_does(value, expected):
    assert engine_dates.resolve(value) == expected
    assert app_dates.resolve(value) == expected


def test_the_two_resolvers_share_their_accepted_shapes_line():
    assert engine_dates.ACCEPTED == app_dates.ACCEPTED


class _WB:
    """Just enough workbook: recency_band reads the pinned reference date."""

    def __init__(self, ref):
        self._ref = ref

    def metadata(self):
        return {"reference_date": self._ref}


@pytest.mark.parametrize("published, band", [
    ("2026-Q2", "CURRENT"),      # quarter end 2026-06-30, 3 months before the reference
    ("2025-Q4", "CURRENT"),      # 2025-12-31: 9 months
    ("2025-06", "RECENT"),       # 15 months
    ("2024-Q1", "DATED"),        # 2024-03-31: 30 months
    ("2023", "STALE"),           # 2023-01-01: 44 months
    ("2020-Q4", "ARCHIVAL"),     # 2020-12-31: 69 months
    ("2027-Q1", "UNVERIFIED"),   # a quarter in the future is a plan, not a publication
    ("Q4 2025", "UNVERIFIED"),   # not an accepted shape
    (None, "UNVERIFIED"),
])
def test_a_partial_date_bands_against_the_pinned_reference_date(published, band):
    assert L.recency_band(published, _WB("2026-09-28")) == band


def test_the_reference_date_itself_may_be_partial():
    # a run pinned to a quarter: 2026-Q3 resolves to 2026-09-30
    assert L.recency_band("2026-07-01", _WB("2026-Q3")) == "CURRENT"
    assert L.recency_band("2024-07-01", _WB("2026-Q3")) == "DATED"


def test_the_ladder_words_are_the_contracts():
    assert [w for w, _ in C.RECENCY_LADDER] == ["CURRENT", "RECENT", "DATED", "STALE"]
    assert C.RECENCY_ARCHIVAL == "ARCHIVAL" and C.RECENCY_UNVERIFIED == "UNVERIFIED"
