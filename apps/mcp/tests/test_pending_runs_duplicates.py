"""A duplicate pending run is a condition, not a preference.

MEASURED 2026-08-16: 105 of 171 entities carried more than one pending run,
every other field identical — same request id, same composite, same cell
count, same completed_at. The answer then was to expose `run_seq` so a caller
could pick the latest.

MEASURED AGAIN 2026-08-19, before a queue of 287 was to be worked: 109 of those
287 are surplus, 101 request ids carry more than one run, and on 100 of the 101
every run shares one completed_at. The charter says the package scan is
idempotent — an unchanged tree creates nothing — so this contradicts it.

`run_seq` alone made the duplicate CHOOSABLE and left it invisible: a caller
reading one row cannot tell it is one of two without grouping the whole list.
These cases pin the shape that says so on the row (MEM-0092).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

SERVER = (ROOT / "apps" / "mcp" / "server.py").read_text()


def _block() -> str:
    i = SERVER.index("def list_pending_runs")
    j = SERVER.index("def claim_run", i)
    return SERVER[i:j]


def test_the_row_says_how_many_runs_its_request_has():
    b = _block()
    assert '"runs_for_request"' in b, \
        "a caller reading one row still cannot tell it is one of two"
    assert '"is_latest_for_request"' in b, \
        "the row names the count and not which of them to work"


def test_the_corpus_level_counts_are_returned():
    """A scheduler about to fan out over this list should know what share of
    it is duplicate BEFORE it starts, not after 287 claims."""
    b = _block()
    assert '"duplicate_requests"' in b and '"surplus_runs"' in b


def test_run_seq_is_still_there():
    """The earlier mitigation is not replaced by the new one: a caller that
    picks on `run_seq` keeps working."""
    assert '"run_seq": r[8]' in _block()


def test_the_grouping_key_is_the_request_not_the_entity():
    """An entity with two DIFFERENT assessments has two request ids and two
    legitimate runs. Grouping by entity would call those duplicates and send a
    producer to drop real work."""
    b = _block()
    m = re.search(r"per_request\.setdefault\(\(([^)]*)\)", b)
    assert m, "the grouping key is gone"
    assert "r[3]" in m.group(1), \
        "the key no longer includes the request id, so two assessments of one " \
        "client would read as duplicates of each other"


def test_the_counts_are_computed_from_the_rows_returned():
    """Invariant 8: a count with a source of truth is computed from it. A
    stored duplicate flag would go stale the moment a run promotes."""
    b = _block()
    assert "for r in rows:" in b and "per_request.setdefault" in b
    assert "SELECT count" not in b.upper().replace("SELECT COUNT", "SELECT count"), \
        "the duplicate count is queried separately from the rows it describes, " \
        "so the two can disagree"
