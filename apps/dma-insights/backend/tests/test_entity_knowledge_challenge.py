"""A3 (2026-07-14 audit): the exec-summary / why-now / platform composers now
CHALLENGE a candidate fact through EntityKnowledge — the woven fact's CITED
evidence must actually support the capability (the same challenge the insight-
card path runs) — not just clear a lexical relevance check.

Deterministic on the keyword tier (DMA_DISABLE_SEMANTIC=1): challenge falls back
to the lexical bi-encoder cosine of capability↔cited-evidence, so a bio line
cited under a technical capability is dropped while the genuine finding survives.
"""
from __future__ import annotations

import pytest

from app.services.nlp.knowledge import build_entity_knowledge, fact_supported


@pytest.fixture(autouse=True)
def _keyword_tier(monkeypatch):
    monkeypatch.setenv("DMA_DISABLE_SEMANTIC", "1")   # lexical tier → deterministic


def test_build_returns_none_for_empty_corpus():
    assert build_entity_knowledge({}) is None
    assert build_entity_knowledge({"E-1": ""}) is None   # blank excerpts dropped


def test_fact_supported_is_none_safe():
    ek = build_entity_knowledge({"E-1": "commercial lending origination is manual"})
    assert fact_supported(None, "any fact", "any capability", ["E-1"]) is True
    assert fact_supported(ek, "", "lending", ["E-1"]) is True     # empty fact
    assert fact_supported(ek, "a fact", "lending", None) is True  # un-cited → no-op


def test_cited_evidence_that_supports_capability_passes():
    ek = build_entity_knowledge({
        "E-1": "The bank's commercial lending origination is manual and paper-based",
        "E-2": "Marketing relies on a single shared inbox for campaigns",
    })
    assert ek is not None
    assert fact_supported(
        ek, "commercial lending origination is manual and paper-based",
        "commercial lending origination", ["E-1"]) is True


def test_roster_line_cited_under_technical_capability_is_rejected():
    ek = build_entity_knowledge({
        "E-1": "Model performance monitoring is ad hoc with no drift alerts",
        "E-2": "Gregory Lindenmuth serves as Executive Vice President and Chief Risk Officer",
    })
    # the bio line E-2 cited under Model Performance Monitoring must NOT ground
    # the claim — E-2 does not support that capability.
    assert fact_supported(
        ek, "Gregory Lindenmuth serves as Chief Risk Officer",
        "Model Performance Monitoring", ["E-2"]) is False


def test_offtopic_capability_with_no_matching_evidence_is_rejected():
    ek = build_entity_knowledge({
        "E-1": "The bank's commercial lending origination is manual and paper-based",
    })
    assert fact_supported(
        ek, "quantum key distribution pilot underway",
        "Quantum Cryptography Research", ["E-1"]) is False
