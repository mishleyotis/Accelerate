"""CG-18f and ET-12 (SWBC, 2026-10-05).

CG-18f — owner decision: compute every CAGR candidate, rank them, serve only
the corroborated figure. The field promoted held ("no consolidated
financials") beside eight dated points of a series nobody had computed.

ET-12 — the tech register promoted without a machine technographic scan:
Clay was called for contacts only and Vibe Prospecting never.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import (_check_cagr_rule,  # noqa: E402
                                 _check_technographic_scan)

SERIES = {"series": [
    {"period": f"CY{y}", "value": v, "as_of": f"{y}-12-31"}
    for y, v in ((2018, 1.84), (2025, 2.29))]}


def _overview(cagr, series=SERIES):
    return {"firmographics": {"fields": [dict(field="cagr", **cagr)]},
            "financial_series": series}


def _gates(r):
    return [x["gate_id"] for x in r]


def test_a_held_cagr_beside_a_dated_series_must_state_its_ranked_candidates():
    held = {"value": None, "quarantined": True,
            "quarantine_reason": "SWBC files no consolidated financials."}
    assert _gates(_check_cagr_rule("overview", _overview(held))) == ["CG-18f"]


def test_a_held_cagr_that_ranks_its_uncorroborated_candidates_passes():
    held = {"value": None, "quarantined": True, "quarantine_reason": (
        "Candidates ranked: enterprise headcount 5.2% a year (Clay), not "
        "corroborated by a second source; SWBC Mortgage originations 3.2% a "
        "year (HMDA), one subsidiary, not corroborated.")}
    assert _check_cagr_rule("overview", _overview(held)) == []


def test_a_held_cagr_with_no_series_is_left_to_the_held_rules():
    held = {"value": None, "quarantined": True, "quarantine_reason": "x"}
    assert _check_cagr_rule("overview", _overview(held, series={})) == []


def test_a_served_cagr_names_its_corroborating_source():
    bare = {"value": "5.2", "unit": "percent a year, headcount, 2021-2026"}
    assert _gates(_check_cagr_rule("overview", _overview(bare))) == ["CG-18f"]
    ok = {"value": "5.2", "unit": "percent a year, SWBC enterprise headcount, "
          "2021-2026, corroborated by SWBC's own stated headcount"}
    assert _check_cagr_rule("overview", _overview(ok)) == []


class _Cur:
    def __init__(self, n):
        self.n, self.sql = n, None

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchone(self):
        return [self.n]


class _Conn:
    def __init__(self, n):
        self.cur = _Cur(n)

    def cursor(self):
        return self.cur


def _techstack(probes=(), e_ids=("E-1",)):
    return {"techstack": {"e_ids": list(e_ids),
                          "items": [{"ts_id": "TS-001", "e_ids": list(e_ids)}],
                          "r_layer": {"probes_run": list(probes)}}}


def test_a_register_with_no_scan_is_refused():
    r = _check_technographic_scan(_Conn(0), "run", "techstack", _techstack())
    assert _gates(r) == ["ET-12"]


def test_a_register_citing_a_scan_passes():
    conn = _Conn(1)
    assert _check_technographic_scan(conn, "run", "techstack",
                                     _techstack()) == []
    assert "connector_tool" in conn.cur.sql


def test_a_scan_that_could_not_run_is_stated_not_silent():
    probes = ["Technographic scan NOT_RUN: Clay and Vibe Prospecting are "
              "session-bound and this run was scheduled."]
    assert _check_technographic_scan(_Conn(0), "run", "techstack",
                                     _techstack(probes)) == []
    half = ["Clay NOT_RUN: session-bound."]
    assert _gates(_check_technographic_scan(
        _Conn(0), "run", "techstack", _techstack(half))) == ["ET-12"]


def test_other_pages_are_untouched():
    assert _check_technographic_scan(_Conn(0), "run", "overview", {}) == []
    assert _check_cagr_rule("platform", {}) == []


def test_an_empty_register_is_left_to_its_empty_state():
    body = {"techstack": {"items": [], "empty_state": {"reason": "x"}}}
    assert _check_technographic_scan(_Conn(0), "run", "techstack", body) == []
