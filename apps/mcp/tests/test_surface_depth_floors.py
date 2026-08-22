"""CG-33 and CG-34 — the two surfaces that were thin, honestly, and shipped.

Both were reported from the rendered T. Rowe Price page. Neither was a broken
gate: both sections disclosed their shortfall exactly as the contract asks, and
that is precisely why nothing refused them.

  thought_leadership  ONE entry, thin=true, with a per-executive search account
                      naming earnings transcripts, PR Newswire, DEF 14A and
                      investor relations. The Surface Spec's floor was 2, so a
                      single entry was one short of a rule that did not bind.
                      Owner raised the floor to 3 on 2026-08-22.

  financial_series    TWO points — FY2025 year-end and Q2 2026 — with
                      verified_sparse set. Its own `reading` called it "a
                      snapshot, not a trajectory". The Surface Spec states
                      "5-year financials" in the Context page header.

The interesting half is what each refusal has to SAY. A producer told only
"find one more quote" goes looking for a sixth publication; the run's own
reason had already established that the five it held were unusable because
they were registered as paraphrases or as fragments under the 80-character
verbatim floor. And a producer told only "serve five years" cannot comply for
an entity with no published history — so CG-34 tests REACH, passing on a search
that names the years it looked at even when it found nothing.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp.gates import GATES                                # noqa: E402
from dma_mcp.validation import (                               # noqa: E402
    FINANCIAL_SERIES_YEARS, THOUGHT_LEADERSHIP_FLOOR,
    _check_financial_series_reach as reach,
    _check_thought_leadership_depth as depth)


# ── CG-33 · thought leadership ──


def _tl(n):
    return {"entries": [{"headline": f"Post {i}"} for i in range(n)],
            "thin": n < THOUGHT_LEADERSHIP_FLOOR}


def test_one_entry_is_refused():
    out = depth("thought_leadership", _tl(1))
    assert len(out) == 1
    assert "1 entry served" in str(out[0]) or "1 entr" in str(out[0])


def test_the_spec_s_old_floor_of_two_is_no_longer_enough():
    """Two passed for the life of the surface. The owner moved the floor, and
    a test that still accepted two would quietly keep the old rule."""
    assert len(depth("thought_leadership", _tl(2))) == 1


def test_three_entries_pass():
    assert depth("thought_leadership", _tl(3)) == []


def test_thin_true_does_not_buy_an_exemption():
    """The whole reason this shipped: the section was honest, and honesty was
    read as compliance."""
    body = _tl(1)
    body["thin"] = True
    body["empty_state"] = {"reason": "searched all seven source families",
                           "sources_searched": ["earnings calls", "DEF 14A"]}
    assert len(depth("thought_leadership", body)) == 1


def test_the_refusal_names_the_registration_route():
    """A producer sent hunting for a sixth publication repeats the run that
    produced this. The message has to name the 80-character verbatim floor and
    the mid-word truncation, because that is where the missing entries are."""
    msg = str(depth("thought_leadership", _tl(1))[0])
    assert "80" in msg
    assert "verbatim" in msg.lower()
    assert "mid-word" in msg


def test_other_sections_are_untouched():
    assert depth("leadership", _tl(1)) == []


# ── CG-34 · financial series reach ──


def _fin(years, searched=None):
    body = {"series": [{"period": f"FY{y}", "as_of": f"{y}-12-31", "value": 1.0}
                       for y in years]}
    if searched is not None:
        body["empty_state"] = {"sources_searched": searched}
    return body


def test_the_trp_shape_is_refused():
    """Two points one year apart, and a search account naming only the years
    it already serves."""
    body = _fin([2025, 2026], searched=[
        "T. Rowe Price Q4 and Full-Year 2025 results release — RESOLVED: "
        "'Year-end 2025 client assets reached $1.78 trillion'"])
    out = reach("financial_series", body)
    assert len(out) == 1
    assert "2022" in str(out[0]), "the refusal should name how far back to go"


def test_five_distinct_years_pass():
    assert reach("financial_series", _fin([2022, 2023, 2024, 2025, 2026])) == []


def test_four_years_is_one_short():
    assert len(reach("financial_series", _fin([2023, 2024, 2025, 2026]))) == 1


def test_a_search_that_reached_back_passes_even_on_two_points():
    """Reach, not luck. An entity with no published history still passes by
    showing where it looked — otherwise the gate would refuse runs that cannot
    possibly comply."""
    body = _fin([2025, 2026], searched=[
        "Annual reports for 2021 and 2022 carry no firm-wide AUM total; the "
        "figure is first disclosed for year-end 2025."])
    assert reach("financial_series", body) == []


def test_a_search_naming_only_recent_years_does_not_count():
    body = _fin([2025, 2026], searched=["the 2024 and 2025 results releases"])
    assert len(reach("financial_series", body)) == 1


def test_an_empty_series_is_left_to_the_empty_state_gates():
    assert reach("financial_series", {"series": []}) == []


def test_undated_points_are_left_to_the_date_gates():
    assert reach("financial_series", {"series": [{"value": 1.0}]}) == []


def test_quarterly_points_within_one_year_do_not_count_as_a_trajectory():
    """Four quarters of one year is one year of history, not four."""
    body = {"series": [{"period": f"Q{q} 2026", "as_of": f"2026-0{q*3}-30",
                        "value": 1.0} for q in range(1, 5)]}
    assert len(reach("financial_series", body)) == 1


# ── both gates can explain themselves, and both are wired ──


def test_the_gates_are_registered_and_block():
    for gid in ("CG-33", "CG-34"):
        assert gid in GATES, f"{gid} has no registry entry to explain itself"
        assert GATES[gid][-1] == "block"


def test_the_floors_have_one_home_each():
    assert THOUGHT_LEADERSHIP_FLOOR == 3
    assert FINANCIAL_SERIES_YEARS == 5


def test_both_checks_are_wired_into_the_dispatch():
    """Every test above calls the checks directly and would stay green with
    them unwired. Asserted over the AST, because each name appears in its own
    def and docstring and a substring check would pass on an unwired file."""
    import ast
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "validation.py").read_text(encoding="utf-8")
    called = {getattr(n.func, "id", None) for n in ast.walk(ast.parse(src))
              if isinstance(n, ast.Call)}
    for fn in ("_check_thought_leadership_depth", "_check_financial_series_reach"):
        assert fn in called, f"{fn} is defined but never called by validate()"


# ── the refusal has to escalate, not just refuse ──
#
# Owner, 2026-08-22: "The search depth where information lacks should be
# incremental." A depth gate that only reports a shortfall sends a producer
# back to do the same search again — which is precisely what happened on
# T. Rowe Price. That section had climbed a real ladder (per-executive
# searches across transcripts, PR Newswire, DEF 14A and investor relations)
# and its disclosure said so; the shortfall was that registration captured
# paraphrases rather than quotable spans. Told only "one entry, three
# required", the next producer looks for a sixth publication. Told where the
# next rung IS, it re-registers the five sources it already holds.
#
# So the property held here is not "did it search" — the contract already
# requires sources_searched — but "does the refusal name a DIFFERENT action
# from the one already taken".


def test_the_thought_leadership_refusal_names_the_registration_rung():
    body = {"entries": [{"quote": "x"}]}
    msg = depth("thought_leadership", body)[0]["message"]
    assert "already registered" in msg, "it must point at what is in hand"
    assert "re-register" in msg.lower()
    assert "80-260" in msg, "the admissibility bar is the actionable detail"
    assert "does not excuse it" in msg, (
        "thin=true is a disclosure, not a discharge — say so or the next "
        "producer sets the flag and stops")


def test_the_financial_refusal_names_the_year_to_walk_back_to():
    body = {"series": [{"as_of": "2026-06-30"}, {"as_of": "2025-12-31"}]}
    msg = reach("financial_series", body)[0]["message"]
    assert "2022" in msg, "name the year, not just the count"
    assert "OWN filings" in msg
    assert "investor-relations" in msg or "annual report" in msg, (
        "name WHERE the earlier figures are, since that is the rung")


def test_both_refusals_say_what_to_do_not_only_what_is_wrong():
    """The shared property. A message that stops at the measurement is a
    measurement, not a gate."""
    msgs = [depth("thought_leadership", {"entries": []})[0]["message"],
            reach("financial_series", {"series": [{"as_of": "2026-06-30"}]})[0]["message"]]
    for m in msgs:
        assert len(m) > 200, "an actionable refusal is not one sentence"
        # An imperative naming the next move.
        assert any(v in m.lower() for v in
                   ("re-register", "walk back", "cite", "check")), m[:120]
