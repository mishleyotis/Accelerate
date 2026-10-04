"""CG-PAR blocks on STRUCTURE only — owner decision B (2026-10-04).

The review of fix/gold-parity-promote measured what the first CG-PAR did to
a client that is not one of the gold runs: goeasy-ltd's promoted run
02e840d4 (Consumer Lending), pulled read-only, drew 16 blocking gaps, and
most of them were COUNTS — 15 tech rows against 56, 2 cited ids against 12,
2 addressable cells against 5. How many tech rows a client has is an
assessment result; blocking on it pushes producers to pad. The same review
found the "three gold runs pass" proof vacuous (each gold run sat in its own
reference set) and the gold applied across sub-verticals (three credit
unions holding an insurance broker and a consumer lender to CU's shape).

The owner's decision, recorded in CLAUDE.md:

  · BLOCK only on structural gaps — a section or key the gold always serves
    is missing, or a must-present field null/held beyond the decision-2 cap;
  · list-length and fill-ratio differences are WARNINGS, in the verdict;
  · leave-one-out: a gold run is never compared with itself;
  · sub-vertical-matched gold preferred; the cross-sub-vertical gold is used
    for structure only.

Targets here are the committed gold SHAPES, thinned — page_shape passes a
shape through unchanged, so no client content is needed — and placeholder
payloads where the must-present names matter.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _promote_fake import ENV, RUN, Conn, skeleton  # noqa: E402

from dma_mcp import parity, promote_checks  # noqa: E402
from dma_mcp.promote import promote_run  # noqa: E402

pytestmark = pytest.mark.real_parity

GOLD = parity.load_gold()
COUNT_KINDS = {"list_len", "item_key_missing", "item_fill", "stated_share"}


def _gold_pages(label):
    return copy.deepcopy(parity.gold_runs(GOLD)[label])


def _thin_list(node):
    node["n"] = min(node.get("n", 0), 1)
    if node.get("rows"):
        node["rows"] = [r.replace("1", "0") if i else r
                        for i, r in enumerate(node["rows"][:1])]
    for sub in (node.get("nested") or {}).values():
        _thin_list(sub)


def _thin(node):
    """Every list cut to one row: a thinner client, structurally whole."""
    if isinstance(node, dict):
        if "n" in node:
            _thin_list(node)
        for v in list(node.values()):
            _thin(v)
    return node


def thinned(label="gold-40971653"):
    return {p: _thin(shape) for p, shape in _gold_pages(label).items()}


def live_of(pages):
    return {p: {"payload": body} for p, body in pages.items()}


# ── blocker 1 + 4: counts are warnings, not refusals ────────────────────
def test_a_thinner_run_of_another_sub_vertical_is_not_refused():
    """The goeasy class: structurally whole, thinner in every list."""
    reasons, report = promote_checks.gold_parity(live_of(thinned()))
    assert reasons == {}, {p: [r["path"] for r in rs][:6]
                           for p, rs in reasons.items()}


def test_counts_and_fill_ratios_are_warnings_in_the_verdict():
    reasons, report = promote_checks.gold_parity(
        live_of(thinned()), sub_vertical="CU")
    assert reasons == {}
    warned = {w["kind"] for w in report["warnings"]}
    assert "list_len" in warned, report["warnings"][:3]
    assert all(w["severity"] == "warn" for w in report["warnings"])


def test_no_count_kind_is_ever_blocking():
    """The floors (LIST_FLOOR, ITEM_FLOOR) were never adjudicated; they may
    only warn."""
    for sv in ("CU", "CL", "IB", None):
        res = parity.check_run(thinned("gold-c1351d25"), GOLD,
                               sub_vertical=sv)
        assert not [g for g in res["blocking"]
                    if g["kind"] in COUNT_KINDS], sv


# ── blocker 2: leave-one-out ────────────────────────────────────────────
@pytest.mark.parametrize("label", sorted(parity.gold_runs(GOLD)))
def test_a_gold_run_is_compared_without_itself_and_passes(label):
    prefix = GOLD["runs"][label]["run_id_prefix"]
    run_id = prefix + "-0000-0000-0000-000000000000"
    res = parity.check_run(_gold_pages(label), GOLD, run_id=run_id,
                           sub_vertical=GOLD["runs"][label]["sub_vertical"])
    assert label not in res["compared_against"], res["compared_against"]
    assert res["left_out"] == [label]
    assert len(res["compared_against"]) == len(GOLD["runs"]) - 1
    assert res["blocking"] == [], (label, res["blocking"][:3])


def test_leave_one_out_measures_something():
    """Compared with itself a gold run could show nothing. Without itself,
    Golden 1's missing value chain (an optional section the other two serve)
    is visible — as a warning, because the contract makes it optional."""
    res = parity.check_run(_gold_pages("gold-40971653"), GOLD,
                           run_id="40971653-aa3e-4373-9163-a967c57a9305",
                           sub_vertical="CU")
    got = {(w["kind"], w["section"]) for w in res["warnings"]}
    assert ("section_absent", "value_chain") in got, sorted(got)[:8]


# ── blocker 3: the gold's sub-vertical ──────────────────────────────────
def test_every_gold_run_records_its_sub_vertical():
    for label, run in GOLD["runs"].items():
        assert run.get("sub_vertical") in parity.SUB_VERTICALS, label


def test_matched_gold_is_preferred_and_cross_gold_is_structure_only():
    cu = parity.check_run(thinned(), GOLD, sub_vertical="CU")
    cl = parity.check_run(thinned(), GOLD, sub_vertical="CL")
    assert cu["tier"] == "sub_vertical" and cu["warnings"]
    assert cl["tier"] == "cross_sub_vertical"
    assert cl["warnings"] == [], "cross-sub-vertical gold warned on counts"
    assert sorted(cl["compared_against"]) == sorted(GOLD["runs"])


# ── what still blocks ───────────────────────────────────────────────────
def _fields(stated_names, held_names):
    row = {"unit": "u", "as_of": "2025", "confidence": "HIGH",
           "recency_band": "CURRENT", "source_e_id": "E-1"}
    return ([{**row, "field": n, "value": "v", "quarantined": False}
             for n in stated_names]
            + [{**row, "field": n, "value": None, "quarantined": True,
                "quarantine_reason": "searched the call report"}
               for n in held_names])


def swbc_shaped():
    """Shaped like SWBC's staged overview (IB): six must-present members
    held, and employee AND customer readings with no gap_analysis."""
    pages = skeleton()
    pages["overview"]["firmographics"] = {
        **ENV, "e_ids": ["E-1"], "narrative_thread": "t " * 50,
        "sub_vertical_undefined": False, "undated_pct": 0.1,
        "fields": _fields(["employees", "HQ", "founded", "website"],
                          ["revenue", "assets", "CAGR", "branches",
                           "primary_regulator", "charter"])}
    pages["overview"]["sentiment"] = {
        **ENV, "e_ids": ["E-1"], "narrative_thread": "s " * 50,
        "empty_state": {"reason": "one rated line",
                        "sources_searched": ["x — VERIFIED ABSENT"]},
        "bars": [{"source": "s", "audience": "customer", "rating": 4.9,
                  "scale": "1-5", "n": 10, "as_of": "2025", "e_id": "E-1",
                  "url": "u", "trend_vs_prior": None}],
        "themes": [{"theme": "t", "audience": a, "cap_statement": "c",
                    "mapped_subcap_ids": ["P1C1.1.1"]}
                   for a in ("customer", "employee")]}
    return pages


def test_a_structural_gap_still_blocks_across_sub_verticals():
    res = parity.check_run(swbc_shaped(), GOLD, sub_vertical="IB")
    got = {(g["kind"], g["section"], g["key"]) for g in res["blocking"]}
    assert ("key_absent", "sentiment", "gap_analysis") in got, sorted(got)
    assert ("held_beyond_cap", "firmographics", "fields") in got, sorted(got)


def test_a_stated_absence_of_a_conditional_key_is_not_refused():
    """gap_analysis: 'absence is correct when only one audience was
    established'. A run that says so, by name, has stated the absence."""
    pages = swbc_shaped()
    pages["overview"]["sentiment"]["empty_state"]["reason"] = (
        "gap_analysis is omitted: only the customer audience was "
        "established")
    res = parity.check_run(pages, GOLD, sub_vertical="IB")
    assert not [g for g in res["blocking"] if g["key"] == "gap_analysis"]


def test_a_required_section_the_gold_always_serves_blocks_when_missing():
    pages = thinned()
    del pages["overview"]["sections"]["leadership"]
    res = parity.check_run(pages, GOLD, sub_vertical="CL")
    assert ("section_absent", "leadership") in {
        (g["kind"], g["section"]) for g in res["blocking"]}


def test_the_held_cap_agrees_with_cg_18b():
    """One rule, two readers: parity's must-present cap is CG-18b's."""
    from dma_mcp.contracts import sections
    from dma_mcp.validation import _member_groups, held_share_exceeded
    spec = sections("overview")["firmographics"]["fields"]["fields"]
    for held in range(0, 7):
        names = ["revenue", "assets", "CAGR", "branches", "primary_regulator",
                 "charter"]
        val = _fields(["employees", "HQ", "founded", "website"] + names[held:],
                      names[:held])
        over = held_share_exceeded(spec, val, _member_groups(spec)) is not None
        mine = parity.must_present_gaps(
            "overview", {"firmographics": {"fields": val}})
        assert bool(mine) == over, held


# ── through promote_run ─────────────────────────────────────────────────
def test_promote_of_a_run_that_states_its_absences_is_not_refused_by_cg_par():
    """Every section an envelope and a stated empty_state, for an entity
    bound to CL (goeasy's binding): contract-legal and structurally whole.
    The first CG-PAR refused it on 66 gaps."""
    out = promote_run(Conn(skeleton(), sub_vertical="Commercial Lending"), RUN)
    by_gate = out.get("blocking_by_gate") or {}
    assert not any("CG-PAR" in g for g in by_gate.values()), by_gate
    parity_report = out["promote_checks"]["parity"]
    assert parity_report["tier"] == "cross_sub_vertical"
    assert parity_report["sub_vertical"] == "CL"
    assert isinstance(parity_report["warnings"], list)


def test_promote_still_refuses_a_structural_gap():
    out = promote_run(Conn(swbc_shaped(), sub_vertical="Insurance Brokers"),
                      RUN)
    assert out["promoted"] is False
    assert out["blocking_by_gate"]["overview"].get("CG-PAR"), \
        out["blocking_by_gate"]
