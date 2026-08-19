"""Gate J's comparison rules, pinned.

The gate answers a question no contract gate can: does this client carry what
the client beside it carries? Three rounds of reports on one client — "this
page is empty", "this card is missing", "the reference has it and this one
does not" — were all true, all contract-legal, and all found by a human with
two browser tabs.

These tests pin the four judgements that make it useful rather than noisy:
structure is compared and values never are; a withheld section is a decision
and not a gap; an empty list is a gap because it renders as a blank card; and
a zero is an answer.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from gate_j_surface_parity import compare_page  # noqa: E402


def page(**sections):
    return {"sections": sections}


def sec(data, **extra):
    return {"data": data, **extra}


def kinds(gaps):
    return sorted((g["kind"], g["section"], g["key"]) for g in gaps)


def test_a_section_the_reference_fills_and_the_target_lacks_is_a_gap():
    ref = page(leadership=sec({"roster": [{"name": "A"}]}))
    tgt = page()
    assert kinds(compare_page("overview", ref, tgt)) == [
        ("section_absent", "leadership", None)]


def test_a_section_served_empty_is_a_gap_because_it_renders_blank():
    ref = page(leadership=sec({"roster": [{"name": "A"}]}))
    tgt = page(leadership=sec({}))
    assert kinds(compare_page("overview", ref, tgt)) == [
        ("section_empty", "leadership", None)]


def test_a_key_the_reference_carries_and_the_target_does_not():
    ref = page(scores=sec({"pillars": [1], "narrative_thread": "x"}))
    tgt = page(scores=sec({"pillars": [1]}))
    assert kinds(compare_page("overview", ref, tgt)) == [
        ("key_absent", "scores", "narrative_thread")]


def test_an_empty_list_on_a_key_the_reference_fills():
    ref = page(sentiment=sec({"bars": [1, 2], "themes": ["t"]}))
    tgt = page(sentiment=sec({"bars": [1], "themes": []}))
    assert kinds(compare_page("overview", ref, tgt)) == [
        ("key_empty", "sentiment", "themes")]


def test_values_are_never_compared():
    """Two clients are different companies. A thinner number is an assessment
    result; a gate that argued otherwise would push every client toward the
    reference's answers, which is the one thing this build must not do."""
    ref = page(scores=sec({"composite": 3.4, "pillars": [1, 2, 3, 4]}))
    tgt = page(scores=sec({"composite": 1.59, "pillars": [1]}))
    assert compare_page("overview", ref, tgt) == []


def test_a_withheld_section_is_a_decision_and_not_a_gap():
    """Otherwise every customer-audience run fails against an internal one,
    and the gate's whole output becomes the redaction rung table."""
    ref = page(ceilings=sec({"rows": [1]}))
    tgt = page(ceilings={"data": None, "withheld": True,
                         "never_served": True})
    assert compare_page("overview", ref, tgt) == []


def test_a_zero_is_an_answer_and_not_an_absence():
    """A computed count of zero is information. Treating it as missing is how
    a real zero gets reported as a drop."""
    ref = page(techstack=sec({"detected": 7, "confirmed": 3}))
    tgt = page(techstack=sec({"detected": 0, "confirmed": False}))
    assert compare_page("overview", ref, tgt) == []


def test_a_key_the_reference_leaves_empty_is_never_demanded():
    """The reference is a reference, not a floor for fields it does not
    carry itself."""
    ref = page(scores=sec({"pillars": [1], "peer_synthesis": None}))
    tgt = page(scores=sec({"pillars": [1]}))
    assert compare_page("overview", ref, tgt) == []


def test_the_extra_a_target_carries_is_not_a_finding():
    """Parity is one-directional: thinner than the reference is the defect,
    richer than it is not."""
    ref = page(scores=sec({"pillars": [1]}))
    tgt = page(scores=sec({"pillars": [1], "peer_synthesis": "more"}),
               extra=sec({"rows": [1]}))
    assert compare_page("overview", ref, tgt) == []


def test_several_gaps_are_all_reported_not_just_the_first():
    ref = page(a=sec({"x": [1], "y": [1]}), b=sec({"z": [1]}))
    tgt = page(a=sec({"x": [1]}))
    assert kinds(compare_page("overview", ref, tgt)) == [
        ("key_absent", "a", "y"), ("section_absent", "b", None)]
