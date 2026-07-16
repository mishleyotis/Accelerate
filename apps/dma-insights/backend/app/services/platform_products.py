"""Zennify product taxonomy — extract the SPECIFIC recommended product from an
analyst recommendation's prose (2026-07-15 platform-fit rework).

The prior mapping (`_infer_platform_id` in package_persist) collapsed every
Salesforce-family product — Financial Services Cloud, Data Cloud, Service
Cloud, Marketing Cloud, MuleSoft, Agentforce, Shield, … — into a single
``"salesforce"`` bucket (326/599 recs) and could not map 42% at all. The
platform-fit engine then ignored the recommendations entirely and enumerated a
fixed 5-family catalogue, so the exec summary always led with generic
best-of-breed data platforms (Databricks/Tableau/nCino) regardless of what the
assessment actually recommended.

The analyst names the specific product in the recommendation TITLE (100%
populated) and description ("Deploy Unified Salesforce FSC Agent Desktop",
"Data Cloud for 16-Charter Customer 360", "MuleSoft as Salesforce Foundation").
This module recovers that specificity so the fit engine can be
recommendation-driven — the candidate set becomes the analyst's own products.

Contract:
  - ``primary_product(title, description)`` → the lead product_id (most-specific
    keyword wins), or None when no known product is named.
  - ``extract_products(text)`` → every product_id mentioned, order-preserving +
    deduped (a rec can pitch a bundle: "FSC + MuleSoft foundation").
  - ``vendor_family(product_id)`` → the coarse family for grouping / the legacy
    ``platform_id`` the D4 cards + catalogue key on.
  - ``display_name(product_id)`` → the client-facing product name.

Everything is pure + None-safe; unknown input yields None / [] and never raises.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    product_id: str          # stable slug, e.g. "financial_services_cloud"
    display_name: str        # client-facing, e.g. "Financial Services Cloud"
    vendor_family: str       # coarse grouping / legacy platform_id
    keywords: tuple[str, ...]  # match phrases, LONGEST/most-specific first


# Order matters: the extractor tries products top-to-bottom and, within a
# product, keyword-by-keyword. List the MOST SPECIFIC products first so
# "Financial Services Cloud" wins over a bare "Salesforce", and a specific
# keyword ("agentforce for service") is reachable before the generic one.
_PRODUCTS: tuple[Product, ...] = (
    Product("financial_services_cloud", "Financial Services Cloud", "salesforce",
            ("financial services cloud", "fsc reactivation", "fsc agent",
             "fsc wealth", "fsc loan", "fsc compliance", "fsc relationship",
             "fsc implementation", "\bfsc\b")),
    Product("data_cloud", "Data Cloud", "salesforce",
            ("data cloud", "customer data platform", "\bcdp\b")),
    Product("service_cloud", "Service Cloud", "salesforce",
            ("service cloud", "omnichannel case", "case management")),
    Product("marketing_cloud", "Marketing Cloud", "salesforce",
            ("marketing cloud", "account engagement", "pardot",
             "journey orchestration")),
    Product("sales_cloud", "Sales Cloud", "salesforce",
            ("sales cloud",)),
    Product("experience_cloud", "Experience Cloud", "salesforce",
            ("experience cloud", "digital onboarding portal", "broker portal",
             "member portal", "partner portal")),
    Product("agentforce", "Agentforce", "salesforce",
            ("agentforce", "virtual agent", "ai agent", "conversational ai")),
    Product("einstein_analytics", "Einstein / CRM Analytics", "salesforce",
            ("crm analytics", "einstein", "tableau crm", "analytics cloud")),
    Product("salesforce_shield", "Salesforce Shield", "salesforce",
            ("salesforce shield", "shield platform", "privacy center",
             "\bshield\b")),
    Product("omnistudio", "OmniStudio / Flow", "salesforce",
            ("omnistudio", "flow orchestration", "flow + omnistudio")),
    Product("mulesoft", "MuleSoft Anypoint", "mulesoft",
            ("mulesoft", "anypoint", "api gateway", "integration orchestration",
             "ipaas")),
    Product("ncino", "nCino", "ncino",
            ("ncino",)),
    Product("tableau", "Tableau", "tableau",
            ("tableau",)),
    Product("snowflake", "Snowflake", "snowflake",
            ("snowflake",)),
    Product("databricks", "Databricks", "databricks",
            ("databricks", "lakehouse")),
    Product("twilio", "Twilio", "twilio",
            ("twilio",)),
    Product("digital_strategy_workshop", "Digital Strategy Workshop", "advisory",
            ("digital strategy workshop", "strategy workshop",
             "advisory engagement", "executive alignment workshop")),
    # Generic Salesforce mention — LAST, so a specific cloud always wins first.
    Product("salesforce_platform", "Salesforce Platform", "salesforce",
            ("salesforce",)),
)

_BY_ID: dict[str, Product] = {p.product_id: p for p in _PRODUCTS}

# Pre-compile: (product, compiled-pattern). A keyword wrapped in \b…\b in the
# source is treated as a regex word-boundary token (e.g. "\bfsc\b" so "fsc"
# doesn't match inside "fscore"); everything else is a plain substring made
# boundary-safe.
_COMPILED: tuple[tuple[Product, re.Pattern[str]], ...] = tuple(
    (p, re.compile("|".join(
        kw if kw.startswith("\\b") else r"\b" + re.escape(kw) + r"\b"
        for kw in p.keywords), re.I))
    for p in _PRODUCTS
)


def extract_products(text: str | None) -> list[str]:
    """Every known product named in ``text``, most-specific first, deduped.
    Position-ordered so a title's lead product tends to sort first."""
    s = str(text or "")
    if not s.strip():
        return []
    hits: list[tuple[int, str]] = []
    seen: set[str] = set()
    for p, pat in _COMPILED:
        m = pat.search(s)
        if m and p.product_id not in seen:
            hits.append((m.start(), p.product_id))
            seen.add(p.product_id)
    # Sort by position in the text, but keep a stable secondary order matching
    # the specificity of _PRODUCTS (earlier = more specific) for ties.
    order = {p.product_id: i for i, p in enumerate(_PRODUCTS)}
    hits.sort(key=lambda t: (t[0], order[t[1]]))
    out = [pid for _, pid in hits]
    # The generic "salesforce_platform" is noise when a specific SF cloud is
    # already present — drop it so the bundle names real products.
    specific_sf = any(_BY_ID[x].vendor_family == "salesforce"
                      and x != "salesforce_platform" for x in out)
    if specific_sf:
        out = [x for x in out if x != "salesforce_platform"]
    return out


def primary_product(title: str | None, description: str | None = None) -> str | None:
    """The lead product for a recommendation. The TITLE wins (the analyst names
    the product there); the description is a fallback when the title is
    product-silent (advisory-worded titles)."""
    for src in (title, description):
        got = extract_products(src)
        if got:
            return got[0]
    return None


# Domain → product FALLBACK. Many analyst recs name the outcome/capability, not
# the product ("Establish Enterprise Data Foundation", "Modernize Customer
# Engagement & Digital Channels", "P3C3 Security & Compliance"). Zennify is a
# Salesforce practice, so a domain-framed rec implies a Salesforce-family
# product. This fires ONLY when no explicit product is named (see
# ``infer_product_from_domain``) — a conservative reading of the analyst's
# intent, not a guess over an explicit pick. Order = most specific first.
_DOMAIN_FALLBACK: tuple[tuple[str, str], ...] = (
    (r"loan origination|\bLOS\b|lending|underwriting|credit decision", "ncino"),
    (r"data (?:foundation|governance|management|platform|warehouse|lake|quality)"
     r"|master data|\bMDM\b|customer 360|analytics|AI-ready|data silo|\bCDP\b"
     r"|\bCDO\b|centralized (?:data|governance)", "data_cloud"),
    (r"compliance|regulatory|consent order|\bAML\b|\bBSA\b|\bKYC\b|\bGRC\b"
     r"|governance|cyber|security posture|data protection|privacy|risk", "salesforce_shield"),
    (r"integration|operations platform|\bAPI\b|middleware|\biPaaS\b|open banking"
     r"|core (?:banking|system)|straight-through", "mulesoft"),
    (r"marketing|demand gen|campaign|personaliz|journey", "marketing_cloud"),
    (r"customer engagement|digital channel|omnichannel|onboarding|self-service"
     r"|member (?:experience|service)|contact center|call center|mobile app"
     r"|customer experience|\bCX\b|service", "service_cloud"),
    (r"advisor|wealth|relationship (?:banking|management)", "financial_services_cloud"),
)
_DOMAIN_FALLBACK_C: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(p, re.I), pid) for p, pid in _DOMAIN_FALLBACK)


def infer_product_from_domain(text: str | None) -> str | None:
    """Fallback for recs that frame the OUTCOME/domain rather than naming a
    product. Returns a Salesforce-family (or nCino) product implied by the
    domain, or None when there's no domain signal (fully-empty recs stay
    residual — we never invent a platform)."""
    s = str(text or "")
    if not s.strip():
        return None
    for pat, pid in _DOMAIN_FALLBACK_C:
        if pat.search(s):
            return pid
    return None


def vendor_family(product_id: str | None) -> str | None:
    """Coarse family for grouping / the legacy D4 platform_id."""
    p = _BY_ID.get(str(product_id or ""))
    return p.vendor_family if p else None


def display_name(product_id: str | None) -> str | None:
    p = _BY_ID.get(str(product_id or ""))
    return p.display_name if p else None


def known_product_ids() -> tuple[str, ...]:
    return tuple(_BY_ID.keys())
