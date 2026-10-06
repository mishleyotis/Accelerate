"""Promote re-runs the fit engine on retained pages — RC-13 / D-18.

SWBC gold audit, 2026-10-04: CG-30/CG-31 compared the platform cards and the
opportunity tiles with the engine ONCE, at submit. After the 2026-10-02
sub-vertical binding and the 2026-10-04 deploy, today's engine returned
relevance 0.971-0.98 and fits 57.2 / 39.7 / 44.6 / 28.2, while the served
pages still carried relevance 1.0 and 58.9 — and promote carried them
forward on retained rows, because it re-ran only the pure pass-1 gates.

A retained row is a dated observation of the ENGINE as well as of the gates.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _promote_fake import RUN, Conn, skeleton, wrote_anything  # noqa: E402

from dma_mcp import fit as fit_mod  # noqa: E402
from dma_mcp.promote import promote_run  # noqa: E402

CELLS = [("P4C3.1.1", 2.0, "P4C3", "integration"),
         ("P4C3.1.2", 1.5, "P4C3", "integration")]
CARD = {"platform": "MuleSoft", "l3_area": "Integration", "alignment": 0.5,
        "readiness": "green"}
# CG-03b (fix/mcp-gates-contract, RC-09) made these two required on every
# platform card at pass 1; the refit tests are about the ENGINE, so the card
# carries them and nothing else changes.
STAGED_CARD = {**CARD,
               "peer_synthesis": "No peer deployment was established.",
               "estate_reach": {"cells_not_yet_reached": 0, "by_category": [],
                                "derivation": "from the run's register"}}


def _engine_fit(sv="Credit Unions"):
    conn = Conn({}, sub_vertical=sv, cells=CELLS)
    return fit_mod.platform_fit(conn, RUN, [CARD])["platforms"][0]


# The tile shape CG-03b reads (RC-09, merged beside this test on the
# integration branch): the negative control must be a WHOLE tile, or it
# measures the shape gate instead of the grain tolerance.
TILE_SHAPE = {
    "peer_synthesis": "No named peer is scored at this layer; identified, "
                      "not scored.",
    "estate_reach": {"cells_not_yet_reached": 2, "by_category": [],
                     "derivation": "two integration cells, no register "
                                   "product linked"},
}


def _pages(fit_score, rank=1):
    pages = skeleton()
    pages["platform"]["platform_story"]["platforms"] = [
        {**CARD, **TILE_SHAPE, "fit_score": fit_score, "rank": rank}]
    return pages


def test_a_staged_fit_that_drifted_from_the_engine_is_refused():
    engine = _engine_fit()["fit_score"]
    conn = Conn(_pages(round(engine + 1.7, 1)), cells=CELLS)
    out = promote_run(conn, RUN)
    assert out["promoted"] is False, (
        "a card 1.7 points off today's engine promoted on a retained row")
    assert out["blocking_by_gate"]["platform"].get("CG-30"), out
    assert any("the engine computes" in r["message"]
               for r in out["reasons"]["platform"])
    assert not wrote_anything(conn)


def test_within_the_grain_tolerance_it_promotes():
    """Negative control: 0.05 is the charter's grain; 0.04 off is the same
    number."""
    engine = _engine_fit()["fit_score"]
    out = promote_run(Conn(_pages(round(engine + 0.04, 2)), cells=CELLS), RUN)
    assert out["promoted"] is True, out.get("reasons")


def test_cards_built_on_an_unchecked_engine_context_are_refused():
    """The entity's sub-vertical does not resolve: relevance is null and
    every fit rests on a neutral default. The number may even match — it is
    still not a checked number."""
    engine = _engine_fit(sv=None)["fit_score"]
    conn = Conn(_pages(engine), sub_vertical=None, cells=CELLS)
    out = promote_run(conn, RUN)
    assert out["promoted"] is False
    msgs = [r["message"] for r in out["reasons"]["platform"]]
    assert any("UNCHECKED" in m for m in msgs), msgs


def test_an_opportunity_tile_off_its_card_is_refused_at_promote():
    """CG-31, re-run: the tile is pinned to the card, the card to the
    engine."""
    engine = _engine_fit()
    pages = _pages(engine["fit_score"], engine["rank"])
    pages["overview"]["opportunity"]["tiles"] = [{
        "platform": "MuleSoft", "composite": round(engine["fit_score"] + 10, 1),
        "rank": engine["rank"],
        "factors": [{"name": n} for n in ("Addressable opportunity",
                                          "Catalogue interconnect",
                                          "Greenfield family",
                                          "Strategic alignment")]}]
    out = promote_run(Conn(pages, cells=CELLS), RUN)
    assert out["promoted"] is False
    assert out["blocking_by_gate"]["overview"].get("CG-31"), out
