"""INGEST_A attaches to THIS engagement's ingest, never a stale one.

2026-10-01, Cross Insurance: the entity had a pending seq 1 from 2026-09-13;
the first poll after the checkpoint push took it instead of the seq 2 the
push created a minute later, and pages began shipping to the wrong run.
"""
from engine.pipeline import _this_engagement

OLD = {"run_id": "old", "request_id": None, "completed_at": "2026-09-13T00:00:00+00:00", "run_seq": 1}
NEW = {"run_id": "new", "request_id": "cross-20261001", "completed_at": "2026-10-01T17:23:13+00:00", "run_seq": 2}
OTHER = {"run_id": "x", "request_id": "someone-else", "completed_at": "2026-10-01", "run_seq": 3}


def test_a_row_naming_our_request_wins():
    assert _this_engagement([OLD, NEW, OTHER], "cross-20261001", "2026-10-01") == [NEW]


def test_before_our_ingest_lands_the_stale_row_is_not_taken():
    assert _this_engagement([OLD], "cross-20261001", "2026-10-01") == []
    assert _this_engagement([OLD, OTHER], "cross-20261001", "2026-10-01") == []


def test_a_legacy_row_from_this_engagement_still_counts():
    legacy = {"run_id": "l", "request_id": None, "completed_at": "2026-10-01T09:00:00", "run_seq": 2}
    assert _this_engagement([legacy], "cross-20261001", "2026-10-01") == [legacy]
    undated = {"run_id": "u", "run_seq": 1}
    assert _this_engagement([undated], "r", "2026-10-01") == [undated]
