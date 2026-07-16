"""Tab-09 rubric contract tests (bands, hard-fails, ask arithmetic, swap test)."""
import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")

import pytest

from app.services.nlp.grader import Item
from app.services.nlp.knowledge import EntityKnowledge, Evidence
from app.services.nlp.rubric100 import (
    WEIGHTS,
    band_for,
    entity_swap_generic,
    score_item,
)


class _FakeState:
    """Minimal grader-compatible state for pure-logic tests."""

    def __init__(self, excerpts: dict[str, str] | None = None):
        self.name = "Testable Bank"
        self.subvertical = "RB"
        self._excerpts = excerpts or {}
        self.capabilities = []
        self.why_now_signals = []
        self.top_findings = []
        self.all_score_values = {2.8, 3.1}
        self.knowledge = EntityKnowledge(
            [Evidence(e_id=k, text=v) for k, v in self._excerpts.items()])

    def in_scope(self, sid):
        return True

    def capability(self, sid):
        return None

    def evidence_excerpt(self, e_id):
        return self._excerpts.get(e_id)

    @property
    def catalogue_subcap_names(self):
        return set()


def test_band_boundaries():
    assert band_for(90.0) == "GOLD"
    assert band_for(89.9) == "SHIP_WITH_NOTES"
    assert band_for(80.0) == "SHIP_WITH_NOTES"
    assert band_for(79.9) == "REVISE"
    assert band_for(65.0) == "REVISE"
    assert band_for(64.9) == "REJECT"


def test_weights_sum_to_100():
    assert sum(WEIGHTS.values()) == 100


def _score(what: str, so_what: str = "Deploy the platform this quarter.",
           e_ids: list[str] | None = None,
           excerpts: dict[str, str] | None = None):
    state = _FakeState(excerpts or {})
    item = Item(surface="insight_card", title="A grounded claim",
                what=what, why="Because the mechanism compounds.",
                so_what=so_what, e_ids=e_ids or [])
    return score_item(item, state, surface="insight_card")


def test_dims_bounded_by_weights():
    r = _score("Members repeat themselves across three channels. "
               "The cores never merged. Insight outruns action.",
               e_ids=["E-001"],
               excerpts={"E-001": "Three production cores run in parallel."})
    assert set(r.dims) == set(WEIGHTS)
    for dim, marks in r.dims.items():
        assert 0.0 <= marks <= WEIGHTS[dim]
    assert sum(r.dims.values()) <= 100.0


@pytest.mark.parametrize("what,expected_fail", [
    ("The ERS score is 0.86 and INT-AE notes confirm it.", "internal_leakage"),
    ("Modernize now or else you will lose members and fall behind competitors.",
     "threat_tone"),
    ("Assets grew 12% to $4.2B last year across the book.", "uncited_number"),
])
def test_hard_fails_zero_the_score(what, expected_fail):
    r = _score(what, e_ids=["E-001"],
               excerpts={"E-001": "An unrelated excerpt about branch counts."})
    assert expected_fail in r.hard_fails
    assert r.total == 0.0
    assert r.band == "REJECT"


def test_uncited_number_passes_when_quoted():
    r = _score("Assets grew to $4.2B last year.",
               e_ids=["E-001"],
               excerpts={"E-001": "The annual report states assets of $4.2B."})
    assert "uncited_number" not in r.hard_fails


def test_ask_marks_arithmetic():
    r = _score("First sentence with detail. Second sentence with more. "
               "Third closes the loop.",
               e_ids=["E-001"],
               excerpts={"E-001": "First sentence with detail evidence."})
    n = len(r.ask_marks)
    passed = sum(1 for ok in r.ask_marks.values() if ok)
    assert r.dims["self_interrogation"] == pytest.approx(
        WEIGHTS["self_interrogation"] * passed / n, abs=0.01)


def test_entity_swap_generic():
    generic = ("The bank has a clear opportunity to close the gap and "
               "prioritize modernization across channels.")
    specific = ("Farm Credit Mid-America runs Fiserv DNA and nCino with "
                "$48.9B assets [E-063].")
    assert entity_swap_generic(generic, "Testable Bank") is True
    assert entity_swap_generic(specific, "Farm Credit Mid-America") is False


def test_score_mutation_hard_fail():
    r = _score("The maturity score of 4.9 against the peer median proves it.",
               e_ids=["E-001"],
               excerpts={"E-001": "The maturity score of 4.9 was recorded."})
    assert "score_mutation" in r.hard_fails
    assert r.total == 0.0


def test_known_score_not_mutation():
    r = _score("The maturity score of 2.8 against a peer median of 3.1 holds.",
               e_ids=["E-001"],
               excerpts={"E-001": "Scored 2.8 against a peer median of 3.1."})
    assert "score_mutation" not in r.hard_fails
