"""Category incumbents + vertical relevance for platform fit (pure, no DB).

Two blind spots in the fit engine motivated this module (2026-07-14
platform-skew audit, 30-client sample of the live pack):

1. **Category blindness.** Absence detection (`PLATFORM_FAMILY_PATTERNS`
   in platform_fit_data) only matches a scored family's OWN product
   names. An entity running Snowflake still counted the databricks
   family as a full greenfield opportunity — 4 of the sampled clients
   carried Databricks cards ≥70 over an installed third-party data
   platform. When a category incumbent is present the argument must
   shift lens: from greenfield adoption to integration with the
   installed platform. :func:`detect_category_incumbents` finds those
   incumbents over the same lowercased "vendor product" haystack the
   absence scan uses; :func:`stack_lens` names the resulting frame.

2. **Vertical blindness.** Nothing tied a family to the subverticals it
   is actually built for — nCino (bank/commercial lending software)
   scored 86.8 READY for a rental REIT. Catalogue affinity cannot
   gate this: `load_catalogue_affinity` is catalogue-version-global
   (identical for every entity), so a REIT presents the same
   nCino-addressable gap surface as a bank. :func:`vertical_relevance`
   is the explicit, honest map — out-of-vertical families keep a
   bounded multiplier and a named reason, never a silent zero.

Incumbent detection deliberately matches vendor/product NAMES, not
`ccg_l3_platforms` ids — tech_linker's snowflake→databricks l3 mapping
is adjacency for gap threading, explicitly NOT presence (see the design
note in tech_linker.py).
"""
from __future__ import annotations

import re

# family -> functional category (the lens a category incumbent occupies)
PLATFORM_CATEGORY: dict[str, str] = {
    "salesforce": "crm",
    "databricks": "data_platform",
    "tableau": "bi",
    "twilio": "engagement",
    "ncino": "lending_os",
}

_CATEGORY_LABEL: dict[str, str] = {
    "crm": "CRM",
    "data_platform": "data platform",
    "bi": "business intelligence",
    "engagement": "customer engagement",
    "lending_os": "lending origination",
}

# category -> [(display name, pattern)] of THIRD-PARTY incumbents. Never a
# scored family's own products — those are already covered by
# PLATFORM_FAMILY_PATTERNS (family present ⇒ boost is zero anyway).
CATEGORY_INCUMBENT_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "data_platform": [
        ("Snowflake", re.compile(r"snowflake", re.I)),
        ("Amazon Redshift", re.compile(r"redshift", re.I)),
        ("Google BigQuery", re.compile(r"big ?query", re.I)),
        ("Azure Synapse", re.compile(r"synapse", re.I)),
        ("Teradata", re.compile(r"teradata", re.I)),
        ("Cloudera", re.compile(r"cloudera", re.I)),
        ("dbt", re.compile(r"\bdbt\b", re.I)),
    ],
    "lending_os": [
        ("MeridianLink", re.compile(r"meridianlink", re.I)),
        ("Blend", re.compile(r"\bblend\b", re.I)),
        ("SimpleNexus", re.compile(r"simplenexus", re.I)),
        ("ICE Mortgage / Encompass", re.compile(r"encompass|ice mortgage", re.I)),
        ("Q2 Lending", re.compile(r"q2 lending|cloud lending", re.I)),
        ("Abrigo", re.compile(r"abrigo|sageworks", re.I)),
        ("Baker Hill", re.compile(r"baker hill", re.I)),
        ("FIS Commercial Lending", re.compile(r"fis commercial", re.I)),
    ],
    "bi": [
        ("Power BI", re.compile(r"power ?bi", re.I)),
        ("Looker", re.compile(r"\blooker\b", re.I)),
        ("Qlik", re.compile(r"\bqlik", re.I)),
        ("MicroStrategy", re.compile(r"microstrategy", re.I)),
        ("Cognos", re.compile(r"cognos", re.I)),
        ("Domo", re.compile(r"\bdomo\b", re.I)),
        ("Sisense", re.compile(r"sisense", re.I)),
    ],
    "engagement": [
        ("Braze", re.compile(r"\bbraze\b", re.I)),
        ("Iterable", re.compile(r"iterable", re.I)),
        ("Klaviyo", re.compile(r"klaviyo", re.I)),
        ("Adobe Campaign/AEP", re.compile(
            r"adobe (?:campaign|experience platform|journey)", re.I)),
        ("mParticle", re.compile(r"mparticle", re.I)),
        ("Tealium", re.compile(r"tealium", re.I)),
        ("Genesys", re.compile(r"genesys", re.I)),
    ],
    "crm": [
        ("Microsoft Dynamics", re.compile(r"dynamics (?:365|crm)", re.I)),
        ("HubSpot", re.compile(r"hubspot", re.I)),
        ("Zoho CRM", re.compile(r"zoho", re.I)),
        ("Redtail", re.compile(r"redtail", re.I)),
        ("Wealthbox", re.compile(r"wealthbox", re.I)),
        ("Pega", re.compile(r"\bpega\b", re.I)),
        ("SugarCRM", re.compile(r"sugarcrm", re.I)),
    ],
}


def detect_category_incumbents(stack_hay: str) -> dict[str, list[str]]:
    """{platform_id: [incumbent display names present in the stack]}.

    ``stack_hay`` is the same lowercased "vendor product" haystack the
    absence scan builds from tech_stack_entries. Families whose category
    has no incumbent in the stack map to an empty list.
    """
    hay = stack_hay or ""
    out: dict[str, list[str]] = {}
    for pid, category in PLATFORM_CATEGORY.items():
        out[pid] = [
            name for name, rx in CATEGORY_INCUMBENT_PATTERNS.get(category, [])
            if rx.search(hay)
        ]
    return out


def stack_lens(
    *,
    family_absent: bool,
    incumbents: list[str],
    evidence_in_use: bool,
) -> str:
    """The frame the platform argument should take for this entity:

    - ``expand``     — the family is present (stack table or in-use
      evidence): the story is expanding an installed footprint.
    - ``integrate``  — the family is absent but a category incumbent is
      deployed: the story is integration/coexistence with the incumbent,
      never a greenfield install.
    - ``greenfield`` — absent and the category layer is genuinely open.
    """
    if not family_absent or evidence_in_use:
        return "expand"
    if incumbents:
        return "integrate"
    return "greenfield"


# ── vertical relevance ──────────────────────────────────────────────────

# Extended export codes seen in QA allowlists → canonical migration-012
# codes (entity_healing normalizes at classification time; this guards
# any caller that hands us an un-normalized value).
_EXTENDED_TO_CANONICAL: dict[str, str | None] = {
    "REIT": "AM",
    "WEALTH_RIA": "RIA",
    "ASSET_MANAGER": "AM",
    "INSURANCE_CARRIER": "IC",
    "INSURANCE_BROKER": "IB",
    "MUTUAL": "IC",
    "FINTECH_SAAS": None,
}

_SUBVERTICAL_NAME: dict[str, str] = {
    "RB": "Retail Banking",
    "CU": "Credit Unions",
    "CL": "Commercial Lending",
    "CIB": "Corp & Investment Banking",
    "FC": "Farm Credit / Ag Lending",
    "AM": "Asset & Wealth Management",
    "RIA": "RIA / Broker-Dealer",
    "IC": "Insurance Carriers",
    "IB": "Insurance Brokerages",
}

# Subverticals with a lending operation to originate — the only cohort
# where a loan-origination system is a sane recommendation.
LENDING_SUBVERTICALS: frozenset[str] = frozenset({"RB", "CU", "CL", "CIB", "FC"})

# family -> applicable subverticals. Families not listed are horizontal
# (CRM/data/BI/engagement apply across the corpus taxonomy).
FAMILY_VERTICAL_SCOPE: dict[str, frozenset[str]] = {
    "ncino": LENDING_SUBVERTICALS,
}

_FAMILY_SCOPE_NOTE: dict[str, str] = {
    "ncino": "nCino is bank/commercial-lending origination software",
}

OUT_OF_VERTICAL_RELEVANCE = 0.35


def normalize_subvertical(subvertical: str | None) -> str | None:
    """Canonical 2/3-letter code, or None when unknown/unmappable."""
    if not subvertical:
        return None
    code = str(subvertical).strip().upper()
    if code in _SUBVERTICAL_NAME:
        return code
    return _EXTENDED_TO_CANONICAL.get(code)


def vertical_relevance(
    platform_id: str,
    subvertical: str | None,
) -> tuple[float, str | None]:
    """(multiplier, reason) — 1.0 in scope / scope-universal / unknown
    subvertical (fail-open, honest); OUT_OF_VERTICAL_RELEVANCE with a
    named reason otherwise."""
    scope = FAMILY_VERTICAL_SCOPE.get(platform_id)
    if not scope:
        return 1.0, None
    code = normalize_subvertical(subvertical)
    if code is None or code in scope:
        return 1.0, None
    reason = (
        f"{_FAMILY_SCOPE_NOTE.get(platform_id, 'the platform is vertical-specific')}; "
        f"the entity's subvertical {code} ({_SUBVERTICAL_NAME.get(code, code)}) "
        "has no lending operation to originate — fit is capped to the "
        "adjacent-use ceiling"
    )
    return OUT_OF_VERTICAL_RELEVANCE, reason
