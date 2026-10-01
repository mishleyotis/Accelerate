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


# ── session 2 (2026-10-01, SWBC): what the fan-out could not see ───────────

def _runtime_parse(src: str, tmp_path) -> "subprocess.CompletedProcess":
    """Parse the script the way the Workflow runtime runs it: the body inside
    an async function, as an ES module. `node --check` on the .js file itself
    passed a script with a broken template literal (CommonJS parse), and all
    sixteen launches were refused at the runtime's parse (I-74)."""
    import subprocess
    body = src.replace("export const meta", "const meta", 1)
    f = tmp_path / "wf_wrapped.mjs"
    f.write_text("const args={root:'/r',internal_documents:[]};const log=()=>{};"
                 "const agent=async()=>null;const parallel=async()=>[];"
                 "const pipeline=async()=>[];\nexport default async function(){\n"
                 + body + "\n}\n")
    return subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)


def test_the_shipped_workflow_parses_as_the_runtime_runs_it(tmp_path):
    import shutil
    import pytest
    if not shutil.which("node"):
        pytest.skip("node is not installed on this runner")
    r = _runtime_parse((PLUGIN / P.RESEARCH_WORKFLOW).read_text(), tmp_path)
    assert r.returncode == 0, r.stderr[-800:]
    # and the check is not vacuous: the exact I-74 defect fails it
    bad = (PLUGIN / P.RESEARCH_WORKFLOW).read_text().replace(
        "the toolkit's primary question FIRST", "the toolkit's `primary` question FIRST")
    assert _runtime_parse(bad, tmp_path).returncode != 0


def test_internal_documents_ride_in_the_workflow_args(tmp_path):
    # I-69: the batch prompt sent agents to a markdown brief that never
    # rendered the internal documents.
    from engine import intake
    run = new_run(tmp_path, selected=two_category_selection(3))
    doc = tmp_path / "ctx.md"
    doc.write_text("# Context\n\nInternal write-up naming the client's platforms.\n")
    intake.add(run.root, doc, title="Context write-up")
    wb = run.open()
    wb.set_metadata("evidence_mode", "HYBRID")
    preflight.record(run, preflight_doc())
    run.open().set_metadata("evidence_mode", "HYBRID")
    opts = P.Options(dispatcher=S.StubDispatcher(handlers={}), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False,
                     folder_root=tmp_path / "client_out", ingest_poll_s=0,
                     sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                     max_rounds=1, stall_rounds=0, research_mode="workflow")
    p = P.Pipeline(run, opts)
    out = p._research_handoff()
    for inv in out["invocations"]:
        assert [d["title"] for d in inv["internal_documents"]] == ["Context write-up"]
        assert Path(inv["internal_documents"][0]["path"]).is_file()
    src = (PLUGIN / P.RESEARCH_WORKFLOW).read_text()
    assert "A.internal_documents" in src and "engine.brief dispatch" not in src


def test_the_handoff_states_search_capacity_before_the_fan_out(tmp_path, monkeypatch):
    # I-78: 31 agents shared one session's 200 WebSearch calls; Tavily and
    # Exa were spent; nothing had compared demand with any of it.
    p, disp, out = _drive(tmp_path, "workflow")
    doc = json.loads(Path(out["handoff"]).read_text())
    cap = doc["capacity"]
    assert cap["searches_owed_floor"] > 0
    assert cap["websearch_budget_env"] == "CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION"
    owed = {"P1C1.1": {"primary", "works", "fails"}, "P1C1.2": {"primary"}}
    monkeypatch.setenv("CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION", "2")
    tight = P.search_capacity(p.run.root, owed)
    assert tight["searches_owed_floor"] == 4 and not tight["fits"]
    assert "CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION" in tight["advice"]
    for ch in ("websearch", "tavily", "exa", "firecrawl"):
        (p.run.qa_dir / f"connector_exhausted_{ch}").touch()
    dead = P.search_capacity(p.run.root, owed)
    assert dead["websearch_session_budget"] == 0 and not dead["connector_channels_live"]
    assert "closes nothing" in dead["advice"]


def test_the_workflow_tells_agents_how_to_treat_a_spent_channel():
    # I-76/I-77/I-79: every agent rediscovered Exa's 402, guessed Clay's
    # people field, and retried spent channels for ~90 turns.
    src = (PLUGIN / P.RESEARCH_WORKFLOW).read_text()
    for must in ("connector_exhausted_", "NO_CONNECTORS", "FAILED:",
                 "headline contains", "--tool firecrawl", "HARD CEILING",
                 "next_batches", "card ${R} --category"):
        assert must in src, must


def test_a_no_push_run_never_reaches_drive_for_toolkits(tmp_path, monkeypatch):
    # I-84: on a container holding the service account, every stub test that
    # reached KG downloaded the toolkits from the real Drive.
    import subprocess
    calls = []
    monkeypatch.setattr(P.subprocess, "run",
                        lambda *a, **k: calls.append(a) or subprocess.CompletedProcess(a, 1))
    p, disp, out = _drive(tmp_path, "workflow")
    assert p.opts.push is False
    assert p._pull_toolkits() is None
    assert not [c for c in calls if "pull-toolkits" in " ".join(map(str, c[0]))]
