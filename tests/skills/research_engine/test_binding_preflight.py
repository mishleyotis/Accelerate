"""The binding is a FILE with a person's answer in it, not a sentence.

Requirement 2 of the 2026-08-29 review: "Ask user question was never used; I
did not see the financial statement review to check revenue lines and
possible LOBs."

Golden 1 bound CU / FULL / PUBLIC from three free-text strings the agent
wrote to itself. `vet_basis` refused FILLER and accepted fluent assertion,
which is the failure that actually costs a run. These pin the checks that a
confident sentence cannot pass: a financial statement with revenue lines, a
census that examines every material LOB, and a recorded AskUserQuestion
whose answer the binding must MATCH.
"""
import json
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2].parent / (
    "plugins/dma-insights/skills/dma-research")
sys.path.insert(0, str(ENGINE))

from engine import preflight as P  # noqa: E402


def _good() -> dict:
    d = P.skeleton(entity="Acme Credit Union", entity_id="acme-cu",
                   run_id="R-PF-1")
    d["financials"]["statements"] = [{
        "source_name": "NCUA Call Report — Acme CU, 2025 Q4",
        "url": "https://mapping.ncua.gov/ResearchCreditUnion",
        "kind": "call_report", "period": "FY2025", "tier": "T1",
        "retrieved_at": "2026-08-29T09:00:00Z"}]
    d["financials"]["revenue_lines"] = [
        {"line": "Interest income — consumer loans", "amount": 612000000,
         "currency": "USD", "period": "FY2025", "share_pct": 74.0,
         "implies_lob": "retail consumer lending", "source": "call report"},
        {"line": "Fee and other operating income", "amount": 103000000,
         "currency": "USD", "period": "FY2025", "share_pct": 26.0,
         "implies_lob": "retail deposit services", "source": "call report"}]
    d["lob_census"]["lines_of_business"] = [
        {"lob": "retail consumer lending", "revenue_share_pct": 74.0,
         "material": True,
         "basis": "largest call-report revenue line, 74.0% of FY2025 income"},
        {"lob": "retail deposit services", "revenue_share_pct": 26.0,
         "material": True,
         "basis": "fee and other operating income, 26.0% of FY2025 income"}]
    d["lob_census"]["candidates"] = [
        {"sub_vertical": "CU", "verdict": "ACCEPT",
         "reason": "state-chartered NCUA-insured credit union; both material "
                   "revenue lines are member retail business"},
        {"sub_vertical": "RB", "verdict": "REJECT",
         "reason": "no OCC or FDIC bank charter exists for this entity"}]
    d["binding_question"] = {
        "asked": True, "tool": "AskUserQuestion",
        "question": "Two material retail revenue lines and no commercial "
                    "book — bind to which sub-vertical?",
        "options": ["CU", "RB"], "answer": "CU — both retail lines in scope",
        "answer_sub_vertical": "CU", "answered_by": "engagement owner",
        "answered_at": "2026-08-29T09:12:00Z"}
    d["mode_question"] = {
        "asked": True, "tool": "AskUserQuestion",
        "question": "What evidence access does this engagement carry?",
        "options": ["PUBLIC", "HYBRID", "INTERNAL"],
        "answer": "PUBLIC — no internal documents provided",
        "answer_mode": "PUBLIC", "answered_by": "engagement owner",
        "answered_at": "2026-08-29T09:12:00Z"}
    d["binding"] = {"sub_vertical": "CU", "evidence_mode": "PUBLIC",
                    "scope_mode": "FULL"}
    return d


def test_the_skeleton_never_passes(tmp_path):
    """A skeleton pre-filled with plausible defaults is how a binding gets
    asserted; this one has to be worked."""
    rep = P.check(P.skeleton(entity="Acme CU", entity_id="acme-cu"))
    assert not rep["ok"]
    joined = " ".join(rep["problems"]).lower()
    assert "financials" in joined and "askuserquestion" in joined


def test_a_full_preflight_passes_and_derives_its_bases():
    doc = _good()
    rep = P.check(doc)
    assert rep["ok"], rep["problems"]
    b = P.bases(doc, rep)
    assert b["sub_vertical"] == "CU" and b["evidence_mode"] == "PUBLIC"
    # the basis is RENDERED from the file, so it carries the file's facts
    assert "engagement owner" in b["sv_basis"]
    assert "2 revenue line(s) read from 1 statement(s)" in b["sv_basis"]
    assert "rejected RB" in b["sv_basis"]
    assert "74.0%" in b["lob_census"]


def test_no_financial_review_is_refused():
    doc = _good()
    doc["financials"] = {"statements": [], "revenue_lines": [], "not_run": ""}
    problems = " ".join(P.check(doc)["problems"])
    assert "no statement was reviewed" in problems


def test_an_unreachable_statement_may_be_laddered_not_asserted():
    doc = _good()
    doc["financials"] = {"statements": [], "revenue_lines": [],
                         "not_run": "none published"}
    assert "not a ladder" in " ".join(P.check(doc)["problems"])
    doc["financials"]["not_run"] = (
        "NCUA call-report lookup, EDGAR full-text, the California DFPI "
        "licensee register and the entity's own investor page all searched "
        "2026-08-29; none carries a revenue statement for this entity.")
    assert P.check(doc)["ok"]


def test_a_revenue_line_naming_no_lob_is_refused():
    doc = _good()
    doc["financials"]["revenue_lines"][0]["implies_lob"] = ""
    assert "implies_lob is empty" in " ".join(P.check(doc)["problems"])


def test_shares_cannot_exceed_one_hundred_percent():
    doc = _good()
    doc["financials"]["revenue_lines"][0]["share_pct"] = 95.0
    assert "cannot exceed 100" in " ".join(P.check(doc)["problems"])


def test_an_unasked_binding_question_is_refused():
    doc = _good()
    doc["binding_question"]["asked"] = False
    problems = " ".join(P.check(doc)["problems"])
    assert "binding_question.asked is false" in problems
    assert "reasoning cannot satisfy" in problems


def test_the_binding_must_match_what_the_owner_answered():
    """The whole point: an agent can talk itself into a sub-vertical and it
    cannot talk itself into a recorded human answer."""
    doc = _good()
    doc["binding"]["sub_vertical"] = "RB"
    problems = " ".join(P.check(doc)["problems"])
    assert "the engagement owner answered CU" in problems


def test_the_binding_cannot_be_a_sub_vertical_the_census_rejects():
    doc = _good()
    doc["binding"]["sub_vertical"] = "RB"
    doc["binding_question"]["answer_sub_vertical"] = "RB"
    assert "itself REJECTs" in " ".join(P.check(doc)["problems"])


def test_two_material_lobs_with_no_question_is_the_multi_lob_trap():
    doc = _good()
    doc["binding_question"]["asked"] = False
    problems = " ".join(P.check(doc)["problems"])
    assert "MATERIAL lines of business" in problems
    assert "Scope is theirs to decide" in problems


def test_a_filler_candidate_reason_is_refused():
    doc = _good()
    doc["lob_census"]["candidates"][1]["reason"] = "n/a"
    assert "165 variant cells riding on it" in " ".join(
        P.check(doc)["problems"])


def test_require_refuses_with_every_problem_at_once(tmp_path):
    p = tmp_path / "pf.json"
    p.write_text(json.dumps(P.skeleton(entity="Acme CU", entity_id="acme-cu")))
    with pytest.raises(P.PreflightRefusal) as e:
        P.require(p)
    # one turn should be able to close them all
    assert "problem(s)" in str(e.value) and str(e.value).count("\n  - ") >= 5


def test_a_missing_preflight_names_the_command_that_builds_one(tmp_path):
    with pytest.raises(P.PreflightRefusal, match="engine.preflight init"):
        P.require(tmp_path / "absent.json")


def test_the_digest_ignores_advisory_prose_but_not_the_binding():
    doc = _good()
    before = P.digest(doc)
    doc["_how_to_fill"] = "rewritten guidance"
    assert P.digest(doc) == before
    doc["binding"]["evidence_mode"] = "HYBRID"
    assert P.digest(doc) != before


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
