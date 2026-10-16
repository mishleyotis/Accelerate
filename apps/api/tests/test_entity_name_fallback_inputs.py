"""The API hands the web everything its name fallback reads.

The web shows a client by `entityName`: legal name -> trading name ->
display id. SWBC promoted with `legal_name` NULL, and the directory and page
entity blocks carried no trading name at all, so the middle rung had nothing
to read. Both now carry `trading_name` (0061 puts it on serving_directory);
neither invents a legal name (invariant 9).
"""
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

pytest.importorskip("httpx")
from fastapi.testclient import TestClient                        # noqa: E402

from dma_api import main                                         # noqa: E402

ROW = ("53d062c3-e309-4033-9438-297b2b8505aa", "swbc", None, "IB", None,
       "7968492e-ba03-47fd-93c3-93f5867f1d43", "REQ-1", 1, True, "PROMOTED",
       2.01, 760, datetime(2026, 9, 30, tzinfo=timezone.utc),
       datetime(2026, 10, 1, tzinfo=timezone.utc), [], 0,
       date(2026, 9, 30), "STATED", "manifest.completed_at",
       date(2027, 3, 30), "SWBC", ["IC", "CL", "RIA"])


class _Conn:
    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self._out = [ROW] if "FROM serving_directory" in sql else []

    def fetchall(self):
        return self._out

    def fetchone(self):
        return (0,)

    def close(self):
        pass


def test_the_directory_row_carries_the_trading_name(monkeypatch):
    monkeypatch.setattr(main, "_connect", lambda: _Conn())
    body = TestClient(main.app).get("/v1/directory?audience=internal").json()
    (ent,) = body["entities"]
    assert ent["name"] is None, "a missing legal name is never invented"
    assert ent["trading_name"] == "SWBC"
    assert ent["id"] == "swbc"
    assert ent["subvertical"] == "IB"
    assert ent["supplementary_subverticals"] == ["IC", "CL", "RIA"]
