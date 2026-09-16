"""The semantic matcher is a READ tool, and this is the number that decided it.

Capability-grain discovery returns one corpus for ~5 sibling cells, and
something has to say which sibling each find grounds. `scripts/subcap_match.py`
was written for that and was never wired in. Before wiring it, it was
measured — against the only labelled data that exists, the Golden 1
reference workbook's own 723 excerpt-to-cell assignments:

    candidates          corpus        top-1   says MATCH   right when it does
    whole catalogue     catalogue     10.9%          337                16.9%
    the category (~58)  catalogue     22.1%          448                27.2%
    the capability (~7) catalogue     31.5%          407                49.9%
    the capability (~7) the run's DQ  47.0%          480                57.7%

    (picking at random inside the capability scores 17.7%)

Raising the abstention margin does not rescue it: precision plateaus at ~73%
with coverage down to 26%.

A WRONG CELL ASSIGNMENT PASSES EVERY GATE THIS SYSTEM HAS. `evidence_smear`
and `single_source_fact` measure how evidence is DISTRIBUTED, not whether it
sits on the right cell; a bidirectional citation records what was asserted,
not whether it was true. So the boundary these tests hold is not a style
preference — it is the containment. The module may rank, and a human or a
producer may read the ranking. Nothing in `engine/` may import it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
ENGINE = PLUGIN / "skills" / "dma-research" / "engine"
sys.path.insert(0, str(PLUGIN / "scripts"))
import subcap_match as SM  # noqa: E402


# ── the boundary ────────────────────────────────────────────────────────

def test_no_engine_module_imports_the_matcher():
    """THE CONTAINMENT. At 57.7% precision when confident, a proposer in the
    write path injects a defect class nothing downstream can see."""
    offenders = []
    for f in sorted(ENGINE.glob("*.py")):
        text = f.read_text(encoding="utf-8")
        if "subcap_match" in text:
            offenders.append(f.name)
    assert offenders == [], (
        f"{offenders} reach for the matcher. It is right 57.7% of the time "
        f"when it declares a MATCH (measured 2026-09-13 against Golden 1's "
        f"723 labelled assignments) and a wrong cell assignment passes every "
        f"gate this system has. Move the number first, then this test.")


def test_the_module_says_what_it_is_not_wired_into():
    """A boundary held only by a test is a boundary the next reader trips
    over. The measurement lives in the module too."""
    doc = SM.__doc__ or ""
    assert "no engine module imports it" in doc
    assert "57.7%" in doc and "17.7%" in doc, (
        "the docstring must carry the measured precision AND the random "
        "baseline — a number with nothing to beat persuades of nothing")


# ── the adapter that made it measurable at all ──────────────────────────

def test_the_corpus_can_be_built_without_the_connector():
    """`load_catalogue` reads what `get_capability_catalogue` returns, which
    a container with no connector does not have — so the module was
    unrunnable exactly where it was proposed to run."""
    cat = SM.catalogue_from_contract()
    assert len(cat) == 851
    row = next(c for c in cat if c["cell_id"] == "P1C1.1.1")
    assert row["name"] == "Digital Strategy Document"
    assert "leadership title" in row["doc"], "the proxy class belongs in the doc"
    assert all(c["doc"].strip() for c in cat), "a cell with no text ranks nowhere"


def test_the_corpus_can_be_narrowed_to_one_capability():
    """The only scope where it beats chance. Ranking over all 851 cells is
    right 10.9% of the time; inside the capability, 31.5%."""
    scope = [c for c in SM.catalogue_from_contract()
             if c["cell_id"].startswith("P1C1.1.")]
    narrowed = SM.catalogue_from_contract([c["cell_id"] for c in scope])
    assert narrowed == scope and 2 <= len(narrowed) <= 20


def test_an_empty_scope_is_refused_rather_than_ranked_over_nothing():
    with pytest.raises(SystemExit):
        SM.catalogue_from_contract(["P9C9.9.9"])


# ── abstention, which is the only thing keeping it honest ───────────────

def test_a_thin_margin_abstains_and_names_the_contenders():
    cat = SM.catalogue_from_contract(
        [c["cell_id"] for c in SM.catalogue_from_contract()
         if c["cell_id"].startswith("P1C1.1.")])
    ranked = SM.rank("The credit union published a three-year digital "
                     "transformation roadmap in March 2025 setting out "
                     "vision, objectives and success criteria.", cat)
    d = SM.decide(ranked, 0.05)
    assert d["decision"] in ("AMBIGUOUS", "MATCH")
    if d["decision"] == "AMBIGUOUS":
        assert d["assign"] is None and d["contenders"]


def test_vocabulary_it_does_not_share_is_a_refusal_not_a_guess():
    cat = SM.catalogue_from_contract(["P1C1.1.1"])
    d = SM.decide(SM.rank("zzzqqq wwwxxx", cat), 0.05)
    assert d["decision"] == "NO_MATCH" and d["assign"] is None


def test_a_wider_margin_only_ever_abstains_more():
    """The sweep that showed precision plateaus: the knob trades coverage for
    precision and cannot manufacture either."""
    cat = SM.catalogue_from_contract(
        [c["cell_id"] for c in SM.catalogue_from_contract()
         if c["cell_id"].startswith("P1C1.1.")])
    ranked = SM.rank("digital strategy vision refresh cadence board", cat)
    decisions = [SM.decide(ranked, m)["decision"] for m in (0.0, 0.3, 0.9)]
    assert decisions[-1] == "AMBIGUOUS" or decisions[-1] == "NO_MATCH"
    assert not (decisions[0] == "AMBIGUOUS" and decisions[-1] == "MATCH")
