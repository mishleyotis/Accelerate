"""Rejections on a superseded run are not work; a run's submission history
is readable.

Measured 28-09-2026 (QA audit F-O04-007, F-I01-028 / O-03): 199 of 200
open rejections sat on a run a later promoted run had superseded, and the
"read this first" list pointed producers at it for 25 days; and
submissions-per-page was not measurable through the connector at all.

These tests run without a database, over a recording cursor: they pin the
SQL the two reads and the close issue — which run states are excluded,
that the close touches only OTHER runs of the entity already marked
SUPERSEDED, that `closed_by` stays NULL and the message says why — and the
shape the tool returns. The database-backed tests beside them run where a
migrated local database exists.
"""
from __future__ import annotations

import datetime as dt
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
from dma_mcp import claims, rejections  # noqa: E402


class _Cur:
    """Records every execute; answers fetchall from a queue."""
    def __init__(self, *results):
        self.calls: list[tuple[str, tuple]] = []
        self._results = list(results)

    def execute(self, sql, args=()):
        self.calls.append((" ".join(sql.split()), tuple(args)))

    def fetchall(self):
        return self._results.pop(0) if self._results else []

    def fetchone(self):
        r = self.fetchall()
        return r[0] if r else None


class _Conn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur


# ── the queue excludes runs that are off the board ─────────────────────

def test_open_corpus_wide_excludes_superseded_and_withdrawn_runs():
    cur = _Cur([])
    rejections.open_corpus_wide(_Conn(cur), "goeasy-ltd", "heatmap", 50)
    sql, args = cur.calls[0]
    assert "FROM rejection_ledger r" in sql and "JOIN runs ru" in sql
    assert "enum_label(ru.status) <> ALL(%s)" in sql
    assert args[0] == ["SUPERSEDED", "WITHDRAWN"]
    assert "e.display_id = %s" in sql and "r.page = %s" in sql
    assert args[1:] == ("goeasy-ltd", "heatmap", 50)
    assert "r.closed_at IS NULL" in sql


def test_open_corpus_wide_rows_carry_the_run_state():
    rid = uuid.uuid4()
    opened = dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc)
    cur = _Cur([(uuid.uuid4(), rid, "goeasy-ltd", "goeasy Ltd.", "heatmap",
                 "cell_evidence", "CG-15", "cells[3].synthesis", "same claim",
                 2, opened, dt.timedelta(days=25), "INGESTED", 15)])
    rows = rejections.open_corpus_wide(_Conn(cur))
    assert rows[0]["run_status"] == "INGESTED" and rows[0]["run_seq"] == 15
    assert rows[0]["gate_id"] == "CG-15" and rows[0]["attempts"] == 2
    assert rejections.summary(rows)["open"] == 1


# ── the close at promote ────────────────────────────────────────────────

def test_close_superseded_touches_only_other_superseded_runs_of_the_entity():
    eid, promoted = uuid.uuid4(), uuid.uuid4()
    old_run = uuid.uuid4()
    cur = _Cur([(uuid.uuid4(), old_run, "heatmap", "CG-15", "cells[3].synthesis")])
    closed = rejections.close_superseded(cur, eid, promoted)
    sql, args = cur.calls[0]
    assert sql.startswith("UPDATE rejection_ledger r SET closed_at = now()")
    assert "closed_by" not in sql, "no submission closed it; closed_by stays NULL"
    assert "run superseded by promoted run" in sql
    assert "ru.entity_id = %s" in sql and "r.run_id <> %s" in sql
    assert "enum_label(ru.status) = 'SUPERSEDED'" in sql
    assert "r.closed_at IS NULL" in sql
    assert args == (str(promoted), eid, promoted)
    assert closed == [{"rejection_id": closed[0]["rejection_id"], "run_id": str(old_run),
                       "page": "heatmap", "gate_id": "CG-15",
                       "path": "cells[3].synthesis"}]


def test_promote_reports_the_close_and_never_fails_on_it():
    """`promote_run` calls the close inside its transaction and reports the
    rows; a failure in the close is reported, not raised, and does not
    un-promote. Pinned by reading the source: the promote body cannot run
    without a database, and the property is in the code path."""
    src = (ROOT / "apps/mcp/dma_mcp/promote.py").read_text()
    demote = src.index("status = 'SUPERSEDED'")
    close = src.index("rejections.close_superseded(cur, entity_id, run_id)")
    commit = src.index("conn.commit()", close)
    assert demote < close < commit, "closed after the demote, before the commit"
    assert 'out["rejections_closed_as_superseded"] = closed_superseded' in src
    assert 'out["rejections_close_error"] = closed_error' in src


# ── the submission history ──────────────────────────────────────────────

def _sub(page, status, at, *, live=True, promoted=None, reasons=()):
    sid = uuid.uuid4()
    return (sid, page, status, "heatmap-surface-producer@v", "cr-1",
            dt.datetime(2026, 9, 1, at, tzinfo=dt.timezone.utc),
            None if live else dt.datetime(2026, 9, 1, at + 1, tzinfo=dt.timezone.utc),
            None if live else uuid.uuid4(),
            promoted, list(reasons), {"sections": 9})


def test_list_submissions_is_the_history_per_page_oldest_first():
    rows = [
        _sub("heatmap", "FAIL", 1, live=False,
             reasons=[{"gate_id": "CG-15", "severity": "block"},
                      {"gate_id": "SG-V4", "severity": "warn"}]),
        _sub("heatmap", "FAIL", 2, live=False, reasons=[{"gate_id": "CG-27", "severity": "block"}]),
        _sub("heatmap", "PASS", 3),
        _sub("overview", "PASS", 1, promoted=dt.datetime(2026, 9, 3, tzinfo=dt.timezone.utc)),
    ]
    cur = _Cur(rows)
    out = claims.list_submissions(_Conn(cur), "run-1")
    sql, args = cur.calls[0]
    assert "FROM submissions s" in sql and "submission_verdicts" in sql
    assert "ORDER BY s.page, s.submitted_at, s.id" in sql and args == ("run-1",)
    assert out["total"] == 4
    hm = out["per_page"]["heatmap"]
    assert hm == {"attempts": 3, "passes": 1, "fails": 2, "live_status": "PASS",
                  "first_pass_attempt": 3}
    assert out["per_page"]["overview"]["first_pass_attempt"] == 1
    first = out["submissions"][0]
    assert first["blocking_reasons"] == 1 and first["gates"] == ["CG-15"]
    assert first["live"] is False and first["superseded_by"]
    assert out["submissions"][3]["promoted_at"].startswith("2026-09-03")


def test_list_submissions_narrows_to_a_page():
    cur = _Cur([])
    out = claims.list_submissions(_Conn(cur), "run-1", "heatmap")
    sql, args = cur.calls[0]
    assert "AND s.page = %s" in sql and args == ("run-1", "heatmap")
    assert out["page"] == "heatmap" and out["submissions"] == []


def test_the_tool_is_registered_grouped_and_documented():
    server = (ROOT / "apps/mcp/server.py").read_text()
    assert "def list_submissions(run_id: str, page: str = \"\") -> dict:" in server
    gen = (ROOT / "plugins/dma-insights/scripts/gen_mcp_tools_md.py").read_text()
    assert '"list_submissions"' in gen
    doc = (ROOT / "plugins/dma-insights/docs/MCP-TOOLS.md").read_text()
    assert "### `list_submissions`" in doc


# ── against a migrated database, where one exists ───────────────────────

@pytest.fixture()
def db():
    try:
        import pg8000.dbapi
        conn = pg8000.dbapi.connect(host="localhost", port=5432, user="postgres",
                                    password="local", database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    cur = conn.cursor()
    eid = uuid.uuid4()
    slug = f"sup-test-{eid.hex[:8]}"
    cur.execute("""INSERT INTO entities (id, display_id, legal_name, status)
                   VALUES (%s,%s,%s,'ACTIVE')""", (eid, slug, "Superseded Test"))
    old, new = uuid.uuid4(), uuid.uuid4()
    cur.execute("""INSERT INTO runs (id, entity_id, run_seq, status)
                   VALUES (%s,%s,1,'SUPERSEDED')""", (old, eid))
    cur.execute("""INSERT INTO runs (id, entity_id, run_seq, status, is_active)
                   VALUES (%s,%s,2,'PROMOTED', TRUE)""", (new, eid))
    conn.commit()
    yield conn, cur, eid, slug, old, new
    cur.execute("DELETE FROM rejection_ledger WHERE run_id IN (%s, %s)", (old, new))
    cur.execute("DELETE FROM runs WHERE entity_id = %s", (eid,))
    cur.execute("DELETE FROM entities WHERE id = %s", (eid,))
    conn.commit()


def test_db_a_superseded_runs_tickets_are_closed_and_unlisted(db):
    conn, cur, eid, slug, old, new = db
    rejections.record_verdict(conn, old, "heatmap", None,
                              [{"gate_id": "CG-15", "path": "cells[0]", "severity": "block",
                                "message": "same claim", "section": "cell_evidence"}])
    conn.commit()
    assert rejections.open_corpus_wide(conn, slug) == [], "a SUPERSEDED run never lists"
    closed = rejections.close_superseded(cur, eid, new)
    conn.commit()
    assert [c["run_id"] for c in closed] == [str(old)]
    cur.execute("SELECT closed_at, closed_by, message FROM rejection_ledger WHERE run_id = %s", (old,))
    closed_at, closed_by, message = cur.fetchone()
    assert closed_at is not None and closed_by is None
    assert "run superseded by promoted run" in message
