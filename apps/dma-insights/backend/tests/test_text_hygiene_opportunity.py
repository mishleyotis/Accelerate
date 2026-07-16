"""Opportunity-language corpus (docs/LANGUAGE_GUIDELINES.md) — the deterministic
floor `text_hygiene.opportunity_reframe` must turn accusatory / deficit phrasing
into forward-looking opportunity copy WITHOUT touching clean-posture positives,
neutral strategy postures, numbers, names, or evidence citations.

Cases are drawn from the real 94-client pack scan (77 clients / 426 hits) so the
floor is pinned to the actual copy it must fix.
"""
from __future__ import annotations

import re

from app.services.text_hygiene import opportunity_reframe as reframe

# accusatory-absence detector — the inverse gate (mirrors countercheck_pack).
_ACCUSATORY = re.compile(
    r"(?:^|[\s|\u2014\u2013-])(?:no|zero|lacks?|lacking|absent|missing|fails?\s+to|"
    r"failing\s+to|cannot|unable\s+to|without)\b", re.I)
# clean-posture / neutral phrases that legitimately keep an absence word.
_ALLOWED = re.compile(
    r"(?:breach|incident|enforcement|consent|litigation|lawsuit|violation|"
    r"penalt|sanction|default|complaint|regulatory\s+record|fraud|outage|"
    r"data\s+loss|m&a|acquisition|interest|appetite|plans?|intention|"
    r"net-zero|zero-trust|zero-copy|zero-day)", re.I)


def _is_accusatory(text: str) -> bool:
    return bool(_ACCUSATORY.search(text or "")) and not _ALLOWED.search(text or "")


# ── capability/tooling absences → opportunity (must be reframed) ──────────

def test_no_capability_lead_becomes_opportunity() -> None:
    assert reframe("No Marketing Automation: 183K Members").startswith("Opportunity:")
    assert not _is_accusatory(reframe("No Enterprise Integration Platform — 200+ Tools"))


def test_no_x_deployed_becomes_greenfield() -> None:
    out = reframe("GREENFIELD CRM — No Salesforce Deployed")
    assert "greenfield" in out.lower()
    assert "no salesforce" not in out.lower()
    # not double-framed
    assert out.lower().count("greenfield") == 1


def test_zero_capability_becomes_greenfield() -> None:
    out = reframe("Zero CRM across 183,768 members & 19 branches.")
    assert "greenfield" in out.lower()
    assert "183,768" in out  # number preserved verbatim
    assert not out.lower().startswith("zero")


def test_no_x_detected_list_reframed_and_number_kept() -> None:
    out = reframe("No MuleSoft, Apigee, or ESB detected despite 200+ technologies.")
    assert "not yet in place" in out.lower()
    assert "MuleSoft" in out and "200+" in out
    assert not _is_accusatory(out)


def test_without_clause_reframed() -> None:
    out = reframe("5 AI models run in production without a governance framework")
    assert "opportunity" in out.lower()
    assert "5 AI models" in out


def test_lacks_and_deficit_verbs() -> None:
    assert "headroom" in reframe("The bank lacks a unified data layer.").lower()
    assert "not yet" in reframe("Cannot originate loans digitally.").lower()


def test_no_public_evidence_is_disclosure_not_accusation() -> None:
    out = reframe("No public evidence surfaced for innovation roi tracking.")
    assert "limited public disclosure" in out.lower()


def test_audit_prefix_dropped() -> None:
    assert reframe(
        "Critical finding: All five CEO strategic objectives are financial",
    ).startswith("All five")


# ── clean-posture / neutral — must be PRESERVED verbatim ──────────────────

def test_clean_posture_risk_absence_preserved() -> None:
    for s in (
        "Clean regulatory record: no enforcement actions, no consent orders.",
        "No data breaches on record; strong security posture.",
    ):
        assert reframe(s) == s


def test_neutral_strategy_absence_preserved() -> None:
    s = "CEO: no M&A interest; all capital in technology."
    assert reframe(s) == s


def test_net_zero_term_not_mangled() -> None:
    out = reframe("ESG reporting without net-zero commitment")
    assert "net-zero" in out  # the hyphenated term survives intact


def test_mixed_sentence_reframes_gap_keeps_positive() -> None:
    out = reframe("No integration layer detected; no data breaches on record.")
    assert "not yet in place" in out.lower()
    assert "no data breaches on record" in out.lower()  # positive preserved


# ── safety: idempotent + citation/number safe + no-op on clean copy ───────

def test_idempotent() -> None:
    for s in (
        "No Marketing Automation: 183K Members",
        "Zero CRM across 183,768 members.",
        "The bank lacks a unified data layer.",
        "Clean regulatory record: no enforcement actions.",
    ):
        once = reframe(s)
        assert reframe(once) == once


def test_citation_preserved() -> None:
    out = reframe("No unified data layer [E-042, E-051].")
    assert "[E-042, E-051]" in out


def test_clean_copy_unchanged() -> None:
    s = "Cross-Channel Application Continuity is an emerging opportunity."
    assert reframe(s) == s
