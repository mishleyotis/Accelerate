"""Deterministic per-subcap synthesis composer (Part 6.3 floor).

Pins the three prototype variants (thin / peer-gap / at-peer), the
2-4-sentence budget, real-value citation, and the banned-phrase guard:
no composed narrative may contain a template family from the
`nlp.quality` filler blacklist ("quality only ships").
"""
from __future__ import annotations

import re

from app.services.nlp.quality import _FILLER_PHRASES
from app.services.subcap_synthesis import (
    SubcapFacts,
    compose_subcap_narrative,
    is_generic_subcap_name,
)


def _facts(**overrides) -> SubcapFacts:
    base = {
        "subcap_id": "P1C1.1.1",
        "name": "Digital Strategy Document",
        "score": 2.5,
        "band": "M2",
        "peer_median": 3.1,
        "is_thin_evidence": False,
        "cap_applied": False,
        "cap_reason": None,
        "evidence_count": 3,
        "evidence_e_ids": ["E-001", "E-007", "E-012"],
        "top_excerpt": (
            "The board approved a three-year digital roadmap with a $4M "
            "modernization budget in Q1 2025."
        ),
        "insight_titles": ["Strategy exists but lacks funding linkage"],
        "rec_titles": ["Stand up a quarterly strategy refresh cadence"],
    }
    base.update(overrides)
    return SubcapFacts(**base)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


class TestVariants:
    def test_peer_gap_variant_cites_real_numbers(self) -> None:
        out = compose_subcap_narrative(_facts())
        assert "2.5" in out and "M2" in out
        assert "3.1" in out            # peer median
        assert "0.6" in out            # the actual gap
        assert "trails the peer median" in out

    def test_at_peer_variant(self) -> None:
        out = compose_subcap_narrative(_facts(score=3.0, peer_median=3.1))
        assert "at the peer median" in out

    def test_above_peer_variant_protects_the_lead(self) -> None:
        out = compose_subcap_narrative(_facts(score=4.2, peer_median=3.1))
        assert "above the peer median" in out
        assert "protecting" in out

    def test_thin_variant_flags_provisional(self) -> None:
        out = compose_subcap_narrative(
            _facts(is_thin_evidence=True, evidence_count=1,
                   evidence_e_ids=["E-001"]),
        )
        assert "provisional" in out
        assert "1 corroborating evidence item" in out

    def test_cap_sentence_carries_reason(self) -> None:
        out = compose_subcap_narrative(
            _facts(cap_applied=True,
                   cap_reason="IR-003 open consent order caps at M2."),
        )
        assert "caps this score" in out
        assert "IR-003" in out

    def test_no_peer_no_evidence_still_says_something_real(self) -> None:
        out = compose_subcap_narrative(
            _facts(peer_median=None, evidence_count=0, evidence_e_ids=[],
                   top_excerpt=None, insight_titles=[], rec_titles=[],
                   is_thin_evidence=False),
        )
        assert "P1C1.1.1" in out
        assert len(_sentences(out)) >= 2


class TestBudgetAndGrounding:
    def test_two_to_four_sentences_always(self) -> None:
        cases = [
            _facts(),
            _facts(is_thin_evidence=True, cap_applied=True,
                   cap_reason="IR-001 caps at M2"),
            _facts(peer_median=None),
            _facts(evidence_count=0, evidence_e_ids=[], top_excerpt=None),
        ]
        for facts in cases:
            n = len(_sentences(compose_subcap_narrative(facts)))
            assert 2 <= n <= 4, f"{n} sentences for {facts}"

    def test_grounding_cites_eid_and_verbatim_excerpt(self) -> None:
        out = compose_subcap_narrative(_facts(peer_median=None))
        assert "E-001" in out
        assert "three-year digital roadmap" in out

    def test_placeholder_excerpt_never_quoted(self) -> None:
        out = compose_subcap_narrative(
            _facts(peer_median=None, top_excerpt="(no excerpt)"),
        )
        assert "(no excerpt)" not in out

    def test_subcap_id_and_name_always_present(self) -> None:
        out = compose_subcap_narrative(_facts())
        assert "Digital Strategy Document" in out
        assert "(P1C1.1.1)" in out


class TestBannedPhraseGuard:
    def test_no_filler_blacklist_phrase_in_any_variant(self) -> None:
        variants = [
            _facts(),
            _facts(score=3.2, peer_median=3.1),
            _facts(score=4.5, peer_median=3.0),
            _facts(is_thin_evidence=True, evidence_count=0,
                   evidence_e_ids=[], top_excerpt=None),
            _facts(cap_applied=True, cap_reason="IR-002 caps at M1"),
            _facts(peer_median=None, insight_titles=[], rec_titles=[]),
        ]
        for facts in variants:
            lowered = compose_subcap_narrative(facts).lower()
            for phrase in _FILLER_PHRASES:
                assert phrase not in lowered, (
                    f"banned template phrase {phrase!r} leaked into the "
                    f"composed narrative"
                )


class TestDepthStressFixes:
    """2026-07 depth stress-test regression pins."""

    def test_substance_guaranteed_when_citable_excerpt_exists(self) -> None:
        # Even a crowded thin+cap+peer cell must carry the evidence
        # excerpt's concrete content, not just "grounded on E-105".
        out = compose_subcap_narrative(_facts(
            is_thin_evidence=True, cap_applied=True,
            cap_reason="IR-001 caps at M2",
        ))
        assert "three-year digital roadmap" in out
        assert "$4M" in out
        assert "grounded on" not in out  # content-free pointer replaced

    def test_eid_pointer_only_when_no_excerpt_citable(self) -> None:
        out = compose_subcap_narrative(_facts(
            peer_median=None, top_excerpt="(no excerpt)",
            evidence_excerpts=["(no excerpt)", "n/a", ""],
        ))
        assert "grounded on E-001" in out

    def test_walks_to_the_first_citable_excerpt(self) -> None:
        out = compose_subcap_narrative(_facts(
            evidence_excerpts=[
                "(no excerpt)",
                "Deployed nCino on FIS core with 12-day loan cycle time.",
                "",
            ],
        ))
        assert "E-007" in out          # the SECOND item's eid is cited
        assert "nCino" in out          # …with its own substance

    def test_leading_markup_tags_stripped_from_excerpt(self) -> None:
        out = compose_subcap_narrative(_facts(
            evidence_excerpts=[
                "[ERS: 2.20] [FACT] SR 11-7 requires model risk management "
                "for all supervised banks over $10B.",
            ],
        ))
        assert "[ERS" not in out
        assert "SR 11-7" in out

    def test_degenerate_cap_reason_never_renders_none(self) -> None:
        for reason in ("None", "null", "N/A", "-", "  "):
            out = compose_subcap_narrative(
                _facts(cap_applied=True, cap_reason=reason),
            )
            assert ": None" not in out
            assert "caps this score until resolved" in out

    def test_generic_names_render_bare_id(self) -> None:
        for generic in ("capability dimension 3", "Subcap 7",
                        "Process Automation — Subcap 10", "Subcap P2C2.1.7",
                        None, "", "P2C2.1.7"):
            out = compose_subcap_narrative(_facts(name=generic, subcap_id="P2C2.1.7"))
            assert out.startswith("P2C2.1.7 scored"), (generic, out)
            assert "capability dimension" not in out.lower()
            assert "Subcap 7" not in out

    def test_real_names_pass_the_generic_guard(self) -> None:
        assert not is_generic_subcap_name("Digital Strategy Document", "P1C1.1.1")
        assert not is_generic_subcap_name("Subcapital Markets Desk", "P1C1.1.1")
        assert is_generic_subcap_name("Subcap 12", "P1C1.1.1")
        assert is_generic_subcap_name("capability dimension 4", "P1C1.1.1")


def test_playbook_sentence_gap_cells_only() -> None:
    from app.services.subcap_synthesis import SubcapFacts, compose_subcap_narrative
    base = {"subcap_id": "P1C1.1.1", "name": "Vision & Mandate", "score": 2.0,
                "band": "M2", "peer_median": 3.5, "evidence_count": 3,
                "evidence_e_ids": ["E-001", "E-002", "E-003"],
                "playbook_features": ["Agentforce Builder", "Data Cloud Segments",
                                   "FSC Compliance Workflows"],
                "playbook_stories": 14}
    md = compose_subcap_narrative(SubcapFacts(**base))
    assert "proven implementation pattern" in md
    assert "Agentforce Builder" in md and "14 catalogued use cases" in md
    # at-peer cells never carry the playbook pitch
    at_peer = dict(base, score=3.6)
    assert "proven implementation pattern" not in compose_subcap_narrative(
        SubcapFacts(**at_peer))
    # a single-story pattern is not "validated" — stays silent
    weak = dict(base, playbook_stories=1)
    assert "proven implementation pattern" not in compose_subcap_narrative(
        SubcapFacts(**weak))


def test_build_playbooks_ranks_recurring_features() -> None:
    from app.services.use_case_stories import build_playbooks
    rows = [
        ("P1C1.1.1", "Agentforce Builder for X, Data Cloud for X", 0.9),
        ("P1C1.1.1", "Agentforce Builder for X; FSC Workflows for X", 0.6),
        ("P1C1.1.1", "Agentforce Builder for X", 0.9),
        ("P2C2.2.2", "", 0.9),           # featureless story → no playbook
    ]
    out = build_playbooks(rows)
    pb = out["P1C1.1.1"]
    assert pb["features"][0] == "Agentforce Builder"   # 3 recurrences lead
    assert pb["n_stories"] == 3 and pb["confidence"] == 0.9
    assert "P2C2.2.2" not in out
