"""CG-43 — the Context sentiment grid and the Overview bars are one dataset.

Owner, 2026-08-23: "Gulf still has no sentiment overview on the context page;
wasn't there supposed to be congruency with the overview page? Which
autocorrecting tests are there to ensure this usually happens without
distorting the UI of the context page?"

The contract had already said it, in the `context_tiles` field doc: the grid
is "a RE-PROJECTION of the same dataset O9 renders as bars, so the two cards
cannot disagree". Nothing read that sentence, so the two surfaces drifted the
moment either was edited alone.

THE DRIFT MEASURED HERE WAS THIS BUILD'S OWN. Fixing the "sentiment has only
1 parameter" report, a second customer bar was added to axos-bank's Overview
— UFB Direct, 4.83 over 19,831 ratings, the bank's own direct-to-consumer
brand — and the Context grid was left carrying one row. Two readings on one
page, one on the other, and every gate passed it. The repair and the gate
landed together.

WHAT THIS GATE IS NOT. It is not a depth floor. Gulf serves no bar and no
tile, because a business-to-business receivables lender accumulates no
consumer review estate, and both cards say so in the same terms. That is
congruent and passes. CG-40 owns depth; this owns agreement.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dma_mcp.validation2 as V2         # noqa: E402


class _Sibling:
    """Stands in for the staged sibling page `_live_submission` reads."""

    def __init__(self, payload):
        self.payload = payload


def run(monkeypatch, page, payload, sibling):
    monkeypatch.setattr(V2, "_live_submission",
                        lambda conn, run_id, p: sibling)
    return V2._check_sentiment_projections_agree(None, "run-1", page, payload)


def ids(out):
    return [r["gate_id"] for r in out]


BAR_A = {"e_id": "E-CC-280", "source": "Apple App Store — Axos All-In-One",
         "rating": 4.71, "scale": 5, "n": 19139, "audience": "customer"}
BAR_B = {"e_id": "E-CC-370", "source": "Apple App Store — UFB Direct",
         "rating": 4.83, "scale": 5, "n": 19831, "audience": "customer"}
ROW_A = {"e_id": "E-CC-280", "source": "Apple App Store — Axos All-In-One",
         "rating": 4.71, "scale": 5, "n": 19139}
ROW_B = {"e_id": "E-CC-370", "source": "Apple App Store — UFB Direct",
         "rating": 4.83, "scale": 5, "n": 19831}


def grid(*rows):
    return {"context_sentiment": {"context_tiles":
                                  [{"audience": "customer", "rows": list(rows)}]}}


def bars(*b):
    return {"sentiment": {"bars": list(b)}}


# ── the drift this build introduced ───────────────────────────────────

def test_the_axos_drift_is_refused_from_the_overview(monkeypatch):
    """Two bars, one row. Reported from the Overview submit."""
    out = run(monkeypatch, "overview", bars(BAR_A, BAR_B), grid(ROW_A))
    assert ids(out) == ["CG-43"], out
    m = out[0]["message"]
    assert "E-CC-370" in m
    assert "render as a bar on the Overview and appear nowhere" in m
    assert out[0]["severity"] == "block"


def test_the_same_drift_is_refused_from_the_context_side(monkeypatch):
    """Symmetry matters: either page may be the one edited, so either submit
    has to catch it. Without this the drift waits for promotion."""
    out = run(monkeypatch, "context", grid(ROW_A), bars(BAR_A, BAR_B))
    assert ids(out) == ["CG-43"], out
    assert "E-CC-370" in out[0]["message"]


def test_adding_the_missing_row_clears_it(monkeypatch):
    assert run(monkeypatch, "overview", bars(BAR_A, BAR_B),
               grid(ROW_A, ROW_B)) == []
    assert run(monkeypatch, "context", grid(ROW_A, ROW_B),
               bars(BAR_A, BAR_B)) == []


def test_a_row_the_overview_never_summarised_is_refused(monkeypatch):
    out = run(monkeypatch, "overview", bars(BAR_A), grid(ROW_A, ROW_B))
    assert ids(out) == ["CG-43"]
    assert "no bar on the Overview" in out[0]["message"]


# ── one dataset means one number ──────────────────────────────────────

def test_the_same_reading_with_two_ratings_is_refused(monkeypatch):
    """A re-projection that renumbers is worse than one that omits, because
    both look authoritative."""
    moved = dict(ROW_A, rating=4.2)
    out = run(monkeypatch, "overview", bars(BAR_A), grid(moved))
    assert ids(out) == ["CG-43"]
    assert "4.71" in out[0]["message"] and "4.2" in out[0]["message"]


def test_a_hair_of_rounding_is_not_a_disagreement(monkeypatch):
    assert run(monkeypatch, "overview", bars(BAR_A),
               grid(dict(ROW_A, rating=4.712))) == []


def test_a_reworded_source_string_is_not_a_disagreement(monkeypatch):
    """Keyed on e_id on purpose. The two surfaces phrase a source differently
    — the bar names the API, the grid names the store — and that is a wording
    choice, not two readings."""
    assert run(monkeypatch, "overview", bars(BAR_A),
               grid(dict(ROW_A, source="App Store listing, lifetime"))) == []


# ── congruently empty is a real answer ────────────────────────────────

def test_gulf_serves_neither_and_passes(monkeypatch):
    """The reported client. No bar, no tile, both cards saying why in the same
    terms — a business-to-business lender has no consumer review estate. A
    gate that refused this would be a depth floor wearing the wrong name."""
    assert run(monkeypatch, "overview",
               {"sentiment": {"bars": [], "empty_state": {"reason": "no rated row exists"}}},
               {"context_sentiment": {"context_tiles": [],
                                      "empty_state": {"reason": "no rated row exists"}}}) == []


def test_bars_with_an_empty_grid_is_still_refused(monkeypatch):
    """Empty on ONE side is the divergence, not the congruence."""
    out = run(monkeypatch, "overview", bars(BAR_A),
              {"context_sentiment": {"context_tiles": []}})
    assert ids(out) == ["CG-43"]


# ── scope and safety ──────────────────────────────────────────────────

def test_an_unstaged_sibling_is_nothing_to_compare(monkeypatch):
    """A page not yet staged is not a disagreement. Promotion re-gates every
    page, so the comparison still happens before anything reaches a client."""
    assert run(monkeypatch, "overview", bars(BAR_A), None) == []
    assert run(monkeypatch, "overview", bars(BAR_A), {}) == []


def test_no_other_page_is_touched(monkeypatch):
    for page in ("heatmap", "platform", "techstack", "insights"):
        assert run(monkeypatch, page, bars(BAR_A), grid()) == []


def test_a_row_without_an_e_id_is_not_matched_on(monkeypatch):
    """An unkeyed row cannot be compared, and inventing a match by position
    would be the adjacent-column defect this build already has a class for."""
    assert V2._sentiment_grid_rows(
        {"context_tiles": [{"rows": [{"source": "x", "rating": 4.0}]}]}) == {}
    assert V2._sentiment_bar_rows({"bars": [{"source": "x", "rating": 4.0}]}) == {}


def test_malformed_shapes_do_not_crash_the_gate(monkeypatch):
    assert V2._sentiment_grid_rows(None) == {}
    assert V2._sentiment_bar_rows("nonsense") == {}
    assert run(monkeypatch, "overview",
               {"sentiment": {"bars": ["x", None, BAR_A]}},
               {"context_sentiment": {"context_tiles": ["y", None,
                                                        {"rows": [ROW_A]}]}}) == []


def test_the_gate_is_registered_with_its_family_and_severity():
    from dma_mcp.gates import GATES
    assert "CG-43" in GATES
    assert GATES["CG-43"][-1] == "block"
    why = GATES["CG-43"][3]
    assert "re-projection" in why.lower()
    assert "axos" in why.lower() and "gulf" in why.lower()


def test_it_runs_inside_pass_two():
    import inspect
    src = inspect.getsource(V2.validate_pass2)
    assert "_check_sentiment_projections_agree" in src, \
        "CG-43 is defined but never dispatched"
