"""A bracketed id list becomes one bracket per id, like a parenthesised one.

WHY THIS EXISTS (B1 Bank, 2026-10-08). `normalize_citations` split only
"(E-1, E-2)" groups. A writer's "[E-086, E-305, E-087]" fell through to the
bare-id pass, which bracketed the middle id alone — "[E-086, [E-305],
E-087]" — and the assessment §1 reviewer reopened the section on it for two
rounds; "[E-086; E-305]" rendered as no citation under `reports.CITE_RE`.
"""
from __future__ import annotations

import pytest

from engine.narrative import normalize_citations
from engine.reports import CITE_RE


@pytest.mark.parametrize("text, want", [
    ("[E-086, E-305, E-087]", "[E-086] [E-305] [E-087]"),
    ("[E-086; E-305]", "[E-086] [E-305]"),
    ("(E-086, E-305, E-087)", "[E-086] [E-305] [E-087]"),
    ("[E-086:F1, E-305:F2, E-087]", "[E-086:F1] [E-305:F2] [E-087]"),
    ("see E-010 and [E-011]", "see [E-010] and [E-011]"),
    ("[E-1234]", "[E-1234]"),
])
def test_every_id_lands_in_its_own_bracket(text, want):
    out = normalize_citations(text)
    assert out == want
    assert len(CITE_RE.findall(out)) == len(want.split("[")) - 1
