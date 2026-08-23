"""CG-46 — the issue register holds the institution's own matters.

Owner, 2026-08-23: "Issue register for Gulf are not issues. Issues entail
enforcement actions; breaches; news that may affect the entity's scores etc."

What the register actually held was two findings about THE ASSESSMENT: 26 of
61 evidence items uncited, and source concentration across 58 of 70 cells.
Both true, both useful, both filed in the one place a client reads as "what
is wrong at this company". Each row stated "Cap: none" in its own text — so
the producer had already noticed the mismatch and filed it there anyway,
which is why this needs a gate and not a note.

The contract agrees with the owner: C2 scopes the register to "the client's
OWN open matters", and "an issue is only interesting here because it CAPS
something".

THE EMPTY REGISTER IS THE OTHER HALF AND MATTERS MORE OFTEN. Most
institutions have no open enforcement matter, so most registers are empty and
empty is correct. But an empty register naming no search is indistinguishable
from one nobody ran — the defect class this build keeps paying for. Gulf's
repaired register names five databases, the one civil matter it found against
the PARENT, and why that matter reaches no scored capability.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import dma_mcp.validation2 as V2         # noqa: E402


def run(body, page="context"):
    return V2._check_issue_register_is_the_entitys(
        page, {"issue_register": body})


def ids(out):
    return [r["gate_id"] for r in out]


# The two rows Gulf actually served, in the fields the gate reads.
ISS_001 = {"title": "Evidence register completeness",
           "summary": "26 of 61 evidence items in the register carry no "
                      "subcapability link at all, so they are uncited by "
                      "this run's scoring workbook. Cap: none."}
ISS_002 = {"title": "Source concentration",
           "summary": "Six evidence items each support more than 15% of "
                      "scored cells, a single-source concentration inherent "
                      "to a lean single-entity assessment. Cap: none."}

# What an issue IS.
REAL_ISSUE = {"title": "FDIC consent order",
              "summary": "The institution entered into a consent order with "
                         "the Federal Deposit Insurance Corporation on "
                         "2025-11-04 over Bank Secrecy Act deficiencies, "
                         "which caps the compliance-automation cells."}

# Gulf's repaired empty state, abbreviated to the fields the gate reads.
GULF_EMPTY = {
    "issues": [],
    "verified_absent": True,
    "empty_state": {
        "reason": "No open matter of this division's own was located. One "
                  "live civil matter names the PARENT bank and not this "
                  "division, and the claims reach no capability this run "
                  "scores.",
        "searched_on": "2026-08-23",
        "sources_searched": [
            "Federal Deposit Insurance Corporation enforcement decisions",
            "Office of the Comptroller of the Currency action database",
            "Federal court records for the parent company",
            "Trade press for the receivables-finance sector",
            "The division's own news page"],
        "closure_condition": "A regulatory action, conduct matter or "
                             "disclosed incident naming the division itself."},
}


# ── the reported defect ───────────────────────────────────────────────

def test_the_uncited_evidence_row_is_refused():
    """The owner's sentence, on the row that provoked it."""
    out = run({"issues": [ISS_001]})
    assert ids(out) == ["CG-46"], out
    m = out[0]["message"]
    assert "the assessment, not the institution" in m
    assert "what is wrong at my company" in m
    assert out[0]["severity"] == "block"
    assert out[0]["path"] == "context.issue_register.issues[0]"


def test_the_source_concentration_row_is_refused():
    out = run({"issues": [ISS_002]})
    assert ids(out) == ["CG-46"]


def test_both_rows_are_named_not_just_the_first():
    out = run({"issues": [ISS_001, ISS_002]})
    assert len(out) == 2


def test_the_verdict_names_where_the_finding_should_live_instead():
    """A gate that only refuses teaches nothing. These observations were
    real and they have a home."""
    out = run({"issues": [ISS_001]})
    assert "record_finding" in out[0]["message"]


# ── what an issue is ──────────────────────────────────────────────────

def test_a_real_enforcement_matter_passes():
    assert run({"issues": [REAL_ISSUE]}) == []


@pytest.mark.parametrize("summary", [
    "A ransomware incident disclosed on 2025-08-02 took the loan origination "
    "platform offline for nine days.",
    "A class action filed in the Northern District of California alleges "
    "improper overdraft sequencing.",
    "The regulator issued a matter requiring attention on model governance "
    "at the 2025 examination.",
    "A civil money penalty of $1.2m was assessed for flood insurance "
    "violations.",
])
def test_the_owners_own_examples_all_pass(summary):
    assert run({"issues": [{"title": "Matter", "summary": summary}]}) == []


def test_an_evidence_gap_that_is_also_a_regulatory_matter_passes():
    """The discriminator is the SUBJECT, not the vocabulary. A regulator
    citing the institution's own evidence discipline is the institution's
    matter, and must not be caught by a keyword."""
    assert run({"issues": [{
        "title": "Examination finding on evidence retention",
        "summary": "The regulator's 2025 examination cited the institution's "
                   "scoring workbook and evidence register controls in a "
                   "matter requiring attention, capping governance cells."}]}) == []


# ── the empty register, which is usually correct ──────────────────────

def test_gulfs_repaired_empty_register_passes():
    assert run(GULF_EMPTY) == []


def test_a_bare_empty_register_is_refused():
    """'No issues' with no search behind it is indistinguishable from
    'nobody looked' — and a client reads the first."""
    out = run({"issues": []})
    assert ids(out) == ["CG-46"]
    assert "indistinguishable from one nobody ran" in out[0]["message"]
    assert out[0]["path"] == "context.issue_register.empty_state"


def test_verified_absent_alone_is_not_a_search():
    """A bare boolean is an assertion. Same rule CG-40 keeps for `thin`."""
    out = run({"issues": [], "verified_absent": True})
    assert ids(out) == ["CG-46"]


def test_a_two_word_empty_state_is_not_a_search():
    out = run({"issues": [], "empty_state": "none"})
    assert ids(out) == ["CG-46"]


def test_the_empty_rule_does_not_fire_when_rows_exist():
    """A register with a real row has answered by serving it; demanding a
    search disclosure as well would be a second gate wearing this one's id."""
    assert run({"issues": [REAL_ISSUE]}) == []


# ── scope and safety ──────────────────────────────────────────────────

def test_no_other_page_is_touched():
    for page in ("overview", "heatmap", "platform", "techstack", "insights"):
        assert run({"issues": [ISS_001]}, page=page) == []


def test_a_run_with_no_register_section_is_not_a_finding():
    assert V2._check_issue_register_is_the_entitys("context", {}) == []
    assert V2._check_issue_register_is_the_entitys(
        "context", {"issue_register": None}) == []


@pytest.mark.parametrize("bad", [None, [], "x", 42,
                                 {"issue_register": "not-a-dict"},
                                 {"issue_register": {"issues": "no"}},
                                 {"issue_register": {"issues": ["x", None]}}])
def test_malformed_shapes_do_not_crash_the_gate(bad):
    V2._check_issue_register_is_the_entitys("context", bad)


def test_the_finding_list_is_bounded():
    out = run({"issues": [dict(ISS_001, title=f"row {i}") for i in range(40)]})
    assert len(out) <= 6


def test_an_issue_with_no_readable_text_is_not_guessed_at():
    """No text is not evidence of the wrong subject. Inventing a verdict
    from an absence is the failure mode this whole gate family exists to
    stop."""
    assert run({"issues": [{"iss_id": "ISS-9", "opened_on": "2026-01-01"}]}) == []


def test_the_gate_is_registered_with_its_family_and_severity():
    from dma_mcp.gates import GATES
    assert "CG-46" in GATES
    assert GATES["CG-46"][-1] == "block"
    why = GATES["CG-46"][3].lower()
    assert "enforcement" in why
    assert "own open matters" in why
    assert "empty is" in why, (
        "the registry says empty is usually correct, so nobody later "
        "mistakes this for a floor on the number of issues")


def test_it_runs_inside_pass_two():
    import inspect
    src = inspect.getsource(V2.validate_pass2)
    assert "_check_issue_register_is_the_entitys" in src, \
        "CG-46 is defined but never dispatched"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))


# ── the false refusals CG-46 shipped with, measured on the live corpus ────
#
# Run over all five clients the directory serves, CG-46 refused three of
# T. Rowe Price's eleven rows. All three were the institution's own matters.
# The gate had committed the reject-rather-than-triage failure it was written
# to describe, which is the failure mode this whole build keeps paying for —
# so these three rows are pinned verbatim.
#
# The cause in every case: the phrase "the workbook" sat in `rationale`,
# describing how the row was SCORED, not what the row is ABOUT. A row may
# explain its own provenance in assessment vocabulary without being about the
# assessment. The subject test now reads the naming fields only; the
# entity-matter test still reads everything, because a real matter is often
# named in full only in the reasoning.

TROWE_ARBITRATION = {
    "title": "Three FINRA customer-dispute arbitration awards against "
             "T. Rowe Price Investment Services",
    "rationale": "FINRA BrokerCheck records three customer arbitration "
                 "awards against T. Rowe Price Investment Services across "
                 "the firm's entire operating history. No binding cap: the "
                 "caps log ties no served cell's ceiling to this matter. The "
                 "registered rows and the workbook's Issue Time Map disagree "
                 "on the award years - 2015 and 2021 against a 1998-to-2019 "
                 "span - so this row keeps the workbook's dates.",
}

TROWE_BOARD_DISCLOSURE = {
    "title": "Board cyber-oversight routing disclosure inconsistency "
             "between FY2024 10-K and 2026 proxy",
    "rationale": "The FY2024 Form 10-K's Item 1C states the Board does not "
                 "delegate this responsibility to a committee; the 2026 "
                 "proxy states the Audit Committee receives regular updates. "
                 "Both board-oversight cells were scored under the "
                 "workbook's Step 6 conservative-default rule (confidence "
                 "reduced to LOW) rather than by picking a side. This row is "
                 "a conflict between two dated filings.",
}

TROWE_DATA_ORG = {
    "title": "Data-organization structure unresolved between enterprise "
             "chief data officer, chief financial officer team and GCAS "
             "governance",
    "rationale": "Three organizationally distinct data-management loci are "
                 "named in parallel public sources. Unresolved and not "
                 "previously carried on this register: the workbook applied "
                 "its Step 6 conservative-default rule rather than picking a "
                 "reading, reducing confidence to LOW on the one cell this "
                 "bears on.",
}


@pytest.mark.parametrize("row,label", [
    (TROWE_ARBITRATION, "three FINRA customer arbitration awards"),
    (TROWE_BOARD_DISCLOSURE, "a 10-K/proxy disclosure conflict"),
    (TROWE_DATA_ORG, "an unresolved data-organization structure"),
])
def test_a_real_matter_that_explains_its_own_scoring_passes(row, label):
    assert run({"issues": [row]}) == [], (
        f"{label} is the institution's own matter and was refused because "
        f"its rationale says how it was scored")


def test_the_subject_test_does_not_read_the_reasoning_fields():
    """The precise mechanism, so a later edit that re-merges the two field
    sets fails here rather than on a client's register."""
    row = {"title": "FDIC consent order over Bank Secrecy Act deficiencies",
           "rationale": "Scored against the workbook's evidence register."}
    assert run({"issues": [row]}) == []
    assert "rationale" not in V2._ISSUE_SUBJECT_KEYS
    assert "rationale" in V2._ISSUE_REASONING_KEYS


def test_an_assessment_row_is_still_refused_when_the_subject_names_it():
    """The repair must not have disarmed the gate. Gulf's original rows put
    the subject in the TITLE, which is exactly where it is still read."""
    assert ids(run({"issues": [ISS_001]})) == ["CG-46"]
    assert ids(run({"issues": [ISS_002]})) == ["CG-46"]


def test_reasoning_alone_can_no_longer_trip_the_subject_test():
    bare = {"title": "Something happened at the firm",
            "rationale": "source concentration across the evidence register"}
    assert run({"issues": [bare]}) == []


@pytest.mark.parametrize("word", [
    "arbitration", "award", "censure", "FINRA", "BrokerCheck", "fiduciary",
    "restitution", "disgorgement", "suspension", "revocation",
])
def test_the_matter_vocabulary_covers_what_the_corpus_actually_carries(word):
    """The first list was written from banking enforcement and missed the
    securities-supervision half entirely."""
    assert V2._ENTITY_MATTER.search(f"a {word} against the firm"), word
