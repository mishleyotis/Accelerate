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


def test_a_publisher_name_or_domain_is_a_label_not_prose():
    """R-INTERAC-20261010 heatmap: 9 of 20 counted FAILs were a publisher
    name ("LinkedIn", sim 0.287) or an evidence row's domain — labels of the
    same class as source_name and url, which no producer can re-ground."""
    from engine import pipeline as P
    fails = ["cell_evidence.cells[181].items[0].publisher (sim 0.287 < 0.5)",
             "evidence_age.rows[273].source_domain (sim 0.29 < 0.5)",
             "cell_evidence.cells[248].synthesis (sim 0.591 < 0.62)"]
    paths = [f.split(" (sim")[0] for f in fails]
    assert P.prose_sg_v4_fails(paths) == ["cell_evidence.cells[248].synthesis"]


def test_a_peer_name_on_a_peer_deployment_is_a_label_not_prose():
    """R-INTERAC-20261010 techstack B (2026-10-12): 8 of 106 counted FAILs
    were peer names; the basis beside each stays counted as prose."""
    from engine import pipeline as P
    fails = [{"path": "techstack.items[3].peer_deployments[1].peer", "similarity": 0.2},
             {"path": "techstack.items[3].peer_deployments[1].basis", "similarity": 0.3}]
    assert [w["path"] for w in P.prose_sg_v4_fails(fails)] == [
        "techstack.items[3].peer_deployments[1].basis"]
