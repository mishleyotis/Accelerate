"""Tech-stack evidence/subcap linker — shared by ingest + backfill.

Promoted out of `app/scripts/clean_techstack.py` (evidence + subcap
grounding) and `app/scripts/apply_catalogue_platforms.py` (the
product-name → scored-platform keyword map) so the linkage runs AT
INGEST inside `package_persist.persist_package` instead of only via a
hand-run cleanup pass. Before this, `tech_stack_entries.evidence_e_ids`
was ~94% empty and `linked_subcap_ids` ~81% empty across the 94-client
corpus, so the tech drilldown had no grounding.

Three deterministic, idempotent primitives, plus the curated maps:

  - ``link_evidence_for_vendor`` — E-IDs whose excerpt mentions the
    vendor (case-insensitive substring).
  - ``link_subcaps_for_vendor`` — the run's scored subcaps tagged with
    the vendor's platform family, weakest-score-first (the gaps that
    family most addresses).
  - ``apply_platform_tags_for_run`` — promote catalogue platform
    addressability onto this run's ``subcap_scores.platform_tags`` from
    ``ccg_subcaps.l3_platforms`` (the DB form of the workbook "L3
    Platforms" cells that ``apply_catalogue_platforms`` parses). This is
    what lets the subcap link (and D4 platform-fit) resolve at ingest;
    without it ``platform_tags`` stays empty until the post-ingest
    derive chain runs.

The two scripts still import these so the already-ingested corpus
(pre-D3 re-ingest) keeps a single source of truth for the vendor map.
"""
from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Curated banking/fintech vendor → (layer, platform_family|None). The
# platform_family is one of the FIVE scored platforms
# (ncino/salesforce/databricks/tableau/twilio) or None — only those five
# carry subcap `platform_tags`, so a None family yields evidence-only
# linkage (no subcap link). Used both to map a tech entry to its scored
# platform and to mine real tech out of the report prose
# (clean_techstack). Curated + extensible; new aliases must resolve into
# one of the existing five families (no scored platform exists otherwise).
_TECH: dict[str, tuple[str, str | None]] = {
    "Fiserv": ("foundation", None), "Jack Henry": ("foundation", None), "FIS": ("foundation", None),
    "Temenos": ("foundation", None), "Finastra": ("foundation", None), "Alkami": ("application", None),
    "Q2": ("application", None), "nCino": ("application", "ncino"), "MeridianLink": ("application", "ncino"),
    "Encino": ("application", "ncino"), "SimpleNexus": ("application", "ncino"),
    "Salesforce": ("application", "salesforce"), "SFDC": ("application", "salesforce"),
    "Force.com": ("platform", "salesforce"), "MuleSoft": ("platform", "salesforce"),
    "HubSpot": ("application", "salesforce"), "Marketo": ("application", "salesforce"),
    "Pardot": ("application", "salesforce"), "Slack": ("application", "salesforce"),
    "Microsoft Azure": ("platform", None), "AWS": ("platform", None), "Google Cloud": ("platform", None),
    "Snowflake": ("intelligence", "databricks"), "Databricks": ("intelligence", "databricks"),
    "dbt": ("intelligence", "databricks"), "Tableau": ("intelligence", "tableau"),
    "Power BI": ("intelligence", "tableau"), "Looker": ("intelligence", "tableau"),
    "Qlik": ("intelligence", "tableau"), "Twilio": ("application", "twilio"),
    "Segment": ("application", "twilio"), "SendGrid": ("application", "twilio"),
    "ServiceNow": ("application", None), "Workday": ("application", None), "DocuSign": ("application", None),
    "Adobe": ("application", None), "Plaid": ("platform", None), "Zelle": ("application", None),
}

# Deterministic product-name → scored-platform-id keyword map. Names come
# from the catalogue's "L3 Platforms" cells (`ccg_subcaps.l3_platforms`);
# first match wins per token. Salesforce's product family is the broadest,
# so it is checked last.
_PLATFORM_KEYWORDS: list[tuple[str, str]] = [
    ("ncino", "ncino"),
    ("twilio", "twilio"),
    ("tableau", "tableau"),
    ("databricks", "databricks"),
    # Salesforce family — broadest, so checked last.
    ("salesforce", "salesforce"),
    ("sales cloud", "salesforce"),
    ("service cloud", "salesforce"),
    ("marketing cloud", "salesforce"),
    ("data cloud", "salesforce"),
    ("financial services cloud", "salesforce"),
    ("experience cloud", "salesforce"),
    ("mulesoft", "salesforce"),
    ("einstein", "salesforce"),
    ("agentforce", "salesforce"),
    ("crm analytics", "salesforce"),
    ("flow", "salesforce"),
    ("slack", "salesforce"),
]


# The five scored platform families, mirrored VERBATIM from the frontend's
# SCORED_PLATFORM_FAMILIES (TechStackPage / Insights tech-landscape strip) so
# the server-generated ABSENT gap rows (Part 9) and the frontend agree on
# what "family present" means. Presence is a regex over "vendor product" of
# the detected (non-flagged) rows — NOT l3_id, because adjacency mappings
# (e.g. Slack→salesforce) would wrongly suppress a Salesforce gap row.
SCORED_PLATFORM_FAMILIES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("salesforce", "Salesforce",
     re.compile(r"salesforce|mulesoft|tableau crm|marketing cloud|data cloud", re.I)),
    ("databricks", "Databricks", re.compile(r"databricks", re.I)),
    ("tableau", "Tableau", re.compile(r"tableau", re.I)),
    ("twilio", "Twilio", re.compile(r"twilio|segment", re.I)),
    ("ncino", "nCino", re.compile(r"ncino", re.I)),
)

# Default layer + DMA pillar per scored family — used to place the ABSENT
# gap rows on the prototype's layer ladder (Customer engagement families →
# application/P2; data & analytics families → intelligence/P4).
FAMILY_LAYER: dict[str, tuple[str, str]] = {
    "salesforce": ("application", "P2"),
    "ncino": ("application", "P3"),
    "twilio": ("application", "P2"),
    "databricks": ("intelligence", "P4"),
    "tableau": ("intelligence", "P4"),
}


def absent_families(detected_haystack: str) -> list[tuple[str, str]]:
    """Scored families with no regex hit in the detected-stack haystack.

    ``detected_haystack`` is the concatenation of "vendor product" for the
    entity's detected (platform-surface) rows. Returns ``[(family_id,
    display_name), ...]`` — the exact family-absence rule the frontend's
    displacement banner used, now server-side so ABSENT rows are real.
    """
    hay = detected_haystack or ""
    return [(fid, name) for fid, name, rx in SCORED_PLATFORM_FAMILIES
            if not rx.search(hay)]


def family_for_vendor(vendor: str | None) -> str | None:
    """Scored platform family for a tech vendor, or None when unmapped.

    Resolution order: exact key, then substring of a known vendor (so
    "Fiserv Premier" / "Salesforce Inc" resolve — the 2026-06-23 audit found
    these variants missed under the old exact-only lookup), then a product-name
    keyword match (so "Sales Cloud" → salesforce). Substring matching is gated
    to keys ≥5 chars so short keys (FIS / AWS / Q2 / dbt) stay exact-only.
    """
    if not vendor:
        return None
    v = vendor.strip()
    hit = _TECH.get(v)
    if hit:
        return hit[1]
    low = v.lower()
    for key in sorted(_TECH, key=len, reverse=True):
        if len(key) >= 5 and key.lower() in low:
            return _TECH[key][1]
    mapped = map_l3_to_platform([v])
    return mapped[0] if mapped else None


def l3_for_tech(vendor: str | None, product: str | None = None, category: str | None = None) -> str | None:
    """Platform/capability id (`l3_id`) linking a tech entry to one of the five
    scored platform areas — the prototype's tech→platform link. Resolves the
    vendor's family first, then falls back to product/category keyword hits.
    None when the tech doesn't map onto a scored platform.
    """
    fam = family_for_vendor(vendor)
    if fam:
        return fam
    mapped = map_l3_to_platform([product or "", category or ""])
    return mapped[0] if mapped else None


def map_l3_to_platform(l3_names: list[str] | None) -> list[str]:
    """Map catalogue L3 platform names onto the five scored platform ids.

    Order-stable + de-duplicated; unmapped names are dropped.
    """
    out: list[str] = []
    for name in l3_names or []:
        low = (name or "").lower()
        for kw, pid in _PLATFORM_KEYWORDS:
            if kw in low:
                if pid not in out:
                    out.append(pid)
                break
    return out


async def link_evidence_for_vendor(
    session: AsyncSession, *, entity_id: str, vendor: str, limit: int = 5
) -> list[str]:
    """E-IDs for this entity whose excerpt mentions the vendor.

    Blank vendor short-circuits (no query). Mirrors clean_techstack's
    excerpt ILIKE match; evidence_index is already persisted by the time
    persist_package reaches the tech-stack block.
    """
    v = (vendor or "").strip()
    if not v:
        return []
    rows = (await session.execute(
        text(
            "SELECT e_id FROM evidence_index "
            "WHERE entity_id = CAST(:e AS uuid) AND excerpt ILIKE '%'||:v||'%' "
            "LIMIT :lim"
        ),
        {"e": entity_id, "v": v, "lim": limit},
    )).all()
    return [r.e_id for r in rows]


async def link_subcaps_for_vendor(
    session: AsyncSession, *, run_id: str, family: str | None, limit: int = 8
) -> list[str]:
    """The run's scored subcaps tagged with the vendor's platform family.

    Weakest-score-first — the capability gaps the platform family most
    addresses. None/unmapped family short-circuits (no query). Depends on
    `subcap_scores.platform_tags`, which `apply_platform_tags_for_run`
    populates earlier in the same ingest.
    """
    if not family:
        return []
    rows = (await session.execute(
        text(
            "SELECT subcap_id FROM subcap_scores "
            "WHERE run_id = CAST(:rid AS uuid) AND :fam = ANY(platform_tags) "
            "ORDER BY score LIMIT :lim"
        ),
        {"rid": run_id, "fam": family, "lim": limit},
    )).all()
    return [r.subcap_id for r in rows]


async def apply_platform_tags_for_run(
    session: AsyncSession, *, run_id: str, catalog_version: str
) -> int:
    """Promote catalogue platform addressability onto this run's tags.

    DB-native, run-scoped equivalent of
    ``app.scripts.apply_catalogue_platforms`` (which parses the v7.0
    workbooks post-ingest): read the per-subcap L3 platform names from
    ``ccg_subcaps.l3_platforms`` and map them onto the five scored
    platform ids via the shared keyword table, then UPDATE this run's
    ``subcap_scores.platform_tags`` — fill-when-empty only, so any
    package-shipped tags stay authoritative.

    Returns the number of subcap_scores rows tagged.
    """
    rows = (await session.execute(
        text(
            "SELECT subcap_id, l3_platforms FROM ccg_subcaps "
            "WHERE version = :cv AND l3_platforms IS NOT NULL"
        ),
        {"cv": catalog_version},
    )).all()
    updated = 0
    for r in rows:
        pids = map_l3_to_platform(list(r.l3_platforms or []))
        if not pids:
            continue
        res = await session.execute(
            text(
                "UPDATE subcap_scores SET platform_tags = CAST(:pids AS varchar[]) "
                "WHERE run_id = CAST(:rid AS uuid) AND subcap_id = :sid "
                "AND cardinality(platform_tags) = 0"
            ),
            {"pids": pids, "rid": run_id, "sid": r.subcap_id},
        )
        updated += res.rowcount or 0
    return updated
