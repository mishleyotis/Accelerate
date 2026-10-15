"""Owner, 2026-10-15 (AAA Western and Central New York):

  "they can include them as part of benchmark scores. But for peer analysis,
   then they are only researched with regard to that entity's focus area.
   Distinguish between peer benchmark (derived from an average of scores of
   already assessed entities), and peer comparison (looking at the selected
   peers and comparing them to the entity being assessed."

PEER BENCHMARK  — a number, the sub-vertical average; names no one.
PEER COMPARISON — the selected (locked) peers, researched only on the
                  client's focus areas; never scored by this engine.
Map: plugins/dma-insights/docs/PEER-BENCHMARK-VS-COMPARISON.md
"""
from __future__ import annotations

import pytest

from engine import prelim, relay, techscan
from fixtures import new_run, researched_run, two_category_selection


def _ts(wb, cells):
    return techscan.record(
        wb, product="Alkami Digital Banking", vendor="Alkami", layer="CUST",
        status="CLAIMED", method="technographic_scan", providers=["explorium"],
        basis="the Explorium export carries this row", subcaps=cells)


def _focus(wb):
    return [r for r in wb.rows("Focus_Areas") if r.get("ID")]


# ── comparison: selected peers only ──────────────────────────────────────

def test_a_peer_outside_the_locked_set_is_not_compared(tmp_path):
    run, wb, cells, _ = researched_run(tmp_path)
    ts = _ts(wb, [_focus(wb)[0]["Cells"].split(",")[0].strip()])
    with pytest.raises(techscan.ScanRefused, match="not in the locked peer set"):
        techscan.peer_record(wb, ts_id=ts, peer="Some Cohort Bank", deployed=None,
                             basis="searched its newsroom and careers pages")


def test_a_shared_first_word_is_not_the_same_peer(tmp_path):
    run, wb, cells, _ = researched_run(tmp_path)
    ts = _ts(wb, [_focus(wb)[0]["Cells"].split(",")[0].strip()])
    with pytest.raises(techscan.ScanRefused, match="not in the locked peer set"):
        techscan.peer_record(wb, ts_id=ts, peer="Peer Zeta CU", deployed=None,
                             basis="searched its newsroom and careers pages")


# ── comparison: on the client's focus areas only ─────────────────────────

def test_no_focus_area_no_comparison(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    prelim.peers(wb, ["Peer Alpha CU", "Peer Beta CU", "Peer Gamma CU"],
                 basis="inferred",
                 rule=("US credit unions in the 15-25bn asset band with a "
                       "geographic field of membership"))
    ts = _ts(wb, [wb.selected_subcaps()[0]])
    with pytest.raises(techscan.ScanRefused, match="no client focus area"):
        techscan.peer_record(wb, ts_id=ts, peer="Peer Alpha CU", deployed=None,
                             basis="searched its newsroom and careers pages")


def test_the_focus_area_is_inferred_and_recorded(tmp_path):
    run, wb, cells, _ = researched_run(tmp_path)
    fa = _focus(wb)[0]
    ts = _ts(wb, [fa["Cells"].split(",")[0].strip()])
    techscan.peer_record(wb, ts_id=ts, peer="peer alpha cu", deployed=None,
                         basis="searched its newsroom and careers pages")
    row = [r for r in wb.rows("Tech_Peer_Deployments") if r["TS_ID"] == ts][-1]
    assert row["Focus_ID"] == fa["ID"]
    assert row["Peer"] == "Peer Alpha CU"          # the locked spelling


def test_a_product_no_focus_area_reaches_is_out_of_scope(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection())
    wb = run.open()
    focus_cats = {c.strip().split(".")[0] for r in _focus(wb)
                  for c in str(r["Cells"]).split(",") if c.strip()}
    other = next(c for c in wb.selected_subcaps()
                 if c.split(".")[0] not in focus_cats)
    ts = _ts(wb, [other])
    with pytest.raises(techscan.ScanRefused, match="out of scope"):
        techscan.peer_record(wb, ts_id=ts, peer="Peer Alpha CU", deployed=None,
                             basis="searched its newsroom and careers pages")
    with pytest.raises(techscan.ScanRefused, match="out of scope"):
        techscan.peer_record(wb, ts_id=ts, peer="Peer Alpha CU", deployed=None,
                             basis="searched its newsroom and careers pages",
                             focus_id=_focus(wb)[0]["ID"])


def test_an_uncelled_product_needs_its_focus_named(tmp_path):
    run, wb, cells, _ = researched_run(tmp_path)
    ts = _ts(wb, None)
    with pytest.raises(techscan.ScanRefused, match="--focus"):
        techscan.peer_record(wb, ts_id=ts, peer="Peer Alpha CU", deployed=None,
                             basis="searched its newsroom and careers pages")
    techscan.peer_record(wb, ts_id=ts, peer="Peer Alpha CU", deployed=None,
                         basis="searched its newsroom and careers pages",
                         focus_id=_focus(wb)[0]["ID"])


def test_the_peer_probes_are_scoped_to_the_focus_areas(tmp_path):
    run, wb, cells, _ = researched_run(tmp_path)
    focus_cats = {c.strip().split(".")[0] for r in _focus(wb)
                  for c in str(r["Cells"]).split(",") if c.strip()}
    relay.report_probes(run, wb)
    for r in relay.requests(run).values():
        proves = str(r.get("proves") or "")
        if proves.startswith((relay.PEER_PROBE, relay.PEER_LAYER, relay.PEER_FOCUS)):
            assert str(r.get("subcap") or r.get("cell") or "").split(".")[0] in focus_cats \
                or not (r.get("subcap") or r.get("cell")), proves


# ── benchmark: a number, never the selected peers' ───────────────────────

def test_the_benchmark_row_counts_the_cohort_not_the_selected_set(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    prelim.peers(wb, ["Peer Alpha CU", "Peer Beta CU", "Peer Gamma CU"],
                 basis="inferred",
                 rule=("US credit unions in the 15-25bn asset band with a "
                       "geographic field of membership"))
    rows = [r for r in wb.rows("Peer_Benchmarks") if r.get("Category_ID")]
    assert rows and all(not r.get("Peer_N") for r in rows)
    assert int(wb.handoff_lock()["peer_n"]) == 3
    cat = rows[0]["Category_ID"]
    prelim.fill_cohort_peers(wb, {"sub_vertical": "CU", "entities": 6, "categories": {
        cat: {"n": 6, "mean": 2.4, "median": 2.3, "p25": 2.0, "p75": 2.8}}})
    got = next(r for r in wb.rows("Peer_Benchmarks") if r["Category_ID"] == cat)
    assert int(got["Peer_N"]) == 6 and float(got["Peer_Median"]) == 2.4
    assert "get_cohort_benchmarks" in got["Peer_Basis"]


def test_the_selected_peers_are_not_scored_by_category(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    out = prelim.peers(wb, ["Peer Alpha CU", "Peer Beta CU", "Peer Gamma CU"],
                       basis="inferred",
                       rule=("US credit unions in the 15-25bn asset band with a "
                             "geographic field of membership"))
    cat = out["categories"][0]
    with pytest.raises(prelim.PrelimRefusal, match="not scored"):
        prelim.peer_median(wb, category=cat, median="2.5", basis="inferred",
                           source="peer research 2026-10-15",
                           peer_scores="2.0, 2.5, 3.0")
    # a published table someone else scored is admissible
    prelim.peer_median(wb, category=cat, median="2.5", basis="table",
                       source="published peer table 2026-10-15",
                       peer_scores="2.0, 2.5, 3.0")
