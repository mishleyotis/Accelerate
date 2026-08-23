"""CG-45 — a card proposing a platform states the client's reach into it.

Owner, 2026-08-23: "The platform still ignores that Gulf has a lot of the
platform proposed. No work has been done to infer utilization."

Both halves of that sentence are one defect. Gulf licenses Salesforce and
Pardot already — its own intake brief asks for help ON THE EXISTING INSTANCE
— and four cards proposed the Salesforce family as though the estate were
empty. A card that has not looked at what the client holds is not a
recommendation, it is a catalogue page.

WHAT THIS GATE CANNOT DO, AND SAYS SO. It cannot check whether the reach is
RIGHT; no gate can. It checks that the card ANSWERED, with enough text to
carry a derivation, because naming the platform again is not an answer.

AND IT MUST NOT PUSH ANYONE INTO INVENTING UTILIZATION — which would be a
worse defect than the one it fixes. Login counts, seat counts and query
volumes are not visible from outside. The repaired cards say exactly that:
"nothing this run can reach shows how much of the licence is actually used
... and no claim is made about them". That is a complete answer and the
hardest-tested case here.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dma_mcp.validation2 as V2         # noqa: E402
from dma_mcp.validation2 import _REACH_MIN_CHARS  # noqa: E402


def run(page, cards):
    key, field = (("platform_story", "platforms") if page == "platform"
                  else ("opportunity", "tiles"))
    return V2._check_cards_state_their_reach(
        None, "run-1", page, {key: {field: list(cards)}})


def ids(out):
    return [r["gate_id"] for r in out]


# Gulf's own repaired tile prose, verbatim in the field the gate reads. It is
# the negative-finding shape the whole build turns on: what is held, how that
# was established, and separately what could not be seen.
GULF_UTILIZATION = (
    "GCBC already licenses Salesforce and Pardot: an intake brief requests "
    "support on that existing instance rather than a new purchase "
    "(E-GULFCOAS-011), and a search of current staff by function finds no "
    "dedicated admin or IT role behind it (E-GULFCOAS-025). On UTILIZATION, "
    "which is the question this card turns on: nothing this run can reach "
    "shows how much of the licence is actually used - there are no login "
    "counts, object volumes or administrator logs in any source available "
    "here, and no claim is made about them.")

# The structured half, as the platform page carries it.
GULF_ESTATE = {
    "e_ids": ["E-CC-232", "E-CC-235"],
    "derivation": "A cell counts as reached when the promoted technology "
                  "register lists it among a row's linked_subcap_ids. "
                  "Against this tile's 6 driving cells, 1 is reached.",
    "why_this_is_established": "CLAIMED rather than CONFIRMED: the register "
                              "grades this row from a 2013 implementation "
                              "announcement, not a first-party statement.",
    "products_holding_this_layer": ["CADENCE for Factoring (CLAIMED)"],
}


# ── the reported defect ───────────────────────────────────────────────

def test_a_platform_card_that_never_looked_at_the_estate_is_refused():
    out = run("platform", [{"platform": "Salesforce Platform Foundation",
                            "fit_score": 35.2}])
    assert ids(out) == ["CG-45"], out
    m = out[0]["message"]
    assert "Salesforce Platform Foundation" in m
    assert "already licenses part of what is being proposed" in m
    assert out[0]["severity"] == "block"


def test_an_overview_tile_that_never_looked_is_refused_too():
    """Either surface may be the one edited. The tile is where a reader meets
    the proposal first, so it cannot be the lenient one."""
    out = run("overview", [{"platform": "MuleSoft Anypoint", "composite": 76.6}])
    assert ids(out) == ["CG-45"]
    assert "MuleSoft Anypoint" in out[0]["message"]


def test_every_bare_card_is_named_not_just_the_first():
    out = run("platform", [{"platform": f"P{i}"} for i in range(4)])
    assert len(out) == 4
    assert [r["path"] for r in out] == [
        f"platform.platform_story.platforms[{i}].estate_reach"
        for i in range(4)]


# ── the answer that has to pass, tested hardest ───────────────────────

def test_an_unobservable_utilization_stated_as_such_passes():
    """THE LOAD-BEARING CASE. A gate that refused this would be demanding
    that someone invent seat counts, which is a worse defect than the one
    it fixes."""
    assert run("overview", [{"platform": "Salesforce Platform Foundation",
                             "their_stack_context": GULF_UTILIZATION}]) == []


def test_a_structured_estate_reach_passes():
    assert run("platform", [{"platform": "Salesforce Platform Foundation",
                             "estate_reach": GULF_ESTATE}]) == []


def test_an_empty_estate_stated_as_a_finding_passes():
    """A client who holds nothing in this area is a real answer, and the
    only thing separating it from a card nobody worked is that it says how
    it counted."""
    assert run("platform", [{"platform": "CRM Analytics", "estate_reach": {
        "derivation": "Against a catalogue-tagged set of 10 of this run's "
                      "served cells for this L3 area, the promoted register "
                      "carries no analytics or business-intelligence product "
                      "row at any status, so none is reached.",
        "products_holding_this_layer": []}}]) == []


@pytest.mark.parametrize("key", ["estate_reach", "their_stack_context",
                                 "current_estate"])
def test_the_answer_is_taken_from_whichever_field_carries_it(key):
    assert run("platform", [{"platform": "X", key: GULF_UTILIZATION}]) == []


# ── what does not count as an answer ──────────────────────────────────

def test_naming_the_platform_again_is_not_an_answer():
    out = run("platform", [{"platform": "Salesforce",
                            "their_stack_context": "Salesforce."}])
    assert ids(out) == ["CG-45"]
    assert f"needs {_REACH_MIN_CHARS}" in out[0]["message"]


def test_the_floor_is_low_and_non_zero():
    """Low on purpose — this is not a word count on quality. Non-zero on
    purpose — a token string is the shape a placeholder takes."""
    assert 0 < _REACH_MIN_CHARS <= 200


def test_a_sentence_that_actually_derives_something_clears_it():
    said = ("The promoted register carries DocuSign eSignature as CONFIRMED "
            "against two of this tile's nineteen tagged cells; nothing else "
            "in the estate reaches this area, and no usage figure is visible.")
    assert len(said) >= _REACH_MIN_CHARS
    assert run("platform", [{"platform": "X", "their_stack_context": said}]) == []


@pytest.mark.parametrize("empty", [None, "", "   ", {}, [], 0])
def test_an_empty_reach_field_is_the_same_as_none(empty):
    assert ids(run("platform", [{"platform": "X",
                                 "estate_reach": empty}])) == ["CG-45"]


# ── scope and safety ──────────────────────────────────────────────────

def test_no_other_page_is_touched():
    for page in ("heatmap", "context", "techstack", "insights"):
        assert V2._check_cards_state_their_reach(
            None, "run-1", page,
            {"platform_story": {"platforms": [{"platform": "X"}]}}) == []


def test_a_page_with_no_cards_is_not_a_finding():
    assert run("platform", []) == []
    assert V2._check_cards_state_their_reach(None, "r", "platform", {}) == []
    assert V2._check_cards_state_their_reach(None, "r", "overview", {}) == []


@pytest.mark.parametrize("bad", [None, [], "x", 42,
                                 {"platform_story": "not-a-dict"},
                                 {"platform_story": {"platforms": "no"}}])
def test_malformed_shapes_do_not_crash_the_gate(bad):
    V2._check_cards_state_their_reach(None, "run-1", "platform", bad)


def test_non_dict_cards_are_skipped_not_crashed():
    assert run("platform", ["x", None, 7]) == []


def test_the_finding_list_is_bounded():
    out = run("platform", [{"platform": f"P{i}"} for i in range(40)])
    assert len(out) <= 6, "a verdict nobody can read is a verdict nobody acts on"


def test_the_gate_is_registered_with_its_family_and_severity():
    from dma_mcp.gates import GATES
    assert "CG-45" in GATES
    assert GATES["CG-45"][-1] == "block"
    why = GATES["CG-45"][3].lower()
    assert "utilization" in why
    assert "catalogue page" in why
    assert "inventing utilization" in why, (
        "the registry says what the gate must NOT push anyone into, so "
        "nobody tightens it into demanding invented seat counts later")


def test_it_runs_inside_pass_two():
    import inspect
    src = inspect.getsource(V2.validate_pass2)
    assert "_check_cards_state_their_reach" in src, \
        "CG-45 is defined but never dispatched"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
