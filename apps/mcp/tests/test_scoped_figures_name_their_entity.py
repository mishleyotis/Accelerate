"""CG-18d — a scoped figure names the entity it describes, on O2 and O8 alike.

RC-06 (SWBC gold audit, 2026-10-04; D-04, slice OH-02). O2.md called every
subsidiary figure "contamination" with no route for a private multi-line
group, while O8 on the same run served a subsidiary-scoped HMDA series. The
two contracts disagreed, so SWBC held revenue and assets on the strip while
the series card beside it carried SWBC Mortgage Corporation's originations.

Owner decision 2 (2026-10-04): a subsidiary or segment figure is admissible
when its unit (O2) or basis (O8) names the entity it describes, e.g. "SWBC
Mortgage Corporation, HMDA 2024". One rule, both surfaces: a scope word
(subsidiary, segment, division, affiliate, line of business) with no entity
named beside it is refused.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import sections  # noqa: E402
from dma_mcp.validation import _check_scoped_figures as check  # noqa: E402


def _o2(unit):
    return check("firmographics", {"fields": [
        {"field": "segment_revenue", "value": "250", "unit": unit}]})


def _o8(basis):
    return check("financial_series", {"series": [
        {"period": "CY2024", "value": 2.3, "basis": basis}]})


def test_a_named_subsidiary_figure_passes_on_both_surfaces():
    assert _o2("USD millions, Financial Institution Group segment revenue, "
               "April 2026") == []
    assert _o8("Dollar volume originated, HMDA, SWBC Mortgage Corporation "
               "only: a subsidiary of the group") == []


def test_an_unnamed_scope_is_refused_on_both_surfaces():
    o2 = _o2("USD millions, one division's revenue")
    o8 = _o8("total assets of a subsidiary")
    assert [r["gate_id"] for r in o2] == ["CG-18d"]
    assert [r["gate_id"] for r in o8] == ["CG-18d"]
    assert o2[0]["path"] == "firmographics.fields[0].unit"
    assert o8[0]["path"] == "financial_series.series[0].basis"


def test_an_unscoped_figure_is_untouched():
    assert _o2("USD billions, total assets FY2025") == []
    assert _o8("total assets, call report") == []


def test_both_contracts_state_the_one_rule():
    o2 = sections("overview")["firmographics"]["fields"]["fields"]["doc"]
    o8 = sections("overview")["financial_series"]["fields"]["series"]["doc"]
    for doc in (o2, o8):
        assert "SCOPED FIGURES" in doc and "names the entity" in doc
