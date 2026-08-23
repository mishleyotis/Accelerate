"""CG-42 — a recommendation names an L3 area the platform page can join on.

Owner, 2026-08-23: "Gulf has platforms with no recommendations — is there a
synthesis layer that challenges recommendations, enhances them, confirms
validity?" The synthesis layer was fine. Gulf's analyst wrote seven real
recommendations with root causes, KPI triples and validation gates. Every
card still read "0 recs".

CG-39 exists because of the first half of this: a page that serves NO
recommendations while the run carries some. It passes Gulf, because Gulf
served all seven. What nothing checked was the ONE STRING the page joins on.

    gulf-coast-business-credit   l3_area absent on 7 of 7 -> 4 cards at
                                 "0 recs", 7 orphans
    axos-bank-...-nyse-ax        l3_area present on 6 of 6 and 2 cards still
                                 at "0 recs", on one word each

Both fixtures below are read off those runs' live promoted submissions on
2026-08-23, trimmed to the fields this gate reads.

THE LINE THIS GATE DOES NOT CROSS. Axos's REC-004 names "Salesforce Platform
Foundation", a platform this page neither ranks nor discards. That is a real
orphan and the page reports it on purpose; folding it into MuleSoft would be
the app deciding two labels mean one platform, which is a producer's call.
So only NEAR-misses are refused — and a shared vendor name is never nearness,
because Databricks MLflow and Databricks Lakehouse Platform are two products
and refusing that pair would teach producers to rename things until the gate
went quiet.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation import (          # noqa: E402
    _check_recommendation_areas_join, _l3_label, _l3_tokens)


def page(cards, recs, discarded=None):
    story = {"platforms": cards}
    if discarded is not None:
        story["discarded"] = discarded
    return {"platform_story": story, "recommendations": {"recommendations": recs}}


def run(cards, recs, discarded=None):
    return _check_recommendation_areas_join("platform", page(cards, recs, discarded))


def ids(out):
    return [r["gate_id"] for r in out]


# ── the label normaliser ──────────────────────────────────────────────

def test_the_code_prefix_is_stripped():
    assert _l3_label("[L3-SF-CRMA] Salesforce CRM Analytics") \
        == "Salesforce CRM Analytics"


def test_the_producers_tally_is_stripped():
    """`(count: 3)` is a vote count from the producer's catalogue pass baked
    into a human label. The web layer already strips it (P-06); the gate has
    to read the same string the page does or it judges a different join."""
    assert _l3_label("[L3-SF-DC-CORE] Data Cloud (count: 3)") == "Data Cloud"


def test_a_plain_label_survives_untouched():
    assert _l3_label("MuleSoft Anypoint Platform") == "MuleSoft Anypoint Platform"


def test_a_vendor_name_is_not_product_identity():
    """The whole basis for leaving honest orphans alone."""
    assert not (_l3_tokens("Databricks MLflow")
                & _l3_tokens("Databricks Lakehouse Platform"))
    assert not (_l3_tokens("Salesforce CRM Analytics")
                & _l3_tokens("Salesforce Data Cloud"))


# ── Gulf: the field absent on every recommendation ────────────────────

#: Gulf's four promoted cards and seven promoted recommendations, verbatim in
#: the two fields this gate reads.
GULF_CARDS = [
    {"rank": 1, "l3_area": "[L3-SF-PLATFORM-FOUNDATION] Salesforce Platform Foundation"},
    {"rank": 2, "l3_area": "[L3-SF-FSC] Salesforce Financial Services Cloud"},
    {"rank": 3, "l3_area": "[L3-SF-MC-ACCT] Marketing Cloud Account Engagement (Pardot)"},
    {"rank": 4, "l3_area": "[L3-SF-CRMA] Salesforce CRM Analytics"},
]
GULF_RECS = [
    {"rec_id": "REC-1", "title": "Establish the platform delivery model and interfaces"},
    {"rec_id": "REC-2", "title": "Connect the lending platform to the client record"},
    {"rec_id": "REC-3", "title": "Orchestrate the funding cycle hand-offs"},
    {"rec_id": "REC-4", "title": "Grade and route enquiries at capture"},
    {"rec_id": "REC-5", "title": "Capture invoice schedules as structured data"},
    {"rec_id": "REC-6", "title": "Specify one client record"},
    {"rec_id": "REC-7", "title": "Record the underwriting exception reasoning"},
]


def test_the_reported_gulf_payload_is_refused():
    out = run(GULF_CARDS, GULF_RECS)
    assert ids(out) == ["CG-42"], out
    assert out[0]["severity"] == "block"
    m = out[0]["message"]
    assert "7 of 7 recommendations state no l3_area" in m
    assert "REC-1" in m and "REC-7" in m
    assert "0 recs" in m


def test_the_refusal_names_how_many_cards_go_dark():
    out = run(GULF_CARDS, GULF_RECS)
    assert "4" in out[0]["message"]


def test_naming_each_area_clears_it():
    """The repair, on the real payload: each recommendation gets the card
    label its own target cells sit under."""
    recs = copy.deepcopy(GULF_RECS)
    for r, area in zip(recs, ["Salesforce Platform Foundation",
                              "Salesforce Financial Services Cloud",
                              "Salesforce Platform Foundation",
                              "Marketing Cloud Account Engagement (Pardot)",
                              "Salesforce Platform Foundation",
                              "Salesforce CRM Analytics",
                              "Salesforce Platform Foundation"]):
        r["l3_area"] = area
    assert run(GULF_CARDS, recs) == []


def test_one_missing_among_named_ones_is_still_named_by_id():
    recs = copy.deepcopy(GULF_RECS)
    for r in recs:
        r["l3_area"] = "Salesforce CRM Analytics"
    recs[3].pop("l3_area")
    out = run(GULF_CARDS, recs)
    assert ids(out) == ["CG-42"]
    assert "1 of 7" in out[0]["message"]
    assert "REC-4" in out[0]["message"]
    assert "REC-1" not in out[0]["message"]


def test_an_empty_string_is_not_a_label():
    recs = [{"rec_id": "REC-1", "l3_area": "   "}]
    out = run(GULF_CARDS, recs)
    assert ids(out) == ["CG-42"]
    assert "1 of 1" in out[0]["message"]


# ── Axos: present, and still one word from joining ────────────────────

AXOS_CARDS = [
    {"rank": 1, "l3_area": "[L3-MS-ANYPOINT] MuleSoft Anypoint Platform"},
    {"rank": 2, "l3_area": "[L3-SF-DATA-CLOUD] Salesforce Data Cloud (Data 360)"},
    {"rank": 3, "l3_area": "[L3-SF-CRMA] Salesforce CRM Analytics"},
    {"rank": 4, "l3_area": "[L3-DB-MLFLOW] Databricks MLflow"},
    {"rank": 5, "l3_area": "[L3-SF-AGENTFORCE] Salesforce Agentforce"},
]
AXOS_RECS = [
    {"rec_id": "REC-001", "l3_area": "Databricks MLflow"},
    {"rec_id": "REC-002", "l3_area": "Salesforce Data Cloud"},
    {"rec_id": "REC-003", "l3_area": "MuleSoft Anypoint Platform"},
    {"rec_id": "REC-004", "l3_area": "Salesforce Platform Foundation"},
    {"rec_id": "REC-005", "l3_area": "Salesforce CRM Analytics"},
    {"rec_id": "REC-006", "l3_area": "Agentforce 360 Platform"},
]
AXOS_DISCARDED = [
    {"platform": "Salesforce Financial Services Cloud"},
    {"platform": "OutSystems"},
    {"platform": "Salesforce Marketing Cloud"},
    {"platform": "Databricks Lakehouse Platform"},
]


def test_the_reported_axos_payload_is_refused_twice():
    """Two cards, two words. REC-002 is a substring of its card's label;
    REC-006 shares the distinctive token."""
    out = run(AXOS_CARDS, AXOS_RECS, AXOS_DISCARDED)
    assert ids(out) == ["CG-42", "CG-42"], out
    joined = " ".join(r["message"] for r in out)
    assert "REC-002" in joined and "Salesforce Data Cloud (Data 360)" in joined
    assert "REC-006" in joined and "Salesforce Agentforce" in joined


def test_the_honest_orphan_is_left_alone():
    """REC-004 names a platform this page neither ranks nor discards. The page
    reports it as an orphan on purpose and the gate says nothing about it —
    this is the boundary the whole design turns on."""
    out = run(AXOS_CARDS, AXOS_RECS, AXOS_DISCARDED)
    assert all("REC-004" not in r["message"] for r in out)


def test_a_discarded_platform_is_a_real_area():
    """A recommendation may point at a platform the page explicitly set
    aside; that is a stated area, not a near-miss on a ranked one."""
    recs = [{"rec_id": "REC-X", "l3_area": "Salesforce Marketing Cloud"}]
    assert run(AXOS_CARDS, recs, AXOS_DISCARDED) == []


def test_two_databricks_products_are_not_a_near_miss():
    """The rule that keeps the gate from teaching producers to rename."""
    recs = [{"rec_id": "REC-X", "l3_area": "Databricks Lakehouse Platform"}]
    assert run(AXOS_CARDS, recs, []) == []


def test_aligning_both_labels_clears_it():
    recs = copy.deepcopy(AXOS_RECS)
    recs[1]["l3_area"] = "Salesforce Data Cloud (Data 360)"
    recs[5]["l3_area"] = "Salesforce Agentforce"
    assert run(AXOS_CARDS, recs, AXOS_DISCARDED) == []


def test_the_code_prefixed_form_joins_too():
    """A producer that writes the card's full coded label is not wrong; the
    page normalises both ends before comparing and so does the gate."""
    recs = [{"rec_id": "REC-X",
             "l3_area": "[L3-SF-CRMA] Salesforce CRM Analytics"}]
    assert run(AXOS_CARDS, recs, AXOS_DISCARDED) == []


# ── scope ─────────────────────────────────────────────────────────────

def test_no_other_page_is_touched():
    for p in ("overview", "heatmap", "context", "techstack", "insights"):
        assert _check_recommendation_areas_join(
            p, page(GULF_CARDS, GULF_RECS)) == []


def test_a_page_with_no_cards_is_cg30s_business():
    assert run([], GULF_RECS) == []


def test_a_page_with_no_recommendations_is_cg39s_business():
    """CG-39 already refuses the dropped-set case with the bundle count in
    hand. Two gates refusing one payload for different reasons would tell a
    producer to fix it twice."""
    assert run(GULF_CARDS, []) == []


def test_a_missing_section_is_not_a_finding():
    assert _check_recommendation_areas_join("platform", {}) == []
    assert _check_recommendation_areas_join(
        "platform", {"platform_story": {"platforms": GULF_CARDS}}) == []


def test_a_non_dict_recommendation_does_not_crash_the_gate():
    out = run(GULF_CARDS, ["a bare string", None, {"rec_id": "REC-9"}])
    assert ids(out) == ["CG-42"]
    assert "REC-9" in out[0]["message"]


def test_the_gate_is_registered_with_its_family_and_severity():
    from dma_mcp.gates import GATES
    assert "CG-42" in GATES
    assert GATES["CG-42"][-1] == "block"
    why = GATES["CG-42"][3]
    assert "Gulf" in why and "Axos" in why
    assert "CG-39" in why


def test_it_runs_inside_pass_one():
    """A gate nobody dispatches is a gate that does not exist — the lesson
    from the deploy that promoted two runs past four green gates."""
    from dma_mcp.validation import validate_pass1
    out = validate_pass1("platform", page(GULF_CARDS, GULF_RECS))
    assert any(r["gate_id"] == "CG-42" for r in out), \
        "CG-42 is defined but not reached from validate_pass1"
