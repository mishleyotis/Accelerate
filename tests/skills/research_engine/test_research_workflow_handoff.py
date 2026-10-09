"""RESEARCH runs as persisted workflows, started by the session.

Root cause measured 2026-09-30 (SWBC; owner: "research works as background
tasks and not real persisted /workflows"): engine.pipeline is a Python
process and cannot start a Workflow, so research always ran as a thread pool
of headless `claude -p` lanes. In research_mode="workflow" the driver hands
the stage to the session instead — one workflow invocation per pillar — and
dispatches no lane.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from engine import pipeline as P, pipeline_stub as S, preflight
from fixtures import (bank_evidence, good_synthesis, new_run, preflight_doc,
                      synthesise, two_category_selection)

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"


def _drive(tmp_path, mode):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    disp = S.StubDispatcher(handlers={"research-p": S.lane_noop,
                                      "finding-challenger": S.lane_noop})
    opts = P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                     push=False, folder_root=tmp_path / "client_out", ingest_poll_s=0,
                     sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                     max_rounds=2, stall_rounds=0, research_mode=mode)
    p = P.Pipeline(run, opts)
    return p, disp, p.run_all()


def test_workflow_mode_hands_research_to_the_session(tmp_path):
    p, disp, out = _drive(tmp_path, "workflow")
    assert out["outcome"] == "AWAITING_WORKFLOW", out
    assert out["outcome"] in P.EXIT_ZERO_OUTCOMES          # a clean handoff, not a failure
    assert not [c for c in disp.calls if c["stage"] == "RESEARCH"], \
        "workflow mode dispatched a headless research lane"
    doc = json.loads(Path(out["handoff"]).read_text())
    assert Path(doc["workflow"]).is_file(), "the named workflow is not shipped in the plugin"
    cats = [c for inv in doc["invocations"] for c in inv["cats"]]
    assert cats and all(inv["cats"][0].startswith(inv["pillar"]) for inv in doc["invocations"])
    for inv in doc["invocations"]:
        assert {"run", "root", "eng", "plugin", "rounds", "domain"} <= set(inv)
    assert "engine.pipeline run" in doc["then"]


def test_lanes_mode_is_unchanged(tmp_path):
    p, disp, out = _drive(tmp_path, "lanes")
    assert out["outcome"] != "AWAITING_WORKFLOW"
    assert [c for c in disp.calls if c["stage"] == "RESEARCH"]


def test_the_shipped_workflow_names_no_client():
    src = (PLUGIN / P.RESEARCH_WORKFLOW).read_text()
    assert src.startswith("export const meta")
    for leaked in ("swbc", "SWBC", "Angelica", "susser", "Susser"):
        assert leaked not in src, f"the plugin workflow hard-codes {leaked!r}"


def test_the_hook_turns_the_handoff_into_workflow_calls(tmp_path):
    p, disp, out = _drive(tmp_path, "workflow")
    spec = importlib.util.spec_from_file_location(
        "stage_advance", PLUGIN / "scripts" / "hooks" / "stage_advance.py")
    sa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sa)
    event = {"tool_name": "Bash",
             "tool_input": {"command": f"python3 -m engine.pipeline run --run {p.run.run_id}"},
             "tool_response": {"stdout": json.dumps(out) + "\n[WORKFLOW] RESEARCH handed "
                               f"to the conducting session: x — {out['handoff']}"}}
    got = sa.awaiting_workflow(event)
    ctx = got["hookSpecificOutput"]["additionalContext"]
    assert ctx.count("Workflow({scriptPath:") == len(out["invocations"])
    assert "THEN" in ctx


def test_each_category_is_split_into_bounded_capability_batches(tmp_path):
    # Measured 2026-09-30 (SWBC r1): one agent per category filled 116-200K
    # tokens of context and closed 0 of 43-68 cells. The unit is now a batch.
    p, disp, out = _drive(tmp_path, "workflow")
    open_caps = P._open_capabilities(p.wb)
    for inv in json.loads(Path(out["handoff"]).read_text())["invocations"]:
        for cat in inv["cats"]:
            batches = inv["batches"][cat]
            flat = [c for b in batches for c in b]
            assert sorted(flat) == sorted(open_caps[cat]), "a capability was dropped or duplicated"
            for b in batches:
                n = sum(open_caps[cat][c] for c in b)
                assert n <= P.BATCH_CELLS or len(b) == 1, (cat, b, n)


def test_batches_pack_whole_capabilities_in_order():
    got = P._batches({"P1C1.10": 2, "P1C1.2": 7, "P1C1.1": 6, "P1C1.3": 20})
    assert got == [["P1C1.1"], ["P1C1.2"], ["P1C1.3"], ["P1C1.10"]]
    assert P._batches({"X.1": 4, "X.2": 4, "X.3": 4}) == [["X.1", "X.2", "X.3"]]


def test_one_workflow_per_category(tmp_path):
    # Concurrency is capped PER WORKFLOW; one per category is what parallelises.
    p, disp, out = _drive(tmp_path, "workflow")
    assert all(len(inv["cats"]) == 1 for inv in out["invocations"])
    assert len(out["invocations"]) == len({c for inv in out["invocations"] for c in inv["cats"]})


def test_lanes_need_a_stated_waiver_with_the_real_dispatcher():
    import argparse
    a = argparse.Namespace(research_mode="lanes", dispatcher="agent_run", allow_lanes=False)
    try:
        P._research_mode(a)
    except SystemExit as e:
        assert "--allow-lanes" in str(e)
    else:
        raise AssertionError("lanes ran on the real dispatcher without a waiver")
    a.allow_lanes = True
    assert P._research_mode(a) == "lanes"
    assert P._research_mode(argparse.Namespace(research_mode=None, dispatcher="agent_run",
                                               allow_lanes=False)) == "workflow"
    assert P._research_mode(argparse.Namespace(research_mode=None, dispatcher="stub",
                                               allow_lanes=False)) == "lanes"


def test_a_resumed_driver_continues_round_numbering(tmp_path):
    # I-44: round dirs were overwritten by the next driver process.
    p, disp, out = _drive(tmp_path, "workflow")
    d = p.run.root / P.BRIEFS_DIR
    (d / "research_r0").mkdir(parents=True, exist_ok=True)
    (d / "research_r1").mkdir(exist_ok=True)
    fresh = P.Pipeline(p.run, p.opts)
    assert fresh._briefs("research_r0").name == "research_r2"
    assert fresh._briefs("research_r1").name == "research_r3"
    assert fresh._briefs("scoring_r0").name == "scoring_r0"


def test_a_handoff_nobody_worked_is_called_out(tmp_path):
    # I-54: a resumed session lost Workflow + connectors; the re-run driver
    # re-issued the same handoff with no sign that nothing had happened.
    p, disp, out = _drive(tmp_path, "workflow")
    assert not out.get("not_worked") if "not_worked" in out else True
    again = P.Pipeline(p.run, p.opts)._research_handoff()
    assert again["not_worked"] and "lanes" in again["not_worked"]


# ── Susser Bank, 2026-10-05: rounds that closed nothing ───────────────────
# Round 2 handed 15 categories; 13 had every blocker on an already-closed
# cell, which the open-cells-only handoff never routed. Round 3 was handed
# with 0 batches, a $6.16 estimate (it cost ~$21) and no stall detection,
# because each workflow round is a fresh driver process.

def _close(p, *cells):
    """Synthesise cells so they are CLOSED. Since 2026-10-09 (MEM-0614) a
    repair is routed only on a closed cell: an open cell is its open batch's
    work, and routing it as a repair too collected for it twice."""
    wb = p.run.open()
    for cell in cells:
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell, n=3)))


def _fail_gate(p, cat, cell, term="single_source_fact"):
    doc = {"category": cat, "gate": "FAIL", "blocking": [term],
           "advisory": ["coverage_below_floor"],
           term: [{"subcap": cell, "distinct_sources": ["example.com"]}],
           "coverage_below_floor": [{"subcap": cell}]}
    (p.run.qa_dir / f"floors_{cat}.json").write_text(json.dumps(doc))
    return doc


def test_gate_summary_names_cells_and_keeps_advisory_out():
    from engine import floors_gate as F
    doc = {"category": "P1C1", "gate": "FAIL",
           "blocking": ["evidence_smear", "volleys_incomplete"],
           "advisory": ["coverage_below_floor"],
           "evidence_smear": [{"subcaps": ["P1C1.1.3", "P1C1.1.4"]}],
           "volleys_incomplete": [{"subcap": "P1C1.3.5", "missing": ["fails"]}],
           "coverage_below_floor": [{"subcap": "P1C1.9.9"}]}
    cells = F.blocking_cells(doc)
    assert cells == {"P1C1.1.3": ["evidence_smear"], "P1C1.1.4": ["evidence_smear"],
                     "P1C1.3.5": ["volleys_incomplete"]}
    s = F.summary(doc)
    assert s["repair_cells"] == 3 and "coverage_below_floor" not in s["blocking"]
    assert s["advisory"] == ["coverage_below_floor"]
    assert F.blocking_cells({**doc, "gate": "PASS"}) == {}
    assert F.summary(None)["gate"] == "NOT_RUN"


def test_handoff_routes_the_gates_cells_even_when_closed(tmp_path):
    p, disp, out = _drive(tmp_path, "workflow")
    cat = out["invocations"][0]["cats"][0]
    cell = f"{cat}.1.1"
    _close(p, cell)
    _fail_gate(p, cat, cell)
    h = P.Pipeline(p.run, p.opts)._research_handoff()
    inv = next(i for i in h["invocations"] if cat in i["cats"])
    assert inv["repairs"][cat] == {cell: ["single_source_fact"]}
    assert inv["repair_batches"][cat] == [[cell]]
    assert h["estimate"]["repair_cells"] >= 1
    assert "repair" in h["summary"]


def test_a_category_that_does_not_move_stops_being_handed(tmp_path):
    p, disp, out = _drive(tmp_path, "workflow")
    p.opts.stall_rounds = 2
    cat = out["invocations"][0]["cats"][0]
    _fail_gate(p, cat, f"{cat}.1.1")
    q = P.Pipeline(p.run, p.opts)
    first = q._research_handoff()                  # seeds the book
    assert cat in [c for i in first["invocations"] for c in i["cats"]]
    for spent in (5.0, 10.0):                      # two worked rounds, nothing moved
        q = P.Pipeline(p.run, p.opts)              # a fresh driver process each round
        q._spent_usd = spent                       # what the ledger reads back
        h = q._research_handoff()
    assert cat in h["stalled"]
    assert cat not in [c for i in h["invocations"] for c in i["cats"]]


def test_an_unworked_handoff_is_not_counted_as_a_stall(tmp_path):
    p, disp, out = _drive(tmp_path, "workflow")
    p.opts.stall_rounds = 1
    cat = out["invocations"][0]["cats"][0]
    _fail_gate(p, cat, f"{cat}.1.1")
    for _ in range(3):                             # no spend lands: never worked
        h = P.Pipeline(p.run, p.opts)._research_handoff()
    assert not h["stalled"] and h["not_worked"]


def test_a_repair_at_source_unstalls_the_category(tmp_path):
    p, disp, out = _drive(tmp_path, "workflow")
    p.opts.stall_rounds = 1
    cat = out["invocations"][0]["cats"][0]
    _close(p, f"{cat}.1.1", f"{cat}.1.2")
    doc = _fail_gate(p, cat, f"{cat}.1.1")
    doc["single_source_fact"].append({"subcap": f"{cat}.1.2"})
    (p.run.qa_dir / f"floors_{cat}.json").write_text(json.dumps(doc))
    q = P.Pipeline(p.run, p.opts); q._research_handoff()
    q = P.Pipeline(p.run, p.opts); q._spent_usd += 3; h = q._research_handoff()
    assert cat in h["stalled"]
    _fail_gate(p, cat, f"{cat}.1.1")               # a person closed one blocker
    h = P.Pipeline(p.run, p.opts)._research_handoff()
    assert cat not in h["stalled"]


def test_the_estimate_is_calibrated_by_the_last_round(tmp_path):
    p, disp, out = _drive(tmp_path, "workflow")
    # This test is about CALIBRATION, not the envelope: a round booked at 3x
    # its estimate would otherwise spend the $10 RESEARCH envelope and the
    # handoff would stop AT_STAGE_BUDGET before pricing (2026-10-09).
    p.opts.stage_budget = {"RESEARCH": 1000.0}
    q = P.Pipeline(p.run, p.opts)
    pilot = q._research_handoff()["estimate"]
    from engine import cost
    cost.record(p.run, stage="RESEARCH", elapsed_s=60, usd=round(pilot["usd"] * 3, 2),
                note="workflow spend")              # the round cost 3x its estimate
    # SCORING spend between two handoffs is not research and must not
    # inflate the ratio.
    cost.record(p.run, stage="SCORING", elapsed_s=60, usd=50.0, note="scoring lanes")
    q = P.Pipeline(p.run, p.opts)
    q._spent_usd += pilot["usd"] * 3 + 50.0
    est = q._research_handoff()["estimate"]
    assert est["usd"] <= round(pilot["usd"] * 3, 2) + 0.05, (pilot, est)
    assert est["usd"] >= round(pilot["usd"] * 3, 2) - 0.01, (pilot, est)
    assert "calibrated" in est["basis"]


def test_the_workflow_stops_on_agent_errors_and_reads_the_summary():
    src = (PLUGIN / P.RESEARCH_WORKFLOW).read_text()
    # An all-failed wave stops the category; a wave the governor refused
    # (nothing ran) is AT_STAGE_BUDGET, not an agent error — hence the
    # `ran.length &&` guard (2026-10-09).
    assert "AGENT_ERROR" in src and "if (ran.length && !got.length)" in src and "if (!c)" in src
    assert "--require-synthesis --summary" in src
    assert "REPAIR_BATCHES" in src and "A.repairs" in src
