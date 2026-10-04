"""A held must-present member is still a gap — it is just a gap with a reason.

RC-04 (SWBC gold audit, 2026-10-04; D-06, slice XC-03). The shared gap module
classed "held: null, quarantined, WITH a reason" as NOT a gap, on the premise
that the reason renders as a documented em dash. It did not: the renderer has
hidden held rows since 2026-08-14. So `list_enrichment_gaps` returned 0 gaps
for a run whose firmographics strip showed four facts and silently dropped
six, and `audit_promoted_client` saw the same nothing. A row may be hidden
from a page, or uncounted on the worklist — never both.

Owner decision 2 (2026-10-04): a held field renders as a stated absence with
its reason, capped. Until that renderer lands, and after, the worklist carries
every held must-present member as kind `held_hidden_at_render` with the
section's closure condition, so it reaches the producer and the audit.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import gaps  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_cg18_held_ceiling import BAXTER, SWBC  # noqa: E402

CLOSURE = ("SWBC publishing consolidated financials, or stating a branch count "
           "and a single supervising regulator in its own words.")


def _swbc_body():
    return {"fields": SWBC, "empty_state": {
        "reason": "privately held group of separately licensed lines",
        "sources_searched": ["our-story page", "FINRA BrokerCheck"],
        "closure_condition": CLOSURE}}


def test_swbc_held_members_are_six_worklist_items():
    out = gaps.gaps_for_section("overview", "firmographics", _swbc_body())
    held = [g for g in out if g["kind"] == "held_hidden_at_render"]
    assert sorted(g["field"] for g in held) == sorted(
        ["revenue", "assets", "cagr", "branches", "primary_regulator",
         "charter"]), [g["field"] for g in held]


def test_each_held_item_carries_its_reason_and_the_closure_condition():
    out = gaps.gaps_for_section("overview", "firmographics", _swbc_body())
    for g in out:
        if g["kind"] != "held_hidden_at_render":
            continue
        assert g["quarantine_reason"].strip()
        assert g["closure_condition"] == CLOSURE
        assert g["closes_with"].strip()


def test_a_declared_empty_state_does_not_hide_held_members():
    """SWBC declared a section empty_state; that removed field-level gaps and
    must not also remove the held must-present members."""
    out = gaps.gaps_for_section("overview", "firmographics", _swbc_body())
    assert len([g for g in out if g["kind"] == "held_hidden_at_render"]) == 6


def test_baxter_carries_exactly_its_one_held_member():
    out = gaps.gaps_for_section("overview", "firmographics", {"fields": BAXTER})
    held = [g for g in out if g["kind"] == "held_hidden_at_render"]
    assert [g["field"] for g in held] == ["founded"]


def test_held_items_sort_beside_the_must_present_class():
    """Ordered so the list is workable: a held must-present member is the
    contract's own set, so it sits with the must-present class, above every
    ordinary empty field."""
    src = Path(gaps.list_enrichment_gaps.__code__.co_filename).read_text()
    assert '"held_hidden_at_render": 0' in src
