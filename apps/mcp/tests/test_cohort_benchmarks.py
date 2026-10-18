"""Peer scores are the sub-vertical cohort mean of entities already assessed
(owner, 2026-10-06), computed server-side, aggregates only."""
from __future__ import annotations

import json

from dma_mcp import cohort


def _rows():
    return [("cu-a", "P1C1", 2.0), ("cu-b", "P1C1", 3.0), ("cu-c", "P1C1", 2.5),
            ("cu-d", "P1C1", 1.5),
            ("cu-a", "P2C1", 2.0), ("cu-b", "P2C1", 4.0)]


def test_the_peer_score_is_the_mean_of_the_other_assessed_entities():
    out = cohort.summarise(_rows())
    p = out["categories"]["P1C1"]
    assert p["n"] == 4 and p["mean"] == 2.25 and p["median"] == 2.25
    assert p["p25"] <= p["mean"] <= p["p75"]
    assert out["entities"] == 4


def test_the_asking_entity_is_not_its_own_peer():
    out = cohort.summarise(_rows(), exclude_entity="CU-D")
    assert out["categories"]["P1C1"]["n"] == 3
    assert out["categories"]["P1C1"]["mean"] == 2.5


def test_below_the_floor_a_category_is_null_with_its_reason_never_imputed():
    p = cohort.summarise(_rows())["categories"]["P2C1"]
    assert p["mean"] is None and p["n"] == 2 and "floor is 3" in p["reason"]


def test_no_entity_is_named_in_what_leaves_the_module():
    text = json.dumps(cohort.summarise(_rows()))
    for ent in ("cu-a", "cu-b", "cu-c", "cu-d"):
        assert ent not in text


class _Cur:
    def __init__(self, rows):
        self.rows, self.sql, self.args = rows, None, None

    def execute(self, sql, args):
        self.sql, self.args = sql, args

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, rows):
        self.cur = _Cur(rows)

    def cursor(self):
        return self.cur


def test_the_query_reads_active_promoted_runs_of_the_sub_vertical_only():
    conn = _Conn([("cu-a", "alpha cu", "P1C1", 2.0), ("cu-b", "beta cu", "P1C1", 3.0),
                  ("cu-c", "gamma cu", "P1C1", 4.0), ("me", "first tech", "P1C1", 1.0)])
    out = cohort.cohort_benchmarks(conn, "CU", exclude_entity_name="First Tech")
    assert "r.is_active" in conn.cur.sql and "promoted_at IS NOT NULL" in conn.cur.sql
    assert conn.cur.args == ("CU",)
    assert out["categories"]["P1C1"] == {"n": 3, "mean": 3.0, "median": 3.0,
                                         "p25": 2.5, "p75": 3.5}
    assert out["basis"] == "recomputed" and out["sub_vertical"] == "CU"


def test_the_tool_is_registered_and_documented():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    assert "def get_cohort_benchmarks(" in (root / "apps/mcp/server.py").read_text()
    assert "get_cohort_benchmarks" in (root / "plugins/dma-insights/docs/MCP-TOOLS.md").read_text()


# ── cell grain (owner request, 2026-10-07, Arbor Bank) ─────────────────

def test_cell_grain_is_the_mean_of_the_other_entities_scores_for_that_cell():
    conn = _Conn([("cl-a", "alpha bank", "P2C2.2.CL1", 2.0),
                  ("cl-b", "beta bank", "P2C2.2.CL1", 3.0),
                  ("cl-c", "gamma bank", "P2C2.2.CL1", 1.0),
                  ("me", "arbor bank", "P2C2.2.CL1", 1.5)])
    out = cohort.cell_benchmarks(conn, "CL", ["P2C2.2.CL1"],
                                 exclude_display_id="me")
    assert "r.is_active" in conn.cur.sql and "promoted_at IS NOT NULL" in conn.cur.sql
    assert conn.cur.args == ("CL", ["P2C2.2.CL1"])
    assert out["cells"]["P2C2.2.CL1"]["n"] == 3
    assert out["cells"]["P2C2.2.CL1"]["mean"] == 2.0
    assert out["grain"] == "cell" and "categories" not in out


def test_a_cell_below_the_floor_or_unscored_is_null_with_its_reason():
    conn = _Conn([("cl-a", "a", "P1C1.1.1", 2.0), ("cl-b", "b", "P1C1.1.1", 3.0)])
    cells = cohort.cell_benchmarks(conn, "CL", ["P1C1.1.1", "P9C9.9.9"])["cells"]
    assert cells["P1C1.1.1"]["mean"] is None and "floor is 3" in cells["P1C1.1.1"]["reason"]
    assert "for this cell" in cells["P1C1.1.1"]["reason"]
    assert cells["P9C9.9.9"]["mean"] is None and cells["P9C9.9.9"]["n"] == 0


def test_cell_grain_names_no_entity_and_refuses_an_unbounded_list():
    conn = _Conn([(f"cl-{i}", f"bank {i}", "P1C1.1.1", 2.0) for i in range(4)])
    text = json.dumps(cohort.cell_benchmarks(conn, "CL", ["P1C1.1.1"]))
    for i in range(4):
        assert f"cl-{i}" not in text and f"bank {i}" not in text
    too_many = [f"P1C1.1.{i}" for i in range(cohort.CELL_LIMIT + 1)]
    assert "error" in cohort.cell_benchmarks(_Conn([]), "CL", too_many)
    assert cohort.cell_benchmarks(_Conn([]), "CL", [])["error"] == "subcap_ids_required"


# ── the fit engine reads a full-scope run's cells in slices (EPIC, 2026-10-18) ──

class _FitCur:
    """Answers the entity lookup _cell_peers makes, then the cohort reads."""
    def __init__(self, cohort_rows):
        self.cohort_rows, self.calls, self._last = cohort_rows, [], None

    def execute(self, sql, args):
        self._last = (sql, args)
        if "subcap_scores" in sql:
            self.calls.append(list(args[1]))

    def fetchone(self):
        return ("IB", "me", "me broker")

    def fetchall(self):
        sql, args = self._last
        ids = set(args[1])
        return [r for r in self.cohort_rows if r[2] in ids]


class _FitConn:
    def __init__(self, cur):
        self.cur = cur

    def cursor(self):
        return self.cur


def test_a_run_wider_than_the_cohort_limit_still_gets_its_gap_row_peers():
    from dma_mcp import fit
    n = cohort.CELL_LIMIT + 194                     # EPIC served 694 cells
    ids = [f"P1C1.{i // 10}.{i % 10}" for i in range(n)]
    last = ids[-1]                                  # beyond the first slice
    rows = [(f"ib-{e}", f"broker {e}", sid, 2.0 + e) for e in range(3)
            for sid in (ids[0], last)]
    cur = _FitCur(rows)
    cells = {sid: {"score": 1.0, "peer": None} for sid in ids}
    fit._cell_peers(_FitConn(cur), cur, "run-1", cells)
    assert len(cur.calls) == 2 and all(len(c) <= cohort.CELL_LIMIT for c in cur.calls)
    assert cells[ids[0]]["peer"] == 3.0 and cells[last]["peer"] == 3.0
    assert cells[ids[1]]["peer"] is None            # unscored by the cohort: stays null


def test_a_refused_cohort_read_is_logged_never_read_as_no_peers(caplog, monkeypatch):
    from dma_mcp import fit
    monkeypatch.setattr(cohort, "cell_benchmarks",
                        lambda *a, **k: {"error": "too_many_subcap_ids: 9 > 8"})
    cur = _FitCur([])
    with caplog.at_level("WARNING"):
        fit._cell_peers(_FitConn(cur), cur, "run-1", {"P1C1.1.1": {"peer": None}})
    assert "refused" in caplog.text and "too_many_subcap_ids" in caplog.text
