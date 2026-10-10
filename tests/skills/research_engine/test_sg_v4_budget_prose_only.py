"""The driver's SG-V4 budget counts prose, never the evidence itself.

A verbatim excerpt, a client quote or a source's name is what the page cites,
not a claim about it: its embedding drifting below the grounding threshold is
not ungrounded prose a producer can re-ground. Counting those fields made a
thin-evidence page unshippable (Arbor Bank, 2026-10-06: 660 of the heatmap's
789 FAILs sat on them), so the budget reads only the prose fields.
"""
from __future__ import annotations

from engine import pipeline as P


def _fail(path):
    return {"path": path, "similarity": 0.41, "threshold": 0.55}


def test_verbatim_fields_do_not_count():
    fails = [_fail(p) for p in (
        "cell_evidence.cells[3].items[0].excerpt",
        "evidence.evidence[12].excerpt",
        "evidence.evidence[12].source_name",
        "cell_evidence.cells[3].items[1].source_title",
        "cell_evidence.cells[3].provenance.source",
        "evidence_age.rows[4].title",
        "focus_areas.focus_areas[0].verbatim_quote",
        "techstack.items[2].product",
        "techstack.dropped[0].candidate",
    )]
    assert P.prose_sg_v4_fails(fails) == []


def test_prose_fields_still_count():
    prose = [_fail(p) for p in (
        "cell_evidence.cells[3].synthesis",
        "cell_evidence.cells[3].reach_note",
        "techstack.items[0].detection_basis",
        "techstack.items[0].peer_deployments[1].basis",
        "focus_areas.focus_areas[0].r_layer.counter",
        "alerts.narrative_thread",
    )]
    mixed = prose + [_fail("evidence.evidence[0].excerpt")]
    assert P.prose_sg_v4_fails(mixed) == prose


def test_a_leaf_that_only_contains_a_verbatim_word_counts():
    # `source_note` and `title_rationale` are prose ABOUT a source/title.
    fails = [_fail("x.items[0].source_note"), _fail("x.title_rationale")]
    assert P.prose_sg_v4_fails(fails) == fails


def test_the_budget_default_is_unchanged():
    assert P.Options.__dataclass_fields__["sg_v4_budget"].default == 8
