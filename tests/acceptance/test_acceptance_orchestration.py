"""Acceptance, issue 8: "There is no orchestration existing between the
subagents and main agents. Ensure efficient context management and
information sharing where needed. As they work independently, they should
also have enough context of the compacted data they have collected to avoid
redoing. Ensure great context optimization is ingrained."

Four properties, and a test for each:

  SHARED      one lane can see what the run knows, including what the other
              fifteen lanes have registered since it started.
  BOUNDED     the packet a lane starts from has a measured ceiling, so
              "more context" cannot become the token bleed issue 7 is about.
  RESUMABLE   a lane that lost its context gets its own material back, not a
              count of it, so it continues instead of starting again.
  HANDED BACK the conductor reads what a lane established from the
              substrate, in a fixed shape, whether the lane succeeded, died
              or reported something else entirely.

The fifth test is the one that matters most and is easiest to skip: the
brief must be REACHABLE — a mechanism the agents are not told about is a
mechanism that does not run.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine import brief, contract as C, ledger as L, memory, runstate

from fixtures import (bank_evidence, declare_absent, fire_volleys,
                      good_synthesis, new_run, researched_run, synthesise,
                      two_category_selection)

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "dma-insights"
SKILL = PLUGIN / "skills" / "dma-research"


# ── SHARED ───────────────────────────────────────────────────────────────

def test_a_lane_sees_what_the_run_knows_without_reading_the_workbook(tmp_path):
    """`shared` is the one read a producer makes before its own work: the
    estate, the peers, the register's reach, the layers already searched and
    found empty. Before this, each lane went and found that out again."""
    run, wb, cells, ev = researched_run(tmp_path)
    s = brief.shared(wb)
    assert s["entity"] == "Acme Credit Union"
    assert s["evidence_rows"] >= 10
    assert s["estate_by_layer"], s
    assert set(s["estate_by_layer"]) >= {"OPS", "CUST", "DATA", "INFRA"}
    assert "INFRA" in s["layers_searched_empty"]      # ABSENT is a RESULT
    assert s["peers"], s
    assert s["searches_fired"] >= 30
    assert s["categories"]["P1C1"]["closed"] >= 5


def test_a_lane_sees_a_sibling_lanes_source_for_its_own_cell(tmp_path):
    """The parallel-lane property. P1C1's lane registers a source that names
    a P1C2 cell; P1C2's brief carries it, so P1C2 does not pay for that
    search again — which is what sixteen independent lanes did before."""
    run = new_run(tmp_path, selected=two_category_selection(4))
    wb = run.open()
    cells = wb.selected_subcaps()
    theirs = [c for c in cells if not c.startswith("P1C1")]
    assert theirs, cells
    target = theirs[0]
    fire_volleys(wb, target, n=0)
    eid = L.append_evidence(
        wb, source_name="Board pack 2025 — technology programme",
        source_url="https://acme.example/board/2025-tech", tier="T2",
        published="2025-05-01", subcaps=[target],
        excerpt=("The board approved the member-onboarding programme in May "
                 "2025 with a named executive owner and a quarterly review "
                 "cadence reporting into the digital steering group."))
    packet = brief.dispatch(wb, brief.category_of(target), run=run)
    named = [i["e_id"] for d in packet["work_next"]
             for i in d["already_registered_for_this_cell"]]
    assert eid in named or any(
        eid in [i["e_id"] for i in d["capability_siblings_worth_reading"]]
        for d in packet["work_next"]), packet["work_next"]


def test_the_lane_that_registered_it_hands_the_lead_to_the_other_category(tmp_path):
    """The push half of the same fact: a lane's handback names the OTHER
    categories its sources reach, so the conductor can route a lead instead
    of hoping the other lane finds it."""
    run = new_run(tmp_path, selected=two_category_selection(4))
    wb = run.open()
    cells = wb.selected_subcaps()
    mine = [c for c in cells if c.startswith("P1C1")][0]
    other = next((c for c in cells if not c.startswith("P1C1")), None)
    fire_volleys(wb, mine, n=0)
    subs = [mine] + ([other] if other else [])
    L.append_evidence(
        wb, source_name="Annual report 2025 — technology and operations",
        source_url="https://acme.example/ar25/tech", tier="T2",
        published="2025-06-01", subcaps=subs,
        excerpt=("The 2025 annual report describes the digital banking "
                 "platform, the data warehouse behind it and the governance "
                 "committee that reviews both on a quarterly cadence."))
    hb = brief.handback(wb, "P1C1")
    assert hb["category"] == "P1C1"
    if other:
        cat = brief.category_of(other)
        assert cat in hb["leads_for_other_categories"], hb
    assert set(hb["synthesised"]) | set(hb["declared_absent"]) | \
        set(hb["still_open"]) == set(c for c in cells if c.startswith("P1C1"))


# ── BOUNDED ──────────────────────────────────────────────────────────────

def test_the_packet_is_measured_and_stays_under_its_ceiling(tmp_path):
    """"Ensure great context optimization is ingrained" — a brief with no
    ceiling is the token bleed under a different name. The packet reports
    its own size and trims its detail rather than a field."""
    run, wb, cells, ev = researched_run(tmp_path)
    packet = brief.dispatch(wb, "P1C1", run=run)
    assert packet["packet_chars"] <= brief.BRIEF_CHAR_CEILING
    assert packet["packet_ceiling"] == brief.BRIEF_CHAR_CEILING
    md = brief.as_markdown(packet)
    assert len(md) <= brief.BRIEF_CHAR_CEILING * 2      # prose, not JSON
    assert "## What the run already knows" in md


def test_a_wide_category_trims_its_detail_and_says_so(tmp_path):
    """Twenty open cells cannot each get a paragraph. The packet details the
    first few, names the count and points at the paged reader that already
    exists — never a truncated field, which reads as a complete one."""
    run = new_run(tmp_path, n=24, prelim=True)
    wb = run.open()
    packet = brief.dispatch(wb, "P1C1", run=run)
    assert packet["open_cells"] >= 20
    assert len(packet["work_next"]) <= brief.CELLS_DETAILED
    assert packet["packet_chars"] <= brief.BRIEF_CHAR_CEILING
    if packet.get("trimmed"):
        assert "orient" in packet["trimmed"]


def test_every_category_in_a_full_run_gets_a_dispatchable_brief(tmp_path):
    """The conductor's dispatch is one command over files it did not
    compose: a prompt per category plus the batch array `agent_run.py`
    takes. A hand-written prompt is where context goes missing or twice."""
    run, wb, cells, ev = researched_run(tmp_path)
    out = brief.batch(wb, run=run, out_dir=tmp_path / "briefs")
    assert out["lanes"] >= 1
    rows = json.loads(Path(out["batch"]).read_text())
    for row in rows:
        assert row["agent"].startswith("research-p")
        assert Path(row["prompt_file"]).is_file()
        assert Path(row["prompt_file"]).read_text().startswith("# ")
    assert all(b["chars"] <= brief.BRIEF_CHAR_CEILING for b in out["briefs"])
    assert "agent_run.py" in out["dispatch"] and "--batch" in out["dispatch"]


# ── RESUMABLE ────────────────────────────────────────────────────────────

def test_a_resumed_lane_gets_its_own_notes_back_not_a_count(tmp_path):
    """"they should also have enough context of the compacted data they have
    collected to avoid redoing" — `memory.status` answered "how many notes";
    a lane that compacted needs "what did I find"."""
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    memory.note(run, category="P1C1", subcap=cell, facet="works",
                kind="lead", note=("the 2024 annual report names a digital "
                                   "steering committee — chase the charter"))
    memory.note(run, category="P1C1", subcap=cell, facet="fails",
                kind="contradiction",
                note=("the newsroom claims a 2023 go-live and the report "
                      "says 2024 — one of them is restating"))

    digest = brief.notebook_digest(run, "P1C1")
    assert digest["notes"] == 2
    assert len(digest["entries"]) == 2
    assert any("steering committee" in e["gist"] for e in digest["entries"])
    assert any(e["kind"] == "contradiction" for e in digest["entries"])

    packet = brief.dispatch(wb, "P1C1", run=run)
    assert packet["your_notes"]["notes"] == 2
    assert "steering committee" in brief.as_markdown(packet)


def test_a_blocked_note_is_surfaced_first_because_it_is_still_owed(tmp_path):
    """Consolidation marks an entry BLOCKED with the ledger's own reason.
    Those are the ones a resumed lane must see, so they rank first."""
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    for i in range(6):
        memory.note(run, category="P1C1", subcap=cell, facet="works",
                    kind="note", note=f"routine observation number {i}")
    memory.note(run, category="P1C1", subcap=cell, facet="works",
                kind="evidence", source_name="Annual Report 2025",
                source_url="https://acme.example/ar25",
                excerpt="too short to register")
    got = memory.consolidate(run, "P1C1", actor="research-p1c1-producer")
    assert got["blocked"] >= 1, got
    digest = brief.notebook_digest(run, "P1C1")
    assert digest["blocked"] >= 1
    assert digest["entries"][0]["status"] == "BLOCKED"


def test_a_lane_with_no_notebook_is_told_so_rather_than_erroring(tmp_path):
    run = new_run(tmp_path, n=2)
    got = brief.notebook_digest(run, "P1C1")
    assert got["notes"] == 0 and got["entries"] == []
    assert "written nothing" in got["note"]


# ── HANDED BACK ──────────────────────────────────────────────────────────

def test_the_handback_is_the_same_shape_whether_the_lane_finished_or_died(tmp_path):
    """The conductor must not have to trust a lane's prose. Every field is
    computed from the sheets, so a lane that died mid-cell reports the same
    fields as one that finished — with different numbers in them."""
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cells = wb.selected_subcaps()
    half = brief.handback(wb, "P1C1")
    assert half["done"] is False
    assert len(half["still_open"]) == len(cells)

    for c in cells[:5]:
        synthesise(wb, c, good_synthesis(c, bank_evidence(wb, c, n=5)))
    declare_absent(wb, cells[5])
    whole = brief.handback(wb, "P1C1")
    assert set(whole) == set(half)
    assert whole["done"] is True
    assert len(whole["synthesised"]) == 5
    assert whole["declared_absent"] == [cells[5]]
    assert whole["evidence_items"] >= 20
    assert whole["tools_used"]
    assert "NOT the gate" in whole["note"]


def test_the_handback_refuses_to_be_the_gate(tmp_path):
    """`done` is bookkeeping, and the verdict is the floors gate's. A
    handback that read as a verdict would be a second gate with weaker
    rules, which is how a run gets two answers."""
    run, wb, cells, ev = researched_run(tmp_path)
    hb = brief.handback(wb, "P1C1")
    assert hb["done"] is True
    assert "gate" not in hb
    assert "engine.cli gate" in hb["note"]


# ── REACHABLE ────────────────────────────────────────────────────────────

def test_the_cli_serves_every_view_an_agent_needs(tmp_path):
    """A view an agent cannot invoke is a view that does not run."""
    run, wb, cells, ev = researched_run(tmp_path)
    env = {"PYTHONPATH": str(SKILL)}
    import os
    env = {**os.environ, **env}
    for args in (["shared"],
                 ["needs"],
                 ["dispatch", "--category", "P1C1"],
                 ["dispatch", "--category", "P1C1", "--with-handback"],
                 ["handback", "--category", "P1C1"],
                 ["reuse", "--subcap", cells[0]],
                 ["prelim", "--out-dir", str(tmp_path / "p")],
                 ["challenge-batch", "--out-dir", str(tmp_path / "c")],
                 ["scoring-batch", "--out-dir", str(tmp_path / "s")],
                 ["report-batch", "--out-dir", str(tmp_path / "r")]):
        out = subprocess.run(
            [sys.executable, "-m", "engine.brief", *args,
             "--run", run.run_id, "--root", str(run.root)],
            capture_output=True, text=True, env=env, cwd=str(SKILL))
        assert out.returncode == 0, (args, out.stderr[-800:])
        assert out.stdout.strip(), args


def test_the_agents_are_told_the_brief_exists():
    """The conductor dispatches with it, the category producers open with
    it, and the session brief names it. Otherwise none of the above runs."""
    conductor = (PLUGIN / "agents" / "research" / "research-conductor.md").read_text()
    assert "engine.brief batch" in conductor
    assert "handback" in conductor

    producers = sorted((PLUGIN / "agents" / "research" / "categories").glob("*.md"))
    assert len(producers) == 16
    for p in producers:
        text = p.read_text()
        assert "engine.brief" in text, p.name

    hook = (PLUGIN / "scripts" / "hooks" / "session_brief.py").read_text()
    assert "engine.brief" in hook


def test_a_category_outside_the_run_is_refused_not_guessed(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    with pytest.raises(ValueError, match="no selected subcapability"):
        brief.dispatch(wb, "P4C4", run=run)
