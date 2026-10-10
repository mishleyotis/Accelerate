"""A research pass priced, capped and routed so the RESEARCH envelope holds
(owner, 2026-10-10: "ensure the entire research loop costs less than $10
for Interac. I keep on getting repair attempts after every run and prompts
to raise budgets across runs. Are you batching the research for multiple
subcaps and limiting tool use accordingly?").

Measured on R-INTERAC-20261010 (715 cells, RB + CIB, HYBRID, DEGRADED), from
the run's own snapshot — one tiers round over five categories:

    collectors    18 lanes   $6.87   28–57 turns a lane (priced 17)
    orchestrators  5 lanes   $3.23   13–20 turns, $0.28–0.81 (priced $0.36)
    challengers    5 lanes   $0.84   7–10 turns (priced $0.20) — to shape
    RESEARCH spent $15.13 of $10; 0 of 5 categories passed; 46 repair cells
    P3C1 fired 200 distinct searches for 37 cells (design 2.2 a cell)
    46 repair cells: boilerplate 15 · challenge_failed 9 · challenge_missing 8
      — 0 collection gaps; every one handed to a COLLECTOR wave
    boilerplate: all 15 were declared ABSENCES whose What_We_Found is the
      engine's own hunt log ("Interac" is one capitalised word, no year)
    the first handoff priced the in-session shape ($84.15) and deferred 14
      categories; the owner raised --stage-budget RESEARCH to 28, then 55

Each test below pins one of the fixes; the last two pin the arithmetic.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from engine import brief, contract as C, cost, floors_gate as FG, ledger as L
from engine import pipeline as P, pipeline_stub as S, preflight, quality as Q
from fixtures import (_cu_may_hold, bank_evidence, fire_volleys, good_synthesis, new_run,
                      preflight_doc, synthesise, two_category_selection)

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"

#: P1C4.1.4's What_We_Found on R-INTERAC-20261010, verbatim (truncated as the
#: workbook holds it): the engine's own absence text, flagged `boilerplate`.
INTERAC_ABSENCE_WWF = (
    'Searched and not found: P1C4.1.4 primary "Interac" "change readiness" assessment on '
    'web_search, then facet queries "Interac" change management digital transformation '
    'program; "Interac" digital transformation delayed OR abandoned; "Interac" digital '
    'adoption results; "Interac" outage complaint digital platform; "Interac" digital '
    'transformation analyst review. Nearest thing that came back for P1C4.1.')


def _agent_run():
    spec = importlib.util.spec_from_file_location("agent_run", PLUGIN / "scripts" / "agent_run.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _tiers(tmp_path, *, selected=None, prepare=None, **kw):
    run = new_run(tmp_path, selected=selected or two_category_selection(3))
    preflight.record(run, preflight_doc())
    if prepare:
        prepare(run)
    disp = S.StubDispatcher(S.default_handlers())
    opts = dict(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(), push=False,
                folder_root=tmp_path / "out", ingest_poll_s=0, sleep=lambda s: None,
                log=lambda s: None, until="RESEARCH", research_mode="tiers",
                stage_budget={"RESEARCH": 100})
    opts.update(kw)
    p = P.Pipeline(run, P.Options(**opts))
    return p, disp, p.run_all()


# ── 1. the gate's false blocker on declared absences ───────────────────────

def test_interacs_absence_text_is_what_the_anchor_rule_rejects():
    why = Q.is_fluent_but_empty(INTERAC_ABSENCE_WWF)
    assert why and "names no figure, date, proper noun or cited id" in why


def test_a_declared_absence_is_judged_by_its_hunt_not_by_the_anchor_rule(tmp_path):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    cat = cell.split(".")[0]
    fire_volleys(wb, cell, n=0)
    proxy_q = f'"Interac" {cell} proxy: head of digital'
    L.append_search(wb, subcap=cell, facet="works", query=proxy_q, tool="exa",
                    hits=0, kept=0, outcome="no hits")
    # a hunt that names only the entity — one capitalised word, no year,
    # no E-id, no domain — exactly Interac's shape
    L.declare_absence(
        wb, cell, actor=f"research-{cat.lower()}-producer",
        ladder=[{"rung": "direct", "query": f'"Acme Credit Union" {cell} rollout OR "went live"'},
                {"rung": "proxy", "query": proxy_q}],
        proxy_log="hunted a named owner for the capability across the site and job boards; "
                  "nothing names one",
        what_was_hunted=f'{cell} primary "Interac" change readiness on web_search, then the '
                        f'facet queries; nearest thing that came back for {cell}: an Interac '
                        f'workplace page')
    row = wb.scoring_row(cell)
    assert Q.is_fluent_but_empty(row.get("What_We_Found")), "the rule would fire on this text"
    g = FG.run(wb, cat, require_synthesis=True, require_challenge=False, qa_dir=run.qa_dir)
    hits = [b for b in g["boilerplate"] if b.get("subcap") == cell and b.get("field") == "What_We_Found"]
    assert not hits, g["boilerplate"]
    assert cell not in FG.blocking_cells(g), FG.blocking_cells(g)


# ── 2. repairs go to the tier that can close them ──────────────────────────

def test_repairs_are_routed_to_the_tier_that_can_close_them():
    interac_p1c4 = {
        "P1C4.1.1": ["challenge_failed"], "P1C4.1.4": ["boilerplate"],
        "P1C4.4.3": ["challenge_missing"], "P1C4.8.1": ["challenge_failed"],
        "P1C4.2.2": ["volleys_incomplete", "challenge_failed"],
        "P1C4.9.9": ["single_source_fact"],
    }
    r = FG.route_repairs(interac_p1c4)
    assert r["collect"] == {"P1C4.2.2": ["volleys_incomplete"], "P1C4.9.9": ["single_source_fact"]}
    assert r["synthesise"] == {"P1C4.1.1": ["challenge_failed"], "P1C4.1.4": ["boilerplate"],
                               "P1C4.8.1": ["challenge_failed"], "P1C4.2.2": ["challenge_failed"]}
    assert r["challenge"] == {"P1C4.4.3": ["challenge_missing"]}
    # every blocking term the gate can emit has a tier; an unknown one is judgement
    routed = {t for ts in FG.REPAIR_ROUTES.values() for t in ts}
    for term in ("unresolved_citations", "boilerplate", "claim_unsupported", "absence_undeclared",
                 "evidence_smear", "challenge_missing", "challenge_not_independent",
                 "challenge_failed", "single_source_fact", "synthesis_missing", "dq_gaps",
                 "absence_unsearched", "volleys_incomplete", "absence_undeclared_empty",
                 "absence_over_evidence", "primary_unfired", "absence_single_tool"):
        assert term in routed, term
    assert FG.route_repairs({"X.1.1": ["a_new_term"]})["synthesise"] == {"X.1.1": ["a_new_term"]}
    doc = {"category": "P1C4", "gate": "FAIL", "blocking": ["boilerplate", "challenge_failed"],
           "boilerplate": [{"subcap": "P1C4.1.4", "field": "What_We_Found", "why": "names no figure"}],
           "challenge_failed": [{"subcap": "P1C4.1.1", "why": "present tense on an undated T4 row"}]}
    why = FG.blocking_reasons(doc)
    assert why == {"P1C4.1.4": "boilerplate on What_We_Found: names no figure",
                   "P1C4.1.1": "challenge_failed: present tense on an undated T4 row"}


def _drive(tmp_path, mode="workflow"):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    disp = S.StubDispatcher(handlers={"research-p": S.lane_noop, "finding-challenger": S.lane_noop})
    opts = P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(), push=False,
                     folder_root=tmp_path / "client_out", ingest_poll_s=0, sleep=lambda s: None,
                     log=lambda s: None, until="RESEARCH", max_rounds=2, stall_rounds=0,
                     research_mode=mode, stage_budget={"RESEARCH": 100})
    p = P.Pipeline(run, opts)
    return p, disp, p.run_all()


def test_the_handoff_sends_a_failed_claim_to_the_orchestrator_not_a_collector(tmp_path):
    p, disp, out = _drive(tmp_path)
    cat = out["invocations"][0]["cats"][0]
    wb = p.run.open()
    cells = [c for c in wb.selected_subcaps() if c.startswith(cat + ".")]
    for c in cells:                                   # the category is CLOSED
        synthesise(wb, c, good_synthesis(c, bank_evidence(wb, c, n=3)))
    doc = {"category": cat, "gate": "FAIL", "blocking": ["boilerplate", "challenge_failed"],
           "advisory": [],
           "boilerplate": [{"subcap": cells[0], "field": "What_We_Found",
                            "why": "names no figure, date, proper noun or cited id"}],
           "challenge_failed": [{"subcap": cells[1],
                                 "why": "Claim in present tense on an undated T4 posting"}]}
    (p.run.qa_dir / f"floors_{cat}.json").write_text(json.dumps(doc))
    h = P.Pipeline(p.run, p.opts)._research_handoff()
    inv = next(i for i in h["invocations"] if cat in i["cats"])
    assert inv["repairs"][cat] == {} and inv["repair_batches"][cat] == []
    assert inv["resynth"][cat] == {cells[0]: ["boilerplate"], cells[1]: ["challenge_failed"]}
    assert "undated T4" in inv["resynth_reasons"][cat][cells[1]]
    assert h["estimate"]["repair_cells"] == 0 and h["estimate"]["resynth_cells"] == 2
    # the rendered prompts: no collector for the closed category, and the
    # orchestrator is told which cells to rewrite and why
    doc = json.loads(Path(h["file"]).read_text())
    rows = json.loads(Path(doc["agent_prompts"]["manifest"]).read_text())
    assert not [r for r in rows if r["category"] == cat and r["kind"] == "collect"]
    orch = Path(next(r["file"] for r in rows if r["category"] == cat and r["kind"] == "orchestrate")).read_text()
    assert "RE-SYNTHESISE THESE CLOSED CELLS" in orch and cells[1] in orch and "undated T4" in orch
    assert "_pack.json" in orch


def test_a_round_runs_only_the_tiers_that_have_work(tmp_path):
    """Category A: every cell closed, one challenge FAIL → the gate routes it
    to the orchestrator. Category B: open. The round pays no collector for A,
    re-synthesises its cell, re-challenges it, and A passes — in ONE round."""
    state = {}

    def prepare(run):
        wb = run.open()
        cells = wb.selected_subcaps()
        a = cells[0].split(".")[0]
        state["A"] = a
        for c in [c for c in cells if c.startswith(a + ".")]:
            fire_volleys(wb, c, n=2)
        acells = [c for c in cells if c.startswith(a + ".")]
        for i, c in enumerate(acells):
            synthesise(wb, c, good_synthesis(c, bank_evidence(wb, c, n=3)),
                       author=f"research-{a.lower()}-producer",
                       verdict="FAIL" if i == 0 else "PASS")
        g = FG.run(wb, a, require_synthesis=True, qa_dir=run.qa_dir)
        assert g["gate"] == "FAIL" and "challenge_failed" in g["blocking"], g["blocking"]
        state["cell"] = acells[0]

    p, disp, out = _tiers(tmp_path, prepare=prepare)
    a = state["A"]
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    collect_for_a = [c for c in disp.calls if c["agent"] == "research-evidence-collector"
                     and f"category {a} " in Path(c["prompt_file"]).read_text()]
    assert not collect_for_a, "a failed claim bought a collector lane"
    orch_for_a = [c for c in disp.calls if c["agent"] == "research-category-orchestrator"
                  and f"category {a} " in Path(c["prompt_file"]).read_text()]
    assert orch_for_a
    g = FG.read_verdict(p.run.qa_dir, a)
    assert g["gate"] == "PASS", FG.summary(g)
    assert p.state["stages"]["RESEARCH"]["rounds"] == 1
    tiers = sorted((p.run.root / "briefs").glob("tiers_*"))
    kinds = {t.name.split("_")[1] for t in tiers}
    assert {"collect", "orchestrate", "challenge"} <= kinds


# ── 3. every lane carries its price as a ceiling ───────────────────────────

def test_lane_rows_carry_their_priced_ceiling_and_the_command_passes_it(tmp_path):
    p, disp, out = _tiers(tmp_path)
    rows = [r for b in sorted((p.run.root / "briefs").glob("tiers_*_r*/batch.json"))
            for r in json.loads(b.read_text())]
    assert rows
    for r in rows:
        cap = r["lean"]["max_usd"]
        tier = {"research-evidence-collector": "collector",
                "research-category-orchestrator": "orchestrator",
                "research-challenger": "challenge"}[r["agent"]]
        assert cap >= cost.LANE_CAP_FLOOR_USD[tier], r
    ar = _agent_run()
    cmd, _cwd = ar.lean_command("research-evidence-collector",
                                {"tools": ["Bash", "Read", "WebSearch", "WebFetch"], "max_usd": 0.25,
                                 "cwd": str(tmp_path)},
                                "collect P1C1.1", stream=False, scratch=tmp_path / ".lean")
    assert "--max-budget-usd" in cmd and cmd[cmd.index("--max-budget-usd") + 1] == "0.2500"
    assert cmd[-1].startswith("LANE CEILING: this lane stops at $0.25")
    cmd2, _ = ar.lean_command("research-challenger", {"tools": ["Bash", "Read"], "cwd": str(tmp_path)},
                              "judge", stream=False, scratch=tmp_path / ".lean")
    assert "--max-budget-usd" not in cmd2


def test_a_phases_caps_never_exceed_the_envelope():
    caps, f = cost.scale_caps_to([0.5, 0.5, 0.5], None)
    assert caps == [0.5, 0.5, 0.5] and f == 1.0
    caps, f = cost.scale_caps_to([0.5, 0.5], 2.0)
    assert f == 1.0
    caps, f = cost.scale_caps_to([0.5, 0.5], 0.6)
    assert f == pytest.approx(0.6) and sum(caps) == pytest.approx(0.6)
    caps, f = cost.scale_caps_to([0.5, 0.5], 0.05)
    assert f == 0.0, "a cap that only buys an open turn is a refusal, not a lane"


def test_a_runaway_lane_is_booked_at_its_cap_and_counted(tmp_path, monkeypatch):
    """The stub plays `claude -p --max-budget-usd`: a lane priced above its
    ceiling is booked at the ceiling and reported budget_cut, so the round's
    spend is bounded by the caps the driver handed out."""
    monkeypatch.setenv("DMA_STUB_USD_PER_LANE", "9")
    p, disp, out = _tiers(tmp_path)
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    rows = cost.ledger(p.run)
    research = [r for r in rows if r.get("stage") in ("RESEARCH", "CHALLENGE") and r.get("usd")]
    assert research
    caps = sum(float(r["lean"]["max_usd"]) for b in (p.run.root / "briefs").glob("tiers_*_r*/batch.json")
               for r in json.loads(b.read_text()))
    assert sum(float(r["usd"]) for r in research) <= caps + 1e-6
    assert sum(float(r["usd"]) for r in research) < 9 * 3     # three lanes at $9 would be $27


def test_a_thin_envelope_scales_the_caps_or_refuses_the_phase(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    p = P.Pipeline(run, P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                                  shipper=S.StubShipper(), push=False, log=lambda s: None,
                                  research_mode="tiers", stage_budget={"RESEARCH": 0.40}))
    rows = [{"agent": "research-evidence-collector", "lean": {"max_usd": 0.3}},
            {"agent": "research-evidence-collector", "lean": {"max_usd": 0.3}}]
    rows, f = p._cap_rows_to_envelope(rows, "RESEARCH")
    assert 0 < f < 1 and sum(r["lean"]["max_usd"] for r in rows) <= 0.40 + 1e-6
    p2 = P.Pipeline(run, P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                                   shipper=S.StubShipper(), push=False, log=lambda s: None,
                                   research_mode="tiers", stage_budget={"RESEARCH": 0.06}))
    _rows, f = p2._cap_rows_to_envelope([{"agent": "x", "lean": {"max_usd": 0.3}},
                                         {"agent": "y", "lean": {"max_usd": 0.3}}], "RESEARCH")
    assert f == 0.0


# ── 4. the collector's window is the capability's cells plus the volleys ──

def test_the_collector_window_is_the_capabilitys_cells_plus_the_volleys(tmp_path):
    run = new_run(tmp_path, n=8)
    wb = run.open()
    cells = wb.selected_subcaps()
    cat = cells[0].split(".")[0]
    cap = ".".join(cells[0].split(".")[:2])
    mine = [c for c in cells if c.startswith(cap + ".")]
    assert L.collector_ceiling(wb, cap) == len(mine) + len(C.FACETS) + L.COLLECTOR_WINDOW_SLACK
    assert L.collector_ceiling(wb, cat) == L.SEARCH_OP_CEILING          # a category keeps the wall
    assert L.collector_ceiling(wb, "P9C9.9") == L.SEARCH_OP_CEILING      # no cells: never refuse on a miscount
    actor = f"research-{cat.lower()}-collector"
    for i in range(L.collector_ceiling(wb, cap)):
        L.append_search(wb, subcap=mine, facet="works", query=f"volley {i}", tool="web_search",
                        hits=0, kept=0, actor=actor)
    with pytest.raises(L.LedgerRefusal) as e:
        L.append_search(wb, subcap=mine[0], facet="primary", query="one more", tool="web_search",
                        hits=0, kept=0, actor=actor)
    msg = str(e.value)
    assert "search window spent" in msg and "move to the next" in msg
    # a repair lane in a later round opens with the category checkpoint
    # and gets a fresh window; the spent one is not inherited
    from engine import runstate
    runstate.checkpoint(wb, "repair lane open", scope=[cat])
    L.append_search(wb, subcap=mine[0], facet="primary", query="the repair's own question",
                    tool="web_search", hits=0, kept=0, actor=actor)
    # the manifest and the prompt tell the lane the same thing
    assert "search window is the capability" in (PLUGIN / "agents" / "research" /
                                                  "research-evidence-collector.md").read_text()
    js = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "YOUR SEARCH WINDOW IS THE CAPABILITY'S" in js and "YOUR LANE HAS A DOLLAR CEILING" in js


# ── 5. the orchestrator reads one pack ─────────────────────────────────────

def test_the_orchestrator_reads_one_pre_rendered_pack(tmp_path):
    p, disp, out = _tiers(tmp_path)
    wb = p.run.open()
    cat = wb.selected_subcaps()[0].split(".")[0]
    pack_file = p.run.root / "briefs" / "research_cards" / cat / "_pack.json"
    assert pack_file.is_file(), "the driver renders the pack after the collectors return"
    pack = json.loads(pack_file.read_text())
    assert pack["category"] == cat and set(pack) >= {"gate", "cells", "rules"}
    cell = next(iter(pack["cells"]))
    entry = pack["cells"][cell]
    assert set(entry) >= {"state", "cites", "facets_logged", "facets_missing", "primary_fired"}
    for row in entry["cites"]:
        assert set(row) >= {"e_id", "excerpt", "tier", "recency", "host"}
        assert len(row["excerpt"]) <= brief.PACK_EXCERPT_CHARS
    live = brief.evidence_pack(wb, cat, qa_dir=p.run.qa_dir)
    assert live["gate"]["gate"] == "PASS"
    md = (PLUGIN / "agents" / "research" / "research-category-orchestrator.md").read_text()
    assert "_pack.json" in md


# ── 6. the arithmetic ──────────────────────────────────────────────────────

def test_the_lean_price_is_the_enforced_shape_and_says_what_ten_dollars_funds():
    """The price is the shape the caps enforce, not a figure fitted to the
    envelope. For the T1_CORE scope it is ABOVE $10 — the model says so
    instead of estimating to the envelope — and far below Interac's measured
    $0.059/cell."""
    p = cost.research_price(686, categories=16, capabilities=129, lean=True)
    assert 10.0 < p["usd"] < 22.0, p["usd"]
    assert p["per_cell"] < 0.059 / 2
    assert p["by_tier"]["repair_collector"] < p["by_tier"]["collector"] * 0.1
    assert "re-synthesis" in p["basis"]
    # a closed cell routed back to the orchestrator buys no collector batch
    q = cost.research_price(0, categories=1, capabilities=None, lean=True, synth_only_cells=12)
    assert q["batches"] == 0 and q["by_tier"]["collector"] == 0 and q["by_tier"]["orchestrator"] > 0
    # the lane caps bound the priced shape with slack, never below it
    assert cost.lane_cap_usd("collect", 12, capabilities=2) >= p["per_batch"]
    assert cost.lane_cap_usd("orchestrate", 43) >= p["per_category_orchestrator"]
    # what the default envelope funds, whole categories, cheapest first
    aff = cost.research_affordable(cost.STAGE_BUDGET_USD["RESEARCH"], 686, categories=16,
                                   capabilities=129, lean=True)
    assert not aff["fits"] and 300 < aff["cells_affordable"] < 686
    # the in-session shape is untouched by the lean refit
    assert cost.research_price(686, categories=16, capabilities=129)["usd"] == pytest.approx(81.72, abs=0.5)


def test_the_calibration_floor_follows_the_cells_not_the_category_count(tmp_path):
    """Interac's fourth handoff: 46 repair cells over 16 categories, floored
    at 16 x the last FULL round's $0.659 a category = $10.55 — the figure
    that asked the owner for more money."""
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    cost.record(run, stage="RESEARCH", elapsed_s=60, usd=10.55, note="one tiers round")
    p = P.Pipeline(run, P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                                  shipper=S.StubShipper(), push=False, log=lambda s: None,
                                  research_mode="tiers"))
    prev = {"usd": 10.55, "categories": 16, "open_cells": 669, "repair_cells": 46,
            "research_at_handoff": 0.0, "spent_at_handoff": 0.0}
    # Interac's 46 repair cells sat in FIVE categories; the old floor was
    # 16 x $0.659 = $10.55 whatever the round held
    est, basis, _price = p._workflow_estimate(0, 0, 5, prev, resynth=46)
    assert est < 3.0, (est, basis)
    assert "/cell" in basis and p.state["workflow_calibration"]["per_cell"] == pytest.approx(10.55 / 715, abs=1e-4)
    # a round with nothing to collect is priced as the repair pass it is,
    # not as a pass plus a repair of the repair
    one = cost.research_price(0, categories=1, lean=True, synth_only_cells=5)
    assert one["per_category_orchestrator"] * 1 + one["per_category_challenge"] == pytest.approx(one["usd"], abs=0.02)
    # the same work again costs what it cost: the ratio still corrects upward
    est2, _b, _p = p._workflow_estimate(669, 46, 16, prev)
    assert est2 >= 10.55 - 0.05


def _sixteen_categories(n=2):
    tax = C.taxonomy()
    out = []
    for cat in tax.categories:
        out += _cu_may_hold(tax, tax.cells_in(cat))[:n]
    return out


def test_sixteen_categories_are_handed_whole_and_pass_in_one_round(tmp_path, monkeypatch):
    """The owner's ask, on the stub: all sixteen categories in ONE tiers
    round under the default RESEARCH envelope — no category deferred for
    budget, no repair round, every gate PASS, every lane under its cap, and
    the ledger under the envelope."""
    monkeypatch.setenv("DMA_STUB_USD_PER_LANE", "0.05")
    p, disp, out = _tiers(tmp_path, selected=_sixteen_categories(2), stage_budget=None)
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    doc = json.loads((p.run.qa_dir / "research_workflow.json").read_text())
    cats = sorted(c for i in doc["invocations"] for c in i["cats"])
    assert len(cats) == 16 and not doc.get("deferred_for_budget"), doc.get("deferred_for_budget")
    assert p.state["stages"]["RESEARCH"]["rounds"] == 1, p.state["stages"]["RESEARCH"]
    for cat in cats:
        g = FG.read_verdict(p.run.qa_dir, cat)
        assert g and g["gate"] == "PASS", (cat, FG.summary(g))
    research = sum(float(r["usd"]) for r in cost.ledger(p.run)
                   if r.get("stage") in ("RESEARCH", "CHALLENGE") and r.get("usd"))
    assert 0 < research < cost.STAGE_BUDGET_USD["RESEARCH"]
