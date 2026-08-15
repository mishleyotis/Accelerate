"""AG-09 — a rank that contradicts its own score has to say why.

Measured on a promoted run, 2026-08-15: the platform set served rank 2 at fit
70.0 and rank 3 at fit 73.0. The acceptance document names it twice (BAX-24,
BAX-10) as "fit-70 ranked above fit-73" and calls it a defect.

Reading the run rather than the complaint, it is not an arithmetic error. That
producer ranks on DEPENDENCY and writes the reason down — "ranked third because
its value multiplies after the data layer lands" — and a dependency order that
disagrees with a weighted composite is the correct answer for a sequence a
client will actually execute. Refusing every inversion would force the producer
to sort, and the R-Layer's whole point is that a ranking which cannot discard is
a sort.

So the gate refuses the narrow thing: an inversion with nothing beside it. The
frontend now renders `rank_rationale` and names the inversion outright; this is
the promotion-side half, because a page can only render a reason the payload
carries.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import _check_rank_against_score  # noqa: E402


def payload(platforms):
    return {"sections": {"platform_story": {"data": {"platforms": platforms}}}}


def P(name, rank, fit, **kw):
    row = {"platform": name, "rank": rank, "fit_score": fit}
    row.update(kw)
    return row


def gates(rows, page="platform"):
    return [r["gate_id"] for r in _check_rank_against_score(page, payload(rows))]


def test_a_clean_descending_set_passes():
    assert gates([P("A", 1, 90.0), P("B", 2, 80.0), P("C", 3, 70.0)]) == []


def test_an_inversion_with_no_basis_is_refused():
    out = _check_rank_against_score("platform", payload([
        P("A", 1, 76.5, fit_basis="rank-1 tile"),
        P("B", 2, 70.0, fit_basis="rank-2 tile"),
        P("C", 3, 73.0),                       # scores above rank 2, says nothing
    ]))
    assert [r["gate_id"] for r in out] == ["AG-09"]
    m = out[0]["message"]
    # Invariant 12: the verdict names the gate, the JSON path and the
    # arithmetic. A verdict that says "ranking is inconsistent" sends the
    # producer looking; one that quotes both pairs sends it to the row.
    assert "'C'" in m and "'B'" in m
    assert "73" in m and "70" in m
    assert out[0]["path"] == "platform_story.platforms[2].fit_basis"


def test_an_inversion_that_states_its_basis_passes():
    """The live shape. This is the case that must NOT fail, or the producer is
    forced to sort by a number it deliberately ranks against."""
    assert gates([
        P("A", 1, 76.5, fit_basis="Read from the opportunity engine's rank-1 tile."),
        P("B", 2, 70.0, fit_basis="Read from the rank-2 tile and not recomputed."),
        P("C", 3, 73.0, fit_basis="Read from the rank-3 tile; sequenced after the "
                                  "data layer it depends on."),
    ]) == []


def test_story_md_is_accepted_as_the_longer_form_of_the_basis():
    assert gates([
        P("A", 1, 70.0),
        P("B", 2, 73.0, story_md="It lands after the data layer it reads through."),
    ]) == []


def test_an_empty_or_whitespace_basis_is_not_a_basis():
    for blank in ("", "   ", "\n", None):
        out = gates([P("A", 1, 70.0), P("B", 2, 73.0, fit_basis=blank)])
        assert out == ["AG-09"], f"{blank!r} was accepted as an ordering basis"


def test_rows_missing_either_number_are_skipped_not_failed():
    """A null rank or a null fit is a different finding. Manufacturing an
    inversion out of two nulls would be a derived value that is neither
    computed nor null (invariant 9)."""
    assert gates([
        P("A", 1, 70.0),
        P("B", None, 73.0),          # unranked: the fifth platform on the live run
        P("C", 3, None),             # no fit figure
        P("D", None, None),
    ]) == []


def test_equal_scores_are_not_an_inversion():
    """Strictly below. Two platforms at the same fit are ordered by something
    else by definition, and that is not a contradiction to explain."""
    assert gates([P("A", 1, 70.0), P("B", 2, 70.0)]) == []


def test_every_inverted_row_is_named_not_just_the_first():
    out = gates([
        P("A", 1, 60.0),
        P("B", 2, 70.0),             # inverted vs A
        P("C", 3, 80.0),             # inverted vs A and B
    ])
    assert out == ["AG-09", "AG-09"], (
        "one verdict per offending row: a producer repairing the first and "
        "resubmitting must not discover the second on the next round trip")


@pytest.mark.parametrize("page", ["overview", "insights", "heatmap",
                                  "context", "techstack"])
def test_the_gate_is_scoped_to_its_page(page):
    assert gates([P("A", 1, 70.0), P("B", 2, 73.0)], page=page) == []


def test_a_malformed_section_does_not_raise():
    """Submissions arrive malformed; a gate that throws takes the whole
    verdict with it and the producer learns nothing."""
    for junk in ({}, {"sections": {}}, {"sections": {"platform_story": None}},
                 {"sections": {"platform_story": {"data": {"platforms": "x"}}}},
                 {"sections": {"platform_story": {"data": {"platforms": [None, 3]}}}}):
        assert _check_rank_against_score("platform", junk) == []
    # rank/fit that will not parse as numbers are skipped, not crashed on
    assert gates([P("A", "first", 70.0), P("B", 2, "high")]) == []


def test_the_gate_is_registered_with_its_arithmetic():
    from dma_mcp.gates import GATES
    assert "AG-09" in GATES, "a gate a verdict can name must be in the registry"
    title, plain, rule, why, severity = GATES["AG-09"]
    assert severity == "block", "an unexplained contradiction does not disclose"
    assert plain is None, "AG is an analysis gate; SG is the family that renders"
    assert "fit_basis" in rule and "story_md" in rule
