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
from fixtures import new_run, preflight_doc, two_category_selection

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
    for leaked in ("swbc", "SWBC", "Angelica"):
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
