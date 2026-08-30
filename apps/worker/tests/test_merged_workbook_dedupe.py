"""A merged workbook states every cell twice, and one of them must win.

23 of the 154 corpus workbooks carry BOTH the assessment's
`P{n}_Subcap_Scoring` and the research layer's `P{n}_Scoring_Detail`, so the
parser emitted two `ParsedScore` rows per cell — 1,420 for a 710-cell
assessment.

What was already safe: `persist` deduplicates on its own (first row wins, the
repeat recorded) and counts a SET, so nothing was inserted twice and no stored
count was inflated. What was not: persist's first-wins is ALPHABETICAL, and
`sorted()` puts `P2_Scoring_Detail` ahead of `P2_Subcap_Scoring` — so the
research calculation chain outranked the tab the workbook's own
`Pillar_Summary` agrees with. Measured, the two tabs never disagree today, so
nothing served was wrong; the precedence was accidental, and the next merged
generation would have inherited it.

Authority was settled by asking the workbook rather than by assuming:
aggregating `P*_Subcap_Scoring` reproduces its stated `Pillar_Summary`
(2.13 / 2.45 / 2.08 / 2.26 against 2.13 / 2.44 / 2.08 / 2.25).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "worker"))

from dma_worker.workbook_parser import (Observation, ParsedScore,  # noqa: E402
                                        WorkbookParse, _dedupe_scores,
                                        _tab_rank)


def _score(sid, tab, row, value):
    return ParsedScore(subcap_id=sid, pillar_id="P1", category_id="P1C1",
                       capability_id="P1C1.1", name=None, tier=None,
                       score=value, source_cell=f"{tab}!D{row}",
                       evidence_quality=None, confidence=None, facets=[],
                       evidence_refs=[], rationale=None)


def _parse(*scores):
    r = WorkbookParse(scores=list(scores), observations=[], toggled_out=[])
    _dedupe_scores(r)
    return r


# ── precedence ────────────────────────────────────────────────────────
def test_the_assessment_tab_outranks_the_research_tab():
    assert _tab_rank("P1_Subcap_Scoring") < _tab_rank("P1_Scoring_Detail")


def test_every_precedence_token_is_reachable():
    """`scoring_detail` CONTAINS `scoring`, so listing the generic token first
    would make the specific one dead code and rank the research tab as though
    it were the assessment's. The ranks must be distinct."""
    ranks = [_tab_rank(t) for t in
             ("P1_Subcap_Scoring", "P1_Scoring_Detail", "P1_Detail", "P1_Scoring")]
    assert len(set(ranks)) == len(ranks), f"a token is unreachable: {ranks}"


def test_an_unknown_tab_ranks_last_rather_than_first():
    """A generation nobody has taught this parser must not silently outrank
    the assessment's own scoring tab."""
    assert _tab_rank("P1_Something_New") > _tab_rank("P1_Subcap_Scoring")


# ── the dedupe itself ─────────────────────────────────────────────────
def test_the_authoritative_tab_wins_regardless_of_read_order():
    """Read order is alphabetical, which puts the research tab FIRST. If this
    ever reverts to first-wins, the research chain serves."""
    r = _parse(_score("P1C1.1.1", "P1_Scoring_Detail", 2, 3.0),
               _score("P1C1.1.1", "P1_Subcap_Scoring", 2, 3.5))
    assert len(r.scores) == 1
    assert r.scores[0].source_cell == "P1_Subcap_Scoring!D2"
    assert str(r.scores[0].score) == "3.5"


def test_it_wins_in_the_other_read_order_too():
    r = _parse(_score("P1C1.1.1", "P1_Subcap_Scoring", 2, 3.5),
               _score("P1C1.1.1", "P1_Scoring_Detail", 2, 3.0))
    assert r.scores[0].source_cell == "P1_Subcap_Scoring!D2"


def test_a_disagreement_is_recorded_as_a_contradiction():
    r = _parse(_score("P1C1.1.1", "P1_Scoring_Detail", 2, 3.0),
               _score("P1C1.1.1", "P1_Subcap_Scoring", 2, 3.5))
    obs = [o for o in r.observations if o.kind == "duplicate_score_disagreement"]
    assert len(obs) == 1
    assert obs[0].detail["kept"]["score"] == "3.5"
    assert obs[0].detail["dropped"]["score"] == "3.0"
    assert "averaged" in obs[0].detail["resolution"], (
        "never average two disagreeing figures — the result is in no source")


def test_an_agreeing_repeat_is_a_different_observation():
    """A benign repeat and a genuine contradiction must not read the same: one
    is a merged file, the other is a workbook defect."""
    r = _parse(_score("P1C1.1.1", "P1_Scoring_Detail", 2, 3.5),
               _score("P1C1.1.1", "P1_Subcap_Scoring", 2, 3.5))
    kinds = [o.kind for o in r.observations]
    assert kinds == ["superseded_duplicate"]


def test_two_rows_on_ONE_sheet_keep_the_first_and_still_report():
    """All 13 disagreements in the corpus are this shape — the workbook itself
    lists a cell twice. Same rank, so first wins, and the conflict is still a
    finding about the workbook."""
    r = _parse(_score("P2C3.2.IC1", "P2_Subcap_Scoring", 154, 2.0),
               _score("P2C3.2.IC1", "P2_Subcap_Scoring", 155, 2.5))
    assert len(r.scores) == 1
    assert r.scores[0].source_cell == "P2_Subcap_Scoring!D154"
    assert [o.kind for o in r.observations] == ["duplicate_score_disagreement"]


def test_order_is_preserved():
    """Rule 10: order is meaning. Dedupe must not reshuffle the cells."""
    r = _parse(_score("P1C1.1.3", "P1_Subcap_Scoring", 4, 1.0),
               _score("P1C1.1.1", "P1_Scoring_Detail", 2, 3.0),
               _score("P1C1.1.2", "P1_Subcap_Scoring", 3, 2.0),
               _score("P1C1.1.1", "P1_Subcap_Scoring", 2, 3.0))
    assert [s.subcap_id for s in r.scores] == ["P1C1.1.3", "P1C1.1.1", "P1C1.1.2"]


def test_a_workbook_with_no_duplicates_is_untouched():
    rows = [_score(f"P1C1.1.{i}", "P1_Subcap_Scoring", i, 2.0) for i in (1, 2, 3)]
    r = _parse(*rows)
    assert len(r.scores) == 3 and r.observations == []
