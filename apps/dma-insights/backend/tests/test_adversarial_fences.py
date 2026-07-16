"""Tranche B — the adversarial fences, now ACTIVATED (2026-07-09).

The challenge/contradiction engine (app.services.nlp.knowledge) shipped inert:
`Evidence.owned` was hardcoded True at the one construction site, so the
peer/benchmark ownership fence never fired; `resolve_contradictions` was never
called from the derive path; and `_same_subject` used only the bi-encoder cosine.
These tests pin the activated behaviour — the peer-NPS fence, CE-precise
same-subject detection, and contradiction suppression — and are pure-logic so
they hold whether or not the cross-encoder is baked (it degrades to the
bi-encoder cosine either way).
"""
from __future__ import annotations

from app.services.nlp.knowledge import (
    Claim,
    EntityKnowledge,
    Evidence,
    classify_owned,
    resolve_contradictions,
)


# ── ownership fence (classify_owned) ───────────────────────────────────────
def test_classify_owned_flags_peer_subject_figure() -> None:
    assert classify_owned("The peer median NPS is 45 across the cohort.") is False
    assert classify_owned("Industry average onboarding time is 3 days.") is False
    assert classify_owned(
        "Peers typically report a 15% digital adoption rate.") is False


def test_classify_owned_keeps_client_first_party_and_comparison() -> None:
    # plain client fact
    assert classify_owned(
        "The bank runs IBM AIX on-premises as its core system.") is True
    # a client-vs-peer comparison is ABOUT the client → owned
    assert classify_owned(
        "Acuity scores 62 vs a peer median of 45.", entity_name="Acuity Bank"
    ) is True
    # first-party possessive cue
    assert classify_owned(
        "Benchmark median is 45, but our own NPS sits at 60.") is True


def test_classify_owned_defaults_true_on_empty_or_neutral() -> None:
    assert classify_owned("") is True
    assert classify_owned("   ") is True
    assert classify_owned("Digital onboarding was launched in Q3 2025.") is True


# ── challenge() honours the ownership fence ─────────────────────────────────
def test_challenge_drops_peer_owned_citation() -> None:
    ek = EntityKnowledge([
        Evidence(e_id="E-1", text="Net promoter score program and survey cadence",
                 owned=True),
        Evidence(e_id="E-2", text="Net promoter score program and survey cadence",
                 owned=False),   # peer-owned twin — must be fenced out
    ])
    claim = Claim(text="NPS program maturity", capability="Net promoter score",
                  e_ids=["E-1", "E-2"])
    ek.challenge(claim, min_support=0.05)
    assert "E-2" not in claim.e_ids          # peer-owned citation fenced
    assert claim.verdict in {"grounded", "ungrounded"}


def test_challenge_ungrounded_when_only_peer_owned() -> None:
    ek = EntityKnowledge([
        Evidence(e_id="E-9", text="Compliance program and controls framework",
                 owned=False),
    ])
    claim = Claim(text="Compliance maturity", capability="Compliance program",
                  e_ids=["E-9"])
    ek.challenge(claim, min_support=0.05)
    assert claim.e_ids == []
    assert claim.verdict == "ungrounded"


# ── contradiction resolution (now called from compose_findings) ─────────────
def test_resolve_contradictions_suppresses_weaker_presence_absence() -> None:
    evidence = [
        Evidence(e_id="E-A", text="CISO hired", tier=2, year=2025, owned=True),
        Evidence(e_id="E-B", text="no CISO", tier=6, year=2022, owned=True),
    ]
    claims = [
        Claim(text="The bank has a CISO in place leading security governance.",
              capability="Cybersecurity Governance", e_ids=["E-A"]),
        Claim(text="The bank has no CISO; the security leadership seat is vacant.",
              capability="Cybersecurity Governance", e_ids=["E-B"]),
    ]
    survivors, notes = resolve_contradictions(claims, evidence, sim_threshold=0.35)
    assert len(survivors) == 1
    # the better-tier / more-recent / client-owned claim wins
    assert "in place" in survivors[0].text
    assert notes and "contradiction" in notes[0].lower()


def test_resolve_contradictions_keeps_unrelated_claims() -> None:
    evidence = [
        Evidence(e_id="E-1", text="core banking platform", owned=True),
        Evidence(e_id="E-2", text="branch network footprint", owned=True),
    ]
    claims = [
        Claim(text="The bank runs a modern core banking platform.",
              capability="Core Banking", e_ids=["E-1"]),
        Claim(text="The bank operates a wide physical branch network.",
              capability="Branch Network", e_ids=["E-2"]),
    ]
    survivors, notes = resolve_contradictions(claims, evidence)
    assert len(survivors) == 2         # different subjects → nothing suppressed
    assert notes == []


def test_resolve_contradictions_empty_and_singleton_are_noops() -> None:
    assert resolve_contradictions([], []) == ([], [])
    one = [Claim(text="single claim", capability="X", e_ids=[])]
    survivors, notes = resolve_contradictions(one, [])
    assert len(survivors) == 1 and notes == []
