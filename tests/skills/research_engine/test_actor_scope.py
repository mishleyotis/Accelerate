"""An actor writes its own work, and the engine is what says so.

Measured 2026-09-14: no write path in the engine checked cell ownership.
`append_evidence` and `append_search` took no actor at all; the others took
one and used it only for attribution and independence. The only cell-scope
refusal was run-membership. So a category lane could write every other
category's rows — sixteen lanes, one workbook, in parallel — and the
containment was three sentences of prose in a SessionStart brief.

These pin the rule table (`engine/scope.py`), one refusal per rule and one
allowed case per actor class, and the two exceptions that are deliberate:
the servicing tier retrieves across the whole run, and an actor the table
does not recognise is not governed by it.
"""
from __future__ import annotations

import pytest

from engine import ledger as L, scope


# ── the table ──────────────────────────────────────────────────────────

def test_a_category_researcher_is_scoped_to_its_own_category():
    assert scope.classify("research-p1c1-producer") == {
        "actor": "research-p1c1-producer", "class": "category-researcher",
        "scope": "P1C1"}


def test_a_pillar_scorer_is_scoped_to_its_own_pillar():
    assert scope.classify("scoring-p3-producer")["scope"] == "P3"


@pytest.mark.parametrize("actor,cls", [
    ("research-challenger", "challenger"),
    ("finding-challenger", "challenger"),
    ("research-conductor", "servicing"),
    ("enrichment-web-specialist", "servicing"),
    ("enrichment-connector-specialist", "servicing"),
    ("scoring-critic", "critic"),
    ("technographic-scanner", "technographic-scanner"),
])
def test_the_named_tiers_classify(actor, cls):
    assert scope.classify(actor)["class"] == cls


@pytest.mark.parametrize("actor", [
    "", None, "a-person", "research-orchestrator", "research-p2c4-challenger",
    "surface-producer", "reviewer-beta"])
def test_an_actor_the_table_does_not_know_is_not_governed_by_it(actor):
    """The closed vocabulary is the set of agents this repo DISPATCHES. A
    name it has never heard of must not be refused by a table that cannot
    describe it — that would refuse every human repair."""
    assert scope.classify(actor)["class"] == ""
    assert scope.violation(actor, "synthesis", ["P9C9.1.1"]) == ""


# ── the refusals, one per rule ─────────────────────────────────────────

def test_a_lane_may_not_write_another_category_s_cell():
    why = scope.violation("research-p1c1-producer", "evidence", ["P3C2.4.1"])
    assert "only P1C1 cells" in why and "P3C2.4.1" in why


def test_a_lane_may_write_its_own_cells():
    assert scope.violation("research-p1c1-producer", "evidence",
                           ["P1C1.1.1", "P1C1.2.3"]) == ""


def test_a_lane_may_not_challenge_at_all():
    """A challenge is the one judgement a lane must not make about its own
    work, and the tier that makes it is dispatched separately."""
    assert "may not challenge" in scope.violation(
        "research-p1c1-producer", "challenge", ["P1C1.1.1"])


def test_a_challenger_judges_any_cell_and_writes_nothing_else():
    assert scope.violation("research-challenger", "challenge", ["P4C4.1.1"]) == ""
    assert "may not synthesis" in scope.violation(
        "research-challenger", "synthesis", ["P4C4.1.1"])
    assert "may not evidence" in scope.violation(
        "research-challenger", "evidence", ["P4C4.1.1"])


def test_the_servicing_tier_retrieves_anywhere_and_judges_nothing():
    """THE CORRELATION POINT. The conductor draining a relay batch logs
    searches and registers evidence against any cell in the run — that is
    how one lane's find reaches another lane's cell."""
    for actor in ("research-conductor", "enrichment-web-specialist"):
        assert scope.violation(actor, "search", ["P1C1.1.1", "P3C2.4.1"]) == ""
        assert scope.violation(actor, "evidence", ["P1C1.1.1", "P3C2.4.1"]) == ""
        assert "may not synthesis" in scope.violation(
            actor, "synthesis", ["P1C1.1.1"])
        assert "may not absence" in scope.violation(actor, "absence", ["P1C1.1.1"])


def test_a_scorer_scores_only_its_own_pillar():
    assert scope.violation("scoring-p1-producer", "score", ["P1C1.1.1"]) == ""
    assert "only P1 cells" in scope.violation(
        "scoring-p1-producer", "score", ["P2C1.1.1"])


def test_an_op_the_table_does_not_govern_is_not_refused():
    assert scope.violation("research-p1c1-producer", "backup", ["P3C2.4.1"]) == ""


# ── the engine raises it, not just the table ───────────────────────────

def _two_category_run(tmp_path):
    from fixtures import new_run, two_category_selection
    run = new_run(tmp_path, selected=two_category_selection())
    wb = run.open()
    foreign = [c for c in wb.selected_subcaps() if not c.startswith("P1C1")]
    assert foreign, "fixture must span two categories"
    return run, wb, foreign


def test_the_ledger_refuses_a_foreign_search(tmp_path):
    run, wb, foreign = _two_category_run(tmp_path)
    with pytest.raises(L.LedgerRefusal) as e:
        L.append_search(wb, subcap=foreign[0], facet="works", query="q",
                        tool="exa", hits=1, kept=1,
                        actor="research-p1c1-producer")
    assert "only P1C1 cells" in str(e.value)


def test_the_ledger_refuses_foreign_evidence(tmp_path):
    run, wb, foreign = _two_category_run(tmp_path)
    with pytest.raises(L.LedgerRefusal) as e:
        L.append_evidence(wb, source_name="Acme 2025 annual report",
                          source_url="https://acme.example/ar2025",
                          tier="T1", excerpt="x" * 120, subcaps=[foreign[0]],
                          actor="research-p1c1-producer")
    assert "only P1C1 cells" in str(e.value)


def test_the_servicing_tier_may_register_across_categories(tmp_path):
    """The same write, by the actor whose job it is."""
    from fixtures import new_run
    run = new_run(tmp_path, n=6)
    wb = run.open()
    cells = wb.selected_subcaps()[:2]
    eid = L.append_evidence(wb, source_name="Acme 2025 annual report",
                            source_url="https://acme.example/ar2025",
                            tier="T1", excerpt="y" * 120, subcaps=list(cells),
                            actor="enrichment-web-specialist")
    assert eid


def test_a_write_with_no_actor_is_unchanged(tmp_path):
    """Every existing caller passes none; the check must not invent one."""
    from fixtures import new_run
    run = new_run(tmp_path, n=6)
    wb = run.open()
    assert L.append_search(wb, subcap=wb.selected_subcaps()[-1], facet="works",
                           query="q", tool="exa", hits=1, kept=1) >= 1
