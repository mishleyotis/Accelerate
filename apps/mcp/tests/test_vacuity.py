"""CG-15 — a wholly vacuous assessment must not pass every gate.

Before this gate existed, a six-page payload with all 34 sections
present, every required field populated with "N/A" or `[]`, produced
ZERO blocking reasons and was eligible for `promote_run`. Every other
gate in the connector checks structure, identity or arithmetic; none of
them reads the prose for content. For clients 2..50 that is the failure
mode that matters most, because the pipeline's own defences cannot tell
a real assessment from an empty shell.

The other half of these tests is the boundary, and it matters more than
the refusals: an honest ABSENCE must still pass. Refusing "we ran the
ladder across every mandatory source and found nothing" would push a
producer toward inventing content to get past a gate, which is a worse
defect than the one being closed. The fixtures for that side are
VERBATIM from the currently promoted Baxter Credit Union run — the
eleven alert justifications that legitimately say the same thing, and
the two cell syntheses with the highest honest 8-gram overlap in the
whole corpus (0.179, against a refusal line of 0.40).

The refusal fixtures are verbatim from the same run: the seventeen
`overview.ceilings.rows[*].rationale` values, which are one template with
the citation swapped and two pairs of which are byte-identical.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.contracts import PAGES, sections
from dma_mcp.gates import GATES
from dma_mcp.validation import validate_pass1
from dma_mcp.vacuity import (FLOOR_FACTOR, GATE, TEMPLATE_OVERLAP,
                             check_vacuity, is_placeholder, prose_floors,
                             residual_content)

ENV = {"produced_at": "2026-08-08T00:00:00Z", "producer_version": "test@1",
       "e_ids": ["E-BCU-001"], "internal_only": []}

# Real prose, comfortably over its 50-word field's refusal line, so a
# section under test is never accidentally the WHOLLY vacuous case.
REAL_SITUATION = (
    "Baxter Credit Union runs a $6.24 billion balance sheet across more than "
    "thirty large employer groups, and its own consolidation describes the "
    "member record as a patchwork assembled per channel rather than held once "
    "and read everywhere by the servicing stack.")


def _cg15(page, payload):
    return [r for r in check_vacuity(page, payload) if r["gate_id"] == GATE]


# ── the derivation: floors come from the contract, not from here ──────

def test_the_floor_is_read_from_each_field_s_own_contract_doc():
    """"some fields are legitimately 6 words, others 45-75" — so the
    registry is derived from the doc text and nothing here is a constant.
    A field the contract gives no budget is not policed for length."""
    findings = prose_floors("overview")["findings"]["items"]["findings"]
    assert findings["consequence"] == 6        # "consequence: 6-14 words"
    assert findings["body"] == 55              # "body: 55-95 words"
    assert findings["strategic_alignment"] == 15
    assert prose_floors("overview")["exec_summary"]["scalars"]["answer"] == 90
    assert prose_floors("overview")["scores"]["scalars"]["narrative_thread"] == 45
    assert prose_floors("heatmap")["cell_evidence"]["items"]["cells"]["synthesis"] == 40
    # `title: <=12 words` states a ceiling and no floor, so it gains none
    assert "title" not in findings


def test_the_gate_is_in_the_registry_with_its_family_and_behaviour():
    name, plain_label, checks, why, on_failure = GATES[GATE]
    assert GATE.startswith("CG") and on_failure == "block"
    assert plain_label is None                 # blocks, so it is not client-visible
    assert "placeholder" in checks and "empty_state" in checks
    assert "N/A" in why


# ── 1 · placeholder scalars where prose is required ───────────────────

@pytest.mark.parametrize("stub", [
    "N/A", "n/a", "N/A.", "N.A.", "na", "TBD", "tbd.", "-", "--", "—", "–",
    "none", "None.", "unknown", "Unknown", "not applicable", "Not Applicable",
    "not available", "pending", "Pending.", "TODO", "nil", "null", "???",
    "", "   ", "\t\n ",
])
def test_every_placeholder_spelling_is_refused(stub):
    payload = {"exec_summary": {**ENV, "situation": REAL_SITUATION,
                                "question": stub}}
    out = _cg15("overview", payload)
    assert len(out) == 1, stub
    assert out[0]["path"] == "exec_summary.question"
    assert out[0]["severity"] == "block"
    assert "placeholder" in out[0]["message"]
    # the verdict tells the producer what the honest alternative IS
    assert "sources_searched" in out[0]["message"]


@pytest.mark.parametrize("stub", ["N / A", "n.a", "N.A", "not-applicable",
                                  "To Be Determined.", "( TBD )", "n/a."])
def test_a_placeholder_cannot_slip_past_one_punctuation_mark_at_a_time(stub):
    payload = {"exec_summary": {**ENV, "situation": REAL_SITUATION,
                                "question": stub}}
    out = _cg15("overview", payload)
    assert len(out) == 1, stub
    assert "placeholder" in out[0]["message"]


def test_a_placeholder_predicate_that_would_swallow_real_prose_is_wrong():
    """The set is the vocabulary of not-having-written-it, and nothing
    wider: a sentence that merely CONTAINS 'unknown' is prose."""
    assert is_placeholder("N/A") and is_placeholder("  —  ")
    assert not is_placeholder("Unknown ownership of the member record is "
                              "the constraint this finding names.")
    assert not is_placeholder("None of the five platforms addresses the "
                              "integration layer.")


# ── 2 · a prose field under a credible floor for ITS contract ─────────

def test_the_floor_is_per_field_and_not_one_number_for_all():
    """A six-word `consequence` and a ninety-word `answer` are held to
    different lines, both derived, and the verdict names each field's own
    contract figure."""
    short_ok = {"findings": [{"f_id": "F-1", "consequence":
                              "Merger conversion lands on bespoke links"}]}
    assert _cg15("overview", {"findings": {**ENV, **short_ok}}) == []

    same_length_answer = {"exec_summary": {
        **ENV, "situation": REAL_SITUATION,
        "answer": "Merger conversion lands on bespoke links"}}
    out = _cg15("overview", same_length_answer)
    assert len(out) == 1
    assert "contract floor of 90" in out[0]["message"]
    assert f"90 × {FLOOR_FACTOR:g}" in out[0]["message"]


def test_a_stub_under_half_its_floor_is_refused_and_real_short_prose_is_not():
    """The promoted run's lowest words-to-floor ratio is 0.64 (a 16-word
    timeline body against a 25-word floor) — real content that undershoots
    its budget. It passes; a four-word stub in the same field does not."""
    promoted = ("A digital service platform was selected for messaging, "
                "video banking and co-browsing, joining the voice estate.")
    body = {"timeline": {**ENV, "events": [{"event_date": "2019-06-01",
                                            "body": promoted}]}}
    assert _cg15("context", body) == []

    body["timeline"]["events"][0]["body"] = "A platform was selected."
    out = _cg15("context", body)
    assert len(out) == 1 and out[0]["gate_id"] == GATE
    assert "4 words against a contract floor of 25" in out[0]["message"]
    assert "refusal line is 13" in out[0]["message"]


# ── 3 · the semantically-empty section, and the six-page shell ────────

def test_a_section_whose_every_present_field_is_vacuous_is_refused():
    payload = {"exec_summary": {**ENV, "situation": "N/A",
                                "complication": "TBD", "question": "-",
                                "answer": "  ", "sequencing_rationale": "none",
                                "cost_of_delay": "unknown"}}
    out = _cg15("overview", payload)
    assert len(out) == 1                       # one verdict for the shell
    assert out[0]["path"] == "exec_summary"
    assert "6 of 6 present content fields are vacuous" in out[0]["message"]
    assert "empty_state" in out[0]["message"]


def test_an_empty_list_and_an_empty_object_count_as_vacuous():
    payload = {"landscape": {**ENV, "tiles": [], "counts": {}}}
    out = _cg15("insights", payload)
    assert len(out) == 1 and out[0]["path"] == "landscape"


def test_a_number_is_a_fact_so_a_section_carrying_one_is_not_a_shell():
    """A score came off a workbook row. A section with a real figure and
    empty prose gets FIELD verdicts, not the section verdict — otherwise
    the headline case would swallow the specific one."""
    payload = {"scores": {**ENV, "composite": 2.14, "framing": "N/A"}}
    out = _cg15("overview", payload)
    assert [r["path"] for r in out] == ["scores.framing"]


def test_the_whole_vacuous_six_page_payload_is_refused_section_by_section():
    """The measured defect, reproduced: all 34 sections present, every
    required field "N/A" or [], and — before this gate — zero blocking
    reasons. Now every one of the 34 is named."""
    fill = {"string": "N/A", "list": [], "object": {}}
    meta = {"produced_at", "producer_version", "e_ids", "internal_only",
            "empty_state", "r_layer"}
    refused = set()
    for page in PAGES:
        payload = {}
        for name, sec in sections(page).items():
            body = dict(ENV)
            for fname, spec in sec["fields"].items():
                if fname in meta:
                    continue
                if spec["type"] in fill:
                    body[fname] = fill[spec["type"]]
            payload[name] = body
        reasons = validate_pass1(page, payload)
        for r in reasons:
            if r["gate_id"] == GATE:
                refused.add((page, r["section"]))
    assert len(refused) == 34
    assert refused == {(p, s) for p in PAGES for s in sections(p)}


# ── 4 · template prose across items ───────────────────────────────────
#
# Verbatim from the promoted run: one template, the cited document
# swapped, two of them byte-identical. Seventeen rows shipped like this.
CEILING_TEMPLATE = [
    "Best evidence is T2-grade (BCU 2024 Annual Report (PDF)), which "
    "licenses observation up to the Differentiating band under the tier "
    "ceiling. The limiting absence is internal utilisation evidence — "
    "public sources establish deployment, not depth of use.",
    "Best evidence is T2-grade (BCU 2024 Annual Report (PDF)), which "
    "licenses observation up to the Differentiating band under the tier "
    "ceiling. The limiting absence is internal utilisation evidence — "
    "public sources establish deployment, not depth of use.",
    "Best evidence is T2-grade (BCU BioCatch Partnership Press Release), "
    "which licenses observation up to the Differentiating band under the "
    "tier ceiling. The limiting absence is internal utilisation evidence — "
    "public sources establish deployment, not depth of use.",
    "Best evidence is T3-grade, which licenses observation up to the "
    "Competing band under the tier ceiling. The limiting absence is "
    "internal utilisation evidence — public sources establish deployment, "
    "not depth of use.",
]


def _ceilings(rationales):
    return {"ceilings": {**ENV, "rows": [
        {"category_id": f"P1C{i + 1}", "ceiling": "Differentiating",
         "rationale": r} for i, r in enumerate(rationales)]}}


def test_the_promoted_ceilings_template_is_refused_on_every_member():
    out = _cg15("overview", _ceilings(CEILING_TEMPLATE))
    assert len(out) == len(CEILING_TEMPLATE)
    assert {r["path"] for r in out} == {
        f"ceilings.rows[{i}].rationale" for i in range(len(CEILING_TEMPLATE))}
    msg = out[0]["message"]
    assert "share 8-word spans" in msg
    assert f"a line of {TEMPLATE_OVERLAP:g}" in msg
    # the repair, and the door back out for a genuine shared absence
    assert "say what is true of THIS one" in msg
    assert "sources_searched" in msg


def test_two_matching_items_are_a_coincidence_and_three_are_a_template():
    """The group floor is three, matching the audit's own '8-word spans
    shared by 3+ cells'. A pair is not refused."""
    assert _cg15("overview", _ceilings(CEILING_TEMPLATE[:2])) == []
    assert len(_cg15("overview", _ceilings(CEILING_TEMPLATE[:3]))) == 3


# The two highest-overlapping HONEST syntheses in the promoted run's 706
# cells (0.179 against a line of 0.40). They share a fact about the
# Illinois CRA and assert different things about different capabilities.
HONEST_SYNTHESES = [
    "Fair lending governance at BCU has a new external driver: the Illinois "
    "Community Reinvestment Act now applies to state-chartered credit unions "
    "above $391 million, and BCU at $6.24 billion must comply from February "
    "2025. Its membership spans more than thirty large employers, so lending "
    "outcomes vary by workforce. No source describes those outcomes being "
    "tested for disparity.",
    "BCU does community work — Habitat for Humanity builds, employee "
    "volunteering — and its own consolidation describes that as informal "
    "activity without a formal framework. The Illinois Community Reinvestment "
    "Act now applies to state-chartered credit unions above $391 million, "
    "which turns an optional document into a dated obligation.",
    "Automated transaction monitoring is named directly by BCU's security "
    "leadership, alongside anomaly and synthetic-identity detection, and the "
    "institution carries a clean supervisory record under joint examination. "
    "Sanctions screening specifically — list management, match tuning, alert "
    "disposition — is a distinct system that no source names.",
]


def test_distinct_arguments_that_share_a_fact_are_not_a_template():
    payload = {"cell_evidence": {**ENV, "cells": [
        {"subcap_id": f"P1C2.9.{i}", "synthesis": s, "grounded_on": 1}
        for i, s in enumerate(HONEST_SYNTHESES)]}}
    assert _cg15("heatmap", payload) == []


# ── 5 · prose that restates a score, or inventories the evidence ──────

@pytest.mark.parametrize("text,marker", [
    ("P4C1 scores 2.1, below the peer median of 3.0, and the category "
     "composite of 2.4 sits below the pillar mean of 2.8 as well.",
     "restatement"),
    ("This cell scores 1.80 against a peer median of 2.40; the category "
     "scores 2.10 and the pillar composite scores 2.35, all below the cohort "
     "averages.", "restatement"),
    ("The category sits in the Building band, below the cohort average, and "
     "the pillar composite ranks below the peer median at every level of the "
     "workbook.", "restatement"),
    ("Two items of evidence speak to this cell, and three more sources were "
     "reviewed; the cited rows cover the capability and are documented in the "
     "pack.", "inventory"),
    ("Three evidence rows cover this capability and two of them are cited; "
     "the other sources are registered in the evidence pack and available in "
     "the bundle.", "inventory"),
])
def test_a_long_sentence_made_only_of_the_score_or_the_pile_is_refused(text, marker):
    """Long enough to clear the 40-word field's floor, and still asserting
    nothing — which is exactly the shape a word count cannot see."""
    payload = {"cell_evidence": {**ENV, "cells": [
        {"subcap_id": "P4C1.1.1", "synthesis": text}]}}
    out = _cg15("heatmap", payload)
    assert len(out) == 1, text
    assert out[0]["path"] == "cell_evidence.cells[0].synthesis"
    assert marker in out[0]["message"]
    assert "content words" in out[0]["message"]


def test_the_evidence_inventory_synthesis_named_in_the_brief_is_refused():
    """"Two items speak to this cell." — six words in a field whose floor
    is six, so the word count has nothing to say and the residual does."""
    payload = {"findings": {**ENV, "findings": [
        {"f_id": "F-1", "consequence": "Two items speak to this cell."}]}}
    out = _cg15("overview", payload)
    assert len(out) == 1
    assert out[0]["path"] == "findings.findings[0].consequence"
    assert "inventory" in out[0]["message"]
    assert "0 content words" in out[0]["message"]


def test_a_score_sentence_that_also_asserts_something_passes_the_residual():
    """The check must not refuse prose for MENTIONING a score — only for
    being nothing but one. Measured on the residual, not on the mention."""
    text = ("P4C1 scores 2.1 against a peer median of 3.0, and the shortfall "
            "sits entirely in lineage tooling that no team currently owns.")
    left, score_hits, _inv = residual_content(text)
    assert score_hits >= 3 and len(left) > 2
    payload = {"cell_evidence": {**ENV, "cells": [
        {"subcap_id": "P4C1.1.1", "synthesis": text}]}}
    # long enough prose is separately under its 40-word floor, so assert
    # on the residual verdict specifically
    assert not [r for r in _cg15("heatmap", payload)
                if "content words" in r["message"]]


def test_the_promoted_run_s_shortest_real_consequence_survives_the_residual():
    """The lowest residual in the whole promoted corpus is 4 content words
    (a seven-word `consequence`), against a floor of 2."""
    left, _s, _i = residual_content("Triggers one of two active cross-pillar caps")
    assert len(left) == 4
    payload = {"findings": {**ENV, "findings": [
        {"f_id": "F-1",
         "consequence": "Triggers one of two active cross-pillar caps"}]}}
    assert _cg15("overview", payload) == []


# ── the boundary · an honest absence must still PASS ──────────────────
#
# Verbatim from the promoted run. Eleven alerts whose ladder ran across
# every mandatory source say the same sentence eleven times because it is
# the same finding eleven times. Refusing that would be demanding
# invention, which is worse than the hole this gate closes.
ALERT_LADDER = {
    "sources_searched": ["package evidence index (82 items, 329 facts)",
                         "client profile", "assessment report",
                         "public web (assessment phase, PUBLIC mode)"],
    "queries_run": ["INT-020: Does BCU hold proprietary technology patents?"],
}
ALERT_TEMPLATE = [
    ("P1C3.4.4", "WORKED_ABSENT",
     "IP/patents: the assessment ran PUBLIC-mode research and recorded this "
     "cell as NO_EVIDENCE. Cannot score without internal evidence. The "
     "evidence that exists licenses a ceiling estimate only; the internal "
     "artefact named in the closure condition settles it."),
    ("P3C3.2.1", "UNWORKED",
     "BSA/AML specifics: the assessment ran PUBLIC-mode research and recorded "
     "this cell as THIN. Ceiling estimate with +0.2 uncertainty. The evidence "
     "that exists licenses a ceiling estimate only; the internal artefact "
     "named in the closure condition settles it."),
    ("P3C4.5.2", "UNWORKED",
     "Vendor concentration risk: the assessment ran PUBLIC-mode research and "
     "recorded this cell as THIN. Ceiling estimate with +0.2 uncertainty. The "
     "evidence that exists licenses a ceiling estimate only; the internal "
     "artefact named in the closure condition settles it."),
]


def _alerts(with_ladder=True):
    return {"alerts": {**ENV, "alerts": [
        {"subcap_id": c, "state": s, "justification": j,
         **(ALERT_LADDER if with_ladder else {})}
        for c, s, j in ALERT_TEMPLATE]}}


def test_a_recorded_absence_with_its_ladder_passes_the_template_check():
    """The promoted alert justifications, verbatim, at an overlap of
    0.90-0.97 — and exempt, because each one records WORKED_ABSENT or
    UNWORKED with the sources it searched."""
    assert _cg15("heatmap", _alerts()) == []


def test_the_same_text_without_the_ladder_is_refused():
    """The exemption is the LADDER, not the wording — strip the record of
    what was searched and the same three justifications are a template."""
    out = _cg15("heatmap", _alerts(with_ladder=False))
    assert len(out) == 3
    assert all("share 8-word spans" in r["message"] for r in out)


def test_a_section_with_a_valid_empty_state_is_not_a_vacuous_section():
    """"An empty surface is a value, not an omission." A section that says
    what it looked for and did not find renders the absence as a finding."""
    payload = {"acquisitions": {
        **ENV, "rows": [],
        "empty_state": {"reason": "No closed or announced transactions were "
                                  "established for this institution.",
                        "sources_searched": ["NCUA merger notices",
                                             "state regulator filings",
                                             "press releases 2021-2026"],
                        "closure_condition": "A published merger notice."}}}
    assert _cg15("context", payload) == []


def test_an_absence_rung_without_a_ladder_does_not_buy_the_exemption():
    """A state that claims the ladder ran and records no search is not an
    absence; it is an assertion with nothing behind it — the same posture
    AG-03 takes."""
    payload = {"acquisitions": {**ENV, "rows": [], "empty_state":
                                {"reason": "None found."}}}
    out = _cg15("context", payload)
    assert len(out) == 1 and out[0]["path"] == "acquisitions"


@pytest.mark.parametrize("marker", [
    {"state": "WORKED_ABSENT", "sources_searched": ["registry", "filings"]},
    {"state": "UNWORKED", "queries_run": ["INT-020"]},
    {"state": "NOT_RUN", "not_run_reason": "The cohort has four members."},
    {"cannot_estimate": True},
    {"verified_absent": True},
    {"verified_sparse": True},
    {"quarantined": True, "quarantine_reason": "Two sources disagree on the "
                                               "date and neither is primary."},
])
def test_each_rung_of_the_absence_ladder_exempts_a_short_honest_statement(marker):
    """A 40-word floor on a synthesis is right for an argument. It is not
    right for "the ladder ran and found nothing", which is the whole of
    what there is to say."""
    payload = {"cell_evidence": {**ENV, "cells": [
        {"subcap_id": "P4C1.1.1",
         "synthesis": "The ladder ran across every mandatory source and "
                      "established no evidence for this capability.",
         **marker}]}}
    assert _cg15("heatmap", payload) == [], marker


@pytest.mark.parametrize("marker", [
    {"thin": True},
    {"recency_band": "UNVERIFIED"},
    {"state": "WORKED_ABSENT"},               # the rung with no ladder
    {"quarantined": True},                    # quarantined with no reason
])
def test_a_marker_that_is_not_a_recorded_absence_buys_no_exemption(marker):
    """`thin` says the evidence is short, not that the argument is; an
    undated SOURCE is CG-10's business and no licence for the sentence
    beside it to say nothing; and a rung with no search behind it is an
    assertion, not a finding — the same posture AG-03 takes. A producer
    who could buy the exemption with one boolean would have a switch."""
    payload = {"cell_evidence": {**ENV, "cells": [
        {"subcap_id": "P4C1.1.1", "synthesis": "Evidence is limited.",
         **marker}]}}
    out = _cg15("heatmap", payload)
    assert len(out) == 1, marker
    assert out[0]["path"] == "cell_evidence.cells[0].synthesis"


def test_a_bare_placeholder_is_refused_even_inside_a_recorded_absence():
    """The one thing no absence excuses. The protocol is a reason and a
    ladder; 'N/A' is neither, and it renders as itself on a client page."""
    payload = {"cell_evidence": {**ENV, "cells": [
        {"subcap_id": "P4C1.1.1", "synthesis": "N/A",
         "state": "WORKED_ABSENT",
         "sources_searched": ["registry", "filings"]}]}}
    out = _cg15("heatmap", payload)
    assert len(out) == 1
    assert out[0]["path"] == "cell_evidence.cells[0].synthesis"
    assert "placeholder is not an absence" in out[0]["message"]


def test_the_verdict_names_the_gate_the_path_and_the_arithmetic():
    """Invariant 12's requirement, asserted over every shape this gate
    can emit."""
    shapes = [
        ("overview", {"exec_summary": {**ENV, "situation": "N/A"}}),
        ("overview", {"exec_summary": {**ENV, "answer": "Too short."}}),
        ("overview", {"exec_summary": {**ENV, "situation": "N/A",
                                       "answer": "TBD"}}),
        ("overview", _ceilings(CEILING_TEMPLATE)),
        ("heatmap", {"cell_evidence": {**ENV, "cells": [
            {"subcap_id": "P4C1.1.1",
             "synthesis": "P4C1 scores 2.1, below the peer median of 3.0."}]}}),
    ]
    for page, payload in shapes:
        out = _cg15(page, payload)
        assert out, payload
        for r in out:
            assert r["gate_id"] == GATE and r["severity"] == "block"
            assert r["path"] and r["section"]
            assert any(ch.isdigit() for ch in r["message"]), r["message"]
