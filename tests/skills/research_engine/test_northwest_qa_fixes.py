"""Defects measured on the Northwest Bank live run (2026-10-01, N-xx in
qa_audit/2026-10-01-northwest/CASE_FACTS.md) — each pinned at its seam."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine import cost, pipeline as P, pipeline_stub as S, preflight, prelim
from fixtures import bank_evidence, new_run, preflight_doc, two_category_selection

ENGINE = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights" / "skills" / "dma-research"


def _run(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    return run


# ── N-09 · the step-4 estimate is the rate the research handoff uses ─────

def test_the_estimate_is_the_measured_workflow_rate(tmp_path):
    run = _run(tmp_path)
    est = cost.workflow_estimate(run.open())
    cats = len(est["pillars"]) and sum(p["categories"] for p in est["pillars"].values())
    assert est["open_cells"] == 6 and cats == 2
    assert est["research_usd"] == round(6 * P.WORKFLOW_USD_PER_CELL
                                        + 2 * P.CHALLENGE_USD_PER_CATEGORY, 2)


def test_the_estimate_and_the_research_handoff_agree(tmp_path):
    run = _run(tmp_path)
    opts = P.Options(dispatcher=S.StubDispatcher(handlers={}), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False,
                     folder_root=tmp_path / "out", ingest_poll_s=0,
                     sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                     max_rounds=2, stall_rounds=0, research_mode="workflow")
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "AWAITING_WORKFLOW", out
    handed = json.loads(Path(out["handoff"]).read_text())["estimate"]
    est = cost.workflow_estimate(run.open())
    assert handed["usd"] == est["research_usd"]
    assert handed["batches"] == est["batches"]


def test_the_cli_estimate_says_over_when_the_ceiling_is_short(tmp_path):
    run = _run(tmp_path)
    cmd = [sys.executable, "-m", "engine.cost", "estimate", "--run", run.run_id,
           "--root", str(run.root)]
    ok = subprocess.run(cmd + ["--max-usd", "50"], cwd=ENGINE, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "RESEARCH estimate" in ok.stdout and "fits" in ok.stdout
    short = subprocess.run(cmd + ["--max-usd", "0.5"], cwd=ENGINE, capture_output=True, text=True)
    assert short.returncode == 1 and "OVER by" in short.stdout


# ── N-10 · the schedule models the workflows research actually runs as ───

def test_the_schedule_is_one_workflow_per_category(tmp_path):
    run = _run(tmp_path)
    sch = cost.workflow_schedule(run.open(), cpus=4)
    assert sch["mode"] == "workflow"
    assert sch["workflows"] == 2 and sch["agents_per_workflow"] == 2
    assert sch["peak_agents"] == 4
    # one batch per category fits in one wave
    assert sch["research_parallel_min"] == cost.WORKFLOW_BATCH_MIN


def test_workflow_concurrency_follows_the_runtime_cap():
    assert cost.workflow_concurrency(4) == 2
    assert cost.workflow_concurrency(2) == 1
    assert cost.workflow_concurrency(64) == 16


# ── N-15 · comma-joined evidence ids are ids, not one unknown id ─────────

def test_comma_joined_evidence_ids_are_split(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    ids = bank_evidence(wb, wb.selected_subcaps()[0], n=2)
    ids = [i if isinstance(i, str) else i.get("evidence_id") for i in ids]
    body = ("Northwest Bancshares is a Pennsylvania-chartered savings bank holding "
            "company with 151 financial centers and $16.8B of assets at FY2025. ") * 3
    with pytest.raises(prelim.PrelimRefusal) as exc:
        prelim.narrate(wb, "firmographics", heading=None, body=body,
                       evidence=["E-998,E-999"])
    assert "E-998, E-999" in str(exc.value)
    out = prelim.narrate(wb, "firmographics", heading=None, body=body,
                         evidence=[",".join(ids)])
    assert out


# ── N-17 · the driver's log lands where the command says to watch ────────

def test_the_driver_log_is_teed_to_the_watched_file(tmp_path):
    seen = []
    log = P._tee_log(tmp_path / P.LOG_NAME, seen.append)
    log("[RELAY] PRELIM connector brief …")
    assert seen == ["[RELAY] PRELIM connector brief …"]
    assert "[RELAY]" in (tmp_path / "pipeline.log").read_text()


# ── N-19 · the batch agent is its own lean type ─────────────────────────

PLUGIN = ENGINE.parents[1]


def _tools(md: Path) -> set[str]:
    import re
    fm = md.read_text().split("---")[1]
    return {t.strip() for t in re.search(r"^tools:\s*(.*)$", fm, re.M).group(1).split(",")}


def test_the_batch_agent_holds_no_session_wide_tool():
    """Skill brings every installed skill's listing into every turn, and an
    untyped agent brings the deferred-tool roster and a ToolSearch turn:
    66,178 tokens at turn 1 measured vs 49,261 for a type without them."""
    t = _tools(PLUGIN / "agents" / "research" / "research-batch-producer.md")
    assert not t & {"Skill", "ToolSearch", "Agent", "Grep", "Glob", "Edit"}, t
    assert "Write" in t, "N-26: the ops file is written with Write, never a python heredoc"
    assert {"Bash", "WebSearch", "mcp__Exa__web_search_exa", "mcp__Tavily__tavily_search",
            "mcp__Tavily__tavily_extract", "mcp__Clay__search-contacts"} <= t, t


def test_the_workflow_starts_every_batch_as_that_type():
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "let BATCH_TYPE = 'dma-insights:research-batch-producer'" in js
    assert "batchAgent(batchPrompt(" in js
    helper = js[js.index("async function batchAgent"):js.index("const BATCHES")]
    assert "agentType: BATCH_TYPE" in helper and "return agent(prompt, opts)" in helper


def test_the_manifest_lists_the_batch_agent():
    pj = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert "./agents/research/research-batch-producer.md" in pj["agents"]
    assert f"{len(pj['agents'])} DMA agents" in pj["description"]


# ── N-18 · a connector measured down is recorded once for the run ───────

def test_a_down_family_rides_the_handoff_to_every_workflow(tmp_path):
    sys.path.insert(0, str(PLUGIN / "scripts"))
    import connector_contract as cc
    run = _run(tmp_path)
    cc.mark_down("exa", "HTTP 402 credits exhausted", str(run.root))
    assert "exa" in cc.down_families(str(run.root))
    opts = P.Options(dispatcher=S.StubDispatcher(handlers={}), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False,
                     folder_root=tmp_path / "out", ingest_poll_s=0,
                     sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                     max_rounds=2, stall_rounds=0, research_mode="workflow")
    out = P.Pipeline(run, opts).run_all()
    inv = json.loads(Path(out["handoff"]).read_text())["invocations"]
    assert inv and all("402" in i["down"]["exa"] for i in inv)
    cc.mark_down("exa", "", str(run.root))                    # --clear
    assert cc.down_families(str(run.root)) == {}
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "A.down" in js and "${DOWN_LINE}" in js


# ── N-24 · the workflow's absence line is one the CLI accepts ────────────

def _sheet_line(cmd: str) -> str:
    import re
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    m = re.search(rf"^\s*{cmd}:\s*(python3 -m engine\.cli .*)$", js, re.M)
    assert m, cmd
    return m.group(1)


def test_the_absence_line_names_every_flag_the_cli_requires(tmp_path):
    """Measured 2026-10-01: the sheet omitted the required --proxy-log, gave
    no ladder shape and paired --validation-question without --inferable
    (which the ledger refuses), so 19 of 40 agents read engine source."""
    line = _sheet_line("absent")
    probe = subprocess.run([sys.executable, "-m", "engine.cli", "absence", "--run", "X"],
                           cwd=ENGINE, capture_output=True, text=True)
    import re
    req = re.search(r"required: (.*)", probe.stderr).group(1)
    for flag in [f.strip() for f in req.split(",")]:
        assert flag in line, f"the sheet's absence line omits required {flag}"
    assert '"rung":"direct"' in line and '"rung":"proxy"' in line
    assert ("--validation-question" in line) == ("--inferable" in line)


def test_a_public_run_does_not_send_batches_to_the_internal_documents():
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "A.mode && A.mode !== 'PUBLIC'" in js


# ── N-20 · the workflows stop at the owner's ceiling ────────────────────

def test_the_ceiling_prices_workflow_spend_not_yet_booked(tmp_path):
    run = _run(tmp_path)
    wf = tmp_path / "proj" / "sess" / "subagents" / "workflows" / "wf_1"
    wf.mkdir(parents=True)
    lines = [json.dumps({"type": "user", "message": {"content": f"run {run.run_id}"}})]
    lines.append(json.dumps({"type": "assistant", "message": {
        "id": "m1", "model": "claude-sonnet-x", "usage": {
            "input_tokens": 0, "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0, "output_tokens": 1_000_000}}}))
    (wf / "agent-a1.jsonl").write_text("\n".join(lines))
    under = cost.ceiling(run, budget_usd=50.0, base=tmp_path)
    assert not under["over"] and under["pending_workflow_usd"] == 10.0, under
    over = cost.ceiling(run, budget_usd=5.0, base=tmp_path)
    assert over["over"] and "person's decision" in over["why"]
    assert cost.ledger(run) == [] or all("workflow" not in r.get("note", "") for r in cost.ledger(run)), \
        "a ceiling check books nothing"


def test_every_batch_checks_the_ceiling_first_and_the_script_stops_on_it():
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "python3 -m engine.cost ceiling ${R}" in js
    assert "r.gate === 'OVER_BUDGET'" in js


# ── N-08 · the run's own preflight survives the remote supersede ────────

def test_open_folder_repushes_this_runs_preflight_after_archiving(tmp_path, monkeypatch):
    from engine import assemble
    run = new_run(tmp_path, folder=False)
    calls = []
    monkeypatch.setattr(assemble, "_archive_remote",
                        lambda *a, **k: calls.append(("archive",)) or {"outcome": "RESOLVED"})
    monkeypatch.setattr(assemble, "_push_one",
                        lambda local, entity, remote: calls.append(("push", remote))
                        or {"outcome": "RESOLVED"})
    pf = tmp_path / "preflight.json"
    pf.write_text("{}")
    out = assemble.open_folder(run, tmp_path / "out", push=True, preflight=pf)
    assert calls[0] == ("archive",)
    assert ("push", "preflight.json") in calls[1:], calls
    assert out["preflight_pushed"]["outcome"] == "RESOLVED"


# ── N-12 / N-16 · PRELIM sections go to the agent holding their tools ───

def test_prelim_peers_go_to_the_web_specialist_and_the_brief_names_the_connector_id(tmp_path):
    from engine import brief
    run = new_run(tmp_path, prelim=False)
    b = brief.prelim_brief(run.open(), run=run, out_dir=tmp_path / "pb")
    orch = b.get("orchestrator")
    assert orch and "peers" in orch["owed"], b.keys()
    assert orch["agents"]["peers"] == "enrichment-web-specialist"
    assert all(v == "enrichment-connector-specialist"
               for k, v in orch["agents"].items() if k != "peers")
    text = Path(orch["prompt_file"]).read_text()
    assert "enrichment-web-specialist" in text and "DEF 14A" in text
    assert "connector_display_id" in text and "record_enrichment" in text


# ── N-13 · the Clay people filter field is the one the connector accepts ─

def test_the_clay_plan_names_the_live_people_field():
    plan = (PLUGIN / "skills" / "dma-surface-production" / "scripts" / "clay_plan.py").read_text()
    assert 'headline contains \\"chief\\"' in plan
    assert "<the DSL's job-title field>" not in plan
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert 'headline contains "<word>"' in js


# ── N-21 · the capability card states each question once ────────────────

def test_the_card_states_a_templated_facet_once(tmp_path):
    from engine import orient
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cap = ".".join(wb.selected_subcaps()[0].split(".")[:2])
    card = orient.capability_card(wb, cap, run=run)
    assert card["entity"] and "{entity}" not in card["entity"]
    assert "--facet <F>" in card["log"]
    for f, slot in card["facets_owed"].items():
        assert slot["cells"], f
        assert "log" not in slot, "one log template, not one per facet"
        if "ask" in slot:
            assert "questions" not in slot and "{name}" in slot["ask"]
    # every open cell's name is on the card, so {name} always resolves
    assert all(c["name"] for c in card["open_cells"])


# ── N-26 · a run root the approver cannot see is said at start ───────────

def test_start_says_when_the_run_root_would_prompt(tmp_path, monkeypatch):
    from engine import cli
    monkeypatch.delenv("DMA_RUN_ROOT", raising=False)
    outside = Path("/var/dma-qa-not-approvable") / "acme"
    got = cli._root_approvable(outside)
    assert got["approvable"] is False and "PROMPT" in got["why"]
    assert cli._root_approvable(Path.home() / "dma_output" / "acme")["approvable"] is True
