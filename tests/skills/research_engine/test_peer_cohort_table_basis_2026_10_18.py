"""EPIC (2026-10-18): the peer SET was frozen with basis `table` (chosen from a
published ranking), every Peer_Median stayed blank, and the cohort refill
skipped all sixteen rows because it read any `table` basis as "a published
peer table is already here". It skipped without a word, and EPIC promoted
with blank peers while the IB cohort figured every category.

Closed three ways: a `table` row wins only when it carries a figure; every
refill outcome is logged and recorded; and the page stage refuses when the
cohort figures a category whose peer row is still blank."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine import ledger as L, pipeline as P, prelim
from fixtures import researched_run

RULE = "Insurance Journal Top 100, ranks 1-20, revenue USD 0.85B-3.0B"


def _cohort(cats, mean=2.37):
    return {"entities": 3, "floor": 3, "basis": "recomputed", "sub_vertical": "CU",
            "categories": {c: {"n": 3, "mean": mean, "median": mean, "p25": 2.1, "p75": 2.6}
                           for c in cats}}


def _table_rows(wb):
    cats = [r["Category_ID"] for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")]
    for c in cats:
        wb.update_row("Peer_Benchmarks", "Category_ID", c,
                      {"Peer_Basis": f"table: {RULE}", "Peer_Median": ""})
    return cats


def test_a_blank_table_row_takes_the_cohort_and_keeps_its_set_rule(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    cats = _table_rows(wb)
    assert all(prelim.peer_row_wants_cohort(r, has_figure=True)
               for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID"))
    got = prelim.fill_cohort_peers(wb, _cohort(cats))
    assert got["filled"] == cats
    for r in wb.rows("Peer_Benchmarks"):
        if r.get("Category_ID"):
            assert float(r["Peer_Median"]) == 2.37
            assert prelim.peer_row_is_cohort_sourced(r)
            assert f"peer set rule: {RULE}" in r["Peer_Basis"], "the set's rule is carried"


def test_a_table_row_with_a_figure_still_wins(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    cats = _table_rows(wb)
    prelim.peer_median(wb, category=cats[0], median=3.1, basis="table",
                       source="published peer table, hand recorded")
    got = prelim.fill_cohort_peers(wb, _cohort(cats))
    assert cats[0] in got["kept"] and cats[0] not in got["filled"]


def test_cohort_unused_names_blank_rows_the_cohort_could_state(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    cats = _table_rows(wb)
    assert prelim.cohort_unused(wb, _cohort(cats)) == cats
    prelim.fill_cohort_peers(wb, _cohort(cats))
    assert prelim.cohort_unused(wb, _cohort(cats)) == []
    below = {**_cohort(cats), "categories": {c: {"n": 2, "mean": None} for c in cats}}
    run2, wb2, _, _ = researched_run(tmp_path / "b")
    assert prelim.cohort_unused(wb2, below) == [], "below the floor is disclosed, not blocked"


def _driver(wb, run, *, reads=None, cohort=None, logs=None):
    d = SimpleNamespace(wb=wb, run=run, state={},
                        opts=SimpleNamespace(log=(logs.append if logs is not None else
                                                  (lambda *a: None)), reads=reads))
    d.reopen = lambda: None
    d._md = lambda: {"sub_vertical": "CU", "entity_id": "x", "entity_name": "X"}
    return d


def test_the_page_stage_refuses_blank_peers_the_cohort_could_state(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    cats = _table_rows(wb)
    d = _driver(wb, run)

    def skipped_refill():            # a refill that read the cohort and wrote nothing
        d._cohort = _cohort(cats)
    d._cohort_peers = skipped_refill
    with pytest.raises(P.StageRefused, match="PEER_COHORT_UNUSED"):
        P.Pipeline._pages_prepare(d, P.PAGES_A)
    assert any(r.get("Gate") == "PEER_COHORT_UNUSED" and str(r.get("Verdict")) == "FAIL"
               for r in wb.rows("Gate_Log"))


def test_the_real_refill_fills_table_rows_and_the_page_stage_proceeds(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    cats = _table_rows(wb)
    logs = []
    reads = SimpleNamespace(cohort_benchmarks=lambda sv, **kw: _cohort(cats))
    d = _driver(wb, run, reads=reads, logs=logs)
    d._cohort_peers = lambda: P.Pipeline._cohort_peers(d)
    P.Pipeline._pages_prepare(d, P.PAGES_A)
    assert all(str(r.get("Peer_Median") or "").strip()
               for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID"))
    assert any("[COHORT]" in line and "filled" in line for line in logs)


def test_every_skipped_refill_says_so(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    _table_rows(wb)
    logs = []
    d = _driver(wb, run, reads=None, logs=logs)
    out = P.Pipeline._cohort_peers(d)
    assert out.get("skipped") == "no_reader"
    assert any("[COHORT] skipped" in line for line in logs)
    assert any(r.get("Gate") == "COHORT_PEERS" and str(r.get("Verdict")) == "NOT_RUN"
               for r in wb.rows("Gate_Log"))
