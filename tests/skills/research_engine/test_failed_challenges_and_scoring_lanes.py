"""A failed challenge is repaired, never scored around; no scoring row is dropped.

Measured 2026-10-05 (Susser Bank), three defects behind one SCORING loop:
  * the floors gate PASSED categories whose cells carried FAIL challenge
    verdicts (MEM-0441) — 103 of them reached SCORING, where
    `engine.assessment score` refuses every one;
  * a re-synthesis never cleared the old verdict, and `challenge_batch`
    skipped any cell ever challenged, so a repaired claim could never be
    challenged again;
  * the scoring brief carried a ~34K-char `shared` block under a 6.4K
    ceiling, so `_bound` halved each pillar's rows to 3: seven rounds scored
    57 of 708 cells for ~$44.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine import brief, floors_gate, ledger as L
from fixtures import (challenge, good_synthesis, researched_run, scored_run)


def _evidenced_cell(wb, ev):
    return next(c for c in ev if ev[c])


def test_a_failed_challenge_blocks_the_floors_gate(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    cell = _evidenced_cell(wb, ev)
    challenge(wb, cell, verdict="FAIL", actor="research-challenger")
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, persist=False)
    assert v["gate"] == "FAIL" and "challenge_failed" in v["blocking"]
    assert cell in floors_gate.blocking_cells(v)
    # Even the convergence probe (challenge terms deferred) sees it: the
    # claim needs repair, not a challenge.
    probe = floors_gate.run(wb, "P1C1", require_synthesis=True,
                            require_challenge=False, persist=False)
    assert "challenge_failed" in probe["blocking"]


def test_a_resynthesis_clears_the_verdict_and_is_challenged_again(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    cell = _evidenced_cell(wb, ev)
    challenge(wb, cell, verdict="FAIL", actor="research-challenger")
    assert wb.scoring_row(cell)["Challenge_Verdict"] == "FAIL"
    L.append_synthesis(wb, cell, good_synthesis(cell, ev[cell]),
                       actor="research-p1c1-producer")
    assert not str(wb.scoring_row(cell).get("Challenge_Verdict") or "").strip()
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, persist=False)
    assert "challenge_missing" in v["blocking"] and "challenge_failed" not in v["blocking"]
    cb = brief.challenge_batch(wb, run=run, out_dir=tmp_path / "cb")
    offered = json.dumps([json.loads(Path(b["prompt_file"].replace(".md", ".json")).read_text())
                          for b in cb.get("briefs") or []])
    assert cell in offered, "a repaired claim was never offered to a challenger"


def test_scoring_lanes_carry_every_scorable_row_and_hold_refused_ones(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    for c in cells:                                  # unscore everything
        wb.set_scoring(c, {"Score": ""})
    held = _evidenced_cell(wb, ev)
    wb.set_scoring(held, {"Challenge_Verdict": "FAIL"})
    b = brief.scoring_batch(wb, run=run, out_dir=tmp_path / "sc")
    offered, held_ids = [], []
    for w in b["briefs"]:
        assert w["chars"] <= brief.BRIEF_CHAR_CEILING, w
        d = json.loads(Path(w["prompt_file"].replace(".md", ".json")).read_text())
        assert not d.get("trimmed"), d.get("trimmed")
        offered += [r["subcap"] for r in d["rows_to_score"]]
        held_ids += d.get("held_for_research") or []
    assert held not in offered
    assert any(h.startswith(held) for h in held_ids)
    assert sorted(offered) == sorted(c for c in cells if c != held)
    rows = json.loads(Path(b["batch"]).read_text())
    assert len({r["label"] for r in rows}) == len(rows), "two lanes share a transcript"
