"""Tests for the v7 L4-layer catalogue affinity (platform_affinity) and its
fusion into the fit engine v2 (catalogue_fit_by_platform)."""
from __future__ import annotations

from app.services.platform_affinity import (
    build_catalogue_affinity,
    families_for_l3,
)
from app.services.platform_fit import (
    SubcapForFit,
    compute_platform_fit_v2,
)


def _gap(sid: str, tags: list[str] | None = None) -> SubcapForFit:
    return SubcapForFit(
        subcap_id=sid, current_score=2.0, platform_ids=tags or [],
        linked_insight_severities=["high"], name=f"Capability {sid}",
        evidence_e_ids=["E-001"], evidence_strength=0.8, evidence_tier=1,
    )


# ── families_for_l3 ─────────────────────────────────────────────────────

def test_family_mapping_covers_scored_vendors() -> None:
    assert families_for_l3("Salesforce", "Agentforce") == ["salesforce"]
    assert families_for_l3("nCino", "nCino Cloud Banking") == ["ncino"]
    assert families_for_l3("Databricks", "Lakehouse") == ["databricks"]
    assert families_for_l3("Twilio", "Twilio Flex") == ["twilio"]
    assert families_for_l3("Tableau", "Tableau Cloud") == ["tableau"]


def test_slash_joined_vendor_maps_to_both_families() -> None:
    fams = families_for_l3("Salesforce / Tableau", "CRM Analytics")
    assert set(fams) == {"tableau", "salesforce"}


def test_tableau_crm_is_salesforce_not_tableau() -> None:
    # "Tableau CRM" is the Salesforce-embedded analytics product.
    assert families_for_l3("Salesforce", "Tableau CRM") == ["salesforce"]


def test_unscored_vendor_maps_nowhere() -> None:
    assert families_for_l3("ServiceNow", "Now Platform") == []


# ── build_catalogue_affinity ────────────────────────────────────────────

def test_affinity_grades_on_feature_depth() -> None:
    rows = (
        [("P1C1.1.1", "Salesforce", "Agentforce", f"Feature {i}") for i in range(8)]
        + [("P1C1.1.2", "Salesforce", "Agentforce", "Single Feature")]
    )
    out = build_catalogue_affinity(rows)
    sf = out["salesforce"]
    assert sf["P1C1.1.1"]["affinity"] == 1.0          # 8 features → full
    assert 0.3 < sf["P1C1.1.2"]["affinity"] < 0.4     # sqrt(1/8) ≈ 0.354
    assert sf["P1C1.1.2"]["features"] == ["Single Feature"]


def test_affinity_feature_names_dedupe_and_cap() -> None:
    rows = [("P2C1.1.1", "nCino", "nCino", f"F{i % 4}") for i in range(12)]
    out = build_catalogue_affinity(rows)
    feats = out["ncino"]["P2C1.1.1"]["features"]
    assert feats == ["F0", "F1", "F2", "F3"]  # deduped, order-preserving


# ── engine fusion ───────────────────────────────────────────────────────

def test_catalogue_linked_subcap_is_addressable_without_keyword_tag() -> None:
    """A gap subcap with NO keyword tag and NO semantic hit is still
    addressable when the v7 catalogue links features onto it."""
    subcaps = [_gap("P1C1.1.1", tags=[])]
    cat = {"salesforce": {"P1C1.1.1": {"affinity": 0.9,
                                       "features": ["Agentforce Builder"]}}}
    rows = compute_platform_fit_v2(
        subcaps, ["salesforce", "ncino"],
        readiness_by_platform={"salesforce": "green", "ncino": "green"},
        catalogue_fit_by_platform=cat,
    )
    by = {r.platform_id: r for r in rows}
    assert by["salesforce"].addressable_subcap_ids == ["P1C1.1.1"]
    assert by["salesforce"].fit_score > 0
    # ncino has no catalogue link and no tag → keyword fallback finds nothing
    assert by["ncino"].addressable_subcap_ids == []
    # breakdown carries the trace + the named features
    bd = by["salesforce"].breakdown
    assert bd["catalogue_fit"]["value"] == 0.9
    assert bd["catalogue_fit"]["n_linked"] == 1
    tops = bd["factors"]["opportunity"] is not None and bd["top_subcaps"]
    assert tops[0]["l4_features"] == ["Agentforce Builder"]


def test_catalogue_weight_lifts_over_semantic_miss() -> None:
    """When the CE missed a subcap (0.70 dampening) but the catalogue links
    it deeply, the catalogue confidence wins (max fusion)."""
    subcaps = [_gap("P1C1.1.1")]
    sem = {"salesforce": {"P9C9.9.9": 0.5}}  # sem tier warm, missed our subcap
    cat = {"salesforce": {"P1C1.1.1": {"affinity": 1.0, "features": ["F"]}}}
    with_cat = compute_platform_fit_v2(
        subcaps, ["salesforce"],
        readiness_by_platform={"salesforce": "green"},
        semantic_fit_by_platform=sem,
        catalogue_fit_by_platform=cat,
    )[0]
    without_cat_subcaps = [_gap("P1C1.1.1", tags=["salesforce"])]
    without_cat = compute_platform_fit_v2(
        without_cat_subcaps, ["salesforce"],
        readiness_by_platform={"salesforce": "green"},
        semantic_fit_by_platform={"salesforce": {"P1C1.1.1": 0.01}},
    )[0]
    assert with_cat.fit_score > without_cat.fit_score


def test_cold_tiers_fall_back_to_keyword_tags_unchanged() -> None:
    """Both precise tiers empty → the keyword path, byte-identical to the
    pre-catalogue engine (zero regression)."""
    subcaps = [_gap("P1C1.1.1", tags=["salesforce"])]
    baseline = compute_platform_fit_v2(
        subcaps, ["salesforce"],
        readiness_by_platform={"salesforce": "green"},
    )[0]
    explicit_empty = compute_platform_fit_v2(
        subcaps, ["salesforce"],
        readiness_by_platform={"salesforce": "green"},
        catalogue_fit_by_platform={},
    )[0]
    assert baseline.fit_score == explicit_empty.fit_score
    assert baseline.addressable_subcap_ids == explicit_empty.addressable_subcap_ids


def test_union_of_semantic_and_catalogue_addressability() -> None:
    """Addressable = union of CE-confirmed and catalogue-linked."""
    subcaps = [_gap("P1C1.1.1"), _gap("P1C1.1.2"), _gap("P1C1.1.3")]
    sem = {"salesforce": {"P1C1.1.1": 0.6}}
    cat = {"salesforce": {"P1C1.1.2": {"affinity": 0.7, "features": []}}}
    row = compute_platform_fit_v2(
        subcaps, ["salesforce"],
        readiness_by_platform={"salesforce": "green"},
        semantic_fit_by_platform=sem,
        catalogue_fit_by_platform=cat,
    )[0]
    assert row.addressable_subcap_ids == ["P1C1.1.1", "P1C1.1.2"]
