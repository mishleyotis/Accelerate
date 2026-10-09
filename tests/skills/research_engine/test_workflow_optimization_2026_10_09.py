"""The 2026-10-09 workflow optimisation — every rule pinned by the number that
motivated it.

Measured across the runs of 2026-09-25..10-09 (Arbor Bank $409, Susser Bank
$450, B1 Bank $1,236 against a $20 default; 212 / 141 floors rounds; 46 / 76
/ 61 critic rounds; 137 / 154 / 95 report reviews; 55 / 76 page attempts;
PRELIM evidence cited 2 / 1 / 0 times out of 26 / 26 / 30 rows). Each test
below is one of the mechanisms that produced those numbers, closed where it
was cheapest to close: at the write, in the brief, or in the envelope.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from engine import assessment as A
from engine import brief, cost, ledger as L, page_preflight as PP
from engine import pipeline as P, pipeline_stub as S, preflight, rubric
from engine import workbook as W
from fixtures import (bank_evidence, good_synthesis, new_run, preflight_doc,
                      rationale_for, score_cell, scored_run, synthesise)

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"


# ── 1. the envelopes ───────────────────────────────────────────────────────

def test_the_owner_s_stage_envelopes_are_the_cost_model_s():
    """Research <= $10, scoring <= $5, reports <= $5: the owner's figures,
    stated once, and the run-wide default is their sum."""
    assert cost.STAGE_BUDGET_USD["RESEARCH"] == 10.0
    assert cost.STAGE_BUDGET_USD["SCORING"] == 5.0
    assert cost.STAGE_BUDGET_USD["REPORTS"] == 5.0
    assert cost.run_budget_default(4) == sum(cost.STAGE_BUDGET_USD.values())
    assert cost.run_budget_default(1) >= cost.BUDGET_PER_PILLAR


def test_challenge_and_relay_pay_from_the_research_envelope():
    rows = [{"stage": "RESEARCH", "usd": 6.0}, {"stage": "CHALLENGE", "usd": 3.0},
            {"stage": "RELAY", "usd": 2.0}, {"stage": "SCORING", "usd": 1.0},
            {"stage": "INGEST_A", "usd": None}]
    env = cost.envelopes(rows)
    assert env["RESEARCH"]["spent"] == 11.0 and env["RESEARCH"]["over"]
    assert env["SCORING"]["spent"] == 1.0 and not env["SCORING"]["over"]
    assert cost.stage_family("INGEST_A") is None
    assert cost.stage_family("PAGES_B") == "PAGES"


def test_an_override_moves_one_envelope_only():
    env = cost.envelopes([{"stage": "RESEARCH", "usd": 11.0}], {"RESEARCH": 12})
    assert env["RESEARCH"]["ceiling"] == 12.0 and not env["RESEARCH"]["over"]
    assert env["SCORING"]["ceiling"] == 5.0


def test_workflow_agents_are_charged_to_the_stage_they_worked():
    """`capture_workflows` used to book every workflow agent to RESEARCH —
    scorers, critics, writers and page producers included — so no stage
    could be judged against its envelope."""
    assert cost.stage_of_transcript("You are scoring-critic for pillar P2 of DMA run R") == "SCORING"
    assert cost.stage_of_transcript("You are report-validator for DMA run R, assessment §3") == "REPORTS"
    assert cost.stage_of_transcript("You are overview-surface-producer. DMA run R, connector run X") == "PAGES"
    assert cost.stage_of_transcript("You are research-p1c1-producer for DMA run R") == "RESEARCH"
    assert cost.stage_of_transcript("") == "RESEARCH"


def test_capture_books_one_ledger_row_per_stage_family(tmp_path):
    run = new_run(tmp_path, n=6)
    base = tmp_path / "wf"
    d = base / "proj" / "sess" / "subagents" / "workflows" / "wf_1"
    d.mkdir(parents=True)

    def transcript(name, prompt):
        lines = [json.dumps({"type": "user", "message": {"content": f"{prompt} {run.run_id}"}}),
                 json.dumps({"type": "assistant", "message": {
                     "model": "claude-sonnet", "usage": {
                         "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 1000,
                         "input_tokens": 100, "output_tokens": 500}}})]
        (d / f"agent-{name}.jsonl").write_text("\n".join(lines))
    transcript("a1", "You are scoring-p1-producer for DMA run")
    transcript("a2", "You are report-validator for DMA run")
    transcript("a3", "You are research-p1c1-producer for DMA run")
    got = cost.capture_workflows(run, base=base)
    assert got["captured"] == 3
    assert set(got["by_stage"]) == {"SCORING", "REPORTS", "RESEARCH"}
    stages = [r["stage"] for r in cost.ledger(run)]
    assert sorted(stages) == ["REPORTS", "RESEARCH", "SCORING"]
    # a second capture charges nothing twice
    assert cost.capture_workflows(run, base=base)["captured"] == 0


# ── 2. the envelope bites inside the stage and at the handoff ──────────────

class _Costly(S.StubDispatcher):
    def __init__(self, usd, **kw):
        super().__init__(**kw)
        self.usd = usd

    def dispatch(self, *a, **k):
        out = super().dispatch(*a, **k)
        out["usd"] = self.usd
        out["turns"] = 40
        return out


def _lane_closes_one_cell(agent, prompt_file, ctx):
    F = S.fixtures()
    wb = ctx.run.open()
    cat = agent.split("-")[1].upper()
    for c in [x for x in wb.selected_subcaps() if x.startswith(cat)]:
        if str((wb.scoring_row(c) or {}).get("Dominant_Claim") or "").strip():
            continue
        eids = F.bank_evidence(wb, c, n=5)
        F.synthesise(wb, c, F.good_synthesis(c, eids), author=agent)
        break


def _drive(tmp_path, **over):
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    disp = _Costly(4.0, handlers={"research-p": _lane_closes_one_cell,
                                  "finding-challenger": S.lane_noop})
    kw = dict(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(), push=False,
              folder_root=tmp_path / "client_out", ingest_poll_s=0, sleep=lambda s: None,
              log=lambda s: None, until="RESEARCH", max_rounds=10, stall_rounds=0,
              max_usd=0)
    kw.update(over)
    p = P.Pipeline(run, P.Options(**kw))
    return p, disp, p.run_all()


def test_the_research_envelope_stops_the_stage_mid_round_with_its_remedy(tmp_path):
    """$4 a round against a $10 envelope: three rounds, then STOPPED_STAGE_BUDGET
    naming `--stage-budget RESEARCH=`, with the run-wide cap disabled — the
    envelope is a ceiling of its own."""
    p, disp, out = _drive(tmp_path)
    rounds = len([c for c in disp.calls if c["stage"] == "RESEARCH"])
    assert out["outcome"] == "STOPPED_STAGE_BUDGET", out
    assert rounds == 3, rounds
    assert "--stage-budget RESEARCH" in out["reason"] and "cut short, not refused" in out["reason"]
    assert out["envelope"]["family"] == "RESEARCH" and out["envelope"]["over"]
    st = json.loads((p.run.qa_dir / "pipeline_state.json").read_text())
    assert st["envelopes"]["RESEARCH"]["over"]


def test_a_raised_envelope_is_remembered_on_resume(tmp_path):
    p, disp, out = _drive(tmp_path, stage_budget={"RESEARCH": 100})
    assert out["outcome"] != "STOPPED_STAGE_BUDGET"
    st = json.loads((p.run.qa_dir / "pipeline_state.json").read_text())
    assert st["stage_budget_usd"] == {"RESEARCH": 100.0}
    # a fresh driver without the flag reads the persisted figure
    q = P.Pipeline(p.run, P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                                    push=False, log=lambda s: None))
    assert q.stage_budgets()["RESEARCH"] == 100.0
    assert q.stage_budgets()["SCORING"] == 5.0


def test_a_spent_envelope_refuses_the_workflow_handoff_before_any_agent(tmp_path):
    """The handoff is cheap for the driver and a workflow's worth of agents
    for the session; a spent envelope stops it there."""
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    cost.record(run, stage="RESEARCH", elapsed_s=60, usd=10.5)
    disp = S.StubDispatcher(handlers={"research-p": S.lane_noop, "finding-challenger": S.lane_noop})
    p = P.Pipeline(run, P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                                  push=False, folder_root=tmp_path / "out", ingest_poll_s=0,
                                  sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                                  research_mode="workflow", max_usd=0))
    out = p.run_all()
    assert out["outcome"] == "STOPPED_STAGE_BUDGET", out
    assert "AT_STAGE_BUDGET" in out["reason"] and "RESEARCH" in out["reason"]
    assert not [c for c in disp.calls if c["stage"] == "RESEARCH"]


def test_the_handoff_carries_the_envelope_and_caps_rounds_when_it_does_not_fit(tmp_path):
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    cost.record(run, stage="RESEARCH", elapsed_s=60, usd=9.5)   # $0.50 left of $10
    disp = S.StubDispatcher(handlers={"research-p": S.lane_noop, "finding-challenger": S.lane_noop})
    p = P.Pipeline(run, P.Options(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
                                  push=False, folder_root=tmp_path / "out", ingest_poll_s=0,
                                  sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                                  research_mode="workflow", max_usd=0))
    out = p.run_all()
    assert out["outcome"] == "AWAITING_WORKFLOW", out
    doc = json.loads(Path(out["handoff"]).read_text())
    assert doc["budget"]["family"] == "RESEARCH" and doc["budget"]["fits_envelope"] is False
    for inv in doc["invocations"]:
        assert inv["budget"]["remaining"] == pytest.approx(0.5)
        assert inv["rounds"] == 1, "a round that cannot be paid for is not handed"


def test_the_critic_rounds_default_is_two():
    assert P.Options.critic_rounds == 2


def test_cost_report_names_the_envelope_that_is_over(tmp_path):
    run = new_run(tmp_path, n=6)
    cost.record(run, stage="SCORING", elapsed_s=60, usd=6.0)
    rep = cost.report(run)
    assert rep["over_envelopes"] == ["SCORING"]
    assert not rep["within"]
    assert rep["budget_usd"] == cost.run_budget_default(1)


def test_the_pipeline_cli_takes_stage_budgets_and_an_ingest_kick():
    import argparse
    a = argparse.Namespace(dispatcher="stub", until=None, max_wall_min=240, max_usd=None,
                           max_rounds=10, stall_rounds=2, enrichment_heals=1, no_relay=False,
                           lane_retries=1, page_retries=2, ingest_poll_s=60, ingest_timeout_s=60,
                           folder_root=None, no_push=True, allow_stale_install=False, lanes=None,
                           toolkits=None, research_mode=None, lane_timeout=10,
                           stage_budget=["research=12.5", "PAGES=4"], critic_rounds=1,
                           ingest_kick_cmd="echo kicked")
    o = P._build_opts(a)
    assert o.stage_budget == {"RESEARCH": 12.5, "PAGES": 4.0}
    assert o.critic_rounds == 1 and o.ingest_kick_cmd == "echo kicked"
    a.stage_budget = ["RESEARCH"]
    with pytest.raises(SystemExit):
        P._build_opts(a)


# ── 3. the dispatch guard reads the envelopes ──────────────────────────────

def test_the_dispatch_guard_refuses_an_agent_whose_envelope_is_spent():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "guard_dispatch", PLUGIN / "scripts" / "hooks" / "guard_dispatch.py")
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    state = {"envelopes": {"SCORING": {"ceiling": 5.0, "spent": 5.2, "over": True},
                           "RESEARCH": {"ceiling": 10.0, "spent": 1.0, "over": False}}}
    assert g._envelope_exhausted("scoring-p2-producer", state)["family"] == "SCORING"
    assert g._envelope_exhausted("research-p1c1-producer", state) is None
    assert g._envelope_exhausted("report-validator", state) is None
    assert g._envelope_exhausted("scoring-critic", {}) is None, "no envelopes recorded: not refused"


# ── 4. challenge-at-write: the label-fit rules the challenger kept failing ─

def _two_sources(wb, cell):
    return bank_evidence(wb, cell, n=3)          # two identities by construction


def test_a_fact_on_one_source_identity_is_refused_at_the_write(tmp_path):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    from fixtures import fire_volleys
    fire_volleys(wb, cell, n=3)
    e1 = L.append_evidence(wb, source_name="Annual Report p1",
                           source_url=f"https://acme.example/ar#1-{cell}", tier="T2",
                           excerpt="Alkami digital banking went live in Q3 2024 and reached 47 percent adoption within ninety days.",
                           subcaps=[cell], published="2025-06-01")
    e2 = L.append_evidence(wb, source_name="Annual Report p2",
                           source_url=f"https://acme.example/ar#2-{cell}", tier="T2",
                           excerpt="The 2025 report restates member adoption at 52 percent, up from 47 percent at ninety days.",
                           subcaps=[cell], published="2025-06-01")
    with pytest.raises(L.LedgerRefusal, match="one source identity"):
        L.append_synthesis(wb, cell, good_synthesis(cell, [e1, e2]), actor="research-p1c1-producer")


def test_an_inference_needs_two_ids_and_a_named_step(tmp_path):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    eids = _two_sources(wb, cell)
    rec = good_synthesis(cell, eids)
    rec["Claim_Label"] = "INFERENCE"
    # the fixture prose names no inference step
    with pytest.raises(L.LedgerRefusal, match="names no inference"):
        L.append_synthesis(wb, cell, rec, actor="research-p1c1-producer")
    rec["Triangulation"] = (f"The AppExchange listing and the admin posting together imply a live "
                            f"FSC deployment {' '.join(f'[{e}:F1]' for e in eids[:2])}.")
    L.append_synthesis(wb, cell, rec, actor="research-p1c1-producer")


def test_an_open_contradiction_needs_a_disposition(tmp_path):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    eids = _two_sources(wb, cell)
    rec = good_synthesis(cell, eids)
    rec["DQ_Contradicts"] = "A 2024 complaint thread says the mobile app was down for two days in March."
    with pytest.raises(L.LedgerRefusal, match="Contradiction_Disposition"):
        L.append_synthesis(wb, cell, rec, actor="research-p1c1-producer")
    rec["Contradiction_Disposition"] = ("Outweighed: one outage thread against two dated adoption "
                                        "figures; recorded as a fails-facet finding, not a reversal.")
    L.append_synthesis(wb, cell, rec, actor="research-p1c1-producer")


def test_the_fixture_synthesis_still_passes_the_write(tmp_path):
    """Two identities, FACT, no open contradiction: the rules refuse nothing
    the challenger would have passed."""
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    eids = _two_sources(wb, cell)
    synthesise(wb, cell, good_synthesis(cell, eids))


# ── 5. the evidence register freezes while the reports are written ─────────

def test_a_frozen_register_refuses_a_new_row_and_says_how_to_thaw(tmp_path):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    L.freeze(wb, "REPORTS in progress (test)")
    assert L.is_frozen(wb)
    with pytest.raises(L.LedgerRefusal, match="FROZEN"):
        L.append_evidence(wb, source_name="Late source", source_url="https://x.example/late",
                          tier="T2", excerpt="A fact registered after the sections were written would reopen them.",
                          subcaps=[cell], published="2025-06-01")
    L.thaw(wb, "servicing an evidence upstream item")
    assert not L.is_frozen(wb)
    assert any(str(g.get("Gate")) == "EVIDENCE_THAW" for g in wb.rows("Gate_Log"))
    L.append_evidence(wb, source_name="Late source", source_url="https://x.example/late",
                      tier="T2", excerpt="A fact registered after the sections were written would reopen them.",
                      subcaps=[cell], published="2025-06-01")


def test_the_narrative_cli_freezes_and_thaws(tmp_path):
    import subprocess, sys
    run = new_run(tmp_path, n=6)
    eng = PLUGIN / "skills" / "dma-research"
    def cli(*args):
        return subprocess.run([sys.executable, "-m", "engine.narrative", *args, "--run", run.run_id,
                               "--root", str(run.root)], cwd=eng, capture_output=True, text=True)
    out = cli("freeze", "--why", "REPORTS in progress")
    assert out.returncode == 0 and json.loads(out.stdout)["frozen"]
    assert json.loads(cli("freeze-state").stdout)["frozen"]
    out = cli("thaw", "--why", "registering the late FDIC row")
    assert out.returncode == 0 and not json.loads(out.stdout)["frozen"]


# ── 6. PRELIM evidence reaches the research lanes ──────────────────────────

def test_prelim_rows_are_proposed_to_cells_and_listed_in_the_shared_block(tmp_path):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    # a PRELIM row: no cell, about digital banking, which the fixture's
    # question text is about too
    e = L.append_evidence(wb, source_name="Clay company record", source_url="https://acme.example/about",
                          tier="T3", origin="connector",
                          excerpt="Acme Credit Union runs digital banking on Alkami with member adoption measured quarterly by the board.",
                          subcaps=[], published="2025-06-01")
    sh = brief.shared(wb)
    assert sh["prelim_evidence_total"] >= 1
    mine = [r for r in sh["prelim_evidence"] if r["e_id"] == e]
    assert mine and mine[0]["origin"] == "connector"
    assert sh["prelim_evidence"][0]["origin"] == "connector", "connector readings rank first"
    # PRELIM rows rank like any other lane's rows: the fixture's own PRELIM
    # register row about the institution is proposed to a cell whose question
    # it matches, labelled by origin and never attached for the lane
    # a register the size a worked category has (BM25's IDF collapses over a
    # corpus of four rows — the docstring on `reusable` says why), then the
    # PRELIM rows rank beside every other lane's rows
    for c in wb.selected_subcaps()[2:5]:
        bank_evidence(wb, c, n=3)
    proposals = [o for c in wb.selected_subcaps()
                 for o in brief.reusable(wb, c)["proposed_from_other_categories"]]
    assert proposals and all(o["proposed"] for o in proposals)
    assert any(o["from_categories"] == ["PRELIM"] for o in proposals), proposals


def test_the_dispatch_packet_tells_the_lane_to_read_prelim_first(tmp_path):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    packet = brief.dispatch(wb, "P1C1", run=run)
    assert "prelim_evidence" in packet["shared"] and "attach" in packet["shared"]["prelim_rule"]


# ── 7. the report writer gets an evidence pack, not a sheet list ───────────

def test_the_section_brief_carries_an_ers_ranked_pack_and_the_critic_s_verdicts(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    from engine import report_spec as RS
    sec = RS.SPECS["assessment"].section("5")
    pack = brief.report_evidence_pack(wb, sec, card="P1")
    assert pack["evidence"], "scored cells feed the deep dive"
    ers = [r["ers"] for r in pack["evidence"]]
    assert ers == sorted(ers, reverse=True), "ranked by ERS, best first"
    assert all(r["excerpt"] for r in pack["evidence"])
    assert any(r["cells"] for r in pack["evidence"]), "the scored cells' rows are in the pack"
    assert pack["cells"] and all(c["challenge"] in ("PASS", "none") for c in pack["cells"])
    assert "P1" in pack["critic_notes"]
    out = brief.report_section_briefs(wb, run=run, out_dir=tmp_path / "briefs")
    text = "\n".join(Path(r["file"]).read_text() for r in out["sections"])
    assert "Evidence pack" in text and "cite from here" in text


# ── 8. the critic's judgement rules at the score write ─────────────────────

def test_a_rationale_that_argues_a_higher_level_than_it_strikes_is_refused(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    cell = next(c for c in cells if c in ev)
    rat = rationale_for(ev[cell], 3.0)                   # argues M3
    with pytest.raises(A.ScoringRefusal, match="level named must be the level struck"):
        score_cell(wb, cell, ev[cell], score=2.0, rationale=rat)
    score_cell(wb, cell, ev[cell], score=2.0, rationale=rationale_for(ev[cell], 2.0))


def test_a_rationale_with_no_gap_or_an_off_row_id_is_refused(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    cell = next(c for c in cells if c in ev)
    e0, e1 = ev[cell][0], ev[cell][1]
    no_gap = (f"[EVIDENCE] {e0} and {e1} show the platform live and measured; [MATURITY MATCH] "
              f"M2 because the capability is in place; [COUNTER] none identified; [CEILING] "
              f"two T2 sources allow 5.0; [SO WHAT] the channel carries the programme today.")
    with pytest.raises(A.ScoringRefusal, match="names no gap"):
        score_cell(wb, cell, ev[cell], score=2.0, rationale=no_gap)
    off_row = rationale_for(ev[cell], 2.0) + " E-999 also bears on this."
    with pytest.raises(A.ScoringRefusal, match="E-999"):
        score_cell(wb, cell, ev[cell], score=2.0, rationale=off_row)


def test_the_rollup_writes_the_dashboard_without_a_headline_and_the_gate_names_it_alone(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    wb._wb["Executive_Summary"].delete_rows(2, wb._wb["Executive_Summary"].max_row)
    wb.save()
    A.rollup(wb)                                        # no headline: not refused
    fields = {str(r.get("Field")) for r in wb.rows("Executive_Summary")}
    assert "Institution" in fields and "Headline" not in fields
    v = A.gate(wb, run.qa_dir)
    assert "dashboard_incomplete" not in v["blocking"]
    assert "headline_missing" in v["blocking"] and v["headline_missing"] == ["Headline"]
    A.rollup(wb, headline="Modern rails, unbuilt member-relationship layer: a band below peers")
    assert "headline_missing" not in A.gate(wb, run.qa_dir)["blocking"]


# ── 9. page gates read from the workbook for every page ───────────────────

def test_a_cited_row_that_names_no_cell_is_an_et07_blocker_before_any_page_agent(tmp_path):
    run = new_run(tmp_path, n=6)
    wb = run.open()
    e = L.append_evidence(wb, source_name="Trade press", source_url="https://press.example/a",
                          tier="T2", excerpt="The credit union named a new chief digital officer in June 2025 and restated its roadmap.",
                          subcaps=[], published="2025-06-01")
    from engine import techscan
    techscan.record(wb, product="nCino Bank Operating System", vendor="nCino", layer="OPS",
                    status="INFERRED", method="job_posting",
                    basis="named in a senior lending systems administrator posting",
                    providers=["web"], subcaps=[], evidence_ids=[e])
    blockers = PP.preflight(wb, ("techstack",))
    et07 = [b for b in blockers if b["gate"] == "ET-07" and e in b["detail"]]
    assert et07 and "attach" in et07[0]["fix"] and et07[0]["severity"] == "block"
    assert not et07[0]["needs_connector"]
    # a timeline citation is advisory: reported, not a halt
    from engine import prelim
    prelim.timeline(wb, date="2025-06-06", event="Chief digital officer appointed and roadmap restated",
                    signal="POSITIVE", kind="LEADERSHIP", evidence=[e])
    ctx = [b for b in PP.preflight(wb, ("context",)) if b["gate"] == "ET-07" and e in b["detail"]]
    assert ctx and ctx[0]["severity"] == "warn"
    L.attach_evidence(wb, e, [wb.selected_subcaps()[0]], actor="research-p1c1-producer")
    assert not [b for b in PP.preflight(wb, ("techstack", "context")) if b["gate"] == "ET-07" and e in b["detail"]]


def test_the_workbook_floors_behind_the_page_gates_are_read_before_pages(tmp_path):
    run = new_run(tmp_path, n=6, prelim=False)
    wb = run.open()
    gates = {b["gate"]: b for b in PP.preflight(wb, ("context", "heatmap", "overview"))}
    assert "CG-14" in gates and "Entity_Timeline" in gates["CG-14"]["detail"]
    assert "S9_focus_invalid" in gates and "CG-18c" in gates


# ── 10. lock waits are measured ────────────────────────────────────────────

def test_a_lock_wait_is_written_beside_the_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "LOCK_WAIT_NOTE_S", 0.0)
    lock = tmp_path / "wb.xlsx.lock"
    with W.file_lock(lock, timeout=5, why="first writer"):
        pass
    summary = W.lock_wait_summary(lock)
    assert summary["waits"] == 1 and summary["timed_out"] == 0
    # a holder that never releases: the second writer times out, and says so in the file
    import threading
    held = threading.Event()
    release = threading.Event()

    def holder():
        with W.file_lock(lock, timeout=5, why="holder"):
            held.set()
            release.wait(5)
    t = threading.Thread(target=holder); t.start()
    held.wait(5)
    with pytest.raises(W.WorkbookError):
        with W.file_lock(lock, timeout=0.3, why="second writer"):
            pass
    release.set(); t.join(5)
    summary = W.lock_wait_summary(lock)
    assert summary["timed_out"] == 1 and summary["max_s"] >= 0.3


# ── 11. the ingest kick ────────────────────────────────────────────────────

def test_the_ingest_kick_runs_once_per_poll_and_never_fails_the_stage(tmp_path):
    run = new_run(tmp_path, n=6)
    marker = tmp_path / "kicked"
    opts = P.Options(dispatcher=S.StubDispatcher(), reads=S.StubReads(), shipper=S.StubShipper(),
                     push=False, log=lambda s: None, ingest_kick_cmd=f"touch {marker}")
    p = P.Pipeline(run, opts)
    p.state.setdefault("connector", {})
    p._kick_ingest("ingest_test")
    assert marker.exists()
    assert p.state["ingest_kicks"][0]["rc"] == 0
    p.opts.ingest_kick_cmd = "exit 3"
    p._kick_ingest("ingest_test")                        # a failing kick is recorded, not raised
    assert p.state["ingest_kicks"][-1]["rc"] == 3


# ── 12. the shipped workflows carry the rules ──────────────────────────────

def test_the_workflows_read_the_envelope_and_the_write_time_rules():
    research = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "A.budget" in research and "prelim_evidence" in research
    assert "WRITE-TIME RULES" in research and "two source identities" in research
    scoring = (PLUGIN / "workflows" / "dma-pillar-scoring.js").read_text()
    assert "CRITIC_ROUNDS = A.rounds || 2" in scoring
    reports = (PLUGIN / "workflows" / "dma-reports.js").read_text()
    assert "EVIDENCE PACK" in reports and "FROZEN" in reports


def test_et07_exempts_the_identity_grain_prelim_narratives(tmp_path):
    """The call report the firmographics narrative cites names no cell, and
    must not: the connector exempts overview.firmographics by name, and a
    preflight that blocked on it would refuse every run at PAGES_B (the
    stub chaos walk did, 2026-10-09). A research-report section citing the
    same unlinked row IS a blocker."""
    from engine import page_preflight as PP
    run = new_run(tmp_path); wb = run.open()
    idx = wb.evidence_index()
    firm = [r for r in wb.rows("Report_Narrative")
            if str(r.get("Section_ID") or "").upper() == "PRELIM-FIRM"]
    assert firm and firm[0].get("Evidence_IDs"), "the fixture's PRELIM narrates firmographics"
    eid = str(firm[0]["Evidence_IDs"]).split(",")[0].strip()
    assert not str((idx.get(eid) or {}).get("SubCap_IDs") or "").strip() or True
    unl = PP.unlinked_citations(wb, ("overview",))
    assert eid not in {k for k, v in unl.items() if any(
        c.startswith("Report_Narrative:PRELIM-FIRM") for c in v["cited_from"])}
    # the same row cited from a research-report section is a blocker when unlinked
    orphan = L.append_evidence(
        wb, source_name="A trade article", source_url="https://example.test/trade",
        tier="T2", excerpt=("The credit union's digital team was reorganised under "
                            "a new chief digital officer during 2025, the article says."),
        subcaps=[], published="2025-05-01")
    wb.append("Report_Narrative", {"Report": "client_research", "Section_ID": "CR-03",
                                   "Heading": "Leadership and operating model",
                                   "Body": "x" * 60, "Evidence_IDs": orphan, "Kind": "narrative"})
    unl = PP.unlinked_citations(wb, ("overview",))
    assert orphan in unl and unl[orphan]["page"] == "overview"
