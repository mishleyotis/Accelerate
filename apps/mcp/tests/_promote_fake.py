"""A connection that answers exactly what promote_run asks, from fixtures.

The promote-time re-checks (promote_checks.py) are pinned against this
rather than only against the real schema, so they run in every environment —
a gate whose tests skip without a database is a gate CI may never exercise.
Shared by test_promote_parity / _refits / _stale_empty_state.
"""
from __future__ import annotations

import datetime as _dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from dma_mcp.contracts import PAGES, sections  # noqa: E402

RUN = "11111111-1111-1111-1111-111111111111"
ENTITY = "22222222-2222-2222-2222-222222222222"
ENV = {"produced_at": "2026-10-04T12:00:00Z", "producer_version": "test@1",
       "e_ids": [], "internal_only": []}
EMPTY = {"reason": "Walking-skeleton empty state",
         "sources_searched": ["package", "research", "enrichment"]}


def _thread_for(name: str) -> str:
    return f"Thread for {name}: " + " ".join(["thread"] * 49)


def skeleton() -> dict:
    """{page: payload} — every section an envelope and an empty state."""
    out = {}
    for page in PAGES:
        out[page] = {}
        for name in sections(page):
            body = {**ENV, "empty_state": dict(EMPTY)}
            if "narrative_thread" in sections(page)[name]["fields"]:
                body["narrative_thread"] = _thread_for(name)
            out[page][name] = body
    return out


class Cur:
    def __init__(self, pages, sub_vertical="Credit Unions", cells=()):
        self.pages, self.sv, self.cells = pages, sub_vertical, list(cells)
        self._rows, self.sql = [], []

    def execute(self, sql, args=None):
        s = " ".join(sql.split())
        self.sql.append(s)
        if "FOR UPDATE" in s and "FROM runs" in s:
            self._rows = [(ENTITY,)]
        elif s.startswith("SELECT enum_label(page)"):
            self._rows = [(p, "PASS", f"sub-{p}", body, "test@1", "producer")
                          for p, body in self.pages.items()]
        elif "JOIN entities" in s:
            self._rows = [(self.sv, None)] if self.sv else []
        elif "FROM runs WHERE id" in s and "promoted_at" not in s:
            self._rows = [("run",)]
        elif "FROM subcap_scores" in s:
            self._rows = [(sid, sc, cat, None, [area])
                          for sid, sc, cat, area in self.cells]
        elif "SELECT promoted_at FROM runs" in s:
            self._rows = [(_dt.datetime(2026, 10, 4, tzinfo=_dt.timezone.utc),)]
        elif "FROM submissions" in s and "page = %s" in s and args:
            body = self.pages.get(args[1])
            self._rows = [(body,)] if body is not None else []
        else:
            self._rows = []
        self.rowcount = len(self._rows)

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class Conn:
    def __init__(self, pages, **kw):
        self.cur = Cur(pages, **kw)
        self.commits = self.rollbacks = 0

    def cursor(self):
        return self.cur

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def wrote_anything(conn) -> bool:
    return any(s.startswith(("INSERT", "DELETE", "UPDATE runs"))
               for s in conn.cur.sql)
