"""Platform-fit addressability is NLP-gated (2026-07-09).

Keyword platform tags are ~11% precise on the 94-client corpus (they mark a
platform "addressing" 9 sub-capabilities it doesn't fit for every 1 it does), so
the fit engine now gates addressability on the cross-encoder's support instead —
falling back to the keyword tags only when the NLP tier is cold. These tests
pin both paths with synthetic, model-free inputs (semantic_fit_by_platform is
passed explicitly).
"""
from __future__ import annotations

from app.services.platform_fit import SubcapForFit, compute_platform_fit_v2


def _sc(sid: str, tags: list[str]) -> SubcapForFit:
    return SubcapForFit(
        subcap_id=sid, current_score=2.0, platform_ids=tags,
        linked_insight_severities=[], name=sid, target_band_score=4.0,
        evidence_strength=0.9, evidence_tier=2, evidence_e_ids=["E-1"],
    )


def test_addressability_is_ce_gated_when_hot() -> None:
    # keyword tags Salesforce onto BOTH subcaps; the CE only supports one.
    subs = [_sc("P2C1.1.1", ["salesforce"]), _sc("P4C1.2.1", ["salesforce"])]
    rows = compute_platform_fit_v2(
        subs, ["salesforce"],
        readiness_by_platform={"salesforce": "green"},
        semantic_fit_by_platform={"salesforce": {"P2C1.1.1": 0.72}},  # only this one
    )
    addr = rows[0].addressable_subcap_ids
    assert addr == ["P2C1.1.1"]                 # CE-gated: the unsupported tag dropped
    assert "P4C1.2.1" not in addr


def test_addressability_recovers_untagged_when_ce_supports() -> None:
    # a subcap the keyword table did NOT tag, but the CE supports → recovered.
    subs = [_sc("P2C1.1.1", []), _sc("P2C1.2.1", [])]
    rows = compute_platform_fit_v2(
        subs, ["salesforce"],
        readiness_by_platform={"salesforce": "green"},
        semantic_fit_by_platform={"salesforce": {"P2C1.2.1": 0.55}},
    )
    assert rows[0].addressable_subcap_ids == ["P2C1.2.1"]


def test_cold_tier_falls_back_to_keyword_tags() -> None:
    subs = [_sc("P2C1.1.1", ["salesforce"]), _sc("P4C1.2.1", ["databricks"])]
    rows = compute_platform_fit_v2(
        subs, ["salesforce"],
        readiness_by_platform={"salesforce": "green"},
        semantic_fit_by_platform=None,          # cold → keyword behaviour
    )
    assert rows[0].addressable_subcap_ids == ["P2C1.1.1"]


def test_breakdown_surfaces_semantic_fit_when_present() -> None:
    subs = [_sc("P2C1.1.1", ["salesforce"])]
    rows = compute_platform_fit_v2(
        subs, ["salesforce"],
        readiness_by_platform={"salesforce": "green"},
        semantic_fit_by_platform={"salesforce": {"P2C1.1.1": 0.80}},
    )
    assert rows[0].breakdown.get("semantic_fit") is not None
    assert rows[0].breakdown["semantic_fit"]["value"] == 0.80
