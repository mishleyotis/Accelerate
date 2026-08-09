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
from dma_mcp.vacuity import (CLAIM_MIN_WORDS, CLAIM_OVERLAP, FLOOR_FACTOR,
                             CLAIM_ALONE, GATE, TEMPLATE_OVERLAP, _overlap, check_vacuity,
                             claim_words, is_placeholder, item_keys,
                             prose_floors, records_absence, residual_content,
                             shingles)

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
    assert f"line {TEMPLATE_OVERLAP:g}" in msg
    # both terms are stated, so the producer can see that the agreement is
    # not the contract's own scaffolding — and the claim term leads, because
    # since pass 3 it can refuse ALONE at CLAIM_ALONE, phrasing or no
    assert "content words" in msg and f"{CLAIM_ALONE:g} alone" in msg
    # the repair, and the route THIS shape actually has
    assert "say what is true of THIS one" in msg
    assert "e_ids" in msg and "leave it out of the array" in msg
    # and never a route it does not have — `overview.ceilings.rows` declares
    # no state and no ladder, so naming them would be the trap again
    assert "sources_searched" not in msg


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


# ── 4b · the second term: the CLAIM, not the contract's scaffolding ───
#
# H2 requires every synthesis to say "where the score sits against the peer
# median" and to cite inline. Two honest syntheses obeying that contract are
# SUPPOSED to share those spans. Pass 1 scored them, which is how a gate
# meant to catch prose that asserts nothing came to threaten prose that
# asserts something in the shape the contract asked for.
#
# These four are the promoted Baxter run's own zero-evidence cells,
# near-verbatim: same finding (nothing was found), same mandated frame, and
# four completely different sets of things looked for. That is what an
# honest absence at 700-cell scale looks like, and it must pass.
BAXTER_ABSENCES = [
    "Academic partnership leaves visible traces — named research "
    "collaborations, sponsored programmes, university recruiting pipelines — "
    "and none appears anywhere in BCU's own materials, its news page, or the "
    "trade coverage of it. The ladder ran across all six mandatory tiers.",
    "User acceptance testing leaves artefacts — test plans, sign-off records, "
    "defect logs — and none is visible in BCU's public record, nor in the "
    "assessment corpus, nor in any vendor case study covering its core "
    "conversion. The ladder ran across all six mandatory tiers.",
    "No emissions baseline, reduction target or transition commitment appears "
    "in BCU's annual report, its about pages, its news releases or the trade "
    "coverage of it. Nothing in the corpus describes a measurement method "
    "either. The ladder ran across all six mandatory tiers.",
    "A roadmap in this domain would sequence commitments against dates, and "
    "BCU has no published commitments to sequence — the ladder ran across its "
    "annual report, its about and community pages, its news releases and the "
    "regulator's own filings index.",
]


def test_four_absences_that_name_different_things_looked_for_are_not_a_template():
    """The line the gate has to hold. All four report the same OUTCOME in
    the same mandated frame; none of them reports the same SEARCH. Once the
    score and evidence registers are stripped, what is left is four
    different vocabularies, and this is the payload that must ship."""
    payload = {"cell_evidence": {**ENV, "cells": [
        {"subcap_id": f"P1C3.6.{i}", "synthesis": s}
        for i, s in enumerate(BAXTER_ABSENCES)]}}
    assert _cg15("heatmap", payload) == []


def test_the_same_outcome_with_nothing_named_is_a_template():
    """The other side of the same line, from the two payloads refused
    today: strip out WHAT was looked for and the four sentences collapse
    onto one, and the content-word term agrees with the phrasing term
    instead of overruling it."""
    one = ("{} was searched across the six mandatory public tiers for this "
           "entity and no entity-specific artefact naming the capability was "
           "returned, so the score is carried by the category position "
           "rather than by direct observation.")
    payload = {"cell_evidence": {**ENV, "cells": [
        {"subcap_id": f"P1C3.6.{i}", "synthesis": one.format(cap)}
        for i, cap in enumerate(("Academic Partnership", "Acceptance Testing",
                                 "Emissions Baseline", "Roadmap Sequencing"))]}}
    out = _cg15("heatmap", payload)
    assert len(out) == 4
    assert all("share 8-word spans" in r["message"] for r in out)


def test_the_two_terms_are_measured_and_separate_on_the_fixtures():
    """The calibration, with its arithmetic, so a future edit to either
    line has to argue with a number rather than a feeling.

    The two terms are near-independent. Honest prose about one institution
    shares VOCABULARY freely — Baxter's own absences run 0.29-0.47 on the
    content-word measure — and is separated by PHRASING, which is where
    they collapse to 0.11 or less. The promoted template is high on both.
    Requiring both is therefore a real narrowing and not a second name for
    the first test."""
    def two(a, b):
        return (_overlap(shingles(a), shingles(b)),
                _overlap(claim_words(a), claim_words(b)))

    honest = [two(a, b) for i, a in enumerate(BAXTER_ABSENCES)
              for b in BAXTER_ABSENCES[i + 1:]]
    assert max(r for r, _c in honest) < TEMPLATE_OVERLAP
    # …and some of those honest pairs DO clear the claim line, which is
    # exactly why the claim term cannot be the only one either
    assert max(c for _r, c in honest) > 0.25

    raw, claim = two(CEILING_TEMPLATE[0], CEILING_TEMPLATE[2])
    assert raw >= TEMPLATE_OVERLAP and claim >= CLAIM_OVERLAP


def test_a_claim_vocabulary_too_small_to_measure_does_not_buy_a_pass():
    """Below CLAIM_MIN_WORDS distinct content words the second term
    abstains and the phrasing term decides alone. Sparing them instead
    would hand a producer a template made of nothing but the register —
    the residual check's own failure mode, re-entering through this door."""
    thin = ("The cited evidence for this cell sits below the peer median "
            "recorded in the workbook for the category above it.")
    assert len(claim_words(thin)) < CLAIM_MIN_WORDS
    payload = {"cell_evidence": {**ENV, "cells": [
        {"subcap_id": f"P4C1.1.{i}", "synthesis": thin} for i in range(3)]}}
    out = _cg15("heatmap", payload)
    # the residual check owns it too — but the template check must not have
    # abstained, or the door is open
    assert len([r for r in out if "share 8-word spans" in r["message"]]) == 3


def test_the_registers_stripped_are_the_scaffolding_the_contract_mandates():
    """The claim term is only defensible if what it removes is what H2
    REQUIRES a synthesis to contain. Assert that directly against the
    contract's own words rather than trusting the register lists."""
    doc = sections("heatmap")["cell_evidence"]["fields"]["cells"]["doc"]
    assert "where the score sits against the peer median" in doc
    mandated = "the score sits against the peer median and the cited evidence"
    assert claim_words(mandated) == set(), claim_words(mandated)


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
    # The corpus rungs are legitimately SHARED (one package, one profile);
    # what must differ per item is the query that asked about IT. A ladder
    # identical across items in full — shared rungs AND one pasted query —
    # is the group rule's business, tested separately below.
    return {"alerts": {**ENV, "alerts": [
        {"subcap_id": c, "state": s, "justification": j,
         **({**ALERT_LADDER,
             "queries_run": [f"INT-{20 + i}: What does the corpus hold on "
                             f"{c}? Nothing was located."]}
            if with_ladder else {})}
        for i, (c, s, j) in enumerate(ALERT_TEMPLATE)]}}


def test_one_ladder_pasted_across_three_items_is_refused_as_a_group():
    """The negative control for the group rule, and the shape both promoted
    runs actually carried: 98 alerts on one run and 11 on the other shared
    ONE byte-identical ladder. One search establishes one absence, not N
    distinct ones — each item's ladder must record the rung that asked
    about THAT item. Before pass 3 this payload produced zero reasons."""
    payload = {"alerts": {**ENV, "alerts": [
        {"subcap_id": c, "state": s, "justification": j, **ALERT_LADDER}
        for c, s, j in ALERT_TEMPLATE]}}
    out = _cg15("heatmap", payload)
    grouped = [r for r in out if "byte-identical ladder" in r["message"]]
    assert len(grouped) == len(ALERT_TEMPLATE), \
        "the pasted ladder must be refused on every member"
    assert all("the rung that asked about THIS item" in r["message"]
               for r in grouped)


def test_a_pointer_rung_is_refused_by_name():
    """The promoted 517: rung 1 was 'Run ladder in section r_layer' on
    every cell — an instruction to a reader, not a search. Before pass 3
    it bought the exemption from this gate AND from AG-03."""
    cell = {"subcap_id": "P2C2.1.1", "e_ids": [], "thin": True,
            "sources_searched": ["Run ladder in section r_layer",
                                 "Corpus search: consent capture - nil"],
            "closure_condition": "A dated document naming consent capture."}
    payload = {"cell_evidence": {**ENV, "linking_stats": {
        "cells_scored": 1, "cells_linked": 0, "rows_unlinkable": 1},
        "cells": [cell]}}
    out = _cg15("heatmap", payload)
    assert any("pointer to another section" in r["message"] for r in out)


def test_a_hostless_unquoted_ladder_cannot_buy_the_exemption():
    """MEM-0038's substantive requirement: a rung must name a host, a URL,
    a quoted query or a re-runnable query string. 'Corpus search: <the
    cell's own topic> - nil' names nothing a reader could re-run, and 515
    'distinct' ladders of that form exempted 517 uncited cells."""
    from dma_mcp.vacuity import ladder_flaw, records_absence
    from dma_mcp.vacuity import item_keys
    declared = item_keys("heatmap", "cell_evidence", "cells")
    cell = {"subcap_id": "P2C2.1.1", "e_ids": [], "thin": True,
            "sources_searched": ["Assessment package reviewed",
                                 "Corpus search: consent capture - nil"],
            "closure_condition": "A dated document naming consent capture."}
    assert ladder_flaw(cell, declared) is not None
    assert records_absence(cell, declared) is False
    # …and the honest version of the same ladder still buys it.
    cell["sources_searched"] = ["Assessment package reviewed",
                                'corpus search: "consent capture" - nil']
    assert ladder_flaw(cell, declared) is None
    assert records_absence(cell, declared) is True


def test_thin_asserted_beside_three_citations_is_not_an_absence():
    """MEM-0038's agreement clause: thin must agree with the evidence
    beside it. At or above the contract's own three-item line the cell is
    not thin, and the absence route is not available to it."""
    from dma_mcp.vacuity import ladder_flaw, item_keys
    declared = item_keys("heatmap", "cell_evidence", "cells")
    cell = {"subcap_id": "P2C2.1.1", "e_ids": ["E-1", "E-2", "E-3"],
            "thin": True,
            "sources_searched": ["sec.gov EDGAR full-text"],
            "closure_condition": "A dated artefact naming this capability."}
    flaw = ladder_flaw(cell, declared)
    assert flaw is not None and "3 citations" in flaw


def test_the_claim_term_refuses_a_round_robin_the_phrasing_term_misses():
    """The hostile payload's shape: opening frames and connectives rotated
    so no pair shares an 8-gram at 0.40, while the content words — what
    the sentences SAY — agree at 0.60+. Before pass 3 this produced zero
    reasons; the conjunction closed the instance, not the class."""
    frames = ["The register shows no deployment evidence for",
              "Across the corpus, nothing addresses",
              "Assessment materials do not surface",
              "The evidence base is silent on",
              "No artefact in the package speaks to",
              "Available documentation omits"]
    connect = ["which constrains", "and this limits", "leaving open",
               "which defers", "and this narrows", "postponing"]
    cells = []
    for i in range(6):
        # six DISTINCT frames and connectives: no two syntheses share an
        # 8-gram, so the phrasing term generates no candidate pair at all —
        # exactly the hostile payload's trick, at test scale
        cells.append({
            "subcap_id": f"P1C1.1.{i + 1}", "e_ids": ["E-BCU-001"],
            "synthesis": (f"{frames[i]} member onboarding workflow "
                          f"automation at this institution, {connect[i]} "
                          "the roadmap for consent capture telemetry in the "
                          "current planning horizon.")})
    payload = {"cell_evidence": {**ENV, "linking_stats": {
        "cells_scored": 6, "cells_linked": 6, "rows_unlinkable": 0},
        "cells": cells}}
    out = _cg15("heatmap", payload)
    claim = [r for r in out if "make the same claim" in r["message"]]
    assert len(claim) == 6, "the claim term must refuse all six alone"
    assert all("share almost no phrasing" in r["message"] for r in claim), \
        "the verdict must say the wording was varied and the argument was not"


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
                        "sources_searched": ["ncua.gov merger notices",
                                             "state regulator filings",
                                             "press releases 2021-2026"],
                        "closure_condition": "A published merger notice."}}}
    assert _cg15("context", payload) == []


def test_an_empty_state_does_not_exempt_the_prose_a_populated_section_carries():
    """`empty_state` answers the section question and nothing more. The
    promoted run's overview.sentiment carries bars, themes AND an
    empty_state naming the review text it could not cite — a producer who
    could switch the gate off for a whole section with one declared
    absence would have a switch, not a gate."""
    payload = _ceilings(CEILING_TEMPLATE)
    payload["ceilings"]["empty_state"] = {
        "reason": "Two categories could not be given a ceiling.",
        "sources_searched": ["package evidence index", "search: \"peer deposit mix\" - nil"]}
    out = _cg15("overview", payload)
    assert len(out) == len(CEILING_TEMPLATE)
    assert all("share 8-word spans" in r["message"] for r in out)


def test_an_absence_rung_without_a_ladder_does_not_buy_the_exemption():
    """A state that claims the ladder ran and records no search is not an
    absence; it is an assertion with nothing behind it — the same posture
    AG-03 takes."""
    payload = {"acquisitions": {**ENV, "rows": [], "empty_state":
                                {"reason": "None found."}}}
    out = _cg15("context", payload)
    assert len(out) == 1 and out[0]["path"] == "acquisitions"


SHORT_ABSENCE = ("The ladder ran across every mandatory source and "
                 "established no evidence for this capability.")


@pytest.mark.parametrize("marker", [
    {"state": "WORKED_ABSENT", "sources_searched": ["sec.gov filings", "query: \"vendor contract\""]},
    # A string under queries_run is a query by the field's own semantics —
    # re-runnable as written. A bare "INT-020" is a label, names nothing a
    # reader could run, and no longer buys the exemption (see below).
    {"state": "UNWORKED",
     "queries_run": ["INT-020: Does BCU hold proprietary technology patents?"]},
])
def test_each_rung_the_item_shape_declares_exempts_a_short_honest_statement(marker):
    """A 40-80 word floor on a justification is right for an argument. It
    is not right for "the ladder ran and found nothing", which is the whole
    of what there is to say.

    On `heatmap.alerts.alerts`, which is the ONE item shape of the
    nineteen that declares `state` + a ladder key. That is not an accident
    of this test's choice of fixture — it is the measured fact that made
    pass 1's escape hatch a trap."""
    payload = {"alerts": {**ENV, "alerts": [
        {"subcap_id": "P4C1.1.1", "justification": SHORT_ABSENCE, **marker}]}}
    assert _cg15("heatmap", payload) == [], marker


def test_the_absence_rungs_are_declared_on_exactly_one_item_shape():
    """The measurement that named the defect, kept as a test so the next
    person does not have to re-run it.

    Of the nineteen item shapes carrying a per-item prose budget, exactly
    one declares the `state` + `sources_searched` protocol pass 1's verdict
    told every producer to use. On the other eighteen the gate named a door
    that is not in the wall — and a producer who would not invent a field,
    because the standing clause forbids it, had nowhere to go."""
    with_ladder = []
    for page in PAGES:
        floors = prose_floors(page)
        for name in sections(page):
            for fname in (floors.get(name) or {"items": {}})["items"]:
                keys = item_keys(page, name, fname)
                if ({"state", "status"} & keys) and (
                        {"sources_searched", "queries_run"} & keys):
                    with_ladder.append(f"{page}.{name}.{fname}")
    assert with_ladder == ["heatmap.alerts.alerts"]


def test_an_absence_key_the_item_shape_does_not_declare_buys_nothing():
    """The Frost hole, measured today: 394 of 697 cell syntheses bought
    this exemption with `state` + `sources_searched` on
    `heatmap.cell_evidence.cells`, which declares neither.

    CG-04 sweeps SECTION keys only, so an undeclared item key validates.
    The writer has no `item:` binding for it, so promote drops it. An
    exemption bought with such a key trades a real refusal for a field the
    client never sees — and, on the same payload, it bought the same
    exemption from AG-03. The exemption is a contract route or it is
    nothing."""
    assert "state" not in item_keys("heatmap", "cell_evidence", "cells")
    # Frost's own sentence, near-verbatim, long enough to clear the 40-word
    # field's floor so the TEMPLATE verdict is the only one under test.
    frost = ("{} was searched across the six mandatory public tiers for this "
             "entity and no entity-specific artefact naming the capability "
             "was returned, so the score is carried by the category position "
             "rather than by direct observation. The absence is recorded, "
             "not inferred.")
    payload = {"cell_evidence": {**ENV, "cells": [
        {"subcap_id": f"P4C1.1.{i}", "synthesis": frost.format(cap),
         "state": "WORKED_ABSENT",
         "sources_searched": ["sec.gov filings", "query: \"board oversight\""]}
        for i, cap in enumerate(("Strategy Refresh Cadence",
                                 "Vision Communication", "Board Engagement"))]}}
    out = _cg15("heatmap", payload)
    assert len(out) == 3
    assert all("share 8-word spans" in r["message"] for r in out)
    # and the verdict points at the route this shape HAS, not the one it
    # was just refused for inventing. Since 0041 that route is the TRD's own
    # cell-grain protocol, which now has columns: thin + sources_searched +
    # closure_condition. `state` remains undeclared and still buys nothing.
    assert "thin + sources_searched + closure_condition" in out[0]["message"]


def test_the_declared_cell_absence_protocol_buys_the_exemption_and_thin_alone_does_not():
    """0041: the TRD states the cell-grain protocol at `Representing absence`
    and it now has storage, so it is a route rather than an invention. All
    three keys, because `thin` on its own marks a cell short of evidence that
    still owes its argument — a switch, not a finding."""
    declared = item_keys("heatmap", "cell_evidence", "cells")
    assert {"thin", "sources_searched", "closure_condition"} <= declared
    full = {"thin": True, "sources_searched": ["sec.gov EDGAR full-text", 'query: "consent capture"'],
            "closure_condition": "A named owner or a dated artefact for this cell."}
    assert records_absence(full, declared)
    assert not records_absence({"thin": True}, declared)
    assert not records_absence({k: v for k, v in full.items()
                                if k != "closure_condition"}, declared)
    assert not records_absence({k: v for k, v in full.items()
                                if k != "sources_searched"}, declared)
    # and the trio buys nothing on a shape that does not declare it
    assert not records_absence(full, item_keys("heatmap", "alerts", "alerts"))


def test_the_same_keys_on_the_shape_that_declares_them_still_work():
    """The other direction, so the narrowing cannot be read as a ban: the
    identical marker on `heatmap.alerts.alerts` is honoured."""
    assert records_absence({"state": "WORKED_ABSENT",
                            "sources_searched": ["ciro.ca registry"]},
                           item_keys("heatmap", "alerts", "alerts"))
    assert not records_absence({"state": "WORKED_ABSENT",
                                "sources_searched": ["ncua.gov registry"]},
                               item_keys("heatmap", "cell_evidence", "cells"))


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
    payload = {"alerts": {**ENV, "alerts": [
        {"subcap_id": "P4C1.1.1", "justification": "Evidence is limited.",
         **marker}]}}
    out = _cg15("heatmap", payload)
    assert len(out) == 1, marker
    assert out[0]["path"] == "alerts.alerts[0].justification"


def test_a_bare_placeholder_is_refused_even_inside_a_recorded_absence():
    """The one thing no absence excuses. The protocol is a reason and a
    ladder; 'N/A' is neither, and it renders as itself on a client page."""
    payload = {"alerts": {**ENV, "alerts": [
        {"subcap_id": "P4C1.1.1", "justification": "N/A",
         "state": "WORKED_ABSENT",
         "sources_searched": ["sec.gov filings", "query: \"data lineage\""]}]}}
    out = _cg15("heatmap", payload)
    assert len(out) == 1
    assert out[0]["path"] == "alerts.alerts[0].justification"
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
