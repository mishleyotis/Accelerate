"""Regressions from the Cross Insurance Agency live QA run (2026-10-01).

Each test names the case-facts id it pins (qa_audit/2026-10-01-cross/
CASE_FACTS.md). The run measured every one of these on a real 694-cell IB
engagement; the tests hold the fix in place on the fixture run.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path

import pytest

from engine import cli, contract as C, cost, ledger as L, orient, pipeline as P
from engine import pipeline_stub as S, preflight, prelim
from engine import brief
from fixtures import (bank_evidence, declare_absent, fire_volleys, new_run,
                      preflight_doc, two_category_selection)

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"


def _run_cli(argv) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = cli.main(argv)
    return rc, out.getvalue()


# ── C-02 · preflight check lists a bad share instead of crashing ─────────

def test_a_non_numeric_share_is_a_listed_problem_not_a_traceback():
    doc = preflight_doc()
    doc["lob_census"]["lines_of_business"][0]["revenue_share_pct"] = "(within 89.3 P/C)"
    rep = preflight.check(doc)
    assert not rep["ok"]
    assert any("is not a number" in p for p in rep["problems"]), rep["problems"]


# ── C-13 · the peer set has the contract's N=3 floor ─────────────────────

RULE = ("privately held brokers ranked adjacent to the entity in the 2025 "
        "largest-brokers table, each placing commercial lines and benefits")


def test_fewer_than_three_peers_is_refused_unless_cannot_estimate(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    with pytest.raises(prelim.PrelimRefusal, match="N=3"):
        prelim.peers(wb, ["Only One"], rule=RULE, basis="table")
    out = prelim.peers(wb, ["Only One"], rule=RULE, basis="cannot_estimate")
    assert out["locked"]["peer_n"] == 1


def test_a_locked_set_widens_before_any_figure_and_never_narrows(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    prelim.peers(wb, ["A Co", "B Co", "C Co"], rule=RULE, basis="table")
    out = prelim.peers(wb, ["A Co", "B Co", "C Co", "D Co", "E Co"],
                       rule=RULE, basis="table")
    assert out["locked"]["peer_n"] == 5 and out["locked"]["widened_from"]
    rows = wb.rows("Peer_Benchmarks")
    assert rows and all(int(r["Peer_N"]) == 5 for r in rows)
    # one row per category, re-stated — not appended twice
    assert len({r["Category_ID"] for r in rows}) == len(rows)
    with pytest.raises(prelim.PrelimRefusal, match="already locked"):
        prelim.peers(wb, ["A Co", "B Co", "Z Co"], rule=RULE, basis="table")


def test_prelim_state_reads_a_one_firm_lock_as_open(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    wb.lock_peer_set(["Lone Co"], basis="table")       # the measured bad state
    wb.append("Peer_Benchmarks", {"Category_ID": "P1C1", "Peer_N": 1})
    st = {s["section"]: s for s in prelim.state(wb)["sections"]}
    assert st["peers"]["status"] == "OPEN" and "N=3" in st["peers"]["detail"]


def test_narrate_accepts_a_comma_listed_evidence_flag(tmp_path):
    # C-14: `--evidence "E-001, E-002"` was read as one id and refused.
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    ids = bank_evidence(wb, wb.selected_subcaps()[0], n=2)
    assert len(ids) == 2
    rc = prelim.main(["narrate", "--run", run.run_id, "--root", str(run.root),
                      "--section", "thought_leadership", "--evidence", ", ".join(ids),
                      "--body", "The chief executive has said in public that the firm "
                                "will keep acquiring regional agencies and integrate "
                                "them onto one platform over the next three years."])
    assert rc == 0


# ── C-06 / C-07 / C-08 / C-12 · PRELIM ownership and command sheets ──────

def test_prelim_sections_have_one_owner_and_a_command_sheet(tmp_path):
    run = new_run(tmp_path, prelim=False)
    out = brief.prelim_brief(run.open(), run=run, out_dir=tmp_path / "b")
    con = json.loads((tmp_path / "b" / "prelim-conductor.json").read_text())
    scan = json.loads((tmp_path / "b" / "prelim-techscan.json").read_text())
    assert "tech_baseline" not in con["owed"]
    assert set(scan["owed"]) <= {"tech_baseline"}
    for packet in (con, scan):
        assert any("engine.prelim narrate" in c or "engine.techscan record" in c
                   for c in packet["commands"])
        assert "trimmed" not in packet, packet.get("trimmed")
    orch = out["orchestrator"]
    assert orch["owed"] == [] and orch["duties"] >= 4      # data only, no narrative
    text = Path(orch["prompt_file"]).read_text()
    assert "headline contains" in text and "technographic_scan" in text
    assert "## also owed\n\n\n" not in text                # no empty headings
    assert "you hold NO connector" in " ".join(scan["rules"])


# ── C-25 · the capability card owes the primary, and skips absences ──────

def test_the_card_lists_the_primary_and_skips_declared_absences(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    cells = wb.selected_subcaps()
    cap = ".".join(cells[0].split(".")[:2])
    card = orient.capability_card(wb, cap, run=run)
    first = card["open_cells"][0]
    assert first["missing"][0] == C.PRIMARY_FACET
    if card["facets_owed"]:            # a run with a DQ bank names the question too
        assert C.PRIMARY_FACET in card["facets_owed"]
    declare_absent(wb, first["cell"])
    card = orient.capability_card(run.open(), cap, run=run)
    assert first["cell"] not in [c["cell"] for c in card["open_cells"]]


# ── C-19 · the absence contract is printed, not reverse-engineered ───────

def test_absence_template_prints_the_contract_from_the_constants():
    rc, out = _run_cli(["absence-template"])
    assert rc == 0
    doc = json.loads(out)
    text = " ".join(doc["requires"])
    for rung in L.ABSENCE_RUNGS_REQUIRED:
        assert rung in text
    assert C.PRIMARY_FACET in text and "firecrawl" in text
    assert any(line.startswith("absence ") for line in doc["ops_lines"])


# ── C-18 / C-24 · firecrawl counts; a failed connector call does not ─────

def test_firecrawl_is_an_enrichment_tool():
    assert "firecrawl" in C.SEARCH_TOOLS and "firecrawl" in C.ENRICHMENT_TOOLS


def test_a_rate_limited_connector_call_is_not_a_volley(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    fire_volleys(wb, cell, n=0)
    L.append_search(wb, subcap=cell, facet="works", query='"Acme Credit Union" x',
                    tool="tavily", hits=0, kept=0, outcome="RATE_LIMITED: 429")
    vs = L.volley_status(wb, cell)
    assert "tavily" not in vs["enrichment_tools"]
    L.append_search(wb, subcap=cell, facet="fails", query='"Acme Credit Union" y',
                    tool="tavily", hits=3, kept=0, outcome="")
    assert "tavily" in L.volley_status(wb, cell)["enrichment_tools"]


# ── C-26 · an applied batch line reports compactly ───────────────────────

def test_batch_output_is_compact_for_applied_lines():
    assert cli._compact_out(json.dumps(
        {"seq": 72, "window": "P3C4", "search_ops": 4, "window_remaining": 56,
         "checkpoint_required": False, "evidence_items": 30})) == \
        '{"window_remaining":56,"checkpoint_required":false}'
    assert len(cli._compact_out("x " * 400)) <= 160


# ── C-04 / C-05 · the estimate and schedule are the workflow model ───────

def test_the_estimate_prices_the_workflow_the_driver_runs(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    wf = cost.workflow_estimate(run.open())
    assert wf["open_cells"] == 6 and wf["batches"] >= 2
    assert wf["research_usd"] == pytest.approx(
        6 * cost.WORKFLOW_USD_PER_CELL + 2 * cost.CHALLENGE_USD_PER_CATEGORY, abs=0.01)
    assert wf["recommended_max_usd"] >= wf["run_total_usd"] * cost.BUDGET_HEADROOM - 0.01
    # one source of truth: the driver's handoff prices with the same constants
    assert P.WORKFLOW_USD_PER_CELL is cost.WORKFLOW_USD_PER_CELL
    sch = cost._workflow_schedule(cost.schedule(6, 2), wf)
    assert any("workflows" in k for k in sch["phases_min"])
    assert not any("lanes" in k for k in sch["phases_min"])


# ── C-11 / C-17 · the handoff carries mode, connector health, background ─

def _drive(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    (run.root / "connector_health.json").write_text(json.dumps(
        {"families": {"exa": {"status": "NO_CREDITS", "note": "HTTP 402"}}}))
    disp = S.StubDispatcher(handlers={"research-p": S.lane_noop,
                                      "finding-challenger": S.lane_noop})
    opts = P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                     push=False, folder_root=tmp_path / "client_out", ingest_poll_s=0,
                     sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                     max_rounds=2, stall_rounds=0, research_mode="workflow")
    p = P.Pipeline(run, opts)
    return p, p.run_all()


def test_the_handoff_carries_mode_health_and_background(tmp_path):
    p, out = _drive(tmp_path)
    inv = json.loads(Path(out["handoff"]).read_text())["invocations"][0]
    assert inv["mode"] == "PUBLIC"
    assert inv["connectors"]["exa"].startswith("NO_CREDITS")
    assert "background" in inv


def test_the_hook_prints_common_args_once(tmp_path):
    # C-21: 34 KB of identical args were injected per driver exit.
    p, out = _drive(tmp_path)
    spec = importlib.util.spec_from_file_location(
        "stage_advance", PLUGIN / "scripts" / "hooks" / "stage_advance.py")
    sa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sa)
    event = {"tool_name": "Bash", "tool_input": {"command": "python3 -m engine.pipeline run"},
             "tool_response": {"stdout": f"AWAITING_WORKFLOW — {out['handoff']}"}}
    ctx = sa.awaiting_workflow(event)["hookSpecificOutput"]["additionalContext"]
    assert ctx.count("COMMON args") == 1
    calls = [ln for ln in ctx.splitlines() if "Workflow({scriptPath:" in ln]
    assert calls and all('"connectors"' not in ln for ln in calls)


# ── C-11 / C-19 / C-27 / C-28 / C-29 · the shipped batch prompt ──────────

def test_the_workflow_prompt_states_what_agents_used_to_reverse_engineer():
    src = (PLUGIN / P.RESEARCH_WORKFLOW).read_text()
    for needle in ("ABSENCE CONTRACT", "TIERS:", "headline contains",
                   "never read engine source", "EXHAUSTED", "exact_match",
                   "WORKDIR", "INTERNAL ?", "closed && round === 1"):
        assert needle in src, needle


# ── C-03 · the remote supersede keeps THIS run's preflight ───────────────

def test_drive_fetch_digest_is_the_preflight_digest():
    spec = importlib.util.spec_from_file_location(
        "drive_fetch", PLUGIN / "scripts" / "drive_fetch.py")
    df = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(df)
    doc = preflight_doc()
    assert df._preflight_digest(doc) == preflight.digest(doc)
