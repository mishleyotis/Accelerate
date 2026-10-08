"""The scoring critic's mechanical rules are enforced where the score is
written, and its moves are routed back to the scorers.

Measured 2026-10-05 (Susser Bank): SCORING took 294 minutes over seven
critic rounds. Every FAIL was mechanical (a score above the row's own
Ceiling_Band, above 2.0 on own-site-only evidence, a stale row without
ADJ_STALE or still at MEDIUM confidence), and the critic's moves lived only
in Gate_Log prose, so it named the same rows four rounds running.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import assessment as A, brief, ledger as L
from fixtures import researched_run, score_cell, scored_run


def _open(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    if A.C.stage_of(wb.metadata()) != "assessment":
        A.open_stage(wb, run.qa_dir)
    cell = next(c for c in cells if ev.get(c))
    return run, wb, cells, ev, cell


def test_a_score_above_the_rows_own_band_is_refused(tmp_path):
    run, wb, cells, ev, cell = _open(tmp_path)
    wb.set_scoring(cell, {"Ceiling_Band": "Activating"})
    with pytest.raises(A.ScoringRefusal, match="CAP-BAND"):
        score_cell(wb, cell, ev[cell], score=2.0)
    assert score_cell(wb, cell, ev[cell], score=1.75)["score"] == 1.75


def test_own_site_only_evidence_caps_at_two(tmp_path):
    run, wb, cells, ev, cell = _open(tmp_path)
    own = [L.append_evidence(
        wb, source_name="Acme product page", source_url=f"https://www.acme.example/p/{cell}",
        tier="T2", excerpt=("Acme's digital banking platform lets members open accounts "
                            "online in minutes with instant funding and e-signature."),
        subcaps=[cell], published="2025-06-01")]
    wb.set_scoring(cell, {"Evidence_IDs": ", ".join(own)})
    ceiling, why = A.ceiling_for(wb, wb.scoring_row(cell))
    assert ceiling == 2.0 and "CAP-OWN" in why


def test_stale_evidence_needs_adj_stale_and_low_confidence(tmp_path):
    run, wb, cells, ev, cell = _open(tmp_path)
    wb.set_metadata("reference_date", "2029-06-01")      # every source now > 36 months
    row = wb.scoring_row(cell)
    assert A.stale_owed(wb, row)
    with pytest.raises(A.ScoringRefusal, match="ADJ_STALE is owed"):
        score_cell(wb, cell, ev[cell], score=2.0, confidence="LOW")
    with pytest.raises(A.ScoringRefusal, match="STALE_DATA"):
        score_cell(wb, cell, ev[cell], score=1.5, confidence="MEDIUM",
                   rationale=A._clean(row.get("Rationale")) or "")
    from fixtures import RATIONALE
    rat = "ADJ_STALE -0.3 applied: " + RATIONALE.format(e0=ev[cell][0], e1=ev[cell][1])
    assert score_cell(wb, cell, ev[cell], score=1.5, confidence="LOW",
                      rationale=rat)["score"] == 1.5


def test_a_critic_fail_must_name_its_moves_and_they_are_enforced(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    cell = next(c for c in cells if ev.get(c))
    with pytest.raises(A.ScoringRefusal, match="names the rows"):
        A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic",
                   note="Re-derived every P1 row against its rubric descriptor; one row flatters its evidence: it reads M3 on one T3 source only.")
    A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic",
               note="Re-derived every P1 row against its rubric descriptor; one row flatters its evidence: it reads M3 on one T3 source only.",
               moves=[f"{cell}:1.75:reads M3 on one T3 source"])
    assert cell in A.critic_moves(wb)
    g = A.gate(wb, run.qa_dir)
    assert "critic_moves_pending" in g["blocking"]
    # the scorer cannot re-score above the target …
    with pytest.raises(A.ScoringRefusal, match="moved"):
        score_cell(wb, cell, ev[cell], score=2.0)
    # … the brief hands the row to its scorer as a rescore …
    b = brief.scoring_batch(wb, run=run, out_dir=tmp_path / "sc")
    rows = [r for w in b["briefs"]
            for r in json.loads(Path(w["prompt_file"].replace(".md", ".json")).read_text())["rows_to_score"]]
    assert [r for r in rows if r["subcap"] == cell and r.get("rescore", {}).get("to") == 1.75]
    # … and applying it clears the pending term.
    score_cell(wb, cell, ev[cell], score=1.75)
    assert "critic_moves_pending" not in A.gate(wb, run.qa_dir)["blocking"]


def test_concurrent_critics_do_not_overwrite_each_others_moves(tmp_path):
    """Pillar critics run as parallel processes, each holding its own handle
    on the workbook. `critique` read the moves book from its in-memory copy
    and saved outside the lock, so the second critic to finish rewrote the
    book without the first one's moves. Measured on the First Tech run
    (2026-10-06): P1's moves never reached Run_Metadata.critic_moves, its
    scorer never saw them, and the critic failed the same rows every round
    until the stall guard stopped SCORING."""
    run, wb, cells, ev = scored_run(tmp_path)
    a, b = [c for c in cells if ev.get(c)][:2]
    other = run.open()                    # a second process's handle, loaded now
    note = ("Re-derived every P1 row against its rubric descriptor; one row "
            "flatters its evidence: it reads M3 on one T3 source only.")
    A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic",
               note=note, moves=[f"{a}:1.75:reads M3 on one T3 source"])
    A.critique(other, pillar="P1", verdict="FAIL", actor="scoring-critic",
               note=note, moves=[f"{b}:1.75:reads M3 on one T3 source"])
    book = A.critic_moves(run.open())
    assert a in book and b in book, f"a critic's moves were lost: {sorted(book)}"


def test_a_critic_pass_withdraws_its_earlier_moves(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    cell = next(c for c in cells if ev.get(c))
    A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic",
               note="Re-derived every P1 row against its rubric descriptor; one row flatters its evidence: it reads M3 on one T3 source only.",
               moves=[(cell, 1.75, "reads M3 on one T3 source")])
    A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-critic",
               note="Re-derived every P1 row again with the counter-source and the descriptors; every score now holds.")
    assert cell not in A.critic_moves(wb)


def test_critic_lanes_are_per_pillar_and_skip_passed_pillars(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    cell = next(c for c in cells if ev.get(c))
    b = brief.scoring_batch(wb, run=run, out_dir=tmp_path / "c0", critic=True)
    assert b["lanes"] == 0, "every pillar already PASSED: no critic lane to buy"
    A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic",
               note="Re-derived every P1 row against its rubric descriptor; one row flatters its evidence: it reads M3 on one T3 source only.",
               moves=[(cell, 1.75, "reads M3 on one T3 source")])
    b = brief.scoring_batch(wb, run=run, out_dir=tmp_path / "c1", critic=True)
    labels = [r["label"] for r in json.loads(Path(b["batch"]).read_text())]
    assert labels == ["scoring-critic-P1"]


def test_scoring_handoff_writes_one_workflow_per_owed_pillar(tmp_path):
    from engine import pipeline as P, pipeline_stub as S
    run, wb, cells, ev = scored_run(tmp_path)
    cell = next(c for c in cells if ev.get(c))
    A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic",
               note="Re-derived every P1 row against its rubric descriptor; one row flatters its evidence: it reads M3 on one T3 source only.",
               moves=[(cell, 1.75, "reads M3 on one T3 source")])
    opts = P.Options(dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False, folder_root=tmp_path / "out",
                     ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None,
                     scoring_mode="workflow")
    h = P.Pipeline(run, opts)._scoring_handoff()
    assert not h.get("passed")
    doc = json.loads(Path(h["file"]).read_text())
    assert Path(doc["workflow"]).is_file()
    assert [i["pillar"] for i in doc["invocations"]] == ["P1"]
    assert "--scoring-mode lanes" in doc["how"]


def test_the_hook_turns_a_scoring_handoff_into_workflow_calls(tmp_path):
    import importlib.util
    plugin = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
    spec = importlib.util.spec_from_file_location(
        "stage_advance", plugin / "scripts" / "hooks" / "stage_advance.py")
    sa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sa)
    f = tmp_path / "07_qa" / "scoring_workflow.json"
    f.parent.mkdir(parents=True)
    f.write_text(json.dumps({"workflow": "/w/dma-pillar-scoring.js", "then": "driver",
                             "invocations": [{"pillar": "P1"}, {"pillar": "P2"}]}))
    event = {"tool_name": "Bash",
             "tool_input": {"command": "python3 -m engine.pipeline run --run R"},
             "tool_response": {"stdout": f"AWAITING_WORKFLOW at SCORING — {f}"}}
    ctx = sa.awaiting_workflow(event)["hookSpecificOutput"]["additionalContext"]
    assert ctx.count("Workflow({scriptPath:") == 2 and "SCORING IS YOURS" in ctx
    assert "--scoring-mode lanes" in ctx


def test_the_scoring_workflow_ships_and_names_no_client():
    plugin = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
    src = (plugin / "workflows" / "dma-pillar-scoring.js").read_text()
    assert src.startswith("export const meta")
    assert "engine.assessment moves" in src and "--move CELL:TARGET:why" in src
    for leaked in ("susser", "Susser", "swbc", "SWBC"):
        assert leaked not in src


def test_a_rewrite_only_move_reaches_the_scorer_and_clears_on_rescore(tmp_path):
    """B1 Bank, 2026-10-08: the critic moved rows whose SCORE was right but
    whose rationale argued the band above it. Target == current score, so a
    score-only test dropped the move from pending_moves and from the scorer
    brief, and the critic failed the same rows every round."""
    run, wb, cells, ev = scored_run(tmp_path)
    cell = next(c for c in cells if ev.get(c))
    cur = float(wb.scoring_row(cell)["Score"])
    A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic",
               note="Re-derived every P1 row against its rubric descriptor; one rationale argues M3 under an M2 score and must be rewritten to argue its own band.",
               moves=[f"{cell}:{cur}:rationale argues M3 under an M2 score"])
    assert [m for m in A.pending_moves(wb, "P1")["moves"] if m["subcap"] == cell]
    assert "critic_moves_pending" in A.gate(wb, run.qa_dir)["blocking"]
    b = brief.scoring_batch(wb, run=run, out_dir=tmp_path / "sc")
    rows = [r for w in b["briefs"]
            for r in json.loads(Path(w["prompt_file"].replace(".md", ".json")).read_text())["rows_to_score"]]
    assert [r for r in rows if r["subcap"] == cell], "the rewrite never reached a scorer"
    score_cell(wb, cell, ev[cell], score=cur)
    assert not [m for m in A.pending_moves(wb, "P1")["moves"] if m["subcap"] == cell]
