"""A bracketed figure is not a citation (B1 Bank, 2026-10-08).

`quality._CITATION` stripped ANY bracketed text before the grounding check,
so "[2025]", "[July 15, 2025]" or "[27 hits]" passed as citations. A research
agent read the module after `synthesise` refused its ungrounded figures and
bracketed them. Only evidence ids are citations now, and the floors gate
re-reads grounding on every synthesised row (`ungrounded_figures`)."""
from __future__ import annotations

import pytest

from engine import floors_gate as F
from engine import quality as Q


@pytest.mark.parametrize("cite", ["[E-0001:F2]", "[E-192, E-195]", "[TS-004]",
                                  "[E-12; E-13:F1]"])
def test_ids_are_still_citations(cite):
    assert Q._CITATION.sub(" ", cite).strip() == ""


@pytest.mark.parametrize("disguised", ["[2025]", "[July 15, 2025]", "[27 hits]",
                                       "[Oct 2025]", "[$11.5 million]"])
def test_a_bracketed_figure_is_still_checked(disguised):
    rec = {"Dominant_Claim": f"Conversion completed {disguised} on schedule."}
    assert Q.ungrounded_numbers(rec, ["an excerpt that carries no such figure"])


def test_a_grounded_bracketed_figure_passes():
    rec = {"Dominant_Claim": "Conversion was set for August 10 [2026] [E-0042]."}
    assert not Q.ungrounded_numbers(rec, ["the conversion is set for August 10, 2026"])




def test_an_id_inside_an_annotated_citation_is_not_a_figure():
    rec = {"What_We_Found": "Initiatives are planned [E-877; fetch refused, row UNVERIFIED]."}
    assert not Q.ungrounded_numbers(rec, ["initiatives are planned"])
