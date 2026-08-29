"""The two client-facing writing gates: no invented figures, no verdicts.

The ungrounded-figure check is the pipeline's named hallucination
pinpointer: a number asserted in a source-claim field that appears in NO
excerpt registered to the subcap is refused BY NAME, so the repair is
always "cite the source that states it or remove the figure". The
accusatory lexicon is the research-side twin of production gate
S2_accusatory — enforcing it here means research prose survives that gate
unchanged. references/functional_language.md is the prose standard both
enforce the mechanical edge of.
"""
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2].parent / (
    "plugins/dma-insights/skills/dma-research")
sys.path.insert(0, str(ENGINE))

from engine import ledger as L  # noqa: E402
from engine import quality as Q  # noqa: E402
from fixtures import bank_evidence, good_synthesis, new_run, small_selection  # noqa: E402


# ── the pinpointer, as a unit ─────────────────────────────────────────────

def test_a_figure_no_excerpt_carries_is_named():
    rec = {"What_We_Found": "Adoption reached 63 percent by 2025 [E-1:F1]."}
    missing = Q.ungrounded_numbers(rec, ["adoption was 47 percent in 2025"])
    assert missing == ["63"], "63 is invented; 2025 is in the excerpt"


def test_grounded_figures_pass_including_comma_forms():
    rec = {"What_We_Found": "Assets of 1,250 million and 47 percent adoption."}
    assert Q.ungrounded_numbers(
        rec, ["total assets of $1,250 million", "47 percent of members"]) == []


def test_not_run_reasons_and_small_counts_are_not_claims():
    rec = {"DQ_Fails": "NOT_RUN: nothing surfaced across 40 queries 2023-2026",
           "What_We_Found": "Two of three sources agree; 5 branches serve the area."}
    assert Q.ungrounded_numbers(rec, ["irrelevant excerpt"]) == []


def test_citation_ids_are_not_figures():
    rec = {"What_We_Found": "Launched in 2024 [E-2024:F14]."}
    assert Q.ungrounded_numbers(rec, ["went live during 2024"]) == []


def test_analyst_argument_fields_are_exempt():
    """Why_It_Matters and DMA_Impact are the analyst's forward reasoning —
    '2027 planning' there is not a sourced claim and must not teach agents
    to strip years from analysis."""
    rec = {"Why_It_Matters": "This shapes what the 2027 plan can lean on.",
           "DMA_Impact": "Raises the ceiling ahead of the 2027 review."}
    assert Q.ungrounded_numbers(rec, []) == []


# ── the lexicon, as a unit ────────────────────────────────────────────────

def test_verdict_words_are_refused_everywhere():
    why = Q.accusatory("a woefully inadequate data programme")
    assert why and "verdict about people" in why


def test_blame_constructions_are_refused_in_impact_fields_only():
    text = "the team failed to deploy real-time monitoring"
    assert Q.accusatory(text, impact_field=True)
    assert Q.accusatory(text, impact_field=False) is None, (
        "DQ_Fails legitimately reports failure evidence; only the fields a "
        "client reads as being about THEM refuse blame framing")


def test_neutral_gap_framing_passes():
    assert Q.accusatory(
        "Fraud review runs on a daily batch; real-time scoring would let "
        "the existing alerting workflow act inside the authorization window",
        impact_field=True) is None


# ── wired into the write path ─────────────────────────────────────────────

def test_synthesis_with_an_invented_figure_is_refused_by_name(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    sub = small_selection(1)[0]
    eids = bank_evidence(wb, sub)
    rec = good_synthesis(sub, eids)
    rec["What_We_Found"] += " Independent testing showed 91 percent task success."
    with pytest.raises(L.LedgerRefusal, match="ungrounded figure '91'"):
        L.append_synthesis(wb, sub, rec, actor="research-p1c1-producer")


def test_synthesis_with_accusatory_impact_is_refused(tmp_path):
    run = new_run(tmp_path)
    wb = run.open()
    sub = small_selection(1)[0]
    eids = bank_evidence(wb, sub)
    rec = good_synthesis(sub, eids)
    rec["Why_It_Matters"] = ("Leadership failed to invest in the channel and "
                             "the programme languished as a result of that.")
    with pytest.raises(L.LedgerRefusal, match="opportunity"):
        L.append_synthesis(wb, sub, rec, actor="research-p1c1-producer")


def test_the_fixture_synthesis_still_passes(tmp_path):
    """The floor must not rise past honest work: the canonical good record
    writes through unchanged."""
    run = new_run(tmp_path)
    wb = run.open()
    sub = small_selection(1)[0]
    eids = bank_evidence(wb, sub)
    out = L.append_synthesis(wb, sub, good_synthesis(sub, eids),
                             actor="research-p1c1-producer")
    assert out["subcap"] == sub


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
