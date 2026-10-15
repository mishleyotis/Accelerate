"""Owner, 2026-10-15 (Verus Financial Partners): "Peer data is empty."

The run locked four peers, the RIA cohort held no other assessed entity, every
Peer_Benchmarks row read cannot_estimate, and every peer field on every page
served null — promoted. Below the cohort floor the locked peers are scored on
abbreviated public evidence; until a figure exists, or the owner records why
none can, no version is ingested and no page agent runs. A fixed run is
re-opened by the driver, never by hand.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from engine import pipeline as P

LOCK = {"locked_peer_set": "Campbell Deegan Financial|Godsey & Gibb|Juno|Kanawha",
        "peer_basis": "table", "peer_n": 4}


def _row(cid, median="", basis="cannot_estimate: sub-vertical cohort (RIA)"):
    return {"Category_ID": cid, "Category_Name": "", "Peer_Median": median,
            "Peer_Basis": basis, "Peer_Names": "A, B, C, D", "Peer_Scores": ""}


def test_a_locked_set_with_no_figure_is_missing():
    rows = [_row("P1C1"), _row("P1C2"), _row("P2C1", basis="")]
    m = P.peer_figures_missing(LOCK, rows)
    assert m and m["n_peers"] == 4 and m["n_categories"] == 3
    assert "cannot_estimate" in m["reason"] and "blank" in m["reason"]


def test_one_figure_anywhere_is_enough_and_no_lock_is_not_this_gate():
    rows = [_row("P1C1"), _row("P1C2", median=2.5, basis="inferred: abbreviated scoring")]
    assert P.peer_figures_missing(LOCK, rows) is None
    assert P.peer_figures_missing({"locked_peer_set": ""}, [_row("P1C1")]) is None
    assert P.peer_figures_missing({}, []) is None


def test_the_handoff_names_the_peers_the_categories_and_the_known_evidence(tmp_path):
    qa = tmp_path / "07_qa"
    qa.mkdir()
    wb = SimpleNamespace(
        handoff_lock=lambda: LOCK,
        metadata=lambda: {"entity_name": "Verus Financial Partners", "sub_vertical": "RIA"},
        rows=lambda tab: {
            "Peer_Benchmarks": [_row("P1C1"), _row("P1C2"), _row("P4C4")],
            "Evidence_Detail": [
                {"E_ID": "E-066", "Source_Name": "FINTRX — Godsey & Gibb profile", "Excerpt": "AUM"},
                {"E_ID": "E-175", "Source_Name": "Kanawha Capital client login", "Excerpt": "Schwab"},
                {"E_ID": "E-001", "Source_Name": "Verus Form ADV", "Excerpt": "custodian"},
            ]}[tab],
        selected_subcaps=lambda: ["P1C1.1.1"])
    run = SimpleNamespace(run_id="R-1", root=tmp_path, qa_dir=qa)
    h = P.peer_scoring_handoff(wb, run)
    doc = json.loads(Path(h["file"]).read_text())
    inv = doc["invocations"][0]
    assert inv["peers"] == ["Campbell Deegan Financial", "Godsey & Gibb", "Juno", "Kanawha"]
    assert [p["pillar"] for p in inv["pillars"]] == ["P1", "P4"]
    assert [c["id"] for c in inv["pillars"][0]["categories"]] == ["P1C1", "P1C2"]
    assert "Godsey & Gibb: E-066" in inv["known_evidence"]
    assert "Kanawha: E-175" in inv["known_evidence"]
    assert "Campbell Deegan Financial: none" in inv["known_evidence"]
    assert doc["workflow"].endswith("dma-peer-scoring.js")
    assert "engine.pipeline run --run R-1" in doc["then"]


def test_the_driver_stops_needs_peer_scoring_unless_the_owner_records_why(tmp_path):
    qa = tmp_path / "07_qa"
    qa.mkdir()
    gates = []
    logged = []
    wb = SimpleNamespace(
        handoff_lock=lambda: LOCK,
        metadata=lambda: {"entity_name": "V", "sub_vertical": "RIA"},
        rows=lambda tab: {"Peer_Benchmarks": [_row("P1C1")], "Evidence_Detail": []}[tab],
        selected_subcaps=lambda: ["P1C1.1.1"])
    orig = P.L.append_gate
    P.L.append_gate = lambda wb, **kw: gates.append(kw)
    try:
        d = SimpleNamespace(wb=wb, state={}, run=SimpleNamespace(run_id="R-1", root=tmp_path, qa_dir=qa),
                            opts=SimpleNamespace(allow_unscored_peers="", log=logged.append),
                            _save_state=lambda: None)
        caught = None
        try:
            P.Pipeline._require_peer_figures(d, "INGEST_A")
            assert False, "a locked set with no figure must stop the stage"
        except P.NeedsPeerScoring as e:
            caught = e
            assert "4 peer(s)" in str(e) and e.handoff.endswith("peer_scoring_workflow.json")
        assert gates and gates[-1]["gate"] == "PEER_FIGURES" and gates[-1]["blocking"] is True
        # the owner's recorded reason is the one escape, logged once
        d.opts.allow_unscored_peers = "peers identified, not scored: owner call 2026-10-15"
        P.Pipeline._require_peer_figures(d, "PAGES")
        P.Pipeline._require_peer_figures(d, "PAGES")
        waivers = [w for w in d.state["waivers"] if w.get("unscored_peers")]
        assert len(waivers) == 1
        assert [g["gate"] for g in gates].count("OWNER_DECISION_UNSCORED_PEERS") == 1
        assert isinstance(caught, P.StageRefused), "a NeedsPeerScoring is a stage refusal"
    finally:
        P.L.append_gate = orig


def test_reopen_clears_the_serving_version_and_names_what_is_reproduced():
    state = {"pages": {
        "overview": {"version": "B", "status": "pass", "versions": {"B": "pass"},
                     "shipped_mtime": {"B": 1.0}, "attempts_by_version": {"B": 4},
                     "n_history": [["B", "pass", 0, 146, None]]},
        "techstack": {"version": "B", "status": "pass",
                      "versions": {"A": "local_precheck_fail", "B": "pass"},
                      "shipped_mtime": {"A": 0.5, "B": 2.0},
                      "attempts_by_version": {"A": 2, "B": 3},
                      "n_history": [["A", "local_precheck_fail", 9, 0], ["B", "pass", 0, 48, None]]}},
        "package": {"verified": True, "folder": "/x"},
        "handoff_guard": {"PAGES_B:overview": {"n": 1}, "RESEARCH:P1C1": {"n": 2}},
        "needs_peer_scoring": {"stage": "INGEST_A"}}
    md = {"connector_run_id": "run-B", "promoted_at": "2026-10-15T17:32:15Z"}
    rec = P.apply_reopen(state, md, reproduce=("overview", "heatmap", "platform"),
                         why="peer figures recorded", now="2026-10-15T18:00:00Z")
    assert rec["reproduce"] == ["overview", "heatmap", "platform"]
    assert rec["restage"] == ["techstack", "insights", "context"]
    assert rec["previous_connector_run"] == "run-B"
    ov, ts = state["pages"]["overview"], state["pages"]["techstack"]
    assert "B" not in ov["versions"] and "B" not in ov["shipped_mtime"] and ov["status"] == "reopened"
    assert ts["versions"] == {"A": "local_precheck_fail"}, "version A's record is kept"
    assert ts["n_history"] == [["A", "local_precheck_fail", 9, 0]]
    assert state["package"] == {}
    assert "PAGES_B:overview" not in state["handoff_guard"] and "RESEARCH:P1C1" in state["handoff_guard"]
    assert "needs_peer_scoring" not in state
    assert state["reopen"] is rec and state["reopens"] == [rec]


def test_a_restaged_page_of_a_reopened_run_ships_from_disk_and_a_reproduced_one_does_not(tmp_path):
    sections = tmp_path / "08_sections"
    sections.mkdir()
    for p in ("insights", "overview"):
        f = sections / f"{p}.x.json"
        f.write_text("{}")
        import os
        os.utime(f, (1_700_000_000.0, 1_700_000_000.0))
    d = SimpleNamespace(state={"connector": {"ingest_b": {"at": "2023-11-15T00:00:00Z"}},
                               "reopen": {"restage": ["insights"], "reproduce": ["overview"]}})
    d._page_mtime = lambda page: max((x.stat().st_mtime for x in sections.glob(f"{page}.*.json")), default=0.0)
    d._version_ingested_at = lambda v: P.Pipeline._version_ingested_at(d, v)
    assert P.Pipeline._produced_for(d, "insights", "B"), "restaged: ships from disk by design"
    assert not P.Pipeline._produced_for(d, "overview", "B"), "reproduced: handed as a fresh production"


def test_peer_n_is_the_count_of_scored_peers():
    """Verus (2026-10-15): sixteen rows recorded from positional peer scores
    kept the cohort's Peer_N 0, and the strip served a median beside n 0."""
    from engine import prelim
    writes = []
    wb = SimpleNamespace(
        rows=lambda tab: [
            {"Category_ID": "P1C2", "Peer_Basis": "inferred: x", "Peer_Scores": "2.0,2.0,2.0,2.0",
             "Peer_Median": 2.0, "Peer_N": 0},
            {"Category_ID": "P1C3", "Peer_Basis": "inferred: x", "Peer_Scores": "2.0,NA,NA,NA",
             "Peer_Median": 2.0, "Peer_N": 0},
            {"Category_ID": "P1C1", "Peer_Basis": "cannot_estimate: x", "Peer_Scores": "NA,NA,NA,NA",
             "Peer_Median": "", "Peer_N": 4},
            {"Category_ID": "P2C1", "Peer_Basis": "table: published", "Peer_Scores": "",
             "Peer_Median": 3.0, "Peer_N": 5},
            {"Category_ID": "P2C2", "Peer_Basis": "recomputed: cohort", "Peer_Scores": "",
             "Peer_Median": 2.5, "Peer_N": 3}],
        update_row=lambda tab, key, cid, fields, **kw: writes.append((cid, fields)))
    out = prelim.recount_peer_n(wb)
    assert out == {"P1C2": 4, "P1C3": 1, "P1C1": 0}
    assert ("P2C1", {"Peer_N": 5}) not in writes and all(c != "P2C2" for c, _ in writes), \
        "a table or cohort row keeps its own count"


def test_a_half_applied_reopen_is_completed_and_a_second_run_is_idempotent():
    """The first --reopen on Verus wrote promoted_at and connector_run_id_prev
    and died on a Run_Metadata key the sheet does not have, before its state
    was saved. The next run must complete it, not refuse it as unpromoted."""
    md = {"connector_run_id": "run-B", "connector_run_id_prev": "run-B", "promoted_at": ""}
    sets, gates, logged = [], [], []
    orig = P.L.append_gate
    P.L.append_gate = lambda wb, **kw: gates.append(kw)
    try:
        d = SimpleNamespace(state={"pages": {}}, wb=object(),
                            opts=SimpleNamespace(reopen="peer figures recorded",
                                                 reproduce=("overview",), log=logged.append),
                            _md=lambda: md, _set_md=lambda k, v: sets.append((k, v)),
                            _save_state=lambda: None)
        P.Pipeline._apply_reopen(d)
        assert sets == [], "metadata already written by the half-applied re-open"
        assert d.state["reopen"]["reproduce"] == ["overview"]
        assert gates and gates[-1]["gate"] == "OWNER_REOPEN"
        # same reason again, still not promoted: nothing happens
        P.Pipeline._apply_reopen(d)
        assert len(gates) == 1 and len(d.state["reopens"]) == 1
        # a promoted run re-opens with its metadata written, no unknown key
        md2 = {"connector_run_id": "run-C", "connector_run_id_prev": "run-B",
               "promoted_at": "2026-10-15T20:00:00Z"}
        d2 = SimpleNamespace(state={"pages": {}}, wb=object(),
                             opts=SimpleNamespace(reopen="again", reproduce=(), log=logged.append),
                             _md=lambda: md2, _set_md=lambda k, v: sets.append((k, v)),
                             _save_state=lambda: None)
        P.Pipeline._apply_reopen(d2)
        assert sets == [("promoted_at", ""), ("connector_run_id_prev", "run-C")]
        # a run never promoted, with no half-applied trace, is refused
        md3 = {"connector_run_id": "run-D", "connector_run_id_prev": "run-C", "promoted_at": ""}
        d3 = SimpleNamespace(state={"pages": {}}, wb=object(),
                             opts=SimpleNamespace(reopen="x", reproduce=(), log=logged.append),
                             _md=lambda: md3, _set_md=lambda k, v: None, _save_state=lambda: None)
        try:
            P.Pipeline._apply_reopen(d3)
            assert False, "an unpromoted run has nothing to re-open"
        except P.StageRefused as e:
            assert "not promoted" in str(e)
    finally:
        P.L.append_gate = orig
