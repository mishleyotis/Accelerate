"""The named peer set holds institutions, never statistics (review of
fix/enrichment-peers-consistency, 2026-10-04; RC-10 follow-up).

`run_peer_set` took every DISTINCT `peer_scores.peer_name` verbatim. Baxter
Credit Union's promoted run c1351d25 carries 144 peer_scores rows: 18
categories x {Alliant CU, CEFCU, Consumers CU, GreenState CU, Lake Michigan
CU, Median, P25, P75} (read-only `get_report_bundle`, peer_table). Replayed
on its promoted platform_story, AG-04 refused every tile with "no row for
Median, P25, P75" — a gate demanding peer_deployments rows about three
statistics, which any Baxter platform resubmit or re-promote would hit.

goeasy's peer_scores holds ONE row whose name is five peers joined by
semicolons; it passed only because `peer_key` took the first token, so four
of its five peers were invisible to the gate.

And where the workbook states a `locked_peer_set` (Handoff_Lock ->
run_manifest.payload.workbook_metadata), that IS the set: the scored table
and the payload rows are what a producer or a parser wrote, the lock is what
the assessment fixed.

These tests drive the connection-backed path with a fake connection that
answers the three reads `run_peer_set` makes, so the SQL branch is exercised
and not only the conn=None core.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import peer_set as PS          # noqa: E402

BAXTER_PEERS = ["Alliant CU", "CEFCU", "Consumers CU", "GreenState CU",
                "Lake Michigan CU"]
BAXTER_STATS = ["Median", "P25", "P75"]


class _Cur:
    def __init__(self, db):
        self.db, self._rows = db, []

    def execute(self, sql, params=()):
        s = " ".join(sql.split())
        if "FROM peer_scores" in s:
            self._rows = [(n,) for n in self.db.get("peer_scores", [])]
        elif "FROM run_manifest" in s:
            self._rows = [self.db["manifest"]] if "manifest" in self.db else []
        elif "FROM submissions" in s:
            page = params[1]
            sub = self.db.get("live", {}).get(page)
            self._rows = [(json.dumps(sub),)] if sub is not None else []
        else:
            raise AssertionError(f"unexpected read: {s[:80]}")

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class FakeConn:
    def __init__(self, **db):
        self.db = db

    def cursor(self):
        return _Cur(self.db)


def _story(rows_by_tile):
    return {"platform_story": {"platforms": [
        {"platform": f"Platform {i}", "rank": i + 1, "state": "READY",
         "peer_deployments": rows}
        for i, rows in enumerate(rows_by_tile)]}}


def _row(peer):
    return {"peer": peer, "deployed": None,
            "basis": "Newsroom and postings searched 2026-10-03; nothing establishes it"}


@pytest.mark.parametrize("name", [
    "Median", "P25", "P75", "Mean", "Average", "Top quartile", "Bottom Quartile",
    "Peer Median", "Peer_P25", "Cohort average", "Peer group", "Q1", "Q3",
    "25th percentile", "Percentile 75", "Min", "Max", "Std Dev", "Avg",
    "Industry average", "Median (n=5)", "Gap_vs_Median", "Benchmark",
])
def test_statistic_and_cohort_pseudo_names_are_not_peers(name):
    assert PS.is_statistic_name(name), name


@pytest.mark.parametrize("name", BAXTER_PEERS + [
    "Delta Community CU", "First Tech FCU", "Assurant", "TruStage/CUNA Mutual",
    "Fortegra", "Oportun", "Mean Green Credit Union", "Median Bancorp",
])
def test_institutions_are_peers(name):
    assert not PS.is_statistic_name(name), name


def test_baxter_peer_scores_yield_no_statistic_names():
    conn = FakeConn(peer_scores=sorted(BAXTER_PEERS + BAXTER_STATS),
                    manifest=(None, None))
    found = PS.run_peer_set(conn, "c1351d25", _story([]))
    names = set(found.values())
    assert names == set(BAXTER_PEERS)
    assert not names & set(BAXTER_STATS)


def test_baxter_platform_tiles_are_not_asked_for_rows_about_statistics():
    conn = FakeConn(peer_scores=sorted(BAXTER_PEERS + BAXTER_STATS),
                    manifest=(None, None))
    story = _story([[_row(p) for p in BAXTER_PEERS]] * 5)
    out = PS.check_named_peer_set(conn, "c1351d25", "platform", story)
    assert out == [], [r["message"][:120] for r in out]


def test_semicolon_joined_peer_score_names_split_into_peers():
    joined = "Oportun; Propel; OneMain; Fairstone; Regional Mgmt"
    conn = FakeConn(peer_scores=[joined], manifest=(None, None))
    found = PS.run_peer_set(conn, "goeasy", {})
    assert list(found.values()) == ["Oportun", "Propel", "OneMain",
                                    "Fairstone", "Regional Mgmt"]


def test_the_workbook_locked_set_is_the_set_where_present():
    conn = FakeConn(
        peer_scores=["Assurant", "Median", "Somebody Else"],
        manifest=(json.dumps("TruStage/CUNA Mutual|Assurant|Fortegra"), None),
        live={"techstack": _story([[_row("Unlocked Peer Co")]])})
    found = PS.run_peer_set(conn, "swbc", _story([[_row("Another Payload Peer")]]))
    assert list(found.values()) == ["TruStage/CUNA Mutual", "Assurant", "Fortegra"]


def test_a_locked_set_made_only_of_statistics_falls_back():
    conn = FakeConn(peer_scores=BAXTER_PEERS + BAXTER_STATS,
                    manifest=(json.dumps(["Median", "P25"]), None))
    found = PS.run_peer_set(conn, "r", {})
    assert set(found.values()) == set(BAXTER_PEERS)


def test_statistic_rows_on_the_payload_are_not_peers_either():
    found = PS.run_peer_set(None, "r", _story([[_row("Assurant"), _row("Median")]]))
    assert list(found.values()) == ["Assurant"]


def test_the_page_under_validation_is_not_read_back_as_its_own_peer_set():
    """The live submission of the SAME page is what this submit replaces. Read
    back, a peer once submitted could never be removed: the ratchet the
    review named. The OTHER peer page still counts."""
    conn = FakeConn(peer_scores=[], manifest=(None, None),
                    live={"platform": _story([[_row("Wrongly Named Co")]]),
                          "techstack": _story([[_row("Assurant")]])})
    found = PS.run_peer_set(conn, "r", _story([[_row("Fortegra")]]),
                            page="platform")
    assert set(found.values()) == {"Fortegra", "Assurant"}


def test_an_unreadable_connection_still_does_not_block():
    class Broken:
        def cursor(self):
            raise RuntimeError("connection gone")
    assert PS.run_peer_set(Broken(), "r", {}) == {}
