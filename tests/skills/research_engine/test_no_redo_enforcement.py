"""Nothing already done is done again unless something changed — enforced
by the engine, not by prompt text.

Owner, 2026-10-07: "a lot of issues on redoing research, redoing scoring,
synthesis, critics, page production leading to a lot of token consumption.
Ensure the entire flow is enforced and predictable such that the level of
repetition reduces unless totally necessary."

Each test below is a redo path the audit measured on the live runs, written
so that it FAILS on the engine before the fix:

  * an unchanged synthesis cleared its challenge verdict (a paid second
    challenge of the same prose; under a FAIL, the loop itself);
  * a category's concurrent capability batches shared one 60-op search
    window, so the later ones were refused mid-capability and closed nothing;
  * the gate's open cells were routed to a capability batch AND a repair
    batch — two agents on the same cells;
  * research had no handoff ceiling: a category that closed one blocker a
    round could be handed ten, twenty times;
  * a re-score at the value the row already held wrote Provenance (and
    disqualified its actor from critiquing);
  * a re-critique drew a fresh sample every round, so SCORING never closed;
  * an identical report rewrite cleared the validator's verdict;
  * the REPORTS stall signature carried review timestamps, so it never fired;
  * a page repair brief trimmed the verdict's reasons from 12 to 3;
  * nothing recorded that a session had STARTED a handoff's workflows, so
    the watchdog and the Stop hook asked for them again.
"""
from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from engine import assessment as A, brief, floors_gate as F, ledger as L
from engine import narrative as N, pipeline as P, pipeline_stub as S, runstate, watchdog as W
from fixtures import (bank_evidence, challenge, fire_volleys, good_synthesis, new_run,
                      preflight_doc, score_cell, scored_run, section_record,
                      two_category_selection)

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
AUTHOR = "research-p1c1-producer"


def _hook(name: str):
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN / "scripts" / "hooks" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── synthesis: unchanged text keeps its verdict ───────────────────────────

def _synthesised(tmp_path):
    run = new_run(tmp_path, n=3, prelim=False)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    eids = bank_evidence(wb, cell)
    fire_volleys(wb, cell)
    rec = good_synthesis(cell, eids)
    L.append_synthesis(wb, cell, rec, actor=AUTHOR)
    return run, wb, cell, eids, rec


def test_an_unchanged_synthesis_keeps_its_pass_and_is_not_rechallenged(tmp_path):
    run, wb, cell, eids, rec = _synthesised(tmp_path)
    challenge(wb, cell, verdict="PASS")
    prov = len([r for r in wb.rows("Provenance") if r.get("Step") == "synthesis"])
    out = L.append_synthesis(wb, cell, dict(rec), actor=AUTHOR)
    assert out["unchanged"] and out["verdict_kept"] == "PASS"
    assert wb.scoring_row(cell)["Challenge_Verdict"] == "PASS"
    assert len([r for r in wb.rows("Provenance") if r.get("Step") == "synthesis"]) == prov
    cb = brief.challenge_batch(wb, run=run, out_dir=tmp_path / "cb")
    assert cell not in json.dumps([json.loads(Path(b["prompt_file"].replace(".md", ".json"))
                                              .read_text()) for b in cb.get("briefs") or []])


def test_new_evidence_on_the_row_makes_the_same_text_a_changed_synthesis(tmp_path):
    run, wb, cell, eids, rec = _synthesised(tmp_path)
    challenge(wb, cell, verdict="FAIL")
    with pytest.raises(L.LedgerRefusal, match="identical"):
        L.append_synthesis(wb, cell, dict(rec), actor=AUTHOR)
    # the counter-source the challenger asked for lands on the row …
    L.append_evidence(wb, source_name="State regulator exam summary 2025",
                      source_url=f"https://regulator.example/exam/2025#{cell}", tier="T1",
                      excerpt=("The 2025 examination summary records the digital banking "
                               "programme's governance cadence and its quarterly board review."),
                      subcaps=[cell], published="2025-09-01")
    # … and the same text, now resting on more evidence, is a different synthesis
    out = L.append_synthesis(wb, cell, dict(rec), actor=AUTHOR)
    assert not out.get("unchanged")
    assert not str(wb.scoring_row(cell).get("Challenge_Verdict") or "").strip()


def test_the_signature_is_stable_and_blind_to_the_verdict_field():
    rec = {"Dominant_Claim": "x", "What_We_Found": "y", "Challenge_Verdict": "PASS"}
    row = {"Evidence_IDs": "E-002:F1, E-001"}
    a = L.synthesis_signature(rec, row)
    assert a == L.synthesis_signature({**rec, "Challenge_Verdict": ""},
                                      {"Evidence_IDs": "E-001, E-002:F2"})
    assert a != L.synthesis_signature({**rec, "What_We_Found": "y."}, row)
    assert a != L.synthesis_signature(rec, {"Evidence_IDs": "E-001"})


# ── the search window is sized for the batches that share it ─────────────

def _log(wb, cell, i):
    return L.append_search(wb, subcap=cell, facet="works", tool="web_search",
                           query=f'"Acme Credit Union" {cell} probe {i}', hits=1, kept=1)


def test_a_category_window_opened_for_several_batches_is_not_walled_at_sixty(tmp_path):
    run = new_run(tmp_path, n=2, prelim=False)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    cat = cell.split(".")[0]
    runstate.checkpoint(wb, "one conversation", scope=[cat])
    assert L.window_cap(wb, cat) == L.SEARCH_OP_CEILING
    for i in range(L.SEARCH_OP_CEILING):
        _log(wb, cell, i)
    with pytest.raises(L.LedgerRefusal, match="search-op ceiling"):
        _log(wb, cell, 999)
    # the driver opens the window for three batches of this category
    runstate.checkpoint(wb, "RESEARCH workflow handoff", scope=[cat],
                        cap=L.SEARCH_OP_CEILING * 3)
    assert L.window_cap(wb, cat) == 3 * L.SEARCH_OP_CEILING
    st = L.stats(wb, cat)
    assert st["search_op_ceiling"] == 3 * L.SEARCH_OP_CEILING and not st["checkpoint_required"]
    for i in range(1000, 1000 + L.SEARCH_OP_CEILING):
        _log(wb, cell, i)                                  # a second batch's searches
    # an agent's own checkpoint mid-round keeps the recorded capacity
    runstate.checkpoint(wb, "agent re-opened its window", scope=[cat])
    assert L.window_cap(wb, cat) == 3 * L.SEARCH_OP_CEILING


# ── the research handoff: disjoint work, a sized window, a ceiling ───────

def _drive(tmp_path, **over):
    run = new_run(tmp_path, selected=two_category_selection(3))
    from engine import preflight
    preflight.record(run, preflight_doc())
    disp = S.StubDispatcher(handlers={"research-p": S.lane_noop,
                                      "finding-challenger": S.lane_noop})
    kw = dict(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
              push=False, folder_root=tmp_path / "client_out", ingest_poll_s=0,
              sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
              max_rounds=2, stall_rounds=0, research_mode="workflow")
    kw.update(over)
    opts = P.Options(**kw)
    p = P.Pipeline(run, opts)
    return p, p.run_all()


def _fail_gate(p, cat, cells, term="single_source_fact"):
    doc = {"category": cat, "gate": "FAIL", "blocking": [term], "advisory": [],
           term: [{"subcap": c, "distinct_sources": ["example.com"]} for c in cells]}
    (p.run.qa_dir / f"floors_{cat}.json").write_text(json.dumps(doc))
    return doc


def test_an_open_cell_is_the_batchs_work_and_never_a_repairs(tmp_path):
    p, out = _drive(tmp_path)
    assert out["outcome"] == "AWAITING_WORKFLOW"
    cat = out["invocations"][0]["cats"][0]
    open_cell, closed = f"{cat}.1.1", f"{cat}.1.2"
    wb = p.run.open()
    eids = bank_evidence(wb, closed)
    L.append_synthesis(wb, closed, good_synthesis(closed, eids), actor=f"research-{cat.lower()}-producer")
    _fail_gate(p, cat, [open_cell, closed])
    h = P.Pipeline(p.run, p.opts)._research_handoff()
    inv = next(i for i in h["invocations"] if cat in i["cats"])
    assert inv["repairs"][cat] == {closed: ["single_source_fact"]}, inv["repairs"]
    assert inv["repair_batches"][cat] == [[closed]]
    # the open cell still rides in its capability batch
    assert any(open_cell.rsplit(".", 1)[0] in b for b in inv["batches"][cat])
    # the same split is what the workflow's round-2 repair agent reads
    doc = F.read_verdict(p.run.qa_dir, cat)
    assert F.repair_cells(doc, wb, include_open=False) == {closed: ["single_source_fact"]}
    assert set(F.repair_cells(doc, wb, include_open=True)) == {open_cell, closed}
    cli = subprocess.run(["python3", "-m", "engine.floors_gate", "--run", p.run.run_id,
                          "--root", str(p.run.root), "--category", cat, "--repair-cells"],
                         capture_output=True, text=True,
                         cwd=str(PLUGIN / "skills" / "dma-research"))
    assert cli.returncode == 0, cli.stderr[-400:]
    assert json.loads(cli.stdout) == {closed: ["single_source_fact"]}


def test_the_handoff_opens_each_categorys_window_sized_for_its_batches(tmp_path):
    p, out = _drive(tmp_path)
    wb = p.run.open()
    for inv in out["invocations"]:
        for cat in inv["cats"]:
            units = len(inv["batches"][cat]) + len(inv["repair_batches"][cat])
            assert units >= 1
            assert L.window_cap(wb, cat) == L.SEARCH_OP_CEILING * units * P.WORKFLOW_ROUNDS
            assert inv["rounds"] == P.WORKFLOW_ROUNDS
    doc = json.loads(Path(out["handoff"]).read_text())
    assert "resumeFromRunId" in doc["how"]


def test_a_category_is_not_handed_past_the_round_ceiling(tmp_path):
    p, out = _drive(tmp_path, max_rounds=2, stall_rounds=0)
    cat = out["invocations"][0]["cats"][0]
    wb = p.run.open()
    cells = [f"{cat}.1.1", f"{cat}.1.2", f"{cat}.1.3"]
    for c in cells:
        eids = bank_evidence(wb, c)
        L.append_synthesis(wb, c, good_synthesis(c, eids), actor=f"research-{cat.lower()}-producer")
    _fail_gate(p, cat, cells)
    logs: list[str] = []
    p.opts.log = logs.append
    P.Pipeline(p.run, p.opts)._research_handoff()                 # seeds the book
    # every round MOVES (one blocker closed) — the stall rule never fires,
    # and before the ceiling this category was handed again forever
    for spent, left in ((5.0, cells[1:]), (10.0, cells[2:])):
        _fail_gate(p, cat, left)
        q = P.Pipeline(p.run, p.opts)
        q._spent_usd = spent
        h = q._research_handoff()
    assert cat in h["stalled"], h
    assert any("max-rounds" in line for line in logs), logs[-3:]
    # --reset-guard is the person's "allow more"
    p.opts.reset_guard = True
    q = P.Pipeline(p.run, p.opts)
    q._spent_usd = 15.0
    assert cat not in q._research_handoff()["stalled"]


# ── scoring: idempotent re-scores, a converging critic ───────────────────

def test_an_identical_rescore_writes_nothing(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    cell = next(c for c in cells if ev.get(c))
    row = wb.scoring_row(cell)
    before = len([r for r in wb.rows("Provenance") if r.get("Step") == "score"])
    out = score_cell(wb, cell, ev[cell], score=float(row["Score"]),
                     confidence=str(row["Confidence"]), rationale=str(row["Rationale"]))
    assert out["unchanged"]
    assert len([r for r in wb.rows("Provenance") if r.get("Step") == "score"]) == before
    # a different value is a score
    out = score_cell(wb, cell, ev[cell], score=float(row["Score"]) - 0.25,
                     confidence=str(row["Confidence"]), rationale=str(row["Rationale"]))
    assert not out.get("unchanged")
    assert len([r for r in wb.rows("Provenance") if r.get("Step") == "score"]) == before + 1


def test_a_recritique_after_a_fail_judges_the_rows_that_moved(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    a, b, c = [x for x in cells if ev.get(x)][:3]
    note = ("Re-derived every P1 row against its rubric descriptor; one row "
            "flatters its evidence: it reads M3 on one T3 source only.")
    # the fixture's critic PASSED; a deliberate re-open draws any sample
    A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic", note=note,
               moves=[f"{a}:1.75:reads M3 on one T3 source"])
    score_cell(wb, a, ev[a], score=1.75)                     # the scorer applies it
    # the re-critique may not pull a fresh row nobody touched …
    with pytest.raises(A.ScoringRefusal, match="did not move before"):
        A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic", note=note,
                   moves=[f"{b}:1.75:now this one flatters"])
    assert b not in A.critic_moves(wb)
    # … but it may move the row it moved (further) and a row re-scored since
    score_cell(wb, c, ev[c], score=2.0)
    out = A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic", note=note,
                     moves=[f"{a}:1.5:still flatters", f"{c}:1.75:re-struck too high"])
    assert out["moves"] == 2 and a in A.critic_moves(wb) and c in A.critic_moves(wb)
    # … and a widened sample is allowed when its reason is on the record
    out = A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic", note=note,
                     moves=[f"{b}:1.75:now this one flatters"],
                     widen="the round-1 pass read the T3 descriptor as T2 across this capability")
    last = [g for g in wb.rows("Gate_Log") if g.get("Gate") == "SCORING_CRITIC"][-1]
    assert "[WIDENED:" in str(last.get("Detail"))
    # a PASS closes the pillar and withdraws every move
    A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-critic",
               note="Re-derived the three moved rows again against their rubric descriptors "
                    "and the counter-sources; every score now holds at or below its target.")
    assert not [k for k in A.critic_moves(wb) if k.startswith("P1")]


# ── reports: an identical rewrite is not a rewrite ───────────────────────

_NOTE = ("Checked both citations against the register and the sheet totals. "
         "1. Name the fiscal year of the adoption figure. "
         "2. State which statement the revenue line comes from.")


def _written(tmp_path, monkeypatch):
    from engine import brief as B
    monkeypatch.setattr(B, "report_preflight", lambda wb, run=None: [])
    run, wb, cells, ev = scored_run(tmp_path, n=6)
    eids = list(ev[cells[0]])
    rec = section_record("1", eids, report="client_research")
    N.write(wb, "client_research", "1", rec, actor="report-research-producer")
    return run, wb, rec


def test_an_identical_rewrite_under_revise_is_refused_and_a_changed_one_clears(tmp_path, monkeypatch):
    run, wb, rec = _written(tmp_path, monkeypatch)
    N.review(wb, "client_research", "1", verdict="REVISE", actor="report-validator",
             dimensions={d: "PASS" for d in N.REVIEW_DIMENSIONS}, note=_NOTE)
    with pytest.raises(N.NarrativeRefusal, match="identical"):
        N.write(wb, "client_research", "1", dict(rec), actor="report-research-producer")
    assert N.rows_for(wb, "client_research")["1"]["Review_Verdict"] == "REVISE"
    changed = dict(rec)
    changed["Body"] = rec["Body"] + " The adoption figure is the 2025 fiscal year's."
    out = N.write(wb, "client_research", "1", changed, actor="report-research-producer")
    assert not out.get("unchanged")
    assert not str(N.rows_for(wb, "client_research")["1"]["Review_Verdict"]).strip()


def test_the_writers_brief_carries_the_current_text_to_edit(tmp_path, monkeypatch):
    run, wb, rec = _written(tmp_path, monkeypatch)
    N.review(wb, "client_research", "1", verdict="REVISE", actor="report-validator",
             dimensions={d: "PASS" for d in N.REVIEW_DIMENSIONS}, note=_NOTE)
    b = brief.report_section_briefs(wb, run=run, out_dir=tmp_path / "rb")
    row = next(r for r in b["sections"] if r["report"] == "client_research" and r["section"] == "1")
    text = Path(row["file"]).read_text()
    assert "EDIT IT IN PLACE" in text
    assert rec["Body"][:120] in text
    assert "1. Name the fiscal year" in text


def test_the_reports_stall_guard_measures_fixes_not_review_timestamps(tmp_path, monkeypatch):
    run, wb, rec = _written(tmp_path, monkeypatch)
    opts = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False, folder_root=tmp_path / "out",
                     ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None,
                     report_mode="workflow", stall_rounds=1)
    N.review(wb, "client_research", "1", verdict="REVISE", actor="report-validator",
             dimensions={d: "PASS" for d in N.REVIEW_DIMENSIONS}, note=_NOTE)
    P.Pipeline(run, opts)._reports_handoff()
    # a round that re-reviewed the section with the SAME two fixes is no movement,
    # whatever its timestamp says
    N.review(wb, "client_research", "1", verdict="REVISE", actor="report-validator",
             dimensions={d: "PASS" for d in N.REVIEW_DIMENSIONS}, note=_NOTE)
    with pytest.raises(P.StageRefused, match="same work"):
        P.Pipeline(run, opts)._reports_handoff()
    # one fix fewer IS movement, and it releases the stall
    N.review(wb, "client_research", "1", verdict="REVISE", actor="report-validator",
             dimensions={d: "PASS" for d in N.REVIEW_DIMENSIONS},
             note="Checked both citations against the register and the sheet totals. "
                  "1. State which statement the revenue line comes from.")
    h = P.Pipeline(run, opts)._reports_handoff()
    assert h["invocations"]


def test_note_fixes_counts_numbered_items_only():
    assert P._note_fixes("1. a\n2) b\n(3) c\n- [ ] d") == 4
    assert P._note_fixes("Checked the totals. 1. Name the year. 2. Cite the statement.") == 2
    assert P._note_fixes("scored 2.0 against M3. The row holds.") == 0
    assert P._note_fixes("") == 0 and P._note_fixes(None) == 0


# ── pages: the verdict's reasons are the point of a repair brief ─────────

def test_a_page_repair_brief_keeps_every_verdict_reason(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    contracts = tmp_path / "contracts"
    contracts.mkdir()
    reads = S.StubReads()
    (contracts / "techstack.json").write_text(json.dumps(reads.page_contract("techstack")))
    verdicts = tmp_path / "verdicts_A.json"
    reasons = [f"CG-{n:02d} at techstack.techstack.items[{n}].status: a long reason "
               f"that names the gate, the JSON path and the arithmetic it failed on"
               for n in range(12)]
    verdicts.write_text(json.dumps({"techstack": reasons}))
    b = brief.page_batch(wb, run=run, out_dir=tmp_path / "pb", connector_run="run-1",
                         contract_file=contracts, verdicts_file=verdicts,
                         pages=["techstack"], phase="assemble", sections_dir=tmp_path / "secs")
    rows = json.loads(Path(b["batch"]).read_text())
    packet = json.loads(Path(rows[0]["prompt_file"].replace(".md", ".json")).read_text())
    assert len(packet["last_verdict_reasons"]) == 12, packet.get("trimmed")


# ── a started workflow is running until it returns ───────────────────────

def _inflight_event(hook: str, run, cat: str, response=None):
    ev = {"hook_event_name": hook, "tool_name": "Workflow",
          "tool_input": {"scriptPath": str(PLUGIN / "workflows" / "dma-pillar-research.js"),
                         "args": {"run": run.run_id, "root": str(run.root), "pillar": cat[:2],
                                  "cats": [cat], "batches": {cat: [["x"]]}}}}
    if response is not None:
        ev["tool_response"] = response
    return ev


def test_a_recorded_workflow_reads_as_running_and_the_driver_waits(tmp_path, monkeypatch):
    p, out = _drive(tmp_path)
    cat = out["invocations"][0]["cats"][0]
    hook = _hook("workflow_inflight")
    assert hook.duplicate_start(_inflight_event("PreToolUse", p.run, cat)) == ""
    assert hook.record(_inflight_event("PreToolUse", p.run, cat))["label"] == f"RESEARCH {cat}"
    e = hook.record(_inflight_event("PostToolUse", p.run, cat,
                                    response={"text": "started wf_7c1d9a-research"}))
    assert e["workflow_run_id"] == "wf_7c1d9a-research" and "resumeFromRunId" in e["resume"]
    # THE SECOND START IS DENIED AT THE TOOL — the double dispatch itself
    why = hook.duplicate_start(_inflight_event("PreToolUse", p.run, cat))
    assert "already started" in why and "wf_7c1d9a-research" in why
    resume = _inflight_event("PreToolUse", p.run, cat)
    resume["tool_input"]["resumeFromRunId"] = "wf_7c1d9a-research"
    assert hook.duplicate_start(resume) == ""                 # a resume is not a second start
    monkeypatch.setenv("DMA_WORKFLOW_RESTART", "1")
    assert hook.duplicate_start(_inflight_event("PreToolUse", p.run, cat)) == ""
    monkeypatch.delenv("DMA_WORKFLOW_RESTART")
    # its transcripts are being written on this machine: RUNNING, whatever
    # the workbook's write age says
    base = tmp_path / "projects"
    tdir = base / "proj" / "sess" / "subagents" / "workflows" / "wf_7c1d9a-research"
    tdir.mkdir(parents=True)
    (tdir / "agent-1.jsonl").write_text("{}\n")
    monkeypatch.setattr(W, "WORKFLOW_TRANSCRIPTS", base)
    row = W.inspect(p.run, stall_seconds=-1)
    assert row["state"] == "WORKFLOW_RUNNING", row["detail"]
    assert row["inflight"][0]["workflow_run_id"] == "wf_7c1d9a-research"
    out2 = P.Pipeline(p.run, p.opts).run_all()
    assert out2["outcome"] == "WORKFLOW_RUNNING", out2
    # the Stop hook's gap nudge stays quiet while workflows run
    sa = _hook("stage_advance")
    assert sa._gaps_blocker({"state": "WORKFLOW_RUNNING"}) == ""
    assert sa._gaps_blocker({"state": "AWAITING_WORKFLOW"}) == ""
    # the transcripts went quiet: it returned (or died) — `then` drives on and
    # forgets the record, and the same workflow may be started again
    monkeypatch.setattr(W, "RUNNING_SECONDS", -1)
    out3 = P.Pipeline(p.run, p.opts).run_all()
    assert out3["outcome"] == "AWAITING_WORKFLOW", out3
    assert W.inflight(p.run) == []
    assert hook.duplicate_start(_inflight_event("PreToolUse", p.run, cat)) == ""


def test_a_record_with_no_transcript_here_is_believed_until_the_driver_runs(tmp_path, monkeypatch):
    """The hourly Routine runs in another container: no transcript to read,
    so a fresh record is a running workflow — and a driver run (the `then`
    a session issues when its workflows return) forgets it."""
    p, out = _drive(tmp_path)
    cat = out["invocations"][0]["cats"][0]
    hook = _hook("workflow_inflight")
    hook.record(_inflight_event("PreToolUse", p.run, cat))
    monkeypatch.setattr(W, "WORKFLOW_TRANSCRIPTS", tmp_path / "nowhere")
    assert W.inspect(p.run, stall_seconds=-1)["state"] == "WORKFLOW_RUNNING"
    out2 = P.Pipeline(p.run, p.opts).run_all()
    assert out2["outcome"] == "AWAITING_WORKFLOW", out2    # `then`: not refused
    assert W.inflight(p.run) == []


def test_a_stale_record_is_not_believed_but_is_offered_as_a_resume(tmp_path):
    p, out = _drive(tmp_path)
    f = p.run.qa_dir / W.INFLIGHT_NAME
    old = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=9)).strftime("%Y-%m-%dT%H:%M:%SZ")
    f.write_text(json.dumps({"workflows": {"k": {
        "started_at": old, "label": "RESEARCH P1C1", "workflow_run_id": "wf_old1234",
        "resume": "Workflow({resumeFromRunId: \"wf_old1234\", scriptPath: \"x\", args: <the same args>})"}}}))
    assert W.inflight(p.run) == []
    row = W.inspect(p.run, stall_seconds=-1)
    assert row["state"] == "AWAITING_WORKFLOW"
    # the Stop hook prints the handoff's calls AND says the old one is resumed, not restarted
    text = _hook("stage_advance").next_step(row)
    assert "Workflow({scriptPath:" in text
    assert "ALREADY STARTED RESEARCH P1C1" in text and "wf_old1234" in text


def test_section_files_count_as_activity_for_a_page_workflow(tmp_path):
    p, out = _drive(tmp_path)
    secs = p.run.root / "08_sections"
    secs.mkdir(exist_ok=True)
    (secs / "overview.scores.json").write_text("{}")
    assert W.activity_age(p.run, {"last_written_at": "2020-01-01T00:00:00Z"}) < 60


def test_the_hooks_manifest_binds_the_inflight_hook_on_both_workflow_events():
    doc = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    for event in ("PreToolUse", "PostToolUse"):
        hit = [e for e in doc[event] if e.get("matcher") == "Workflow"
               and "workflow_inflight.py" in e["hooks"][0]["command"]]
        assert hit, f"{event}: no Workflow hook"


# ── the rendered prompts carry the same rules as the workflow ────────────

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed here")
def test_the_rendered_research_prompts_route_repairs_through_repair_cells(tmp_path):
    p, out = _drive(tmp_path)
    out_dir = tmp_path / "rendered"
    r = subprocess.run(["node", str(PLUGIN / "workflows" / "render-prompts.mjs"),
                        out["handoff"], str(out_dir)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-400:]
    texts = "\n".join(f.read_text() for f in out_dir.glob("*.md"))
    assert "Do NOT run engine.cli checkpoint at start" in texts
    assert "engine.cli checkpoint" in texts                 # still named, for the refusal case
    src = (PLUGIN / "workflows" / "dma-pillar-research.js").read_text()
    assert "--repair-cells" in src and "--include-open" in src
    assert "identical to the text the challenger FAILED" in src


def test_an_unchanged_card_under_revise_is_a_noop_not_a_refusal(tmp_path, monkeypatch):
    """The validator's REVISE covers the whole list and its note names the
    cards to change: a card it did not name is re-sent unchanged beside the
    ones that did, and must not be refused."""
    from engine import report_spec as RS
    from engine import brief as B
    monkeypatch.setattr(B, "report_preflight", lambda wb, run=None: [])
    run, wb, cells, ev = scored_run(tmp_path, n=6)
    eids = list(ev[cells[0]])
    report, sec = next((k, s) for k, spec in RS.SPECS.items() for s in spec.sections
                       if s.is_card and s.kind != "pillar")
    actor = "report-research-producer" if report == "client_research" else "report-assessment-producer"
    rec = section_record(sec.id, eids, report=report)
    cards = [f"{sec.card_prefix}{i + 1:02d}" for i in range(N.card_floor_for(wb, sec))]
    for c in cards:
        N.write(wb, report, sec.id, rec, actor=actor, card=c)
    N.review(wb, report, sec.id, verdict="REVISE", actor="report-validator",
             dimensions={d: "PASS" for d in N.REVIEW_DIMENSIONS},
             note=(f"Opened every citation against the register and the sheet totals. "
                   f"1. {cards[0]}: name the fiscal year of its adoption figure."))
    out = N.write(wb, report, sec.id, rec, actor=actor, card=cards[-1])   # a card the note did not name
    assert out["unchanged"] and out["verdict_kept"] == "REVISE"
    changed = dict(rec)
    changed["Body"] = rec["Body"] + " The figure is the 2025 fiscal year's."
    out = N.write(wb, report, sec.id, changed, actor=actor, card=cards[0])
    assert not out.get("unchanged")
    st = N.state(wb, report)["reports"][report]
    row = next(x for x in st["sections"] if str(x.get("id") or x.get("section")) == str(sec.id))
    assert row["status"] == "UNREVIEWED"                   # the named card changed: re-review
