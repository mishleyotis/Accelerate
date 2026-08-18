"""The empty-field worklist, and the distinction it exists to draw.

Build owner, 2026-08-14: "Never place an em dash. There should always be a way
to send a signal to the MCP to give us an enrichment of the empty field."

An em dash reads identically whether the producer searched and found nothing,
held a figure that failed the identity gate, or was never asked. Those are three
different facts and only one is a finding. These tests pin that the computed
worklist tells them apart — because if it does not, the list is just the em
dashes again in JSON.

The queue is COMPUTED, not stored. The build owner chose that shape over a
click-to-request table: the set of empty fields is derivable from the staged
payloads at any moment, so a stored request could only go stale — it would keep
asking for a field a later re-promote had already filled.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import gaps


def _sec(**kw):
    return kw


# ── the three states an empty spot can be in ──────────────────────────
def test_a_silent_field_is_a_gap():
    out = gaps.gaps_for_section("techstack", "techstack",
                                _sec(items=[], compliance_attestations=None))
    paths = [g["path"] for g in out]
    assert "techstack.compliance_attestations" in paths


def test_a_held_field_is_not_a_gap():
    """Quarantined WITH a reason is the producer's most defensible output: the
    ladder ran, the figure failed the identity gate, and the reason IS the
    content. Queueing it would ask for work already done."""
    body = {"fields": [
        {"field": "website", "value": None, "quarantined": True,
         "quarantine_reason": "two domains resolve to this legal name and "
                              "neither could be tied to the filing entity"},
    ]}
    out = gaps.gaps_for_section("overview", "firmographics", body)
    assert not any("website" in g["path"] for g in out)


def test_a_quarantine_with_no_reason_is_still_a_gap():
    """Silence dressed as a finding. This is the state CG-18 refuses at submit,
    and it must not buy its way out of the worklist either."""
    body = {"fields": [{"field": "website", "value": None, "quarantined": True,
                        "quarantine_reason": "   "}]}
    out = gaps.gaps_for_section("overview", "firmographics", body)
    assert any("website" in g["path"] for g in out)


def test_a_declared_empty_state_removes_the_section_s_field_gaps():
    """A section that ran the ladder and recorded it has answered. Reporting
    each of its fields would drown the real gaps in a run that did its work."""
    body = {"items": None, "empty_state": {
        "reason": "no technology register could be established",
        "sources_searched": ["vendor case studies", "job postings", "Clay"]}}
    assert gaps.gaps_for_section("techstack", "techstack", body) == []


# ── the must-present class, which is the one to work first ────────────
def test_a_missing_must_present_member_is_the_top_class():
    body = {"fields": [{"field": "employees", "value": 767}]}
    out = gaps.gaps_for_section("overview", "firmographics", body)
    kinds = {g["kind"] for g in out}
    assert "must_present_member" in kinds
    websites = [g for g in out if g["field"] == "website"]
    assert len(websites) == 1
    assert "every sub-vertical" in websites[0]["reason"]


def test_the_website_gap_is_the_one_the_owner_reported():
    """The promoted reference client carries 13 firmographic fields and none of
    them is the website; the row renders as an em dash today. It must appear in
    the worklist by name."""
    served = ["branches", "loans", "roa", "charter", "primary_regulator",
              "shares", "total_assets", "member_count", "employees",
              "net_worth_ratio", "hq", "cagr", "founded"]
    body = {"fields": [{"field": f, "value": 1} for f in served]}
    out = gaps.gaps_for_section("overview", "firmographics", body)
    assert "website" in {g["field"] for g in out}


def test_a_stated_member_is_not_reported():
    body = {"fields": [{"field": "website", "value": "bcu.org"}]}
    out = gaps.gaps_for_section("overview", "firmographics", body)
    assert "website" not in {g.get("field") for g in out}


# ── noise control: a worklist nobody skims ────────────────────────────
def test_envelope_fields_are_never_gaps():
    """`produced_at`, `e_ids`, `internal_only` are the submission's own
    machinery. An earlier draft reported produced_at on all 34 sections, which
    put 34 non-gaps at the top of the list."""
    out = gaps.gaps_for_section("insights", "insights",
                                _sec(cards=[{"x": 1}], produced_at=None,
                                     e_ids=None, internal_only=None))
    assert all(g["field"] not in ("produced_at", "e_ids", "internal_only")
               for g in out), [g["field"] for g in out]


def test_a_boolean_is_not_a_gap_when_absent():
    """A boolean's absence IS its value: a run declares `identity_mismatch`
    when true and omits it when false."""
    out = gaps.gaps_for_section("overview", "firmographics",
                                _sec(fields=[{"field": "website", "value": "x"}],
                                     identity_mismatch=None,
                                     sub_vertical_undefined=None))
    assert all(g["field"] not in ("identity_mismatch", "sub_vertical_undefined")
               for g in out)


def test_may_be_empty_fields_are_not_gaps():
    out = gaps.gaps_for_section("techstack", "techstack",
                                _sec(items=[{"vendor": "a"}], dropped=[]))
    assert "dropped" not in {g["field"] for g in out}


# ── shape ─────────────────────────────────────────────────────────────
def test_every_gap_says_how_to_close_it():
    body = {"fields": [{"field": "employees", "value": 767}]}
    for g in gaps.gaps_for_section("overview", "firmographics", body):
        assert g["closes_with"].strip(), g["path"]
        assert g["page"] and g["section"] and g["path"]


def test_closing_a_must_present_member_can_be_done_by_holding_it():
    """The escape hatch must be stated, or a producer who genuinely cannot find
    a value has only one way out of the list: inventing one."""
    body = {"fields": [{"field": "employees", "value": 1}]}
    g = next(x for x in gaps.gaps_for_section("overview", "firmographics", body)
             if x["field"] == "website")
    assert "quarantine_reason" in g["closes_with"]


def test_a_non_dict_body_does_not_raise():
    assert gaps.gaps_for_section("overview", "firmographics", None) == []
    assert gaps.gaps_for_section("overview", "firmographics", []) == []


def test_an_unknown_section_yields_nothing_rather_than_raising():
    assert gaps.gaps_for_section("overview", "not_a_section", {"x": None}) == []
