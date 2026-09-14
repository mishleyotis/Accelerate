"""The challenge stage is briefed for the job it is dispatched for, sized to
it, and drops nothing the gate will demand.

MEASURED 2026-09-14 (MEM-0515), reading the stage against its own agent:

  * `challenge_batch` dispatched `finding-challenger` — model opus, effort
    high, maxTurns 100 — one lane per category, for every synthesised cell,
    INSIDE the research round loop, every round. The research lanes it
    judges are sonnet/medium.
  * That agent's body is written about challenging SURFACE JSON before page
    consolidation: 0 mentions of `engine.cli challenge`, `Challenge_Log`,
    `--dimension` or the seven dimensions it must record, and 8 of
    `get_staged_payload`/HOLDS/BREAKS. An agent handed a job its own
    instructions do not describe will explore, on the most expensive tier.
  * The packet carried `claim[:200]` and an evidence COUNT, so the lane had
    to re-read every evidence row to judge `evidence_sufficiency` — and its
    mandated first command was `orient --category`, which returns the
    research next-card view, not a challenge list.
  * `_bound` silently halved `cells_to_challenge` to a floor of 3 while the
    floors gate demands 100% of synthesised cells challenged, so the stage
    could not converge in one round by construction and nothing reported
    the shortfall as the reason.
  * `cost.lane_turn_budget` globbed `research-p*-producer.md` only, so the
    100-turn opus lane was outside the projection that exists to say what a
    run will cost before it spends it.

These pin the rebuilt stage.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine import brief, contract as C, cost, floors_gate
from fixtures import (bank_evidence, good_synthesis, new_run,
                      two_category_selection)
from engine import ledger as L

AGENTS = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights" / "agents"


def _synthesised(tmp_path, n_cells=None, selected=None):
    run = new_run(tmp_path, n=6, selected=selected)
    wb = run.open()
    cells = wb.selected_subcaps()[:n_cells] if n_cells else wb.selected_subcaps()
    for cell in cells:
        eids = bank_evidence(wb, cell, n=5)
        rec = {k: v for k, v in good_synthesis(cell, eids).items()
               if k != "Challenge_Verdict"}
        L.append_synthesis(wb, cell, rec, actor=f"research-{cell.split('.')[0].lower()}-producer")
    return run, wb, cells


# ── the agent is briefed for the job ───────────────────────────────────

def test_the_stage_dispatches_the_agent_written_for_it(tmp_path):
    run, wb, cells = _synthesised(tmp_path)
    out = brief.challenge_batch(wb, run=run, out_dir=tmp_path / "b")
    agents = {p["agent"] for p in out["packets"]}
    assert agents == {"research-challenger"}, agents


def test_that_agent_is_the_cheaper_tier_and_holds_no_web_tools():
    fm = (AGENTS / "research" / "research-challenger.md").read_text()[:1200]
    assert "model: sonnet" in fm and "effort: medium" in fm
    assert "WebSearch" not in fm and "WebFetch" not in fm
    assert "mcp__Exa" not in fm and "mcp__Tavily" not in fm


def test_its_body_names_the_seven_dimensions_it_must_record():
    body = (AGENTS / "research" / "research-challenger.md").read_text()
    for dim in C.CHALLENGE_DIMENSIONS:
        assert dim in body, dim
    assert "engine.cli challenge" in body


# ── the packet carries what the dimensions need ────────────────────────

def test_the_packet_ships_the_evidence_rather_than_a_count(tmp_path):
    """`evidence_sufficiency` cannot be judged from an integer."""
    run, wb, cells = _synthesised(tmp_path)
    out = brief.challenge_batch(wb, run=run, out_dir=tmp_path / "b")
    cell = out["packets"][0]["cells_to_challenge"][0]
    assert cell["evidence"], "the packet still carries no evidence rows"
    row = cell["evidence"][0]
    assert row["e_id"] and row["excerpt"] and row["tier"]
    assert isinstance(cell["evidence_total"], int)


def test_the_packet_carries_the_fields_the_other_dimensions_read(tmp_path):
    run, wb, cells = _synthesised(tmp_path)
    out = brief.challenge_batch(wb, run=run, out_dir=tmp_path / "b")
    cell = out["packets"][0]["cells_to_challenge"][0]
    for key in ("facets_answered", "contradiction", "ceiling", "recency_bands"):
        assert key in cell, key


def test_it_is_not_sent_to_the_research_card(tmp_path):
    run, wb, cells = _synthesised(tmp_path)
    out = brief.challenge_batch(wb, run=run, out_dir=tmp_path / "b")
    first = " ".join(out["packets"][0]["first_commands"])
    assert "orient" not in first
    assert "engine.cli challenge" in first


# ── nothing is silently dropped ────────────────────────────────────────

def test_no_synthesised_cell_is_silently_trimmed(tmp_path):
    """The gate demands every synthesised cell challenged. A packet that
    quietly keeps three of forty cannot converge, and said so nowhere."""
    run, wb, cells = _synthesised(tmp_path, selected=two_category_selection(n=8))
    out = brief.challenge_batch(wb, run=run, out_dir=tmp_path / "b")
    shipped = {c["subcap"] for p in out["packets"]
               for c in p["cells_to_challenge"]}
    assert shipped | set(out["deferred_cells"]) == set(cells)
    assert not (shipped & set(out["deferred_cells"]))


def test_a_big_category_is_paged_rather_than_truncated(tmp_path):
    run, wb, cells = _synthesised(tmp_path, selected=two_category_selection(n=8))
    out = brief.challenge_batch(wb, run=run, out_dir=tmp_path / "b")
    assert all(len(p["cells_to_challenge"]) <= brief.CELLS_PER_CHALLENGE_LANE
               for p in out["packets"])
    labels = [lane for lane in out["lane_names"]]
    assert len(labels) == len(set(labels)), "two lanes share a label"


def test_a_shortfall_is_recorded_not_swallowed(tmp_path, monkeypatch):
    monkeypatch.setattr(brief, "CHALLENGE_CHAR_CEILING", 1200)
    run, wb, cells = _synthesised(tmp_path)
    out = brief.challenge_batch(wb, run=run, out_dir=tmp_path / "b")
    shipped = {c["subcap"] for p in out["packets"]
               for c in p["cells_to_challenge"]}
    assert out["deferred_cells"], "a trim happened and nothing recorded it"
    assert set(out["deferred_cells"]) == set(cells) - shipped


def test_the_challenge_packet_has_its_own_ceiling(tmp_path):
    """It carries evidence the dispatch packet does not, so it cannot share
    the dispatch packet's budget — but it still has one."""
    assert brief.CHALLENGE_CHAR_CEILING > brief.BRIEF_CHAR_CEILING
    run, wb, cells = _synthesised(tmp_path)
    out = brief.challenge_batch(wb, run=run, out_dir=tmp_path / "b")
    for p in out["packets"]:
        assert p["packet_chars"] <= brief.CHALLENGE_CHAR_CEILING


# ── only what has converged ────────────────────────────────────────────

def test_only_the_categories_asked_for_are_challenged(tmp_path):
    run, wb, cells = _synthesised(tmp_path, selected=two_category_selection(n=4))
    cats = sorted({c.split(".")[0] for c in cells})
    out = brief.challenge_batch(wb, run=run, out_dir=tmp_path / "b",
                                categories=[cats[0]])
    assert {p["category"] for p in out["packets"]} == {cats[0]}


def test_the_gate_can_defer_the_challenge_terms(tmp_path):
    """A category whose research has not converged is not challenged yet, so
    the gate must be askable without the challenge terms — and must still
    compute them, or the deferral becomes a relaxation nobody can see."""
    run, wb, cells = _synthesised(tmp_path)
    cat = cells[0].split(".")[0]
    v = floors_gate.run(wb, cat, require_synthesis=True,
                        require_challenge=False, persist=False)
    assert "challenge_missing" not in v["blocking"]
    assert v["challenge_missing"], "the term stopped being computed"
    strict = floors_gate.run(wb, cat, require_synthesis=True, persist=False)
    assert "challenge_missing" in strict["blocking"]


def test_the_convergence_probe_records_nothing(tmp_path):
    """A PASS written with the challenge terms deferred reads as 'this
    category is done', and the challenge it was asking about would never be
    dispatched."""
    run, wb, cells = _synthesised(tmp_path)
    cat = cells[0].split(".")[0]
    before = len(wb.rows("Gate_Log"))
    floors_gate.run(wb, cat, require_synthesis=True, require_challenge=False,
                    persist=False, qa_dir=run.qa_dir)
    assert len(run.open().rows("Gate_Log")) == before
    assert not (run.qa_dir / f"floors_{cat}.json").exists()


# ── it is in the projection that prices the run ────────────────────────

def test_lane_fit_models_the_challenger(tmp_path):
    run, wb, cells = _synthesised(tmp_path)
    fit = cost.lane_fit(wb)
    ch = fit["challenge"]
    assert ch["lane_turns"] == cost.lane_turn_budget(kind="challenge")
    assert ch["cells"] and ch["lanes"] >= 1
    assert isinstance(ch["fits"], bool)


def test_the_challenger_s_turn_budget_is_read_from_its_manifest():
    assert cost.lane_turn_budget(kind="challenge") == 60
    assert cost.lane_turn_budget() != cost.lane_turn_budget(kind="challenge")
