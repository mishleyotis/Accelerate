"""CG-03b (O7) — a tenure is derived from an appointment date, so it carries one.

RC-09 (SWBC gold audit, 2026-10-04; slice OH-08). The roster contract says
"Emit tenure where the source gives a start date" and nothing tied
`tenure_months` to `appointed_on`. SWBC promoted six roster rows with a tenure
(605, 6, 37, 128, 130 and 10 months) and appointed_on null on every one — a
derived figure with no basis (invariant 9). The gold runs (Golden 1, Baxter,
Logix) carry appointed_on on every row that states a tenure.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation import _check_prose_shapes  # noqa: E402


def _run(roster):
    return _check_prose_shapes("overview", "leadership", {"roster": roster})


SWBC = [{"name": f"Exec {i}", "tenure_months": t, "appointed_on": None}
        for i, t in enumerate([None, 605, None, 6, 37, 128, 130, 10])]


def test_swbc_leadership_is_refused():
    out = _run(SWBC)
    assert len(out) == 6
    assert {r["gate_id"] for r in out} == {"CG-03b"}
    assert out[0]["path"] == "leadership.roster[1].tenure_months"


def test_the_gold_shape_passes():
    assert _run([{"tenure_months": 92, "appointed_on": "2018-07-01"},
                 {"tenure_months": None, "appointed_on": None}]) == []
