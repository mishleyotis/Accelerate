"""An unresolved sub-vertical is an UNCHECKED vertical guard, not relevance 1.0.

RC-13 (SWBC gold audit, 2026-10-04): `fit.platform_fit` kept every cell when
the entity's sub-vertical did not resolve — correct, "not knowing who the
client is is not grounds for hiding scores" — and then reported
`relevance: 1.0` on every row, with only a context note saying it was
unchecked. A producer copied 1.0 onto every opportunity tile of a run whose
own reasoning trace called relevance unchecked; once the binding resolved,
the engine returned 0.971-0.98 and the served tiles were stale.

Invariant 9: a derived value is computed or null — never a default that looks
like data. The FIT still computes (neutrally); the RELEVANCE says it is null
and why.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from dma_mcp import fit as fit_mod  # noqa: E402

CELLS = [("P1C1.1.1", 2.0, "P1C1", "integration"),
         ("P1C1.1.2", 1.5, "P1C1", "integration")]


class _Cur:
    def __init__(self, sub_vertical):
        self.sv, self._rows = sub_vertical, []

    def execute(self, sql, args=None):
        if "JOIN entities" in sql:
            self._rows = [(self.sv, None)] if self.sv else []
        elif "FROM runs WHERE id" in sql:
            self._rows = [("run",)]
        elif "FROM subcap_scores" in sql:
            self._rows = [(sid, sc, cat, None, [area])
                          for sid, sc, cat, area in CELLS]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Conn:
    def __init__(self, sv):
        self._cur = _Cur(sv)

    def cursor(self):
        return self._cur


CAND = [{"platform": "MuleSoft", "l3_area": "Integration",
         "alignment": 0.5, "readiness": "green"}]


def test_entity_code_none_gives_relevance_none_not_one():
    got = fit_mod.platform_fit(_Conn(None), "run", CAND)
    row = got["platforms"][0]
    assert row["relevance"] is None, (
        "an unresolved sub-vertical reported relevance "
        f"{row['relevance']!r}; it is unchecked, so it is null")
    assert row["relevance_state"] == "unchecked"
    assert got["context"]["relevance_state"] == "unchecked"
    assert row["fit_score"] is not None, "the fit itself still computes"


def test_a_resolved_sub_vertical_still_reports_a_number():
    got = fit_mod.platform_fit(_Conn("Credit Unions"), "run", CAND)
    row = got["platforms"][0]
    assert isinstance(row["relevance"], float)
    assert got["context"]["relevance_state"] == "checked"
