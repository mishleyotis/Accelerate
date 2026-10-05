"""The floors gate's worklist reaches the actors who can do it.

Measured on arbor-bank-2026-10-05 (2026-10-05): thirteen categories failed
their floors gate on cells that already held a claim — the primary query
never fired, a FACT resting on one source, volleys short, an empty cell with
no declared absence. The gate named those cells; the capability card, the
driver's batch planner and the workflow prompt all defined work as "a cell
with no claim", so none of them showed the named cells to anyone. Eleven
category workflows ran research agents that read an empty card and returned
"nothing open" (~215K agent tokens each, two rounds), the driver re-handed
the same categories, and the in-memory stall counter never fired because
each workflow-mode driver run is a fresh process.

Also pinned here, from the same run: the search-op ceiling advised on a
run-wide window nothing enforces ("5750 search-ops against a ceiling of 60"
with every category 42-60 searches clear), and a duplicated Run_Metadata key
froze `last_written_at` so the watchdog reported "no write for 7843s" one
second after a save.

Every test below FAILS on the pre-fix engine.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import floors_gate, ledger as L, orient, pipeline as P, runstate
from engine import pipeline_stub as S, preflight, watchdog
from fixtures import (challenge, good_synthesis, new_run, preflight_doc,
                      two_category_selection)

FACETS_BUT_PRIMARY = ("works", "fails", "value", "contradicts", "corroborates")


def _closed_with_primary_unfired(wb, cell):
    """A cell holding a synthesis, two sources and a challenge — and no
    primary-facet search. The gate fails it on `primary_unfired`."""
    for f in FACETS_BUT_PRIMARY:
        L.append_search(wb, subcap=cell, facet=f,
                        query=f'"Acme Credit Union" {cell} {f} probe',
                        tool="web_search", hits=2, kept=1, outcome="kept 1")
    L.append_search(wb, subcap=cell, facet="works",
                    query=f'"Acme Credit Union" {cell} connector probe',
                    tool="exa", hits=1, kept=1, outcome="kept 1")
    eids = []
    for i, (name, url) in enumerate((
            ("Annual Report 2025 p1", f"https://acme.example/ar25#{cell}"),
            ("NCUA Call Report 2025 — digital channel volumes",
             f"https://ncua.example/callreport/2025#{cell}"))):
        eids.append(L.append_evidence(
            wb, source_name=name, source_url=url, tier="T2",
            excerpt=("Alkami digital banking went live in Q3 2024 and reached "
                     f"47 percent member adoption within ninety days, restated "
                     f"at 52 percent in the 2025 report ({cell}, source {i + 1})."),
            subcaps=[cell], published="2025-06-01"))
    L.append_synthesis(wb, cell, good_synthesis(cell, eids),
                       actor="surface-producer")
    challenge(wb, cell)
    return eids


@pytest.fixture()
def deadlocked(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    _closed_with_primary_unfired(wb, cell)
    return run, wb, cell


# ── the one definition ────────────────────────────────────────────────────

def test_the_gate_fails_on_a_claimed_cell(deadlocked):
    run, wb, cell = deadlocked
    cat = cell.split(".")[0]
    v = floors_gate.run(wb, cat, require_synthesis=True, persist=False)
    assert "primary_unfired" in v["blocking"] and cell in v["primary_unfired"]
    rw = floors_gate.repair_worklist(wb, cat)
    assert cell in rw
    assert rw[cell]["terms"] == ["primary_unfired"]
    assert "primary" in rw[cell]["missing"]


def test_every_cell_level_blocking_term_has_a_repair_action():
    """A new blocking term with no repair action would name cells no
    researcher is ever shown — the deadlock, re-opened by one edit."""
    owed = set(floors_gate.BLOCKING_TERMS) - set(floors_gate.CHALLENGE_TERMS)
    assert owed <= set(floors_gate.REPAIR_ACTIONS), owed - set(floors_gate.REPAIR_ACTIONS)


def test_repair_cells_reads_both_finding_shapes():
    out = {"blocking": ["primary_unfired", "volleys_incomplete",
                        "single_source_fact", "challenge_missing"],
           "primary_unfired": ["P1C1.1.2"],
           "volleys_incomplete": [{"subcap": "P1C1.1.2", "missing": ["fails"]}],
           "single_source_fact": [{"subcap": "P1C1.4.2",
                                   "distinct_sources": ["a.example"]}],
           "challenge_missing": ["P1C1.9.9"]}
    rc = floors_gate.repair_cells(out)
    assert set(rc) == {"P1C1.1.2", "P1C1.4.2"}       # challenge cells are not research work
    assert rc["P1C1.1.2"]["missing"] == ["primary", "fails"]


# ── the card serves it ────────────────────────────────────────────────────

def test_the_card_serves_a_gate_named_claimed_cell(deadlocked):
    run, wb, cell = deadlocked
    cap = cell.rsplit(".", 1)[0]
    card = orient.capability_card(wb, cap, run=run)
    served = {c["cell"]: c for c in card["open_cells"]}
    assert cell in served, "the gate names this cell and the card hid it"
    assert served[cell]["repair"] and "primary" in served[cell]["missing"]
    assert cell in card["repair_cells"]
    assert "primary" in card["facets_owed"]


def test_the_card_accepts_a_category_id(deadlocked):
    run, wb, cell = deadlocked
    card = orient.capability_card(wb, cell.split(".")[0], run=run)
    assert cell in {c["cell"] for c in card["open_cells"]}


def test_a_gate_content_claimed_cell_stays_off_the_card(tmp_path):
    from fixtures import researched_run
    run, wb, cells, ev = researched_run(tmp_path)
    card = orient.capability_card(wb, cells[0].split(".")[0], run=run)
    assert card["open_cells"] == [] and card["repair_cells"] == []


# ── the planner counts it ─────────────────────────────────────────────────

def test_the_planner_batches_a_gate_named_claimed_cell(deadlocked):
    run, wb, cell = deadlocked
    cap, cat = cell.rsplit(".", 1)[0], cell.split(".")[0]
    unclaimed = sum(1 for r in wb.scoring_rows()
                    if str(r.get("SubCap_ID") or "") in set(wb.selected_subcaps())
                    and str(r.get("SubCap_ID")).rsplit(".", 1)[0] == cap
                    and not str(r.get("Dominant_Claim") or "").strip())
    caps = P._open_capabilities(wb)
    assert caps.get(cat, {}).get(cap) == unclaimed + 1, \
        "the gate-named claimed cell is not counted as work"


# ── the driver stops handing out work nobody can do ───────────────────────

def _pipe(tmp_path, *, stall_rounds=2):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    opts = P.Options(dispatcher=S.StubDispatcher(handlers={}), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False,
                     folder_root=tmp_path / "client_out", ingest_poll_s=0,
                     sleep=lambda s: None, log=lambda s: None,
                     stall_rounds=stall_rounds, research_mode="workflow")
    return P.Pipeline(run, opts)


def _fake_reasons(monkeypatch, reasons):
    from engine import brief
    monkeypatch.setattr(brief, "categories_needing_dispatch",
                        lambda wb: {"dispatch": sorted(reasons), "passed": [],
                                    "reasons": reasons})


def test_a_failing_category_with_no_work_is_withheld(tmp_path, monkeypatch):
    p = _pipe(tmp_path)
    _fake_reasons(monkeypatch, {"P1C1": ["boilerplate"]})
    monkeypatch.setattr(P.Pipeline, "_research_progress", lambda self: {"P1C1": (1, 0, 0, 0, 0)})
    keep, withheld, _, _ = p._withhold_unworkable(["P1C1"], {}, {})
    assert keep == [] and withheld["P1C1"].startswith("UNSERVABLE")


def test_challenge_only_work_is_still_handed(tmp_path, monkeypatch):
    p = _pipe(tmp_path)
    _fake_reasons(monkeypatch, {"P1C1": ["challenge_missing"]})
    monkeypatch.setattr(P.Pipeline, "_research_progress", lambda self: {})
    keep, withheld, _, _ = p._withhold_unworkable(["P1C1"], {}, {})
    assert keep == ["P1C1"] and not withheld


def test_the_stall_count_survives_the_process(tmp_path, monkeypatch):
    p = _pipe(tmp_path, stall_rounds=2)
    _fake_reasons(monkeypatch, {"P1C1": ["primary_unfired"]})
    monkeypatch.setattr(P.Pipeline, "_research_progress", lambda self: {"P1C1": (3, 1, 0, 2, 0)})
    work = {"P1C1": {"P1C1.1": 4}}
    sig = [3, 1, 0, 2, 0, -4]
    p._workflow_agents_captured = 5                       # the last handoff WAS worked
    keep, withheld, prog, stalls = p._withhold_unworkable(
        ["P1C1"], work, {"progress": {"P1C1": sig}, "stalls": {"P1C1": 1}})
    assert stalls["P1C1"] == 2 and withheld["P1C1"].startswith("STALLED") and keep == []
    # a handoff nobody worked neither advances nor resets the count
    p._workflow_agents_captured = 0
    keep, withheld, _, stalls = p._withhold_unworkable(
        ["P1C1"], work, {"progress": {"P1C1": sig}, "stalls": {"P1C1": 1}})
    assert stalls["P1C1"] == 1 and keep == ["P1C1"]
    # fewer cells carrying work IS progress
    p._workflow_agents_captured = 5
    keep, _, _, stalls = p._withhold_unworkable(
        ["P1C1"], {"P1C1": {"P1C1.1": 3}}, {"progress": {"P1C1": sig}, "stalls": {"P1C1": 1}})
    assert stalls["P1C1"] == 0 and keep == ["P1C1"]


def test_everything_withheld_stops_the_driver_for_a_person(tmp_path, monkeypatch):
    p = _pipe(tmp_path)
    monkeypatch.setattr(P.Pipeline, "_withhold_unworkable",
                        lambda self, need, oc, prev: ([], {c: "UNSERVABLE: test" for c in need}, {}, {}))
    out = p.run_all()
    assert out["outcome"] == "STALLED" and out["needs"] == "person", out
    assert out["outcome"] not in P.EXIT_ZERO_OUTCOMES
    state = json.loads((p.run.qa_dir / P.STATE_NAME).read_text())
    assert state["last_outcome"] == "STALLED" and "UNSERVABLE" in state["last_reason"]


# ── the workflow never sends a label where a capability belongs ──────────

def test_the_workflow_has_no_label_only_batches():
    src = (P.PLUGIN / P.RESEARCH_WORKFLOW).read_text()
    for label in ("(all open capabilities)", "(cells the gate names)"):
        assert label not in src, f"label-only batch {label!r} is back"
    assert "repair" in src
    assert "a cell with a synthesis or declared absence is done; skip it" not in src


# ── the ceiling is advised at the scope it is enforced ───────────────────

def _log(wb, cell, n, tag):
    for i in range(n):
        L.append_search(wb, subcap=cell, facet="works", query=f"{tag} probe {i}",
                        tool="web_search", hits=0, kept=0, outcome="no hits")


def test_two_categories_under_their_walls_are_not_at_the_ceiling(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    wb = run.open()
    a, b = sorted({c.split(".")[0] for c in wb.selected_subcaps()})[:2]
    cell_a = next(c for c in wb.selected_subcaps() if c.startswith(a))
    cell_b = next(c for c in wb.selected_subcaps() if c.startswith(b))
    runstate.checkpoint(wb, "test start", scope=[a, b, "PRELIM"])
    _log(wb, cell_a, 40, "a")
    _log(wb, cell_b, 40, "b")
    s = L.stats(wb)
    assert s["checkpoint_required"] is False, s     # 80 run-wide, 40 per enforced scope
    assert s["search_ops_since_checkpoint"] == 40 and s["scopes_at_ceiling"] == []


def test_a_category_at_its_wall_is_named(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    cat = cell.split(".")[0]
    runstate.checkpoint(wb, "test start", scope=[cat])
    _log(wb, cell, L.SEARCH_OP_CEILING, "w")
    s = L.stats(wb)
    assert s["checkpoint_required"] is True and s["scopes_at_ceiling"] == [cat]
    out = orient.orient(wb, None)
    assert cat in out["do_first"][0]


# ── one key, one row ─────────────────────────────────────────────────────

def test_a_duplicated_metadata_key_cannot_read_stale(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    ws = wb._sheet("Run_Metadata")
    ws.append(["last_written_at", "2000-01-01T00:00:00Z"])  # the arbor shape
    wb.set_metadata("last_written_at", "2026-10-05T05:29:41Z")
    assert wb.metadata()["last_written_at"] == "2026-10-05T05:29:41Z"


# ── the watchdog names the workflow handoff, never a lane ────────────────

def _row_for(tmp_path, outcome, reason=""):
    run = new_run(tmp_path, selected=two_category_selection(3))
    (run.qa_dir / "pipeline_state.json").write_text(
        json.dumps({"last_outcome": outcome, "last_reason": reason}))
    return watchdog.inspect(run)


def test_awaiting_workflow_points_at_the_handoff(tmp_path):
    row = _row_for(tmp_path, "AWAITING_WORKFLOW")
    assert row["state"] == "AWAITING_WORKFLOW", row
    plan = watchdog.resume_plan(row)
    assert plan.get("workflow") and not plan.get("agent")


def test_withheld_research_ends_on_a_person(tmp_path):
    row = _row_for(tmp_path, "STALLED", "P1C1 UNSERVABLE: test")
    assert row["state"] == "RESEARCH_WITHHELD", row
    assert "RESEARCH_WITHHELD" not in watchdog.AGENT_ADVANCEABLE
    plan = watchdog.resume_plan(row)
    assert plan["actionable"] is False and plan.get("needs") == "person"
