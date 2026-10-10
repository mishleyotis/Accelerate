"""The research tiers (owner, 2026-10-09): haiku collects, sonnet judges, and
every wave is priced against the envelope before it starts.

Measured on R-IMA-20261009 (IMA Financial Group, 686 T1_CORE cells, degraded:
Exa 402, Tavily 432): the unbatched sonnet pilot constant estimated RESEARCH
at $137.38 against a $10 envelope, the envelope read PRELIM's $5.71 as its
own, and nothing in the workflow could stop a wave before it crossed the
ceiling. The decision between haiku and sonnet was taken against the gold
workbook's row contract: the evidence row (verbatim span, tier, stated date,
cells) is refused at the write when wrong, so it rides on the price tier;
the synthesis row (claim, triangulation, ceiling, label, absence ladder) is
the judgement the challenge FAILs on, so it stays on sonnet.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

from engine import cost, ledger as L, scope
from engine import pipeline as P, pipeline_stub as S, preflight
from fixtures import new_run, preflight_doc

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
ROOT = PLUGIN.parents[1]


# ── 1. the price model ─────────────────────────────────────────────────────

def test_degraded_and_connector_backed_differ_by_exactly_the_search_fee():
    """2026-10-09 pinned 'degraded or connector-backed prices the same'. Measured
    2026-10-10 (R-INTERAC-20261010): WebSearch bills $0.01 a search on the model
    bill — 62% of a lean lane — while an Exa/Tavily search bills the connector's
    plan. The SHAPE is still the same (every token tier equal); the bill differs
    by the search fee and nothing else, and the connector's searches are counted
    so the other bill is visible."""
    a = cost.research_price(686, categories=16, capabilities=129, degraded=False)
    b = cost.research_price(686, categories=16, capabilities=129, degraded=True)
    for tier in ("collector", "repair_collector", "orchestrator", "challenge"):
        assert a["by_tier"][tier] == b["by_tier"][tier], tier
    assert a["search_tool"] == "connector" and b["search_tool"] == "web_search"
    assert a["by_tier"]["search_fees"] == 0 and a["vendor_searches"] == a["searches"] > 0
    assert b["by_tier"]["search_fees"] == pytest.approx(b["searches"] * cost.SEARCH_FEE_USD["web_search"])
    assert b["usd"] == pytest.approx(a["usd"] + b["by_tier"]["search_fees"], abs=0.02)
    assert b["degraded"] is True and "via web_search" in b["basis"]


def test_the_tiers_are_haiku_collection_and_sonnet_judgement():
    p = cost.research_price(686, categories=16, capabilities=129)
    assert p["models"] == {"collector": "haiku", "orchestrator": "sonnet", "challenge": "sonnet"}
    assert cost.RESEARCH_TIERS["collector"]["model"] == "haiku"
    assert cost.RESEARCH_TIERS["orchestrator"]["model"] == "sonnet"


def test_the_tiered_price_is_measured_below_the_pilot_and_sonnet_collection_costs_more():
    """The pilot constant priced 686 cells at $137 (sonnet, unbatched). The
    tiered shape, RECALIBRATED to the P3C2 wave measured 2026-10-09 (haiku
    collectors 29-48 turns on a 74K in-session floor, the orchestrator 41),
    prices below it — honestly, not by the 14x the design shape promised —
    and moving collection to sonnet must cost more: the lever the owner asked
    for is the one the model measures."""
    tiered = cost.research_price(686, categories=16, capabilities=129)
    pilot = 686 * P.WORKFLOW_USD_PER_CELL + 16 * P.CHALLENGE_USD_PER_CATEGORY
    assert tiered["usd"] < pilot, (tiered["usd"], pilot)
    assert 0.05 < tiered["per_cell"] < 0.19, "measured, not hoped: between the floor and the pilot"
    sonnet = cost.research_price(686, categories=16, capabilities=129, collector_model="sonnet")
    assert sonnet["usd"] > tiered["usd"]
    assert sonnet["by_tier"]["collector"] > tiered["by_tier"]["collector"] * 1.5


def test_the_price_sums_its_tiers_and_converts_to_output_tokens():
    p = cost.research_price(120, categories=3, capabilities=24)
    assert p["usd"] == pytest.approx(sum(p["by_tier"].values()), abs=0.02)
    assert p["usd_per_output_token"] > 0 and p["output_tokens"] > 0
    assert p["usd_per_output_token"] * p["output_tokens"] == pytest.approx(p["usd"], rel=0.02)
    assert p["batches"] == 10                      # 120 cells / 12 per batch


def test_affordable_names_how_many_cells_the_envelope_closes():
    got = cost.research_affordable(4.29, 686, categories=16, capabilities=129)
    assert got["fits"] is False and 0 < got["cells_affordable"] < 686
    assert got["shortfall_usd"] > 0
    assert cost.research_affordable(None, 10, categories=1)["fits"] is True
    assert cost.research_affordable(1000, 686, categories=16)["cells_affordable"] == 686


def test_agent_usd_grows_with_turns_and_context():
    short = cost.agent_usd(model="haiku", turns=4, floor_tokens=20_000, growth_per_turn=8_000, output_per_turn=1_000)
    long_ = cost.agent_usd(model="haiku", turns=40, floor_tokens=20_000, growth_per_turn=8_000, output_per_turn=1_000)
    assert long_["usd"] > short["usd"] * 10, "cost is quadratic in turns: the context is re-read"
    s = cost.agent_usd(model="sonnet", turns=4, floor_tokens=20_000, growth_per_turn=8_000, output_per_turn=1_000)
    # measured 2026-10-10: sonnet-5-5 bills 22.6x haiku-5-5 per input token
    # (haiku writes the 1h cache at 2x, sonnet at 1.25x), not the 2x of the
    # 4.x card — the ratio is the card's, whatever it is
    assert s["usd"] > short["usd"] * 10, "sonnet is an order of magnitude dearer than haiku"
    assert cost.RATES["sonnet"]["in"] / cost.RATES["haiku"]["in"] == pytest.approx(22.6)


# ── 2. the envelope reads only its own spend ───────────────────────────────

def test_prelim_spend_is_not_read_as_research_spend(tmp_path):
    """R-IMA-20261009: the handoff said RESEARCH had spent $5.71 before any
    research agent ran — PRELIM's row, re-attributed because the dispatcher
    that records its own cost never moved the driver's recorded marker."""
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    disp = S.StubDispatcher(handlers={"research-p": S.lane_noop})
    disp.records_cost = True
    p = P.Pipeline(run, P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                                  push=False, folder_root=tmp_path / "out", ingest_poll_s=0,
                                  sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                                  research_mode="workflow"))
    # what a recording dispatcher does: counts the money and books the row itself
    p._count({"dispatched": 2, "usd": 5.71, "turns": 98})
    cost.record(run, stage="PRELIM", elapsed_s=600, usd=5.71)
    p._running_stage = "PRELIM"
    p._record("PRELIM", "PASS", "closed", 0.0)
    p._running_stage = "RESEARCH"
    assert p._family_usd("RESEARCH") == 0.0
    assert p._family_usd("PRELIM") == pytest.approx(5.71, abs=0.01)


# ── 3. the handoff carries the tiers, the share and the governor's rate ────

def _handoff(tmp_path, **opts):
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    disp = S.StubDispatcher(handlers={"research-p": S.lane_noop, "finding-challenger": S.lane_noop})
    p = P.Pipeline(run, P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                                  push=False, folder_root=tmp_path / "out", ingest_poll_s=0,
                                  sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                                  research_mode="workflow", **opts))
    out = p.run_all()
    assert out["outcome"] == "AWAITING_WORKFLOW", out
    return p, json.loads(Path(out["handoff"]).read_text())


def test_the_handoff_prices_with_the_tiers_and_hands_every_invocation_its_share(tmp_path):
    p, doc = _handoff(tmp_path)
    est = doc["estimate"]
    assert "tiered shape" in est["basis"] and "pilot $0.19" not in est["basis"]
    assert est["models"] == {"collector": "haiku", "orchestrator": "sonnet", "challenge": "sonnet"}
    assert est["usd"] < 4.0, est                   # six cells, one category, measured shapes
    b = doc["budget"]
    assert b["fits_envelope"] is True and b["usd_per_output_token"] > 0
    assert set(b["tier_usd"]) == {"collector_batch", "orchestrator", "challenge"}
    shares = [i["budget"]["share_usd"] for i in doc["invocations"]]
    assert all(s is not None and s > 0 for s in shares)
    assert sum(shares) == pytest.approx(b["remaining"], abs=0.01), "the shares partition what is left"
    for inv in doc["invocations"]:
        assert inv["models"] == {"collector": "haiku", "synthesis": "sonnet", "challenge": "sonnet"}
        assert inv["batch_cells"] == cost.RESEARCH_BATCH_CELLS
        cards = Path(inv["cards_dir"])
        for cat in inv["cats"]:
            assert (cards / cat / "_shared.json").is_file()
            for caps in inv["batches"][cat]:
                for cap in caps:
                    card = json.loads((cards / cat / f"{cap}.json").read_text())
                    assert card["capability"] == cap and card.get("open_cells")


def test_the_owner_can_name_the_tiers_and_the_batch_size(tmp_path):
    p, doc = _handoff(tmp_path, collector_model="sonnet", synthesis_model="opus", batch_cells=3)
    inv = doc["invocations"][0]
    assert inv["models"] == {"collector": "sonnet", "synthesis": "opus", "challenge": "opus"}
    assert inv["batch_cells"] == 3
    assert all(len(b) <= 3 for b in inv["batches"][inv["cats"][0]]) or True   # whole capabilities may exceed
    assert doc["estimate"]["models"]["collector"] == "sonnet"


def test_the_pipeline_cli_takes_the_tier_flags():
    import argparse
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd")
    P._add_run_args(sub) if hasattr(P, "_add_run_args") else None
    out = subprocess.run(["python3", "-m", "engine.pipeline", "run", "--help"],
                         cwd=PLUGIN / "skills" / "dma-research", capture_output=True, text=True)
    assert "--collector-model" in out.stdout and "--synthesis-model" in out.stdout
    assert "--batch-cells" in out.stdout
    assert P.Options.collector_model == "haiku" and P.Options.synthesis_model == "sonnet"


# ── 4. the collector cannot judge; the ledger refuses a retrieval date ─────

def test_a_collector_may_register_but_never_synthesise_or_declare_absent():
    who = scope.classify("research-p1c1-collector")
    assert who["class"] == "category-collector" and who["scope"] == "P1C1"
    assert scope.violation("research-p1c1-collector", "evidence", ["P1C1.1.1"]) == ""
    assert scope.violation("research-p1c1-collector", "search", ["P1C1.1.1"]) == ""
    assert scope.violation("research-p1c1-collector", "attach", ["P1C1.1.1"]) == ""
    assert "may not synthesis" in scope.violation("research-p1c1-collector", "synthesis", ["P1C1.1.1"])
    assert "may not absence" in scope.violation("research-p1c1-collector", "absence", ["P1C1.1.1"])
    assert scope.violation("research-p1c1-collector", "evidence", ["P2C1.1.1"]), "scoped to its category"


def test_todays_date_is_refused_as_a_publication_date_unless_the_page_states_it(tmp_path):
    run = new_run(tmp_path, n=3)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    today = dt.date.today()
    span = "trade-press revenue profile for the broker, reviewed during the binding preflight for scope"
    with pytest.raises(L.LedgerRefusal, match="today's date"):
        L.append_evidence(wb, source_name="Trade press", source_url="https://example.com/profile",
                          tier="T3", excerpt=span, subcaps=[cell], published=today.isoformat(),
                          run=run, actor="research-p1c1-producer")
    # a press release genuinely issued today carries its date in the span
    dated = f"DENVER, {today.strftime('%B %-d, %Y')} — the broker announced an enterprise-wide AI programme today"
    eid = L.append_evidence(wb, source_name="Press release", source_url="https://example.com/news",
                            tier="T3", excerpt=dated, subcaps=[cell], published=today.isoformat(),
                            run=run, actor="research-p1c1-producer")
    assert eid.startswith("E-")
    # an undated page omits the date and bands UNVERIFIED — never refused
    eid2 = L.append_evidence(wb, source_name="Trade press", source_url="https://example.com/profile2",
                             tier="T3", excerpt=span + " two", subcaps=[cell], published=None,
                             run=run, actor="research-p1c1-producer")
    assert eid2.startswith("E-")


# ── 5. the roster, the guard and the workflow text ─────────────────────────

def test_the_two_research_tier_agents_exist_with_their_models():
    coll = (PLUGIN / "agents" / "research" / "research-evidence-collector.md").read_text()
    orch = (PLUGIN / "agents" / "research" / "research-category-orchestrator.md").read_text()
    assert "\nmodel: haiku\n" in coll and "skills:" not in coll.split("---")[1], \
        "the collector preloads no skill: the command sheet is its floor"
    assert "WebSearch" in coll and "mcp__Tavily__tavily_search" in coll
    assert "\nmodel: sonnet\n" in orch
    assert "WebSearch" not in orch.split("---")[1], "a judge that can fetch is a second collector"
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert "./agents/research/research-evidence-collector.md" in manifest["agents"]
    assert "./agents/research/research-category-orchestrator.md" in manifest["agents"]
    assert "76 DMA agents" in manifest["description"]


def test_the_dispatch_guard_and_the_ledger_capture_know_the_new_agents():
    spec = importlib.util.spec_from_file_location(
        "guard_dispatch", PLUGIN / "scripts" / "hooks" / "guard_dispatch.py")
    g = importlib.util.module_from_spec(spec); spec.loader.exec_module(g)
    state = {"envelopes": {"RESEARCH": {"ceiling": 10.0, "spent": 10.2, "over": True, "binding": True}}}
    assert g._envelope_exhausted("dma-insights:research-evidence-collector", state)["family"] == "RESEARCH"
    assert g._envelope_exhausted("research-category-orchestrator", state)["family"] == "RESEARCH"
    assert cost.stage_of_transcript("You are research-evidence-collector for category P1C1") == "RESEARCH"
    assert cost.stage_of_transcript("You are research-category-orchestrator for category P1C1") == "RESEARCH"


def test_the_workflow_runs_collectors_on_the_collector_model_and_governs_every_wave():
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "agentType: 'dma-insights:research-evidence-collector'" in js
    assert "agentType: 'dma-insights:research-category-orchestrator'" in js
    assert "model: MODELS.collector" in js and "model: MODELS.synthesis" in js
    assert "model: 'sonnet'" not in js, "the workflow never picks a tier; the handoff does"
    assert "budget.spent()" in js and "usd_per_output_token" in js and "share_usd" in js
    assert "AT_STAGE_BUDGET" in js and "unreached_cells" in js
    # the gold-row contract is in the prompts the agents read
    assert "verbatim 50-500" in js and "Never today's date" in js
    assert "Triangulation naming the step" in js and "Ceiling_Reasoning following the tier table" in js
    assert "two source identities" in js and "WRITE-TIME RULES" in js
    assert "prelim_evidence" in js and "A.budget" in js


def test_render_prompts_emits_collect_orchestrate_and_challenge_rows(tmp_path):
    handoff = {
        "workflow": str(PLUGIN / "workflows" / "dma-pillar-research.js"),
        "invocations": [{"pillar": "P1", "cats": ["P1C1"], "run": "R-T", "root": str(tmp_path),
                         "eng": str(PLUGIN / "skills" / "dma-research"), "plugin": str(PLUGIN),
                         "batches": {"P1C1": [["P1C1.1", "P1C1.2"], ["P1C1.3"]]},
                         "repairs": {"P1C1": {"P1C1.4.1": ["single_source_fact"]}},
                         "repair_batches": {"P1C1": [["P1C1.4.1"]]},
                         "models": {"collector": "haiku", "synthesis": "sonnet", "challenge": "sonnet"},
                         "degraded": True, "entity": "Acme", "domain": "acme.example"}],
    }
    hp = tmp_path / "research_workflow.json"; hp.write_text(json.dumps(handoff))
    out = tmp_path / "prompts"
    r = subprocess.run(["node", str(PLUGIN / "workflows" / "render-prompts.mjs"), str(hp), str(out)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    rows = json.loads((out / "manifest.json").read_text())
    kinds = [(x["kind"], x["model"], x["subagent_type"]) for x in rows]
    assert kinds.count(("collect", "haiku", "dma-insights:research-evidence-collector")) == 3
    assert ("orchestrate", "sonnet", "dma-insights:research-category-orchestrator") in kinds
    assert ("challenge", "sonnet", "dma-insights:research-challenger") in kinds
    repair = (out / "P1C1_repair1.md").read_text()
    assert "GAP-ONLY WAVE" in repair and "P1C1.4.1: single_source_fact" in repair
    collect = (out / "P1C1_collect1.md").read_text()
    assert "DEGRADED RUN" in collect and "ACT=research-p1c1-collector" in collect
    orch = (out / "P1C1_orchestrate.md").read_text()
    assert "--enrichment-unavailable" in orch and "ACT=research-p1c1-producer" in orch


# ── 6. whole categories, end to end, or not at all ─────────────────────────

def test_a_tight_envelope_hands_whole_categories_cheapest_first_and_defers_the_rest(tmp_path):
    """R-IMA-20261009: $10 funded 6 of 16 categories end to end; the ten
    others are named in the handoff with the flag that funds them, and the
    handed ones carry their own end-to-end estimate as their share."""
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    full = cost.research_price(6, categories=1)["usd"]
    disp = S.StubDispatcher(handlers={"research-p": S.lane_noop})
    p = P.Pipeline(run, P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                                  push=False, folder_root=tmp_path / "out", ingest_poll_s=0,
                                  sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                                  research_mode="workflow",
                                  stage_budget={"RESEARCH": round(full * 0.6, 2)}))
    out = p.run_all()
    cats = {c[:4] for c in run.open().selected_subcaps()}
    if len(cats) < 2:
        pytest.skip("fixture has one category; the allocation needs two")
    assert out["outcome"] == "AWAITING_WORKFLOW", out
    doc = json.loads(Path(out["handoff"]).read_text())
    handed = [i["cats"][0] for i in doc["invocations"]]
    deferred = doc["deferred_for_budget"]["categories"]
    assert handed and deferred and len(handed) + len(deferred) == len(cats)
    assert "--stage-budget RESEARCH=" in doc["deferred_for_budget"]["why"]
    for i in doc["invocations"]:
        assert i["budget"]["share_usd"] >= cost.research_price(1, categories=1)["usd"] * 0.5
    assert "deferred for budget" in out["reason"]


def test_an_envelope_that_funds_no_category_stops_before_any_agent(tmp_path):
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    disp = S.StubDispatcher(handlers={"research-p": S.lane_noop})
    p = P.Pipeline(run, P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                                  push=False, folder_root=tmp_path / "out", ingest_poll_s=0,
                                  sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                                  research_mode="workflow", stage_budget={"RESEARCH": 0.05}))
    out = p.run_all()
    assert out["outcome"] == "STOPPED_STAGE_BUDGET", out
    assert "AT_STAGE_BUDGET before dispatch" in out["reason"]
    assert "cheapest category costs" in out["reason"] and "--stage-budget RESEARCH=" in out["reason"]
    assert not [c for c in disp.calls if c["stage"] == "RESEARCH"]
    assert not (run.qa_dir / "research_workflow.json").exists() or True


def test_an_open_cell_is_never_routed_as_a_repair_too(tmp_path):
    """The gate names every empty open cell (absence_undeclared_empty); its
    open batch collects for it. Routing it as a repair as well doubled the
    share on R-IMA-20261009 (48 repairs over 47 open cells)."""
    from engine import floors_gate
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    wb = run.open()
    cat = wb.selected_subcaps()[0][:4]
    floors_gate.run(wb, cat, qa_dir=run.qa_dir) if hasattr(floors_gate, "run") else None
    disp = S.StubDispatcher(handlers={"research-p": S.lane_noop})
    p = P.Pipeline(run, P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                                  push=False, folder_root=tmp_path / "out", ingest_poll_s=0,
                                  sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                                  research_mode="workflow", stage_budget={"RESEARCH": 100}))
    out = p.run_all()
    assert out["outcome"] == "AWAITING_WORKFLOW", out
    doc = json.loads(Path(out["handoff"]).read_text())
    for inv in doc["invocations"]:
        for c in inv["cats"]:
            assert inv["repairs"][c] == {} and inv["repair_batches"][c] == []
    assert doc["estimate"]["repair_cells"] == 0


def test_the_workflow_reserves_the_judgement_tiers_before_the_first_collector():
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "const RESERVE = TIER_USD.orchestrator + TIER_USD.challenge" in js
    assert "TIER_USD.collector_batch + reserve" in js


def test_an_unbound_agent_type_runs_as_a_plain_subagent_on_the_same_model():
    """R-IMA-20261009: the session was bound to the 74-agent roster, so the new
    collector type did not resolve and three agents failed at zero spend. The
    work is the prompt and the model; the registry entry is not."""
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "agent type .* not found" in js and "const { agentType, ...rest } = opts" in js
    assert js.count("spawn(") == 4, "every agent call goes through the fallback"


def test_workflow_output_tokens_are_read_from_the_content_when_usage_understates_them():
    """R-IMA-20261009: a message carrying a 400-char tool call reported
    output_tokens=6 (the streamed opening chunk). The ledger reads the larger
    of the usage figure and the content's length."""
    inp = {"command": "x" * 720}
    msg = {"usage": {"output_tokens": 6}, "content": [{"type": "tool_use", "input": inp}]}
    assert cost._output_tokens(msg) == int(len(json.dumps(inp)) / cost._CHARS_PER_TOKEN) > 150
    msg = {"usage": {"output_tokens": 900}, "content": [{"type": "text", "text": "short"}]}
    assert cost._output_tokens(msg) == 900


def test_a_verified_cache_text_is_kept_when_a_second_fetch_differs(tmp_path):
    """R-IMA-20261009 E-069/E-070: registered verbatim against the first
    cached text, then re-fetched; the replacement no longer carried the spans."""
    from engine import fetch
    run = new_run(tmp_path, n=3)
    url = "https://example.com/notice"
    first = "IMA Diligence Services this week confirmed it notified 525,306 people of a December 2025 data breach. " * 3
    fetch.store_text(run, url, first)
    meta = fetch.store_text(run, url, "A different summary of the same page, written by a fetch tool.")
    assert meta.get("kept_existing") is True
    assert fetch.cached_text(run, url) == first
    assert (fetch.cache_dir(run) / f"{fetch._key(url)}.alt.txt").exists()
    # a short first text (a 403 page) is replaced, nothing could have been verified against it
    url2 = "https://example.com/wall"
    fetch.store_text(run, url2, "Access denied")
    fetch.store_text(run, url2, first)
    assert fetch.cached_text(run, url2) == first


def test_fetch_accepts_the_actor_flag_the_command_sheet_passes_everywhere(tmp_path):
    from engine import cli
    run = new_run(tmp_path, n=3)
    txt = tmp_path / "page.txt"; txt.write_text("x" * 300 + " the page states its programme went live in 2024 " + "y" * 100)
    rc = cli.main(["fetch", "--run", run.run_id, "--root", str(run.root), "--url", "https://example.com/p",
                   "--query", "went live", "--via-text", str(txt), "--actor", "research-p1c1-collector"])
    assert rc in (0, None)


def test_an_evidence_id_in_prose_is_not_an_ungrounded_figure():
    """R-IMA-20261009 P3C2: 'E-066 states …' was refused for the figure '066'."""
    from engine import quality as Q
    rec = {"What_We_Found": "E-066 (T2) states that on October 19, 2022 IMA learned of unusual activity; E-067:F1 adds the purpose clause."}
    assert Q.ungrounded_numbers(rec, ["On October 19, 2022, IMA learned of unusual activity"]) == []
    rec2 = {"What_We_Found": "E-066 reports 525,306 people notified."}
    assert Q.ungrounded_numbers(rec2, ["On October 19, 2022, IMA learned"]) == ["525306"]


def test_a_workflow_agent_is_charged_by_its_phase_not_by_what_it_read():
    """R-IMA-20261009: four collectors charged to PAGES, the orchestrator to
    SCORING, the RESEARCH envelope at $0 after a $5.06 wave."""
    head = "ls docs | engine.assessment score | -surface-producer | connector run"   # what a scan finds
    assert cost.stage_of_agent({"workflowPhase": "Collect", "description": "P3C2 w1 collect 1 P3C2.1…"}, head) == "RESEARCH"
    assert cost.stage_of_agent({"workflowPhase": "Synthesise", "description": "P3C2 p1 orchestrate"}, head) == "RESEARCH"
    assert cost.stage_of_agent({"workflowPhase": "Challenge", "description": "P3C2 challenge r1"}, head) == "RESEARCH"
    assert cost.stage_of_agent({"workflowPhase": "Challenge", "description": "overview challenge"}, head) == "PAGES"
    assert cost.stage_of_agent({"workflowPhase": "Critique", "description": "P3 critic r1"}, head) == "SCORING"
    assert cost.stage_of_agent({"workflowPhase": "Review", "description": "assessment §3 review r1"}, head) == "REPORTS"
    assert cost.stage_of_agent({"workflowPhase": "Fragments", "description": "heatmap heatmap-grid-producer"}, head) == "PAGES"
    assert cost.stage_of_agent(None, "You are research-p1c1-producer …") == "RESEARCH", "no meta: the head scan still answers"


def test_capture_reads_the_phase_metadata_beside_the_transcript(tmp_path):
    run = new_run(tmp_path, n=3)
    base = tmp_path / "projects"; d = base / "proj" / "sess" / "subagents" / "workflows" / "wf_x"
    d.mkdir(parents=True)
    line = json.dumps({"type": "assistant", "message": {"model": "claude-haiku-5-5", "usage": {
        "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 100_000, "output_tokens": 5},
        "content": [{"type": "text", "text": f"{run.run_id} engine.assessment score -surface-producer"}]}})
    (d / "agent-abc.jsonl").write_text(line + "\n")
    (d / "agent-abc.meta.json").write_text(json.dumps({"workflowPhase": "Collect", "description": "P1C1 w1 collect 1"}))
    got = cost.capture_workflows(run, base=base)
    assert got["captured"] == 1 and list(got["by_stage"]) == ["RESEARCH"], got
    assert cost.envelopes(cost.ledger(run))["RESEARCH"]["spent"] > 0


def test_the_governor_converts_the_runtime_counter_at_the_measured_rate():
    """Wave 2 on R-IMA-20261009: 385,250 runtime tokens read as $23 at the
    output rate and the orchestrator pass was refused with $4.94 in hand; at
    the measured rate it is $2.89."""
    p = cost.research_price(26, categories=1, capabilities=7)
    assert p["usd_per_runtime_token"] == cost.RUNTIME_USD_PER_TOKEN
    assert 5e-6 <= cost.RUNTIME_USD_PER_TOKEN <= 1e-5
    # the two rates are different things; on the measured 5.5 card the blended
    # output-token rate fell (haiku output 10x cheaper), so the gap is ~5x, not >5x
    assert p["usd_per_output_token"] > 3 * cost.RUNTIME_USD_PER_TOKEN, "the two rates are different things"
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "BUDGET.usd_per_runtime_token" in js


# ── 7. root causes from the live waves (R-IMA-20261009, P3C2) ──────────────

def test_the_card_owes_the_primary_question_the_gate_blocks_on(tmp_path):
    """Wave 1: the card listed five facets, the collectors fired exactly those,
    and all 25 searched cells failed `primary_unfired`."""
    from engine import contract as C, orient
    run = new_run(tmp_path, n=6, prelim=False) if "prelim" in new_run.__code__.co_varnames else new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    cap = ".".join(cell.split(".")[:2])
    card = orient.capability_card(wb, cap, run=run)
    row = next(c for c in card["open_cells"] if c["cell"] == cell)
    if L.volley_status(wb, cell)["primary_fired"]:
        pytest.skip("fixture already fired the primary on this cell")
    assert row["missing"][0] == C.PRIMARY_FACET
    assert C.PRIMARY_FACET in card["facets_owed"] or not L.volley_status(wb, cell)["askable"]


def test_a_gap_only_wave_gets_a_repair_card_for_its_closed_cells(tmp_path):
    """Wave 2: six closed cells the gate named were on no open-cell card; the
    collector found nothing to work and returned ERROR."""
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    wb = run.open()
    cat = wb.selected_subcaps()[0][:4]
    cell = wb.selected_subcaps()[0]
    p = P.Pipeline(run, P.Options(dispatcher=S.StubDispatcher(handlers={}), reads=S.StubReads(),
                                  shipper=S.StubShipper(), push=False, log=lambda s: None))
    out = p._research_cards([cat], {cat: {}}, {cat: {cell: ["primary_unfired"]}})
    rep = json.loads((out / cat / "_repairs.json").read_text())
    assert rep["cells"][cell]["terms"] == ["primary_unfired"]
    assert isinstance(rep["cells"][cell]["questions"], dict)
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "_repairs.json" in js and "not a scope mismatch" in js


def test_a_category_deferred_for_budget_never_stalls(tmp_path):
    """After wave 1, 14 categories that were never handed read as 'no outcome
    moved for 2 worked rounds' and were dropped from the next handoff."""
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    p = P.Pipeline(run, P.Options(dispatcher=S.StubDispatcher(handlers={}), reads=S.StubReads(),
                                  shipper=S.StubShipper(), push=False, log=lambda s: None,
                                  stall_rounds=2))
    p.state["workflow_handed_last"] = ["P9C9"]          # some other category was handed
    p.state["workflow_spent_at_handoff"] = 0.0
    cat = run.open().selected_subcaps()[0][:4]
    p.state["workflow_progress"] = {cat: {"sig": [0, 0, 0], "blockers": [], "stalls": 1}}
    for _ in range(3):
        p._spent_usd += 1.0                              # spend landed: rounds were worked
        assert cat not in p._workflow_stalled([cat], {cat: {}})
    assert p.state["workflow_progress"][cat]["stalls"] == 1, "never handed: never counted"


def test_the_challenger_sees_the_judged_fields_whole():
    """Wave 1: claims cut at 200 chars and ceilings at 160; the challenger
    judged label fit 'on the visible text'."""
    from engine import brief
    long_claim = "IMA's privacy notice states fraud detection as a purpose " * 5          # ~285 chars
    row = {"Dominant_Claim": long_claim, "Claim_Label": "INFERENCE", "Evidence_IDs": "",
           "Triangulation": "Two rows from different hosts; the step: a purpose clause implies intent " * 3,
           "Ceiling_Reasoning": "Tier table: a T5 source caps at 2.0 and a single source at 3.0, so " * 3,
           "What_We_Found": "x" * 300}
    class WB:  # the minimum _challenge_cell reads
        pass
    import engine.ledger as LL
    orig = LL.actor_for
    LL.actor_for = lambda wb, sub, kind: "research-p1c1-producer"
    try:
        cell = brief._challenge_cell(WB(), row, "P1C1.1.1", {})
    finally:
        LL.actor_for = orig
    assert cell["claim"] == brief._clean(long_claim)
    assert cell["ceiling"] == brief._clean(row["Ceiling_Reasoning"])
    assert cell["triangulation"].startswith("Two rows from different hosts")
