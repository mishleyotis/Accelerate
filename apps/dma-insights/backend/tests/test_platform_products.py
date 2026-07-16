"""Zennify product taxonomy extractor (2026-07-15 platform-fit rework)."""
from __future__ import annotations

from app.services import platform_products as pp


def test_primary_product_recovers_specific_salesforce_clouds():
    assert pp.primary_product("Deploy Unified Salesforce FSC Agent Desktop") == "financial_services_cloud"
    assert pp.primary_product("Data Cloud for 16-Charter Customer 360") == "data_cloud"
    assert pp.primary_product("Unify Omnichannel Experience with Service Cloud") == "service_cloud"
    assert pp.primary_product("Rationalize Marketing Cloud (3 Platforms -> 1)") == "marketing_cloud"
    assert pp.primary_product("Expand MuleSoft to External APIs (Open Banking)") == "mulesoft"
    assert pp.primary_product("Deploy Agentforce Virtual Agent for Self-Service") == "agentforce"
    assert pp.primary_product("Salesforce Shield + Privacy Center for Post-Breach") == "salesforce_shield"
    assert pp.primary_product("Experience Cloud for Digital Onboarding") == "experience_cloud"


def test_specific_cloud_beats_generic_salesforce():
    # a title naming both must lead with the specific product, not the bucket
    assert pp.primary_product(
        "Salesforce FSC Reactivation + Alma Wealth Management") == "financial_services_cloud"
    got = pp.extract_products("MuleSoft as Salesforce Foundation for Data Cloud")
    assert "salesforce_platform" not in got          # generic dropped
    assert got[0] in ("mulesoft", "data_cloud")      # a specific product leads


def test_bundle_extraction_orders_and_dedupes():
    got = pp.extract_products(
        "Deploy Data Cloud + Service Cloud; MuleSoft foundation; Data Cloud again")
    assert got == list(dict.fromkeys(got))           # deduped
    assert set(got) >= {"data_cloud", "service_cloud", "mulesoft"}


def test_non_salesforce_families_distinct():
    assert pp.vendor_family(pp.primary_product("Tableau Cloud migration")) == "tableau"
    assert pp.vendor_family(pp.primary_product("nCino LOS: Digital Lending")) == "ncino"
    assert pp.vendor_family(pp.primary_product("Databricks lakehouse buildout")) == "databricks"


def test_none_safe():
    assert pp.primary_product(None) is None
    assert pp.primary_product("") is None
    assert pp.extract_products(None) == []
    assert pp.primary_product("Improve governance maturity") is None   # no product named
    assert pp.vendor_family(None) is None
    assert pp.display_name("financial_services_cloud") == "Financial Services Cloud"


def test_domain_fallback_maps_outcome_recs_to_family():
    # outcome/domain-worded recs (no explicit product) → implied SF-family product
    assert pp.vendor_family(pp.infer_product_from_domain(
        "Establish Enterprise Data Foundation with AI-Ready Analytics")) == "salesforce"
    assert pp.vendor_family(pp.infer_product_from_domain(
        "Modernize Customer Engagement & Digital Channels")) == "salesforce"
    assert pp.infer_product_from_domain(
        "Strengthen Digital Governance & Compliance") == "salesforce_shield"
    # "Channel Integration" is domain-ambiguous (channel vs integration) — either
    # resolves to a Salesforce-platform product (mulesoft groups under the
    # salesforce card family downstream), which is what drives the fix.
    assert pp.vendor_family(
        pp.infer_product_from_domain("P2C4 (Channel Integration)")) in ("salesforce", "mulesoft")
    assert pp.infer_product_from_domain("Deploy nCino LOS for lending") == "ncino"
    # no domain signal / empty → None (never invent a platform)
    assert pp.infer_product_from_domain("(untitled)") is None
    assert pp.infer_product_from_domain("") is None
    assert pp.infer_product_from_domain(None) is None


def test_specific_product_still_wins_over_domain_fallback():
    # a rec that names a product must resolve to THAT product, not the domain
    assert pp.primary_product("Deploy Data Cloud for the data foundation") == "data_cloud"
