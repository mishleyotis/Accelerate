"""Tests for the pillar → offering router."""
from __future__ import annotations

from app.services.platform_routing import (
    GapSubcap,
    OfferingSubcapLink,
    route_offerings_per_pillar,
)


def test_empty_catalogue_emits_one_row_per_pillar_with_no_offerings() -> None:
    result = route_offerings_per_pillar(catalogue_links=[], entity_gaps=[])
    assert [r.pillar for r in result] == ["P1", "P2", "P3", "P4"]
    for r in result:
        assert r.offerings == []


def test_offerings_ranked_by_total_gap_within_pillar() -> None:
    catalogue = [
        OfferingSubcapLink(offering_id="marketing_cloud", subcap_id="P2C1.1.1", pillar="P2"),
        OfferingSubcapLink(offering_id="marketing_cloud", subcap_id="P2C2.1.1", pillar="P2"),
        OfferingSubcapLink(offering_id="service_cloud",  subcap_id="P2C1.1.1", pillar="P2"),
    ]
    gaps = [
        GapSubcap(subcap_id="P2C1.1.1", pillar="P2", severity="high", gap_size=2.0),
        GapSubcap(subcap_id="P2C2.1.1", pillar="P2", severity="medium", gap_size=1.0),
    ]
    out = {r.pillar: r for r in route_offerings_per_pillar(catalogue_links=catalogue, entity_gaps=gaps)}
    # marketing_cloud touches both gaps (sum 3.0); service_cloud only first (2.0) → MC first
    assert out["P2"].offerings == ["marketing_cloud", "service_cloud"]


def test_offerings_filtered_by_pillar_match() -> None:
    catalogue = [
        # Catalogue links say this offering is for P2; the subcap also belongs to P2.
        OfferingSubcapLink(offering_id="marketing_cloud", subcap_id="P2C1.1.1", pillar="P2"),
        # Mismatched pillar — should be ignored.
        OfferingSubcapLink(offering_id="marketing_cloud", subcap_id="P2C1.1.1", pillar="P4"),
    ]
    gaps = [GapSubcap(subcap_id="P2C1.1.1", pillar="P2", severity="high", gap_size=1.5)]
    out = {r.pillar: r for r in route_offerings_per_pillar(catalogue_links=catalogue, entity_gaps=gaps)}
    assert out["P2"].offerings == ["marketing_cloud"]
    assert out["P4"].offerings == []


def test_subcaps_with_zero_gap_are_ignored() -> None:
    catalogue = [
        OfferingSubcapLink(offering_id="x", subcap_id="P1C1.1.1", pillar="P1"),
    ]
    gaps = [GapSubcap(subcap_id="P1C1.1.1", pillar="P1", severity="high", gap_size=0.0)]
    out = {r.pillar: r for r in route_offerings_per_pillar(catalogue_links=catalogue, entity_gaps=gaps)}
    assert out["P1"].offerings == []


def test_offering_never_rendered_without_addressable_gap() -> None:
    """The router only emits offerings that actually cover an addressable gap."""
    catalogue = [
        OfferingSubcapLink(offering_id="ipa_suite", subcap_id="P3C1.1.1", pillar="P3"),
    ]
    # No gap on the addressed subcap → no offering for P3.
    gaps = [GapSubcap(subcap_id="P4C1.1.1", pillar="P4", severity="high", gap_size=2.0)]
    out = {r.pillar: r for r in route_offerings_per_pillar(catalogue_links=catalogue, entity_gaps=gaps)}
    assert out["P3"].offerings == []
