"""The read half of submit, which did not exist.

Invariant 3 retains promoted staging rows so that fixing one card costs one
resubmission rather than six re-syntheses. The skill documents that flow. It
works only while the producer still holds the payload it sent, and that does
not survive a session — nothing in this connector could hand a staged
submission back.

Measured 2026-08-15 on the second client: a producer asked to repair the
heatmap so ten newly-evidenced cells would stop reading as alerts declined,
correctly, because the only copy it could reach was a SERVED projection that
had already lost `internal_only` on all nine sections. Resubmitting that would
have promoted the redaction. The repair the retention design exists to make
cheap was the one repair it could not make.
"""
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp import staged  # noqa: E402

WHEN = dt.datetime(2026, 8, 9, 5, 18, tzinfo=dt.timezone.utc)


class _Cur:
    def __init__(self, row): self._row, self.sql = row, None
    def execute(self, sql, args=None): self.sql = sql
    def fetchone(self): return self._row


class _Conn:
    def __init__(self, row): self._row = row
    def cursor(self): return _Cur(self._row)


def _row(payload, status="PASS"):
    """Column order matches the SELECT in staged.py — if that query changes
    and this does not, the test is measuring a fiction."""
    return (1234, status, json.dumps(payload), WHEN, "p/1.0", "c/7.0", None)


PAYLOAD = {
    "alerts": {"alerts": [{"a_id": "A-1", "severity": "high"}],
               "internal_only": ["r_layer"]},
    "cell_evidence": {"items": [{"cell": f"P1C1.{i}", "text": "x" * 900}
                                for i in range(300)]},
    "grid": {"cells": [{"id": "P1C1.1", "score": 2.4}]},
}


def test_no_section_returns_the_index_with_sizes():
    out = staged.get_staged_payload(_Conn(_row(PAYLOAD)), "r", "heatmap")
    assert out["submission_id"] == "1234" and out["status"] == "PASS"
    idx = out["sections"]
    assert set(idx) == {"alerts", "cell_evidence", "grid"}
    assert idx["alerts"]["inline"] is True
    assert idx["cell_evidence"]["inline"] is False, (
        "a 270KB section must be flagged before the caller asks for it")
    assert idx["alerts"]["keys"] == ["alerts", "internal_only"]
    assert out["total_bytes"] > idx["cell_evidence"]["bytes"]


def test_a_small_section_comes_back_verbatim_with_internal_only_intact():
    """The exact loss that stopped the repair. `internal_only` names the paths
    the SERVE layer strips; a readback that stripped them too would hand back
    a payload whose resubmission promotes the redaction."""
    out = staged.get_staged_payload(_Conn(_row(PAYLOAD)), "r", "heatmap",
                                    "alerts")
    assert out["data"] == PAYLOAD["alerts"]
    assert out["data"]["internal_only"] == ["r_layer"]
    assert "error" not in out


def test_an_oversized_section_is_described_never_truncated():
    """A truncated payload that LOOKS whole is worse than a refusal: resubmit
    it and a complete section is silently emptied."""
    out = staged.get_staged_payload(_Conn(_row(PAYLOAD)), "r", "heatmap",
                                    "cell_evidence")
    assert out["error"] == "section_too_large"
    assert "data" not in out, "it must not hand back a partial body"
    assert out["item_count"] is None or out["keys"] == ["items"]
    assert out["bytes"] > staged.SECTION_INLINE_BYTES


def test_an_unknown_section_names_what_is_actually_there():
    out = staged.get_staged_payload(_Conn(_row(PAYLOAD)), "r", "heatmap",
                                    "alertz")
    assert out["error"] == "unknown_section"
    assert "alerts" in out["hint"]


def test_no_live_submission_says_so_rather_than_returning_empty():
    out = staged.get_staged_payload(_Conn(None), "r", "heatmap")
    assert out["error"] == "no_staged_submission"
    assert "sections" not in out, "an empty index reads as an empty page"


def test_it_reads_the_live_row_only():
    """A superseded row is not what a resubmit replaces. Returning one would
    hand the producer a payload that is already history."""
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "staged.py").read_text()
    assert "superseded_at IS NULL" in src


def test_it_reads_submissions_not_the_serving_tables():
    """Serving tables are the promoted projection, written by the writer
    registry. The staged row is the thing a resubmit supersedes."""
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "staged.py").read_text()
    assert "FROM submissions" in src
    for served in ("overview_", "heatmap_", "serving"):
        assert f"FROM {served}" not in src


def test_a_dict_payload_from_the_driver_is_handled_as_well_as_a_string():
    """pg8000 returns a JSON column already decoded; psycopg may not. A
    readback that only handled one would work in tests and fail in prod."""
    row = (1, "PASS", PAYLOAD, WHEN, "p", "c", None)   # already a dict
    out = staged.get_staged_payload(_Conn(row), "r", "heatmap", "grid")
    assert out["data"] == PAYLOAD["grid"]
