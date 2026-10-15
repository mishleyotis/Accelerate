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
    """Routes the cohort's three queries: the run choice, the variant-cell
    inference, and the scores. `runs` rows are (run_id, ent, name, sv,
    promoted); `scores` rows are (run_id, key, value); `variants` rows are
    (run_id, subcap_id)."""

    def __init__(self, runs, scores, variants=()):
        self.runs, self.scores, self.variants = runs, scores, list(variants)
        self.sqls, self.args, self._out = [], [], []

    def execute(self, sql, args):
        self.sqls.append(sql)
        self.args.append(args)
        if "DISTINCT ON (r.entity_id)" in sql:
            self._out = list(self.runs)
        elif "~ '[.][A-Z]+[0-9]+$'" in sql:
            want = set(args[0])
            self._out = [r for r in self.variants if r[0] in want]
        else:
            want = set(args[0])
            self._out = [r for r in self.scores if r[0] in want]

    def fetchall(self):
        return self._out


class _Conn:
    def __init__(self, runs, scores, variants=()):
        self.cur = _Cur(runs, scores, variants)

    def cursor(self):
        return self.cur


def _cohort(rows, sv="CU", promoted=True):
    """rows: (ent, name, key, score) -> one run per entity."""
    runs, scores = [], []
    for ent, name, key, v in rows:
        rid = f"run-{ent}"
        if rid not in {r[0] for r in runs}:
            runs.append((rid, ent, name, sv, promoted))
        scores.append((rid, key, v))
    return runs, scores


def test_the_query_chooses_one_run_per_entity_promoted_first_withdrawn_never():
    runs, scores = _cohort([("cu-a", "alpha cu", "P1C1", 2.0), ("cu-b", "beta cu", "P1C1", 3.0),
                            ("cu-c", "gamma cu", "P1C1", 4.0), ("me", "first tech", "P1C1", 1.0)])
    conn = _Conn(runs, scores)
    out = cohort.cohort_benchmarks(conn, "CU", exclude_entity_name="First Tech")
    sql = conn.cur.sqls[0]
    assert "DISTINCT ON (r.entity_id)" in sql and "withdrawn_at IS NULL" in sql
    assert "SUPERSEDED" in sql
    assert sql.index("r.is_active AND r.promoted_at IS NOT NULL) DESC") > sql.index("ORDER BY")
    assert out["categories"]["P1C1"] == {"n": 3, "mean": 3.0, "median": 3.0,
                                         "p25": 2.5, "p75": 3.5}
    assert out["basis"] == "recomputed" and out["sub_vertical"] == "CU"


# ── AAA Western and Central New York, first promotion 2026-10-15 ──────────
#    IB read 2 entities while six scored brokerages sat in the store:
#    unpromoted, and spelled "Insurance Brokers" / "Insurance Brokerages (IB)"
#    / NULL rather than "IB".

def test_an_assessed_but_unpromoted_entity_is_a_peer():
    runs, scores = _cohort([("ib-a", "a", "P1C1", 2.0), ("ib-b", "b", "P1C1", 3.0)],
                           sv="IB", promoted=True)
    runs.append(("run-ib-c", "ib-c", "c", "IB", False))
    scores.append(("run-ib-c", "P1C1", 4.0))
    out = cohort.cohort_benchmarks(_Conn(runs, scores), "IB")
    assert out["categories"]["P1C1"]["n"] == 3
    assert out["categories"]["P1C1"]["mean"] == 3.0
    assert out["assessed_unpromoted"] == 1


def test_the_sub_vertical_is_resolved_through_the_alias_table_not_matched_literally():
    runs = [("r1", "townebank", "t", "Insurance Brokers", False),
            ("r2", "alera", "a", "Insurance Brokerages (IB)", False),
            ("r3", "sv7", "s", "SV7", True),
            ("r4", "a-cu", "c", "Credit Unions", True)]
    scores = [(r[0], "P2C1", 2.0) for r in runs]
    out = cohort.cohort_benchmarks(_Conn(runs, scores), "IB")
    assert out["categories"]["P2C1"]["n"] == 3        # the credit union is not a peer
    out2 = cohort.cohort_benchmarks(_Conn(runs, scores), "Insurance Brokerages")
    assert out2["categories"]["P2C1"]["n"] == 3


def test_a_null_sub_vertical_is_inferred_only_from_one_sub_vertical_s_variant_cells():
    runs = [("r1", "x", "x", "IB", True), ("r2", "y", "y", "IB", True),
            ("r3", "onedigital", "o", None, False),      # IB variants only
            ("r4", "mixed", "m", None, False),           # IB and CU variants
            ("r5", "bare", "b", None, False)]            # no variant cells
    scores = [(r[0], "P1C1", 2.0) for r in runs]
    variants = [("r3", "P4C3.8.IB1"), ("r3", "P2C2.4.IB2"),
                ("r4", "P4C3.8.IB1"), ("r4", "P2C1.1.CU1")]
    out = cohort.cohort_benchmarks(_Conn(runs, scores, variants), "IB")
    assert out["categories"]["P1C1"]["n"] == 3


def test_the_asking_entity_is_excluded_even_when_it_is_the_promoted_one():
    runs, scores = _cohort([("aaa", "aaa western and central new york", "P1C1", 1.0),
                            ("b", "b", "P1C1", 2.0), ("c", "c", "P1C1", 3.0),
                            ("d", "d", "P1C1", 4.0)], sv="IB")
    out = cohort.cohort_benchmarks(_Conn(runs, scores), "IB",
                                   exclude_display_id="AAA")
    assert out["categories"]["P1C1"]["n"] == 3 and out["categories"]["P1C1"]["mean"] == 3.0


def test_counts_leave_the_module_never_names():
    runs, scores = _cohort([("ib-a", "alpha", "P1C1", 2.0)], sv="IB", promoted=False)
    text = json.dumps(cohort.cohort_benchmarks(_Conn(runs, scores), "IB"))
    assert "ib-a" not in text and "alpha" not in text and "run-ib-a" not in text


def test_the_tool_is_registered_and_documented():
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    assert "def get_cohort_benchmarks(" in (root / "apps/mcp/server.py").read_text()
    assert "get_cohort_benchmarks" in (root / "plugins/dma-insights/docs/MCP-TOOLS.md").read_text()


# ── cell grain (owner request, 2026-10-07, Arbor Bank) ─────────────────

def test_cell_grain_is_the_mean_of_the_other_entities_scores_for_that_cell():
    conn = _Conn(*_cohort([("cl-a", "alpha bank", "P2C2.2.CL1", 2.0),
                           ("cl-b", "beta bank", "P2C2.2.CL1", 3.0),
                           ("cl-c", "gamma bank", "P2C2.2.CL1", 1.0),
                           ("me", "arbor bank", "P2C2.2.CL1", 1.5)], sv="CL"))
    out = cohort.cell_benchmarks(conn, "CL", ["P2C2.2.CL1"],
                                 exclude_display_id="me")
    assert "withdrawn_at IS NULL" in conn.cur.sqls[0]
    assert conn.cur.args[-1][1] == ["P2C2.2.CL1"]
    assert out["cells"]["P2C2.2.CL1"]["n"] == 3
    assert out["cells"]["P2C2.2.CL1"]["mean"] == 2.0
    assert out["grain"] == "cell" and "categories" not in out


def test_a_cell_below_the_floor_or_unscored_is_null_with_its_reason():
    conn = _Conn(*_cohort([("cl-a", "a", "P1C1.1.1", 2.0), ("cl-b", "b", "P1C1.1.1", 3.0)],
                          sv="CL"))
    cells = cohort.cell_benchmarks(conn, "CL", ["P1C1.1.1", "P9C9.9.9"])["cells"]
    assert cells["P1C1.1.1"]["mean"] is None and "floor is 3" in cells["P1C1.1.1"]["reason"]
    assert "for this cell" in cells["P1C1.1.1"]["reason"]
    assert cells["P9C9.9.9"]["mean"] is None and cells["P9C9.9.9"]["n"] == 0


def test_cell_grain_names_no_entity_and_refuses_an_unbounded_list():
    conn = _Conn(*_cohort([(f"cl-{i}", f"bank {i}", "P1C1.1.1", 2.0) for i in range(4)],
                          sv="CL"))
    text = json.dumps(cohort.cell_benchmarks(conn, "CL", ["P1C1.1.1"]))
    for i in range(4):
        assert f"cl-{i}" not in text and f"bank {i}" not in text
    too_many = [f"P1C1.1.{i}" for i in range(cohort.CELL_LIMIT + 1)]
    assert "error" in cohort.cell_benchmarks(_Conn([], []), "CL", too_many)
    assert cohort.cell_benchmarks(_Conn([], []), "CL", [])["error"] == "subcap_ids_required"
