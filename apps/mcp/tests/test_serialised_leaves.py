"""CG-21 — a payload leaf is the value, not a serialisation of it.

Measured 2026-08-14: a promoted run carried
`platform.stairstep.ladder.steps[*].blocking_findings` as JSON-ENCODED
STRINGS — `'{"f_id": "F-1", "e_ids": ["E-CC-139"]}'` — where the contract asks
for finding ids. The frontend printed each item into a chip verbatim, so the
stair-step ladder showed literal JSON to the AE.

The reason this needs its own gate rather than a widening of CG-03: CG-03 asks
whether a list's items are the declared type, and a serialised object IS a
valid string. Every type check in the module is structurally blind to it.

The predicate is narrow on purpose. The false-positive tests below carry the
prose shapes this corpus actually contains — sentences with braces, ranges in
brackets, a bare figure — because a gate that refuses real prose is a gate the
producer learns to route around.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation import (_check_serialised_leaves,
                                _looks_like_serialised_json)


def _run(body, section="stairstep"):
    return _check_serialised_leaves(section, body)


# ── the shape that actually promoted ──────────────────────────────────
def test_the_promoted_shape_is_refused():
    """Verbatim from the withdrawn run."""
    body = {"ladder": {"steps": [
        {"step_level": 1, "blocking_findings": []},
        {"step_level": 2, "blocking_findings":
            ['{"f_id": "F-1", "e_ids": ["E-CC-139"]}']},
    ]}}
    out = _run(body)
    assert len(out) == 1
    assert out[0]["gate_id"] == "CG-21"
    assert out[0]["severity"] == "block"
    assert out[0]["path"] == "stairstep.ladder.steps[1].blocking_findings[0]"


def test_the_clean_shape_passes():
    """The reference client's ladder: bare finding ids on every step. Measured
    against the deployed API 2026-08-14 — 0 serialised leaves in 11 live
    projections."""
    body = {"ladder": {"steps": [
        {"step_level": 1, "blocking_findings": []},
        {"step_level": 2, "blocking_findings": ["F-2"]},
        {"step_level": 3, "blocking_findings": ["F-1", "F-2"]},
        {"step_level": 4, "blocking_findings": ["F-1", "F-3"]},
    ]}}
    assert _run(body) == []


def test_the_reason_names_what_to_send_instead():
    out = _run({"x": '{"a": 1}'})
    assert "SERIALISED" in out[0]["message"]
    assert "Send the value" in out[0]["message"]


def test_the_reason_quotes_the_offending_leaf():
    out = _run({"x": '{"f_id": "F-1"}'})
    assert "f_id" in out[0]["message"]


def test_it_names_object_and_array_distinctly():
    assert "JSON object" in _run({"x": '{"a": 1}'})[0]["message"]
    assert "JSON array" in _run({"x": '["a", "b"]'})[0]["message"]


# ── every leaf, however deep ──────────────────────────────────────────
def test_it_reaches_a_leaf_nested_below_lists_and_dicts():
    body = {"a": [{"b": {"c": [{"d": '[1, 2, 3]'}]}}]}
    out = _run(body)
    assert len(out) == 1
    assert out[0]["path"] == "stairstep.a[0].b.c[0].d"


def test_every_offending_leaf_is_reported_not_just_the_first():
    body = {"p": ['{"a": 1}', "fine", '{"b": 2}']}
    out = _run(body)
    assert len(out) == 2
    assert [r["path"] for r in out] == ["stairstep.p[0]", "stairstep.p[2]"]


# ── prose the corpus contains must keep passing ───────────────────────
def test_prose_mentioning_a_brace_is_not_json():
    for s in ("The estate is {mostly} on-premise",
              "Growth of [15-20%] year over year",
              "{",
              "[",
              "[redacted]",
              "Data Management >= 1.5 with a named owner — met at 1.95"):
        assert _run({"x": s}) == [], s


def test_a_leaf_that_parses_to_a_scalar_is_left_alone():
    """A bare number or a quoted word parses as JSON but is not a
    serialisation of a STRUCTURE, which is the defect this gate names."""
    for s in ("42", "true", "null", '"a quoted word"', "2.71"):
        assert not _looks_like_serialised_json(s), s
        assert _run({"x": s}) == [], s


def test_an_empty_or_whitespace_leaf_does_not_raise():
    assert _run({"a": "", "b": "   ", "c": None}) == []


def test_an_empty_structure_is_still_a_serialisation():
    """An earlier draft carved these out, reasoning that CG-19 owns emptiness
    and two gates should not fire on one leaf. Wrong on both counts: CG-19
    judges an empty LIST FIELD, not a string that happens to contain '{}', so
    there is nothing to collide with — and '{}' in a string slot is a
    serialisation whatever it serialises. The rule stays "parses as a
    structure", with no exception to remember."""
    assert len(_run({"x": "{}"})) == 1
    assert len(_run({"x": "[]"})) == 1


def test_non_string_leaves_are_not_this_gate_s_business():
    """A real list or dict in the payload is the CORRECT shape."""
    assert _run({"blocking_findings": [{"f_id": "F-1"}]}) == []
    assert _run({"n": 42, "b": True, "z": None}) == []


# ── registered so a verdict can be explained ──────────────────────────
def test_it_is_registered():
    from dma_mcp.gates import GATES
    assert "CG-21" in GATES and GATES["CG-21"][-1] == "block"


def test_it_runs_inside_pass1():
    """The walker is wired into the per-section sweep, not merely defined —
    the failure mode this whole file exists for is a check nobody called."""
    import inspect

    from dma_mcp import validation
    src = inspect.getsource(validation.validate_pass1)
    assert "_check_serialised_leaves" in src
