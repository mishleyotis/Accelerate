"""CG-34 — reach is read from completed rungs about THIS series, never from the
fix the producer named and did not run.

RC-05 (SWBC gold audit, 2026-10-04; slices CTX-05, CTX-06). `_check_financial_
series_reach` harvested years from EVERY string in empty_state — including the
closure_condition describing the 2018-2021 back-fill NOT done, a different
subsidiary's EDGAR rung and a 2009 trade-press profile kept out of the series.
SWBC served four years (2022-2025) of SWBC Mortgage originations and passed,
because its closure_condition said "HMDA volumes for 2018 to 2021 would extend
this subsidiary card to five years". The gate rewarded naming the unfetched
fix.

The rule now: years count only from `sources_searched` rungs with a terminal
outcome (RESOLVED or VERIFIED_ABSENT) that do not disclaim the series ("a
different subsidiary and a different measure", "kept out of the series");
reason and closure_condition are never read for reach; and a closure_condition
naming a back-fill of earlier years for the same series is refused outright.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation import _check_financial_series_reach as reach  # noqa: E402


def _series(years):
    return [{"period": f"CY{y}", "as_of": f"{y}-12-31", "value": 2.0,
             "basis": "Dollar volume originated, HMDA, SWBC Mortgage "
                      "Corporation only"} for y in years]


SWBC = {
    "series": _series([2022, 2023, 2024, 2025]),
    "empty_state": {
        "reason": "These four points describe SWBC Mortgage Corporation; a "
                  "group-level measure for 2019 onward is not published.",
        "sources_searched": [
            "HMDA aggregation, SWBC Mortgage Corporation by LEI, originations "
            "2022 to 2025 — RESOLVED, four points",
            "SEC EDGAR audited statements for SWBC Investment Services, LLC — "
            "RESOLVED, three points of one subsidiary's total assets: 2019, "
            "2021 and 2024; a different subsidiary and a different measure, "
            "so never joined to the mortgage series",
            "SEC EDGAR filings for the parent — not applicable: privately held",
            "Business Insurance 100 Largest Brokers — REACHED, NOT USABLE: a "
            "2009 profile reporting 2008 revenue is kept out of the series",
            "Employee stock ownership plan Form 5500 filings — not retrieved; "
            "neither found nor ruled out",
        ],
        "closure_condition": "A group-level measure with three dated points. "
                             "A longer mortgage series (HMDA volumes for 2018 "
                             "to 2021) would extend this subsidiary card to "
                             "five years.",
    },
}


def test_swbc_financial_series_is_refused():
    out = reach("financial_series", SWBC)
    assert out and all(r["gate_id"] == "CG-34" for r in out)
    assert any("2018" in r["message"] or "named the fix" in r["message"]
               for r in out)


def test_the_closure_condition_alone_is_refused_even_with_reach():
    """Naming a same-source back-fill and not running it is refused even when
    another rung reached back: the fix is in hand."""
    body = dict(SWBC, empty_state=dict(SWBC["empty_state"], sources_searched=[
        "HMDA aggregation for 2021 — VERIFIED ABSENT: the browser serves no "
        "row for this LEI before 2022"]))
    out = reach("financial_series", body)
    assert len(out) == 1 and "named the fix" in out[0]["message"]


def test_a_verified_absent_rung_on_the_series_reaches_back():
    body = dict(SWBC, empty_state={
        "reason": "x",
        "sources_searched": [
            "HMDA aggregation for SWBC Mortgage Corporation, 2018 to 2021 — "
            "VERIFIED ABSENT: the browser serves no row for this LEI before "
            "2022"],
        "closure_condition": "SWBC publishing consolidated financials."})
    assert reach("financial_series", body) == []


def test_years_in_the_reason_do_not_count():
    body = dict(SWBC, empty_state={
        "reason": "Nothing for 2019 or 2020 is published.",
        "sources_searched": ["HMDA 2022 to 2025 — RESOLVED"],
        "closure_condition": "Consolidated financials."})
    assert len(reach("financial_series", body)) == 1
