"""Reading back a SUPERSEDED submission.

THE TRAP, hit on 2026-08-19. A resubmit supersedes the previous submission
for that page. If the new payload omits a section the old one carried —
easily done, because a section over the inline budget is DESCRIBED by
`get_staged_payload` rather than returned, so a payload rebuilt from that
read simply does not have it — the resubmit fails CG-01 on the missing
section AND the content is now behind a row the tool will not hand back.

Measured: a heatmap resubmit dropped `cell_evidence`, 1.36 MB across 697
cells. Nothing was lost from the database. The tool refusing to read a
superseded row was the whole of the problem.
"""
import json
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
from dma_mcp import staged  # noqa: E402


class _Cur:
    """The two queries `staged` makes, answered from a dict of rows."""

    def __init__(self, rows):
        self.rows, self._out = rows, None

    def execute(self, sql, args):
        if "s.id = %s" in sql:
            run_id, page, sub_id = args
            self._out = self.rows.get((run_id, page, sub_id))
        else:
            run_id, page = args
            self._out = next((r for k, r in self.rows.items()
                              if k[0] == run_id and k[1] == page
                              and r[-1] == "LIVE"), None)
        if self._out is not None:
            self._out = self._out[:-1]

    def fetchone(self):
        return self._out


class _Conn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur


RUN, PAGE = "run-1", "heatmap"
OLD, NEW = "sub-old", "sub-new"
BIG = {"cells": [{"subcap_id": f"P1C1.1.{i}"} for i in range(1, 400)]}


def _rows():
    return {
        (RUN, PAGE, OLD): (OLD, "PASS", json.dumps(
            {"cell_evidence": BIG, "alerts": {"alerts": []}}),
            None, "p@1", "cr-1", None, "SUPERSEDED"),
        (RUN, PAGE, NEW): (NEW, "FAIL", json.dumps(
            {"alerts": {"alerts": []}}),
            None, "p@1", "cr-1", None, "LIVE"),
    }


def test_the_live_read_returns_the_failure_that_dropped_the_section():
    out = staged.get_staged_payload(_Conn(_Cur(_rows())), RUN, PAGE)
    assert out["submission_id"] == NEW
    assert "cell_evidence" not in out["sections"]


def test_the_superseded_row_is_reachable_by_id():
    """The recovery. Without it a producer has to re-author 697 cells."""
    out = staged.get_staged_payload(_Conn(_Cur(_rows())), RUN, PAGE,
                                    submission_id=OLD)
    assert out["submission_id"] == OLD
    assert "cell_evidence" in out["sections"]


def test_the_recovered_section_comes_back_whole():
    """A single-section read answers flat — `section` + `data` — so a caller
    that reaches for `sections[name]` gets a KeyError, not a silent None."""
    out = staged.get_staged_payload(_Conn(_Cur(_rows())), RUN, PAGE,
                                    section="cell_evidence", submission_id=OLD)
    assert out["section"] == "cell_evidence"
    assert out["data"] == BIG
    assert "sections" not in out


def test_an_unknown_id_says_so_rather_than_falling_back_to_live():
    """Silently serving the live row would hand back the very payload the
    caller is trying to recover FROM, and it would look like it worked."""
    out = staged.get_staged_payload(_Conn(_Cur(_rows())), RUN, PAGE,
                                    submission_id="sub-nope")
    assert out["error"] == "unknown_submission"
    assert "sections" not in out


def test_the_absent_page_hint_names_the_recovery_route():
    out = staged.get_staged_payload(_Conn(_Cur({})), RUN, "overview")
    assert out["error"] == "no_staged_submission"
    assert "submission_id" in out["hint"], \
        "a producer in this hole needs the way out in the message"


# ── Reading an oversize section back, in parts ─────────────────────────

HUGE = {"cells": [{"subcap_id": f"P{p}C{c}.{i}.{j}", "synthesis": "x" * 400}
                  for p in range(1, 5) for c in range(1, 5)
                  for i in range(1, 6) for j in range(1, 6)]}


def _huge_rows():
    return {
        (RUN, PAGE, OLD): (OLD, "PASS", json.dumps({"cell_evidence": HUGE}),
                           None, "p@1", "cr-1", None, "SUPERSEDED"),
        (RUN, PAGE, NEW): (NEW, "FAIL", json.dumps({"alerts": {}}),
                           None, "p@1", "cr-1", None, "LIVE"),
    }


def _read(**kw):
    return staged.get_staged_payload(_Conn(_Cur(_huge_rows())), RUN, PAGE, **kw)


def test_an_oversize_section_still_refuses_to_truncate():
    out = _read(section="cell_evidence", submission_id=OLD)
    assert out["error"] == "section_too_large"
    assert "data" not in out and "chunk" not in out, \
        "a partial body that looks whole is worse than a refusal"
    assert out["parts"] > 1


def test_the_refusal_names_the_way_out():
    out = _read(section="cell_evidence", submission_id=OLD)
    assert f"part=1..{out['parts']}" in out["hint"]


def test_the_parts_reassemble_into_the_section_byte_for_byte():
    """The whole point. 697 cells came back or a producer re-authored them."""
    first = _read(section="cell_evidence", submission_id=OLD)
    blob = "".join(_read(section="cell_evidence", submission_id=OLD, part=i)["chunk"]
                   for i in range(1, first["parts"] + 1))
    assert json.loads(blob) == HUGE


def test_a_part_out_of_range_says_the_range():
    out = _read(section="cell_evidence", submission_id=OLD, part=9999)
    assert out["error"] == "no_such_part" and "1.." in out["hint"]


def test_a_small_section_needs_no_parts():
    rows = _rows()
    out = staged.get_staged_payload(_Conn(_Cur(rows)), RUN, PAGE,
                                    section="cell_evidence", submission_id=OLD)
    assert out.get("data") == BIG and "chunk" not in out
