"""Acceptance, issues 8 and 9 — the orchestration the owner could not see.

Issue 8: "There is no orchestration existing between the subagents and main
agents … they should also have enough context of the compacted data they
have collected to avoid redoing." Measured 2026-09-03: only the sixteen
category researchers received a brief; the scorers, the critic, the report
producers, the validator and the six page producers were dispatched "with
the run id and the root", and the category handback was computed and never
fed back, so a re-dispatched lane started the category from nothing.

Issue 9: "the assessment takes more than 6 hours". Measured: the conductor
said `--lanes 4` while the schedule divided by 16; `engine.cost record` was
documented and did not exist; no stage persisted its wall clock; a timed-out
lane was re-run by hand.

Every assertion is against the shipped path — the CLI the agents run and the
files the driver reads.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from engine import brief, cost, floors_gate, ledger as L

from fixtures import (bank_evidence, declare_absent, fire_volleys, good_synthesis,
                      new_run, researched_run, scored_run, synthesise)

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "dma-insights"
SKILL = PLUGIN / "skills" / "dma-research"


def _roster() -> set[str]:
    return {p.stem for p in (PLUGIN / "agents").rglob("*.md")}


def _cli(mod: str, *args, run) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", mod, *args, "--run", run.run_id, "--root", str(run.root)],
        capture_output=True, text=True, cwd=str(SKILL))


# ═══════════════════════════════════════════════════════════════════════════
# ISSUE 8 · every lane type starts from a bounded brief
# ═══════════════════════════════════════════════════════════════════════════

def test_issue8_every_lane_type_has_a_bounded_brief_and_a_real_agent(tmp_path):
    """PRELIM, challenge, scoring (three shapes), reports (two shapes) and
    pages: each view writes one prompt file per lane, names an agent that
    exists in the roster, and stays under the packet ceiling."""
    run, wb, cells, ev = researched_run(tmp_path / "r")
    srun, swb, scells, sev = scored_run(tmp_path / "s")
    roster = _roster()
    views = [
        brief.prelim_brief(wb, run=run, out_dir=tmp_path / "p"),
        brief.scoring_batch(swb, run=srun, out_dir=tmp_path / "sc"),
        brief.scoring_batch(swb, run=srun, out_dir=tmp_path / "scc", critic=True),
        brief.scoring_batch(swb, run=srun, out_dir=tmp_path / "scs", solutions=True),
        brief.report_batch(swb, run=srun, out_dir=tmp_path / "rp"),
        brief.report_batch(swb, run=srun, out_dir=tmp_path / "rpv", validator=True),
        brief.page_batch(swb, run=srun, out_dir=tmp_path / "pg", connector_run="RUN-1",
                         contract_file=tmp_path / "contract.json"),
    ]
    agents = set()
    for v in views:
        assert v["lanes"] >= 1, v
        rows = json.loads(Path(v["batch"]).read_text())
        assert len(rows) == v["lanes"]
        for row, w in zip(rows, v["briefs"]):
            assert row["agent"] in roster, row["agent"]
            assert Path(row["prompt_file"]).is_file()
            assert w["chars"] <= brief.BRIEF_CHAR_CEILING, (row["agent"], w["chars"])
            text = Path(row["prompt_file"]).read_text()
            assert "Your first commands" in text and run.run_id in text or srun.run_id in text
            agents.add(row["agent"])
    for must in ("research-conductor", "technographic-scanner",
                 "enrichment-connector-specialist", "scoring-p1-producer",
                 "scoring-critic", "report-research-producer",
                 "report-assessment-producer", "report-validator",
                 "heatmap-surface-producer", "overview-surface-producer",
                 "platform-surface-producer"):
        assert must in agents, must


def test_issue8_a_report_brief_carries_the_templates_and_the_preconditions(tmp_path):
    """The report producer's first sentence used to be 'run id and root'.
    Now its brief names the pinned template files it must read, the Doc's
    sections with THIS run's floors, and the preconditions verdict."""
    run, wb, cells, ev = researched_run(tmp_path)          # NOT scored on purpose
    out = brief.report_batch(wb, run=run, out_dir=tmp_path / "rp")
    pk = json.loads(Path(out["briefs"][1]["prompt_file"]).with_suffix(".json").read_text())
    assert pk["agent"] == "report-assessment-producer"
    assert pk["preconditions_failing"], "an unscored run must show its blockers"
    assert any("SCORING" in p for p in pk["preconditions_failing"])
    for k in ("report_templates", "gold_reference", "shell_docx"):
        assert Path(pk["templates_read_before_authoring"][k]).is_file(), k
    assert [s["id"] for s in pk["sections"]][:3] == ["1", "2", "3"]
    pillar = next(s for s in pk["sections"] if s["kind"] == "pillar")
    assert pillar["cards_min"] == 1                     # one pillar in scope
    assert any("narrative preconditions" in c for c in pk["first_commands"])


def test_issue8_a_redispatched_category_carries_the_gates_blocking_terms(tmp_path):
    """A category whose floors gate FAILED is dispatched again with the exact
    terms the gate refused and what its previous lane established — not the
    category from scratch."""
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cells = wb.selected_subcaps()
    for c in cells[:2]:                     # two cells worked, four left open
        synthesise(wb, c, good_synthesis(c, bank_evidence(wb, c, n=5)))
    v = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    assert v["gate"] == "FAIL" and v["blocking"]
    need = brief.categories_needing_dispatch(wb)
    assert need["dispatch"] == ["P1C1"] and need["passed"] == []
    assert set(need["reasons"]["P1C1"]) == set(v["blocking"])
    pk = brief.dispatch(wb, "P1C1", run=run, with_handback=True)
    assert pk["last_gate"]["verdict"] == "FAIL"
    assert set(pk["last_gate"]["blocking"]) == set(v["blocking"])
    assert len(pk["handback"]["synthesised"]) == 2
    md = brief.as_markdown(pk)
    assert "BLOCKING:" in md and "RE-DISPATCH" in md and "previous run established" in md
    assert pk["packet_chars"] <= brief.BRIEF_CHAR_CEILING


def test_issue8_a_passed_category_is_not_redispatched(tmp_path):
    """The redo the owner measured: a lane re-working a category that already
    PASSED. `batch --with-handback` skips it and says so; `needs` names it."""
    run, wb, cells, ev = researched_run(tmp_path)          # P1C1 PASS
    need = brief.categories_needing_dispatch(wb)
    assert need["passed"] == ["P1C1"] and need["dispatch"] == []
    out = brief.batch(wb, run=run, out_dir=tmp_path / "b", with_handback=True)
    assert out["lanes"] == 0 and out["skipped_passed"] == ["P1C1"]
    assert out["dispatch"] is None
    # a plain (first) dispatch still serves every category
    first = brief.batch(wb, run=run, out_dir=tmp_path / "b1")
    assert first["lanes"] == 1


def test_issue8_a_page_brief_carries_paths_and_verdict_reasons_never_payload_bytes(tmp_path):
    run, wb, cells, ev = scored_run(tmp_path)
    vf = tmp_path / "verdicts.json"
    vf.write_text(json.dumps({"heatmap": ["CG-14 heatmap.workbook_scores[3].band: "
                                          "'Transformational' not in band_t"]}))
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"page": "heatmap", "sections": {"x": {"e_ids": []}}}))
    out = brief.page_batch(wb, run=run, out_dir=tmp_path / "pg", connector_run="RUN-9",
                           contract_file=contract, verdicts_file=vf, pages=["heatmap"])
    text = Path(out["briefs"][0]["prompt_file"]).read_text()
    assert "RUN-9" in text and str(contract) in text
    assert "CG-14" in text and "Transformational" in text
    assert '"e_ids"' not in text                  # the contract's BYTES stay on disk
    assert "ship_page.py" in text and "--claim" in text
    with pytest.raises(ValueError, match="unknown page"):
        brief.page_batch(wb, run=run, out_dir=tmp_path / "pg2", connector_run="RUN-9",
                         contract_file=contract, pages=["dashboard"])


def test_issue8_every_view_is_reachable_from_the_cli(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    for args in (["needs"],
                 ["prelim", "--out-dir", str(tmp_path / "p")],
                 ["challenge-batch", "--out-dir", str(tmp_path / "c")],
                 ["scoring-batch", "--out-dir", str(tmp_path / "s")],
                 ["scoring-batch", "--out-dir", str(tmp_path / "s"), "--critic"],
                 ["report-batch", "--out-dir", str(tmp_path / "r"), "--validator"],
                 ["page-batch", "--out-dir", str(tmp_path / "g"), "--connector-run", "X",
                  "--contract-file", str(tmp_path / "c.json"), "--pages", "heatmap"],
                 ["batch", "--out-dir", str(tmp_path / "b"), "--with-handback"]):
        out = _cli("engine.brief", *args, run=run)
        assert out.returncode == 0, (args, out.stderr[-600:])
        json.loads(out.stdout)


def test_issue8_the_challenger_has_a_command_and_cannot_be_the_author(tmp_path):
    """A headless finding-challenger could not record: `record_challenge`
    was a library call with no CLI. Now it has one, with the same refusals."""
    run, wb, cells, ev = researched_run(tmp_path)
    cell = cells[0]
    author = L.actor_for(wb, cell, "synthesis")
    common = ["challenge", "--subcap", cell, "--verdict", "PASS", "--all", "PASS",
              "--rationale", "An independent review with enough words to clear the floor "
                             "and say something real about the synthesis."]
    out = _cli("engine.cli", *common, "--actor", author, run=run)
    assert out.returncode == 1 and "cannot also be its challenger" in out.stderr
    out = _cli("engine.cli", *common, "--actor", "finding-challenger", run=run)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["verdict"] == "PASS"
    out = _cli("engine.cli", "challenge", "--subcap", cell, "--verdict", "PASS",
               "--actor", "finding-challenger", "--rationale", "x" * 50,
               "--dimension", "recency=FAIL", "--all", "PASS", run=run)
    assert out.returncode == 1 and "Any FAIL means FAIL" in out.stderr


# ═══════════════════════════════════════════════════════════════════════════
# ISSUE 9 · where the hours went
# ═══════════════════════════════════════════════════════════════════════════

def test_issue9_cost_record_and_report_are_real_commands(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    out = _cli("engine.cost", "record", "--stage", "PRELIM", "--elapsed-s", "600",
               "--turns", "40", "--tokens",
               json.dumps({"cache_read": 2_000_000, "cache_write": 50_000,
                           "uncached": 20_000, "output": 900}), "--model", "sonnet",
               run=run)
    assert out.returncode == 0, out.stderr
    rec = json.loads(out.stdout)
    assert rec["usd"] and rec["elapsed_s"] == 600.0 and rec["known_stage"]
    assert Path(rec["ledger"]).is_file()
    # no duration at all is refused — a timing that cannot be added is not a timing
    out = _cli("engine.cost", "record", "--stage", "KG", run=run)
    assert out.returncode == 1 and "elapsed" in out.stderr
    # the workbook carries the mirror
    md = run.open().metadata()
    assert json.loads(md["stage_timings"])["PRELIM"]["elapsed_s"] == 600.0
    assert json.loads(md["cost_summary"])["turns"] == 40
    # the report: within → 0; over the run budget → 1, and it says which
    out = _cli("engine.cost", "report", "--json", run=run)
    rep = json.loads(out.stdout)
    assert out.returncode == 0 and rep["within"] and rep["stages"][0]["stage"] == "PRELIM"
    assert "RESEARCH" in rep["unrecorded"]
    _cli("engine.cost", "record", "--stage", "RESEARCH", "--elapsed-s", "9000",
         "--usd", "12.50", run=run)
    out = _cli("engine.cost", "report", "--json", run=run)
    rep = json.loads(out.stdout)
    assert out.returncode == 1 and rep["over_wall_clock"] and rep["over_budget"]


def test_issue9_a_recorded_run_replaces_the_hand_typed_baseline(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    cost.record(run, stage="RESEARCH", elapsed_s=1800, turns=200,
                tokens={"cache_read": 10_000_000, "cache_write": 100_000,
                        "uncached": 50_000, "output": 2000}, model="sonnet")
    b = cost.as_baseline(run)
    mb = cost.measured_baseline(b["written_to"])
    assert mb["source"] == b["written_to"] and mb["turns"] == 200
    assert cost.measured_baseline()["source"] == "constant"
    # a ledger with nothing measured cannot become a baseline
    run2, wb2, *_ = researched_run(tmp_path / "empty")
    cost.record(run2, stage="KG", elapsed_s=5)
    with pytest.raises(ValueError, match="no turns or no tokens"):
        cost.as_baseline(run2)


def test_issue9_the_documented_dispatch_uses_the_lanes_the_schedule_divides_by(tmp_path):
    """One constant. The schedule divides by it, agent_run defaults to it,
    `brief batch` prints it, and no document says another number."""
    spec = importlib.util.spec_from_file_location(
        "agent_run", PLUGIN / "scripts" / "agent_run.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    assert m.DEFAULT_LANES == cost.PARALLEL_LANES == 16
    run, wb, cells, ev = new_run(tmp_path, n=6), None, None, None
    wb = run.open()
    out = brief.batch(wb, run=run, out_dir=tmp_path / "b")
    assert f"--lanes {cost.PARALLEL_LANES}" in out["dispatch"]
    assert "--retries 1" in out["dispatch"] and "--record-stage RESEARCH" in out["dispatch"]
    for doc in (PLUGIN / "docs" / "END-TO-END.md",
                PLUGIN / "agents" / "research" / "research-conductor.md"):
        text = doc.read_text()
        for m_ in re.finditer(r"--lanes\s+(\d+)", text):
            assert int(m_.group(1)) == cost.PARALLEL_LANES, (doc.name, m_.group(0))


def test_issue9_the_schedule_can_be_read_from_the_runs_own_selection(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    out = _cli("engine.cost", "schedule", "--json", run=run)
    assert out.returncode == 0, out.stderr
    sch = json.loads(out.stdout)
    assert sch["subcaps"] == len(cells) and sch["lanes"] == cost.PARALLEL_LANES
    assert sch["within_target"]
