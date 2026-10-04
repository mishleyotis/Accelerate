"""CG-10 reaches the tech register (SWBC gold audit 2026-10-04, RC-12(i);
D-23).

`_ITEM_DATING` named seven sections and not `techstack.techstack`, so a
register row with `as_of: null` and nothing saying why passed every gate.
SWBC served TS-011, TS-014, TS-015, TS-029 and TS-031 with a null `as_of`
although every e_id they cite is dated 2026-09-01 — the techstack card's
recency dot had nothing to draw, and nothing said whether anybody looked.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation import _ITEM_DATING, _check_date_absence   # noqa: E402

# SWBC TS-011, cut to the dating fields
TS_011 = {"ts_id": "TS-011", "product": "Snowflake", "vendor": "Snowflake",
          "status": "CONFIRMED", "layer": "DATA", "as_of": None,
          "e_ids": ["E-CC-870"]}


def test_techstack_is_a_dated_section():
    assert "techstack.techstack" in _ITEM_DATING
    assert _ITEM_DATING["techstack.techstack"][0] == "items[*].as_of"


def test_swbc_ts_011_with_a_bare_null_as_of_is_refused():
    out = _check_date_absence("techstack", "techstack", {"items": [TS_011]})
    assert len(out) == 1 and out[0]["gate_id"] == "CG-10"
    assert out[0]["path"] == "techstack.items[0].as_of"


def test_the_date_of_the_cited_evidence_clears_it():
    fixed = {**TS_011, "as_of": "2026-09-01"}
    assert _check_date_absence("techstack", "techstack", {"items": [fixed]}) == []


def test_an_unverified_rung_clears_it_without_inventing_a_date():
    """TS-006's honest repair: the rung that says the date was not established."""
    rung = {**TS_011, "recency_band": "UNVERIFIED"}
    assert _check_date_absence("techstack", "techstack", {"items": [rung]}) == []
