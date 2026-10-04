"""Cross-section arithmetic and consistency invariants the contracts name, now
executed by check_consistency.py (SWBC gold audit 2026-10-04, RC-12;
D-18, D-19, D-21, D-24, D-27, D-29).

Every rule here was written in a contract and trusted. Each test is the
SWBC measurement that showed it was not executed, cut to the fields the
rule reads, plus the repaired shape that passes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _consistency as cc  # noqa: E402

MULE = "[L3-MS-ANYPOINT] MuleSoft Anypoint Platform"
GRC = "[L3-PARTNER-SERVICENOW-IRM] ServiceNow IRM"
FACTORS = [  # SWBC MuleSoft, platform submission 45a861d1
    {"name": "Addressable opportunity", "value": 0.7634, "weight": 0.528, "contribution": 0.4031},
    {"name": "Catalogue interconnect", "value": 0.7011, "weight": 0.208, "contribution": 0.1458},
    {"name": "Greenfield family", "value": 1.0, "weight": 0.064, "contribution": 0.064},
    {"name": "Strategic alignment", "value": 0.4, "weight": 0.2, "contribution": 0.08},
]


def _mule_tile(**kw):
    t = {"platform": "MuleSoft Anypoint Platform", "l3_area": MULE, "rank": 1,
         "state": "READY", "fit_score": 58.9, "factors": FACTORS,
         "subtotal": 0.6929, "readiness_multiplier": 0.85, "relevance": 1.0,
         "gaps": [{"subcap_id": "P4C3.3.1"}]}
    t.update(kw)
    return t


def _o5_tile(**kw):
    t = {"platform": "MuleSoft Anypoint Platform", "rank": 1, "composite": 58.9,
         "relevance": 1.0, "factors": FACTORS}
    t.update(kw)
    return t


# ── O5 / P1 arithmetic (RC-12(a), D-18) ─────────────────────────────────

def test_swbc_o5_tile_whose_factors_do_not_reach_its_composite_is_refused(tmp_path):
    """SWBC: contributions sum to 0.6929 -> 69.3, the tile states 58.9; the
    0.85 readiness multiplier lived only in the unserved r_layer."""
    pages = {"overview": {"opportunity": {"tiles": [_o5_tile()]}},
             "platform": {"platform_story": {"platforms": [_mule_tile()]}}}
    _, out = cc.run(cc.rundir(tmp_path, pages))
    msgs = cc.blocks(out, "O5 arithmetic")
    assert msgs and "69.3" in msgs[0] and "58.9" in msgs[0], out


def test_an_o5_tile_carrying_its_multiplier_reconciles(tmp_path):
    pages = {"overview": {"opportunity": {"tiles": [_o5_tile(readiness_multiplier=0.85)]}},
             "platform": {"platform_story": {"platforms": [_mule_tile()]}}}
    _, out = cc.run(cc.rundir(tmp_path, pages))
    assert not cc.blocks(out, "O5 arithmetic"), out
    assert not cc.blocks(out, "P1 arithmetic"), out
    assert not cc.blocks(out, "O5 ↔ P1"), out


def test_o5_and_p1_disagreeing_on_one_platform_block(tmp_path):
    pages = {"overview": {"opportunity": {"tiles": [
                 _o5_tile(readiness_multiplier=0.85, rank=2)]}},
             "platform": {"platform_story": {"platforms": [_mule_tile()]}}}
    _, out = cc.run(cc.rundir(tmp_path, pages))
    assert cc.blocks(out, "O5 ↔ P1"), out


def test_a_tile_relevance_the_engine_does_not_return_blocks(tmp_path):
    """SWBC: relevance 1.0 on every tile; the engine returned 0.971-0.98."""
    pages = {"platform": {"platform_story": {"platforms": [_mule_tile()]}}}
    fit = {"platforms": [{"platform": "MuleSoft Anypoint Platform", "l3_area": MULE,
                          "state": "READY", "relevance": 0.971,
                          "readiness_multiplier": 0.85}]}
    _, out = cc.run(cc.rundir(tmp_path, pages, fit=fit))
    msgs = cc.blocks(out, "P1 ↔ engine")
    assert msgs and "relevance" in msgs[0], out


# ── states, area tabs, discards (RC-12(e)(f)(g), D-19) ──────────────────

def test_swbc_too_narrow_tile_with_a_rank_is_refused(tmp_path):
    grc = {"platform": "Governance, risk and compliance platform", "l3_area": GRC,
           "state": "TOO_NARROW", "rank": 8, "fit_score": 22.8}
    pages = {"platform": {"platform_story": {"platforms": [_mule_tile(), grc]}}}
    _, out = cc.run(cc.rundir(tmp_path, pages))
    msgs = cc.blocks(out, "P1 state")
    assert msgs and "TOO_NARROW" in msgs[0], out


def test_a_recommendation_area_with_no_tile_is_refused(tmp_path):
    pages = {"platform": {
        "platform_story": {"platforms": [_mule_tile()]},
        "recommendations": {"recommendations": [
            {"rec_id": "REC-13", "l3_area": MULE, "dma_impact": []},
            {"rec_id": "REC-01", "dma_impact": [],
             "l3_area": "Digital Strategy Workshop (advisory engagement, no platform area)"}]}}}
    _, out = cc.run(cc.rundir(tmp_path, pages))
    msgs = cc.blocks(out, "P2 ↔ P1")
    assert msgs and "REC-01" in msgs[0], out
    # a declared null-fit tile for the advisory area satisfies it
    pages["platform"]["platform_story"]["platforms"].append(
        {"platform": "Digital Strategy Workshop", "state": "ADVISORY",
         "l3_area": "Digital Strategy Workshop (advisory engagement, no platform area)",
         "fit_score": None, "rank": None,
         "fit_basis": "advisory engagement; the engine ranks platform areas, not workshops"})
    _, out = cc.run(cc.rundir(tmp_path, pages, name="run2"))
    assert not cc.blocks(out, "P2 ↔ P1"), out


def test_a_discard_without_a_cell_count_is_reported(tmp_path):
    pages = {"platform": {"platform_story": {"platforms": [_mule_tile()], "discarded": [
        {"platform": "Salesforce CRM Analytics",
         "reason": "Already owned according to discovery conversations."}]}}}
    _, out = cc.run(cc.rundir(tmp_path, pages))
    assert "P1 discards" in out and "cell count" in out


def test_a_large_catalogue_area_neither_tile_nor_discard_blocks(tmp_path):
    """SWBC: Tableau Pulse (78 cells), Platform Foundation (82), Flow (58)
    were neither tiles nor discards."""
    cat = {"subcaps": [{"subcap_id": f"P1C1.{i}.1", "l3_platform_areas":
                        ["[L3-TBL-PULSE] Tableau Pulse"]} for i in range(1, 9)]
           + [{"subcap_id": "P4C3.3.1", "l3_platform_areas": [MULE]}]}
    bundle = {"sub_vertical": "IB", "supplementary_sub_verticals": [],
              "scores": [{"subcap_id": f"P1C1.{i}.1", "score": 1.5} for i in range(1, 9)]
              + [{"subcap_id": "P4C3.3.1", "score": 1.9}]}
    pages = {"platform": {"platform_story": {"platforms": [_mule_tile()], "discarded": []}}}
    _, out = cc.run(cc.rundir(tmp_path, pages, bundle=bundle, catalogue=cat))
    msgs = cc.blocks(out, "P1 candidate set")
    assert msgs and "Tableau Pulse" in msgs[0] and "8" in msgs[0], out


# ── H2 thin (RC-12(c), D-21) — the definition stays open ────────────────

def _cell(sid, n, thin, prov="cited"):
    return {"subcap_id": sid, "thin": thin, "synthesis": "x",
            "provenance": f"{prov} synthesis over {n} registered item(s)",
            "e_ids": [f"E-{sid}-{i}" for i in range(n)],
            "items": [{"e_id": f"E-{sid}-{i}", "excerpt": "y" * 60} for i in range(n)]}


def test_a_payload_applying_two_thin_definitions_blocks(tmp_path):
    cells = [_cell("P1C1.1.1", 1, False),   # follows citable<1
             _cell("P1C1.1.2", 1, True)]    # follows fewer-than-three
    _, out = cc.run(cc.rundir(tmp_path, {"heatmap": {"cell_evidence": {"cells": cells}}}))
    msgs = cc.blocks(out, "H2 thin")
    assert msgs and "two" in msgs[0].lower(), out


def test_thin_false_with_nothing_quotable_blocks_under_either_definition(tmp_path):
    cells = [_cell("P1C1.1.1", 0, False, prov="declared")]
    _, out = cc.run(cc.rundir(tmp_path, {"heatmap": {"cell_evidence": {"cells": cells}}}))
    assert cc.blocks(out, "H2 thin"), out


def test_one_consistent_definition_is_a_warning_naming_the_open_adjudication(tmp_path):
    cells = [_cell("P1C1.1.1", 1, True), _cell("P1C1.1.2", 4, False)]
    _, out = cc.run(cc.rundir(tmp_path, {"heatmap": {"cell_evidence": {"cells": cells}}}))
    assert not cc.blocks(out, "H2 thin"), out
    assert "open adjudication" in out


# ── H6 index completeness (RC-12(d), D-27) ──────────────────────────────

def test_swbc_e_cc_925_cited_and_missing_from_h6_is_reported(tmp_path):
    pages = {
        "heatmap": {"evidence": {"evidence": [{"e_id": "E-CC-1"}]},
                    "evidence_age": {"rows": [{"e_id": "E-CC-1"}, {"e_id": "E-CC-925"}]}},
        "context": {"regulatory_standing": {"e_ids": ["E-CC-925", "E-CC-1"]}},
    }
    _, out = cc.run(cc.rundir(tmp_path, pages))
    msgs = cc.blocks(out, "H6 index")
    assert any("E-CC-925" in m for m in msgs), out
    assert any("evidence_age" in m for m in msgs), out


# ── O7 leadership counts and tenure (D-24) ──────────────────────────────

def _roster(n):
    return [{"name": f"P{i}", "title": "Chief", "appointed_on": None,
             "tenure_months": None} for i in range(n)]


def test_swbc_thirteen_executives_over_fourteen_rows_is_reported(tmp_path):
    rows = _roster(14)
    lead = {"roster": rows, "internal_only": ["roster[10]"],
            "narrative_thread": "The panel names thirteen executives across the enterprise."}
    _, out = cc.run(cc.rundir(tmp_path, {"overview": {"leadership": lead}}))
    msgs = cc.blocks(out, "O7 counts")
    assert msgs and "13" in msgs[0] and "14" in msgs[0], out


def test_tenure_with_no_appointment_date_is_reported(tmp_path):
    rows = _roster(2)
    rows[0]["tenure_months"] = 605
    _, out = cc.run(cc.rundir(tmp_path, {"overview": {"leadership": {"roster": rows}}}))
    assert cc.blocks(out, "O7 tenure"), out


# ── O6 ranking basis and counts (RC-12(h), D-29) ────────────────────────

def _f(fid, score, chips=("Data Cloud",)):
    return {"f_id": fid, "title": "t", "platform_chips": list(chips),
            "strategic_alignment": {"score": score, "statement": "s"},
            "strategic_alignment_score": score}


def test_swbc_impact_fallback_over_out_of_order_alignment_scores_is_refused(tmp_path):
    fnd = {"ranking_basis": "impact_fallback", "findings": [
        _f("F-1", 0.8), _f("F-2", 0.4), _f("F-3", None, chips=()),
        _f("F-4", None), _f("F-5", 0.8)]}
    _, out = cc.run(cc.rundir(tmp_path, {"overview": {"findings": fnd}}))
    msgs = cc.blocks(out, "O6 ranking")
    assert msgs and "F-5" in msgs[0], out
    assert "F-3" in out and "platform_chips" in out


def test_a_stated_finding_count_must_match(tmp_path):
    fnd = {"ranking_basis": "alignment", "findings": [_f("F-1", 0.8), _f("F-2", 0.4)],
           "narrative_thread": "Three findings rank constraints, not work."}
    _, out = cc.run(cc.rundir(tmp_path, {"overview": {"findings": fnd}}))
    assert cc.blocks(out, "O6 counts"), out
