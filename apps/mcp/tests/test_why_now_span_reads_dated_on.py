"""CG-40's span check has to read the field the contract actually requires.

Owner, 2026-08-23: "the evolution timeline spans 1 year? At least 3 years
should be covered. Enrichment should pick this up." CG-40 was written that
same day and shipped with a three-year floor.

It never fired on the run that prompted it.

`_why_now_span_days` read `date`, `as_of`, `observed_at`, `published_date`
and `window`. The why_now contract says: "dated_on required (an undated
signal is dropped)". Every producer writes `dated_on` and none of them
writes `date`, so on a real payload the loop matched nothing, returned None,
and the caller's `span is not None` guard skipped the check entirely. The
gate reported nothing — not a pass, not a failure, nothing — which is the
defect class this build keeps paying for: a check that cannot see its own
subject is indistinguishable from a check that ran and was satisfied.

Measured on axos-bank-...-nyse-ax, promoted 2026-08-23: three signals dated
2026-01-26, 2026-07-07 and 2026-07-30. Six months, against a floor of three
years, and the run promoted clean.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import (          # noqa: E402
    WHY_NOW_SPAN_DAYS, _WHY_NOW_DATE_KEYS, _why_now_span_days)

#: Axos's three promoted signals, in the one field this test is about.
AXOS = {"signals": [{"wn_id": "WN-1", "dated_on": "2026-01-26"},
                    {"wn_id": "WN-2", "dated_on": "2026-07-07"},
                    {"wn_id": "WN-3", "dated_on": "2026-07-30"}]}


def test_the_contracts_own_field_is_read_first():
    assert _WHY_NOW_DATE_KEYS[0] == "dated_on"


def test_the_reported_axos_payload_is_now_measurable():
    """The regression. Before the fix this returned None and the gate was
    skipped; the number it returns now is what the owner was looking at."""
    span = _why_now_span_days(AXOS)
    assert span is not None, "dated_on is invisible again — the gate is dark"
    assert span == 185
    assert span < WHY_NOW_SPAN_DAYS


def test_a_run_reaching_back_three_years_clears_the_floor():
    span = _why_now_span_days({"signals": [{"dated_on": "2023-02-01"},
                                           {"dated_on": "2026-07-30"}]})
    assert span >= WHY_NOW_SPAN_DAYS


def test_a_month_precision_date_still_dates_a_signal():
    """Gulf dates one signal to the month. The contract asks for 'at least
    the month', so a day-less date must count rather than silently drop."""
    span = _why_now_span_days({"signals": [{"dated_on": "2015-07"},
                                           {"dated_on": "2026-05-19"}]})
    assert span is not None and span > WHY_NOW_SPAN_DAYS


def test_every_documented_key_still_dates_a_signal():
    """The older shapes stay readable: declaring a promoted payload undatable
    after the fact strands a run that did the work."""
    for k in _WHY_NOW_DATE_KEYS:
        span = _why_now_span_days({"signals": [{k: "2021-01-01"},
                                               {k: "2026-01-01"}]})
        assert span == 1826, k


def test_one_dated_signal_is_not_a_span():
    """Two points make a span; one makes a date. Returning 0 here would read
    as a floor breach on a single-signal section, which is CG-40's depth
    floor's business, not this check's."""
    assert _why_now_span_days({"signals": [{"dated_on": "2026-01-26"}]}) is None
    assert _why_now_span_days({"signals": []}) is None
    assert _why_now_span_days({}) is None


def test_an_undatable_signal_set_still_returns_none():
    """Honest ignorance. A payload that dates nothing cannot be measured, and
    the caller must not read that as a pass — CG-40's own depth floor and the
    contract's 'an undated signal is dropped' cover that case."""
    assert _why_now_span_days({"signals": [{"wn_id": "WN-1"},
                                           {"wn_id": "WN-2"}]}) is None


def test_a_non_dict_signal_does_not_crash_the_check():
    assert _why_now_span_days(
        {"signals": ["x", None, {"dated_on": "2022-01-01"},
                     {"dated_on": "2026-01-01"}]}) == 1461


def test_an_unparseable_date_is_skipped_not_guessed():
    span = _why_now_span_days({"signals": [{"dated_on": "2026-13-45"},
                                           {"dated_on": "2022-01-01"},
                                           {"dated_on": "2026-01-01"}]})
    assert span == 1461


def test_the_check_is_reachable_from_the_gate_that_uses_it():
    """A gate nobody dispatches is a gate that does not exist — and this
    file's whole subject is a check that was dispatched and blind."""
    import inspect

    from dma_mcp import validation2
    src = inspect.getsource(validation2._check_depth_floors)
    assert "_why_now_span_days" in src
