"""The producer reads what the routine already resolved.

Migration 0047 granted svc_mcp SELECT on the enrichment tables for one stated
purpose — "the producer session reads what the routine already resolved so it
does not re-run a search that has an answer" — and then nothing read them.

Measured 2026-08-15 in production: the hourly job resolved this run's website to
a value and recorded it. `list_enrichment_gaps`, the producer's worklist, went
on reporting the field as untouched. A producer working that list would have run
the same search again, and had no way to know an answer was sitting one table
away. The only reader of `enrichment_attempts` in the whole tree was the API's
health endpoint, which counts rows.

That is the write-path-with-no-read-path shape occurring INSIDE the machinery
built to close it, which is the reason for this file: the loop is only a loop if
the last hop exists.

Three properties, and the second is the one that keeps this honest:

  1. a RESOLVED attempt reaches the gap, with its provenance
  2. it does NOT read as done. A resolved attempt is a LEAD — the value still
     has to be registered as evidence and submitted through the connector,
     which is the only path content may take (invariant 2). A worklist that
     let a producer treat a resolver's output as promoted content would be a
     side door into the serving tier.
  3. an UNRESOLVED attempt reaches the gap WITH ITS REASON, so the producer
     neither repeats a dead search nor mistakes an unattempted field for an
     exhausted one — the distinction the whole loop exists to make.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import gaps


class FakeCursor:
    """Just enough DB-API to answer the two queries the worklist makes."""

    def __init__(self, submissions, attempts, fail_on_attempts=False):
        self._submissions = submissions
        self._attempts = attempts
        self._fail = fail_on_attempts
        self._rows = []

    def execute(self, sql, params=None):
        if "enrichment_attempts" in sql:
            if self._fail:
                raise RuntimeError("permission denied for table "
                                   "enrichment_attempts")
            self._rows = list(self._attempts)
        else:
            self._rows = list(self._submissions)

    def fetchall(self):
        return self._rows


class FakeConn:
    def __init__(self, *a, **kw):
        self._cur = FakeCursor(*a, **kw)
        self.rolled_back = False

    def cursor(self):
        return self._cur

    def rollback(self):
        self.rolled_back = True


class _When:
    """A stand-in for a timestamptz, so the shape is exercised without
    importing datetime semantics the DB owns."""

    def __init__(self, s):
        self._s = s

    def isoformat(self):
        return self._s


# An empty firmographics section. It produces TEN gaps, not one: `website` is
# a must-present member the contract names on every sub-vertical, and so are
# seven of its siblings. The path the assertions join on is the one the routine
# itself writes — enrichment.py records `gap["path"]` verbatim into
# `field_path`, so both sides of the join come from this same computation and
# cannot drift.
SUBMISSIONS = [("overview", {"firmographics": {"website": None}})]
WEBSITE = "firmographics.fields[website]"

ATTEMPT_COLS = ("field_path", "status", "value", "unit", "as_of", "reason",
                "resolver", "source_url", "excerpt", "confidence",
                "attempted_at")


def attempt(path, status, **kw):
    row = {"field_path": path, "status": status, "value": None, "unit": None,
           "as_of": None, "reason": None, "resolver": "self_domain",
           "source_url": None, "excerpt": None, "confidence": None,
           "attempted_at": _When("2026-08-15T06:36:39+00:00")}
    row.update(kw)
    return tuple(row[c] for c in ATTEMPT_COLS)


def worklist(attempts, fail=False):
    conn = FakeConn(SUBMISSIONS, attempts, fail_on_attempts=fail)
    return gaps.list_enrichment_gaps(conn, "run-1"), conn


def gap_at(out, path=WEBSITE):
    for g in out["gaps"]:
        if g["path"] == path:
            return g
    raise AssertionError(
        f"no gap at {path!r}; the fixture produced {[g['path'] for g in out['gaps']]}")


def test_the_gap_exists_at_all_without_any_attempt():
    """A guard on the guard. If the fixture stops producing a gap, every
    assertion below passes over an empty list."""
    out, _ = worklist([])
    g = gap_at(out)
    assert g["field"] == "website"
    assert g["kind"] == "must_present_member"
    assert "enrichment_attempt" not in g
    assert out["never_attempted"] == out["count"] == 10
    assert out["with_resolved_value"] == 0


def test_a_resolved_attempt_reaches_the_gap_with_its_provenance():
    out, _ = worklist([attempt(
        WEBSITE, "RESOLVED", value="bcu.org",
        source_url="https://www.bcu.org/", confidence="HIGH")])
    a = gap_at(out)["enrichment_attempt"]
    assert a["status"] == "RESOLVED"
    assert a["value"] == "bcu.org"
    # The value without its source is exactly the "Clay reports 340 employees"
    # failure: a figure with no traceable origin is an inference.
    assert a["source_url"] == "https://www.bcu.org/"
    assert a["resolver"] == "self_domain"
    assert a["attempted_at"] == "2026-08-15T06:36:39+00:00"
    assert out["with_resolved_value"] == 1
    assert out["attempted_by_routine"] == 1


def test_a_resolved_attempt_does_not_read_as_done():
    """Invariant 2 at the worklist layer. The routine records that an attempt
    happened; it does not promote anything, and the producer must not read it
    as though it had."""
    out, _ = worklist([attempt(WEBSITE, "RESOLVED",
                               value="bcu.org")])
    g = gap_at(out)
    # It is still a gap. It has not left the list.
    assert g["kind"] == "must_present_member"
    assert out["count"] == 10
    todo = g["enrichment_attempt"]["still_to_do"]
    assert "register_evidence" in todo and "submit" in todo, (
        "a resolved attempt is a lead; the worklist has to say so or a "
        "producer will treat a resolver's output as promoted content")


def test_an_unresolved_attempt_carries_its_reason():
    """The fail-closed half, and the more valuable one on a second pass: a
    resolver that came back empty without saying why is indistinguishable from
    one that never ran."""
    out, _ = worklist([attempt(
        WEBSITE, "NO_SOURCE",
        reason="no non-aggregator host reached the 3-hit floor across this "
               "run's evidence; two hosts tied at 2")])
    a = gap_at(out)["enrichment_attempt"]
    assert a["status"] == "NO_SOURCE"
    assert "tied" in a["reason"]
    assert "value" not in a, "an unresolved attempt must not carry a value"
    assert out["with_resolved_value"] == 0
    assert out["attempted_by_routine"] == 1
    assert out["never_attempted"] == out["count"] - 1


def test_the_newest_attempt_wins():
    """Attempts accumulate — the job runs hourly. An older NO_SOURCE must not
    mask a later RESOLVED, or the loop reports its own progress as failure."""
    out, _ = worklist([
        attempt(WEBSITE, "RESOLVED", value="bcu.org",
                attempted_at=_When("2026-08-15T06:36:39+00:00")),
        attempt(WEBSITE, "NO_SOURCE", reason="tied hosts",
                attempted_at=_When("2026-08-15T05:36:39+00:00")),
    ])
    a = gap_at(out)["enrichment_attempt"]
    assert a["status"] == "RESOLVED" and a["value"] == "bcu.org"


def test_a_resolved_gap_sorts_ahead_of_its_peers():
    """Cheapest to close, so it leads its own kind. An answer buried at the
    bottom of a long list goes unused for another hour."""
    conn = FakeConn(SUBMISSIONS, [attempt(WEBSITE, "RESOLVED", value="bcu.org")])
    out = gaps.list_enrichment_gaps(conn, "run-1")
    members = [g for g in out["gaps"] if g["kind"] == "must_present_member"]
    assert len(members) >= 2, "need two gaps of one kind to test the order"
    assert members[0]["field"] == "website", (
        "the gap with an answer waiting must lead its kind, even though CAGR, "
        "HQ, branches and charter all sort ahead of it alphabetically; an "
        f"answer buried at position {[m['field'] for m in members].index('website')} "
        "goes unused for another hour")


def test_an_unreadable_attempts_table_degrades_the_worklist_and_does_not_kill_it():
    """The worklist is the product. A missing grant on a HISTORY table must not
    take it down — which is not hypothetical: this exact loop spent two runs
    dead on `permission denied for table submissions`."""
    out, conn = worklist([attempt(WEBSITE, "RESOLVED",
                                  value="bcu.org")], fail=True)
    assert out["count"] == 10, "the gaps still compute"
    assert "enrichment_attempt" not in gap_at(out)
    assert out["attempted_by_routine"] == 0
    assert conn.rolled_back, (
        "a failed statement leaves the transaction aborted; without a rollback "
        "every later query on this connection fails too")


def test_an_attempt_on_an_unrelated_path_attaches_to_nothing():
    """The join is by path. A near-miss must not decorate the wrong gap with
    another field's answer."""
    out, _ = worklist([attempt("firmographics.fields[founded_year]",
                               "RESOLVED", value="1981")])
    assert "enrichment_attempt" not in gap_at(out)
    # It attaches to founded_year, which is a real sibling gap here — the join
    # is exact, not fuzzy, and neither gap wears the other's answer.
    assert gap_at(out, "firmographics.fields[founded_year]")[
        "enrichment_attempt"]["value"] == "1981"


def test_the_connector_re_exports_the_read_path():
    """dma_mcp.gaps is the import path the server and its tests use. A helper
    that exists only in packages/shared is not reachable from the connector."""
    assert hasattr(gaps, "attempts_for_run")
