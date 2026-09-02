"""CG-44 — a peer figure the assessment holds reaches the overview strip.

Owner, 2026-08-23: "For Gulf and Axos, the overview has no peer scores which
have not been cascaded from the heatmaps."

Neither surface was wrong in isolation, which is exactly why nothing caught
it. The heatmap's focus areas carried `peer_score`; the overview's pillar
strip drew the entity's own bar alone. A figure the assessment already held
stopped one page short of the page where a reader forms the comparison —
the same shape as CG-39 (recommendations written, never served) and CG-43
(one dataset, two drifting projections).

THE SECOND HALF IS WHAT KEEPS IT HONEST. A cascade gate that only counted
fields would be satisfied by three numbers that do not agree with each other.
Where a row states its own score and a peer median, the delta is derived, and
a derived value is computed or null — never restated, never a default that
looks like data (invariant 9).

Fixtures are the two runs' own promoted shapes: axos-bank cascades with
peer_n 3, gulf-coast-business-credit cascades pillar medians while its focus
areas carry peer_score null throughout, because the workbook states no
area-level cohort. Both are correct and both must pass.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dma_mcp.validation2 as V2         # noqa: E402
from dma_mcp.validation2 import PEER_DELTA_TOLERANCE  # noqa: E402


def run(monkeypatch, payload, heatmap=None, page="overview"):
    monkeypatch.setattr(V2, "_live_submission",
                        lambda conn, run_id, p: heatmap)
    return V2._check_peer_scores_cascade(None, "run-1", page, payload)


def ids(out):
    return [r["gate_id"] for r in out]


def strip(*pillars):
    return {"scores": {"pillars": list(pillars)}}


def heatmap(*peers):
    return {"focus_areas": {"focus_areas":
                            [{"fa_id": f"FA-{i}", "peer_score": p}
                             for i, p in enumerate(peers)]}}


# axos-bank's own first pillar row, verbatim in the fields the gate reads.
AXOS_P1 = {"pillar_id": "P1", "score": 2.02, "peer_median": 3.5,
           "delta": -1.48, "direction": "below", "peer_n": 3}
# gulf's, which carries the same shape with an honestly-null cohort size.
GULF_P1 = {"pillar_id": "P1", "score": 1.86, "peer_median": 3.0,
           "delta": -1.14, "direction": "below", "peer_n": None}


# ── the reported defect ───────────────────────────────────────────────

def test_a_strip_with_no_peers_beside_a_heatmap_with_peers_is_refused(monkeypatch):
    """The owner's sentence, exactly."""
    out = run(monkeypatch,
              strip({"pillar_id": "P1", "score": 2.02},
                    {"pillar_id": "P2", "score": 1.85}),
              heatmap(4.0, 3.5, 4.0))
    assert ids(out) == ["CG-44"], out
    m = out[0]["message"]
    assert "3 focus area(s) with a peer score" in m
    assert "median 4.00" in m, "the gate shows the figure it is asking to see"
    assert out[0]["severity"] == "block"


def test_cascading_one_pillar_clears_the_silence(monkeypatch):
    """Deliberately weak on the count: this half catches the whole set being
    dropped, not a judgement about which pillars deserve a peer."""
    assert run(monkeypatch,
               strip(AXOS_P1, {"pillar_id": "P2", "score": 1.85}),
               heatmap(4.0, 3.5)) == []


def test_a_named_reason_is_as_good_as_a_cascade(monkeypatch):
    """Area-level peers need not roll up to a pillar. Saying so is a real
    answer — the same escape CG-40 keeps, for the same reason."""
    body = strip({"pillar_id": "P1", "score": 2.02})
    body["scores"]["empty_state"] = {
        "reason": "the workbook's cohort figures are stated per focus area "
                  "and carry no pillar roll-up, so none is asserted here",
        "sources_searched": ["Pillar_Summary sheet", "peer cohort table"]}
    assert run(monkeypatch, body, heatmap(4.0)) == []


# ── the arithmetic half ───────────────────────────────────────────────

def test_a_restated_delta_that_drifts_from_its_operands_is_refused(monkeypatch):
    out = run(monkeypatch, strip(dict(AXOS_P1, delta=-0.9)))
    assert ids(out) == ["CG-44"]
    assert "2.02 - 3.5 = -1.48" in out[0]["message"]
    assert "different row" in out[0]["message"]


def test_a_delta_left_null_with_both_operands_present_is_refused(monkeypatch):
    """Invariant 9: derived values are computed or null — and null is only
    honest when the value cannot be derived. Here it can."""
    out = run(monkeypatch, strip(dict(AXOS_P1, delta=None)))
    assert ids(out) == ["CG-44"]
    assert "-1.48" in out[0]["message"]
    assert "one line of arithmetic" in out[0]["message"]


def test_display_rounding_is_not_a_disagreement(monkeypatch):
    for delta in (-1.48, -1.5, -1.44):
        assert run(monkeypatch, strip(dict(AXOS_P1, delta=delta))) == [], delta


def test_the_tolerance_is_the_contracts_grain_tolerance():
    assert PEER_DELTA_TOLERANCE == 0.05


def test_a_direction_word_that_contradicts_its_own_bar_is_refused(monkeypatch):
    out = run(monkeypatch, strip(dict(AXOS_P1, direction="above")))
    assert ids(out) == ["CG-44"]
    assert "'above'" in out[0]["message"] and "'below'" in out[0]["message"]


@pytest.mark.parametrize("score,peer,delta,word", [
    (2.02, 3.50, -1.48, "below"),
    (3.90, 3.50, 0.40, "above"),
    (3.50, 3.50, 0.00, "at"),
    (3.50, 3.50, 0.00, "level"),
])
def test_every_direction_word_that_matches_passes(monkeypatch, score, peer,
                                                  delta, word):
    assert run(monkeypatch, strip({"pillar_id": "P1", "score": score,
                                   "peer_median": peer, "delta": delta,
                                   "direction": word})) == []


def test_an_absent_direction_is_not_a_finding(monkeypatch):
    """Optional field. The delta already carries the sign; a gate that
    demanded the word would be inventing a contract requirement."""
    row = dict(AXOS_P1)
    row.pop("direction")
    assert run(monkeypatch, strip(row)) == []


# ── the two live runs, which are both correct ─────────────────────────

def test_gulf_passes_though_its_focus_areas_carry_no_peer(monkeypatch):
    """Honest in both directions: peer_score null throughout because the
    workbook states no area-level cohort, and the strip still carries pillar
    medians with peer_n null rather than a guessed cohort size."""
    assert run(monkeypatch, strip(GULF_P1),
               heatmap(None, None, None)) == []


def test_axos_passes_as_promoted(monkeypatch):
    assert run(monkeypatch, strip(AXOS_P1), heatmap(4.0, 4.0, 2.3)) == []


def test_a_null_peer_score_is_not_a_peer_figure(monkeypatch):
    """A row saying it has no peer is not a row holding one, so it cannot
    make the overview's silence a finding."""
    assert V2._heatmap_peer_scores({"focus_areas":
                                    [{"peer_score": None},
                                     {"peer_score": True}]}) == []


# ── scope and safety ──────────────────────────────────────────────────

def test_an_unstaged_heatmap_proves_nothing(monkeypatch):
    """Promotion re-gates every page, so the comparison still happens before
    anything reaches a client. Refusing here would refuse page order."""
    assert run(monkeypatch, strip({"pillar_id": "P1", "score": 2.02}),
               None) == []
    assert run(monkeypatch, strip({"pillar_id": "P1", "score": 2.02}),
               {}) == []


def test_no_other_page_is_touched(monkeypatch):
    for page in ("heatmap", "platform", "context", "techstack", "insights"):
        assert run(monkeypatch, strip(dict(AXOS_P1, delta=-99)),
                   heatmap(4.0), page=page) == []


def test_a_run_with_no_strip_is_not_a_finding(monkeypatch):
    assert run(monkeypatch, {"scores": {"pillars": []}}, heatmap(4.0)) == []
    assert run(monkeypatch, {}, heatmap(4.0)) == []


@pytest.mark.parametrize("bad", [None, [], "x", 42,
                                 {"scores": "not-a-dict"},
                                 {"scores": {"pillars": "no"}},
                                 {"scores": {"pillars": ["x", None]}}])
def test_malformed_shapes_do_not_crash_the_gate(monkeypatch, bad):
    run(monkeypatch, bad, heatmap(4.0))


def test_a_row_missing_either_operand_is_skipped(monkeypatch):
    """Nothing to subtract is not a wrong subtraction."""
    assert run(monkeypatch, strip({"pillar_id": "P1", "score": 2.02,
                                   "peer_median": None, "delta": None},
                                  AXOS_P1)) == []


def test_the_gate_is_registered_with_its_family_and_severity():
    from dma_mcp.gates import GATES
    assert "CG-44" in GATES
    assert GATES["CG-44"][-1] == "block"
    why = GATES["CG-44"][3].lower()
    assert "cascade" in why or "stopped one page short" in why
    assert "gulf" in why and "invariant 9" in why


def test_it_runs_inside_pass_two():
    import inspect
    src = inspect.getsource(V2.validate_pass2)
    assert "_check_peer_scores_cascade" in src, \
        "CG-44 is defined but never dispatched"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# ── the empty bar ─────────────────────────────────────────────────────
#
# Golden 1, run 40971653, promoted 2026-09-02T14:35:12Z. The overview hero
# rendered P1-P4 as four blank tracks with only a peer-median tick, because
# `score` was null on all four. This gate had the row in its hands and let
# it through: `if score is None or peer is None: continue` skipped every
# check below, so a strip could serve four empty bars and pass.
#
# It was never a missing input. The workbook stated the figures twice
# (Pillar_Summary.Weighted_Score and Pillar_Rollup.score), the heatmap
# already served exactly those figures with their source cells, and the
# composite on this very section was their mean. The delta beside each null
# was computed FROM the number the row declined to state.
#
# The rule is the mirror of the delta branch: a derived value with its
# operands in hand is computed, never left null. score = peer + delta.

# verbatim from that promoted payload, before the repair
GOLDEN1_P1_EMPTY = {"pillar_id": "P1", "score": None, "peer_median": 3.1,
                    "delta": -0.7, "direction": "below", "peer_n": 4}
GOLDEN1_P1_FIXED = {**GOLDEN1_P1_EMPTY, "score": 2.4}


def test_the_promoted_empty_bar_is_refused(monkeypatch):
    out = run(monkeypatch, strip(GOLDEN1_P1_EMPTY))
    assert ids(out) == ["CG-44"]
    r = out[0]
    assert r["path"] == "overview.scores.pillars[0].score"
    # the verdict hands back the recoverable figure, 3.1 + (-0.7)
    assert "2.4" in r["message"]
    assert "EMPTY BAR" in r["message"]


def test_serving_the_figure_clears_it(monkeypatch):
    assert run(monkeypatch, strip(GOLDEN1_P1_FIXED)) == []


def test_all_four_golden1_pillars_are_reported_not_just_the_first(monkeypatch):
    """The promoted defect was four bars, not one."""
    rows = [
        {"pillar_id": "P1", "score": None, "peer_median": 3.1, "delta": -0.7},
        {"pillar_id": "P2", "score": None, "peer_median": 3.0, "delta": -0.89},
        {"pillar_id": "P3", "score": None, "peer_median": 3.0, "delta": -0.75},
        {"pillar_id": "P4", "score": None, "peer_median": 3.1, "delta": -0.85},
    ]
    out = run(monkeypatch, strip(*rows))
    assert ids(out) == ["CG-44"] * 4
    # each names its own recoverable score: 2.4, 2.11, 2.25, 2.25
    for want, r in zip(("2.4", "2.11", "2.25", "2.25"), out):
        assert want in r["message"]


def test_a_row_with_no_peer_median_is_still_not_this_gates_business(monkeypatch):
    """Only a row whose operands are BOTH present can have its score
    recovered. A genuinely peerless row is another gate's concern, and this
    one must not invent a figure for it."""
    assert run(monkeypatch, strip({"pillar_id": "P1", "score": None,
                                   "peer_median": None, "delta": None})) == []


def test_a_null_score_beside_a_peer_but_no_delta_is_not_recoverable(monkeypatch):
    """Two operands or nothing. With only the peer median in hand the score
    is not arithmetic, and this gate refuses to guess it."""
    assert run(monkeypatch, strip({"pillar_id": "P1", "score": None,
                                   "peer_median": 3.1, "delta": None})) == []
