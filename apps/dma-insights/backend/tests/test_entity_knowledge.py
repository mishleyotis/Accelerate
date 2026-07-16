"""L1 EntityState (nlp/entity_knowledge.py) — the shared per-entity state read by
every composer. The async DB loader is exercised against the live regen DB in the
local harness; this pins the pure logic (scope gate, ranked selection, catalogue
names, evidence retrieval) on a synthetic state so the contract holds in CI.
"""
from __future__ import annotations

import os

os.environ.setdefault("DMA_DISABLE_SEMANTIC", "1")

from app.services.nlp.entity_knowledge import Capability, EntityState
from app.services.nlp.knowledge import EntityKnowledge, Evidence


def _cap(sid, name, score, gap, in_scope=True, eids=()):
    return Capability(
        subcap_id=sid, name=name, score=score, peer_median=score - (gap or 0),
        peer_gap=gap, pillar=sid[:2], category=sid.split(".")[0],
        rationale="", tier="T1", in_scope=in_scope, evidence_ids=list(eids),
    )


def _state() -> EntityState:
    evidence = [
        Evidence("E-crm", "Salesforce Financial Services Cloud is the CRM system of record.", tier=1, year=2026, owned=True),
        Evidence("E-peer", "Peer benchmark: FCSA reports NPS 60, top of the cohort.", tier=2, year=2025, owned=False),
    ]
    caps = [
        _cap("P2C2.5.5", "Asset Transfer (ACATs)", 1.0, -1.75, in_scope=False),
        _cap("P4C1.4.1", "Master Data Management", 1.5, -1.5, in_scope=True, eids=["E-crm"]),
        _cap("P4C2.1.2", "AI & ML Strategy", 4.5, 1.75, in_scope=True),
        _cap("P1C3.9.1", "Innovation Lab", 1.0, -1.0, in_scope=True),
    ]
    st = EntityState(
        run_id="r", entity_id="e", name="Test Bank", subvertical="RB",
        catalog_version="v7.0", capabilities=caps,
        knowledge=EntityKnowledge(evidence), firmographics={}, platforms=[],
        tech_stack=[], scqa=None, top_findings=[], why_now_signals=[],
        na_subcap_ids={"P2C2.5.5"},
        _by_subcap={c.subcap_id: c for c in caps},
        _excerpt_by_eid={e.e_id: e.text for e in evidence},
        _catalogue_names={c.name.lower() for c in caps},
    )
    return st


def test_in_scope_gate_drops_na_subcap() -> None:
    st = _state()
    assert st.in_scope("P2C2.5.5") is False       # in the A5 NA list
    assert st.in_scope("P4C1.4.1") is True


def test_ranked_gaps_excludes_out_of_scope_and_orders_by_peer_gap() -> None:
    st = _state()
    gaps = st.ranked_gaps
    ids = [c.subcap_id for c in gaps]
    assert "P2C2.5.5" not in ids                  # NA cell never a gap
    assert ids[0] == "P4C1.4.1"                    # widest in-scope negative gap
    assert "P4C2.1.2" not in ids                   # a strength, not a gap


def test_ranked_strengths_orders_by_outperformance() -> None:
    st = _state()
    strengths = st.ranked_strengths
    assert strengths[0].subcap_id == "P4C2.1.2"


def test_catalogue_names_are_the_g1_bare_label_set() -> None:
    st = _state()
    assert "master data management" in st.catalogue_subcap_names
    assert "innovation lab" in st.catalogue_subcap_names


def test_supporting_evidence_is_ownership_checked() -> None:
    st = _state()
    hits = st.supporting_evidence("Salesforce CRM system of record", k=3, min_score=0.05)
    ids = [e for e, _ in hits]
    assert "E-crm" in ids
    assert "E-peer" not in ids                     # peer-owned excluded


def test_evidence_excerpt_and_evidence_for() -> None:
    st = _state()
    assert "Salesforce" in (st.evidence_excerpt("E-crm") or "")
    assert st.evidence_for("P4C1.4.1") == ["E-crm"]
    assert st.evidence_for("P4C2.1.2") == []


# ── analyst SCQA section parsing (the L4 spine wiring) ──────────────────────
from app.services.nlp.entity_knowledge import parse_scqa_section  # noqa: E402


def test_parse_scqa_section_structured_4part() -> None:
    body = (
        "## 1. Situation\nAcme scores 2.3 overall.\n\n"
        "## 2. Complication\nLargest gaps are in data.\n\n"
        "## 3. Question\nWhere to invest first?\n\n"
        "## 4. Answer\nStand up MuleSoft then Data Cloud to unify the estate.\n\n"
        "*Derived from extracted scores + recommendations.*")
    out = parse_scqa_section(body)
    assert out is not None
    assert out["answer"].startswith("Stand up MuleSoft")
    assert "situation" in out and "complication" in out and "question" in out
    assert "narrative" in out and "Derived from" not in out["narrative"]  # footer trimmed


def test_parse_scqa_section_free_prose_keeps_narrative_only() -> None:
    body = ("Access Credit Union is a $14.1B credit union regulated by DGCM, "
            "operating since 2009. The deepest gap is data segregation.")
    out = parse_scqa_section(body)
    assert out is not None and set(out) == {"narrative"}
    assert out["narrative"].startswith("Access Credit Union")


def test_parse_scqa_section_empty_is_none() -> None:
    assert parse_scqa_section("") is None
    assert parse_scqa_section(None) is None
    assert parse_scqa_section("   \n  ") is None
