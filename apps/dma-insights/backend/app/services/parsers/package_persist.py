"""Map a parsed `IngestedPackage` onto the live DB.

Returns the new `runs.id`. Idempotent on `runs.request_id`: a re-upload
of the same package no-ops the run row and refreshes the child tables.

State-branch contract:
  - new entity        → INSERT entities, INSERT firmographics if present
  - existing entity   → UPDATE firmographics.leadership / clay_synced_at
                         only when the package supplied a leadership
                         block (Clay enrichment never gets clobbered by
                         an empty package payload)
  - new run           → INSERT runs row + child tables
  - existing run      → UPDATE run fields; UPSERT child rows; rows present
                         in the DB but absent from the package are kept
                         (we never delete; supersede via a new run)
  - supersede prior   → existing ACTIVE runs for this entity flip to
                         SUPERSEDED with `superseded_by_run_id = new`

Post-persist Pub/Sub publish (`dma.ingest.completed`) state branches —
controlled by `app.services.pubsub_publisher.publish_ingest_completed`:
  - publish_succeeds          → message_id returned; embedder fires
  - publish_fails_topic_missing → log warning, ingest still commits
  - publish_fails_auth_missing  → log warning, ingest still commits
  - publish_disabled_in_dev   → no log spam; ingest still commits
  - publish_timeout           → warn; embedder picks up on nightly sweep
The publish call is fire-and-forget but awaited with a 2-second timeout
so we capture and structured-log publish errors. It runs AFTER the
caller commits — never before — so a publish failure can never leave
an embedder running against an uncommitted row.
"""
from __future__ import annotations

import json
import re
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.package import IngestedPackage
from app.schemas.package import normalize_tier as _normalize_tier
from app.services.alerts_producer import derive_thin_evidence_alerts
from app.services.catalogue_alias_bridge import (
    build_broadcast_rows,
    derive_broadcast_category,
    get_category_children,
)
from app.services.catalogue_resolver import (
    CatalogueResolver,
    ResolvedSubcap,
    SubcapNotFound,
)
from app.services.parsers.firmographics_facts import firmographics_parsed_facts
from app.services.parsers.run_id import compute_assessment_date
from app.services.parsers.section_analysis import (
    strip_template_markers as _strip_markers,
)
from app.services.parsers.tech_linker import (
    apply_platform_tags_for_run,
    family_for_vendor,
    l3_for_tech,
    link_evidence_for_vendor,
    link_subcaps_for_vendor,
)

log = structlog.get_logger()


_SUBVERTICAL_CANONICAL = {
    # The bot/n8n pipeline uses descriptive subvertical labels
    # ("Commercial Lending", "SV1 Regional Banks") instead of the 2-3
    # letter codes we store. We map both forms here.
    "RB": "RB", "RETAIL BANKING": "RB",
    "CU": "CU", "CREDIT UNIONS": "CU", "CREDIT UNION": "CU",
    "CL": "CL", "COMMERCIAL LENDING": "CL",
    "CIB": "CIB", "CORP & INVESTMENT BANKING": "CIB",
    "FC": "FC", "FARM CREDIT": "FC", "FARM CREDIT / AG LENDING": "FC",
    "AM": "AM", "ASSET & WEALTH MANAGEMENT": "AM",
    "RIA": "RIA", "RIA / BROKER-DEALER": "RIA",
    "IC": "IC", "INSURANCE CARRIERS": "IC",
    "IB": "IB", "INSURANCE BROKERAGES": "IB",
    # Legacy SV-codes from the ALMA package — best-effort to RB.
    "SV1 REGIONAL BANKS": "RB",
}


# SV-number framework codes (bot pipeline): observed corpus-wide forms
# include bare "SV2", "SV2 — Credit Unions", "SV2_Credit_Unions",
# "Regional Bank (SV1)", "SV3 - Commercial Lending (Mortgage
# Sub-Servicing variant)". SV5 confirmed = Independent
# RIA/Broker-Dealer (LPL, Pentegra packages).
_SV_NUMBER_CODES = {
    "SV1": "RB", "SV2": "CU", "SV3": "CL", "SV5": "RIA", "SV6": "AM",
    # SV7 confirmed = Insurance Brokers (Alliant section_analysis:
    # "SV7 (Insurance Brokers)").
    "SV7": "IB",
}

# Keyword fallbacks, MOST specific first ("INSURANCE BROKER" must win
# over the generic insurance-carrier match).
_SUBVERTICAL_KEYWORDS = (
    ("CREDIT UNION", "CU"),
    ("INSURANCE BROKER", "IB"),
    ("INSURANCE", "IC"),          # carriers, P&C, mutual
    ("INVESTMENT BANK", "CIB"),
    ("FARM CREDIT", "FC"),
    ("AGRICULTURAL", "FC"),
    ("RIA", "RIA"),
    ("BROKER-DEALER", "RIA"),
    ("BROKER DEALER", "RIA"),
    ("RETIREMENT PLAN", "RIA"),
    ("ASSET MANAGEMENT", "AM"),
    ("WEALTH", "AM"),
    ("COMMERCIAL LEND", "CL"),
    ("CONSUMER LEND", "CL"),
    ("MORTGAGE", "CL"),           # SV3 variants: sub-servicing, IMB, alt-mortgage
    ("LENDING", "CL"),
    ("REGIONAL BANK", "RB"),
    ("RETAIL BANK", "RB"),
    ("COMMUNITY", "RB"),
    ("BANK", "RB"),
)


def _canonical_subvertical(code: str | None, name: str | None) -> str | None:
    """Tolerant raw-label → canonical-code mapper (2026-06-10).

    The old exact-match-only version left 82 of 95 ACTIVE corpus
    entities with a NULL subvertical — every peer-cohort surface
    (D1 peer ticks, D3 peer overlay, peer_benchmarks lookups, RAG
    cohorts) silently rendered empty. The corpus census shows ~40
    spelling variants of 9 subverticals ("SV2 — Credit Unions",
    "Regional Bank (SV1)", "SV2_Credit_Units", "P&C Insurance -
    Mutual", …). Resolution ladder per candidate value:

      1. exact canonical map (legacy behavior, codes win)
      2. embedded SV-number token (SV1/SV2/SV3/SV5/SV6)
      3. keyword containment, most specific first

    Garbage ("TBD - Step 1.4", file paths) matches nothing → None.
    """
    for v in (code, name):
        if v is None:
            continue
        k = v.strip().upper()
        if not k:
            continue
        if k in _SUBVERTICAL_CANONICAL:
            return _SUBVERTICAL_CANONICAL[k]
        # Normalize separators (em/en dashes, underscores) to spaces so
        # "SV2_Credit_Unions" and "SV2 \u2014 Credit Unions" tokenize.
        norm = re.sub(r"[\u2014\u2013_/()-]+", " ", k)  # em/en dash, _, /, (), -
        norm = re.sub(r"\s+", " ", norm).strip()
        # Garbage guards: bot placeholders and leaked file paths.
        if norm.startswith("TBD") or ".JSON" in k or v.count("/") >= 2:
            continue
        if norm in _SUBVERTICAL_CANONICAL:
            return _SUBVERTICAL_CANONICAL[norm]
        m = re.search(r"\bSV(\d+)\b", norm)
        if m and f"SV{m.group(1)}" in _SV_NUMBER_CODES:
            return _SV_NUMBER_CODES[f"SV{m.group(1)}"]
        for kw, code_out in _SUBVERTICAL_KEYWORDS:
            if kw in norm:
                return code_out
    return None


def _evidence_mode_to_canonical(mode: str | None) -> str:
    """Maps raw evidence_mode strings to our DB constraint values.

    Real-world packages emit `RESEARCH_HANDOFF`, `PUBLIC`,
    `PUBLIC/RESEARCH_HANDOFF`, `HYBRID`, `INTERNAL+PUBLIC`, etc.
    Anything mentioning HYBRID or INTERNAL is hybrid; everything else
    falls back to public.
    """
    if not mode:
        return "public"
    upper = mode.upper()
    if "HYBRID" in upper or "INTERNAL" in upper:
        return "hybrid"
    return "public"


def _display_id_for(
    name: str,
    run_id: str,
    drive_folder_id: str | None = None,
) -> str:
    """Derive the canonical entities.display_id (UNIQUE, VARCHAR(32)).

    Identity composition (longest-prefix wins):
      1. ``{name-slug[:24]}-{run_id_alnum[-4:]}``  — normal case (well-
         formed institution_name from the manifest).
      2. ``entity-{drive_folder_hash[:8]}`` — when the institution_name
         is empty/degenerate AND drive_folder_id is set. The folder hash
         is the strongest identity available at this point: two
         distinct Drive folders / two distinct ``local:<dir>`` keys
         always produce distinct salts. The run_id-suffix fallback is
         NOT used here because real packages commonly share a tail of
         ``0001`` (Pentegra DMA-ASM-PENT-...-0001, Penderfund DMA-ASM-
         PFCM-...-0001, etc.) → without the folder salt, every package
         lacking an institution_name collided on ``entity-0001`` and
         cross-attributed runs to the wrong entity (2026-06-07 corpus:
         Pentegra+Virtuity+Penderfund all merged under entity-0001).
      3. ``{base}-0001`` final fallback only when both name and
         drive_folder_id are absent — pre-existing tests pin this.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if slug:
        base = slug[:24]
        suffix_from_run = "".join(c for c in run_id if c.isalnum())[-4:].lower()
        return f"{base}-{suffix_from_run or '0001'}"
    # Degenerate institution_name. Prefer the drive_folder_id hash —
    # the run_id suffix alone is not collision-safe (many packages
    # legitimately end in -0001).
    if drive_folder_id:
        import hashlib
        folder_hash = hashlib.sha1(
            drive_folder_id.encode("utf-8"), usedforsecurity=False,
        ).hexdigest()[:8]
        return f"entity-{folder_hash}"
    suffix_from_run = "".join(c for c in run_id if c.isalnum())[-4:].lower()
    return f"entity-{suffix_from_run or '0001'}"


def _rubric_version_to_catalog(
    rubric: str | None,
    *,
    data_source: str = "MANUAL_BACKFILL",
) -> str:
    """`rubric_version` 5.5 → catalogue version 'v5.5'.

    The package's rubric_version (or skill_version) tells us which v# of
    the capability catalogue the workbook was scored against. We map it
    to the closest stored `ccg_catalog_versions.version`; older versions
    resolve through `ccg_subcap_aliases` at read time.

    Missing-rubric defaults:
      data_source='DRIVE_BACKFILL' → settings.backfill_default_catalogue_version
                                     (typically v5.0 — historical assessments
                                     predate v7.0; mis-mapping them to v7.0
                                     mis-routes every subcap ID through
                                     aliases that don't exist).
      anything else                → settings.catalogue_default_version
                                     (v7.0 — current production catalogue;
                                     used by manual operator uploads,
                                     project API ingest, and the live
                                     Drive crawler for fresh packages).

    See ADR 0005 (catalogue-versioning) + ADR 0013 (two-phase-deploy)
    for the operator-facing contract.
    """
    if not rubric:
        # Lazy import to avoid pulling settings at module import time
        # (some tests instantiate this module without settings env).
        from app.config import get_settings
        settings = get_settings()
        if data_source == "DRIVE_BACKFILL":
            return settings.backfill_default_catalogue_version
        return settings.catalogue_default_version
    s = str(rubric).strip().lower()
    # e.g. "5.5", "v5.5", "dma-assessment v5.5"
    m = re.search(r"v?(\d+\.\d+)", s)
    if m:
        return f"v{m.group(1)}"
    # Last resort: same data-source-aware default as above.
    from app.config import get_settings
    settings = get_settings()
    if data_source == "DRIVE_BACKFILL":
        return settings.backfill_default_catalogue_version
    return settings.catalogue_default_version


def _to_band(score: float) -> str:
    """Score → 5-band canonical label."""
    if score < 1.5:
        return "M1"
    if score < 2.5:
        return "M2"
    if score < 3.5:
        return "M3"
    if score < 4.5:
        return "M4"
    return "M5"


def _severity_to_alert(sev: str) -> str:
    s = (sev or "MEDIUM").upper()
    if s in ("CRITICAL", "S1"):
        return "critical"
    if s in ("HIGH", "MATERIAL", "S2"):
        return "high"
    if s in ("MEDIUM", "S3"):
        return "medium"
    return "low"


def _iso_or_none(raw: str | None):
    if not raw:
        return None
    from datetime import date as _date
    try:
        return _date.fromisoformat(raw)
    except ValueError:
        return None


def issue_register_params(
    run_id, entity_id, issues: list,
) -> list[dict[str, Any]]:
    """Pure param builder for the `issue_register` executemany.

    Contract (2026-07-06 Context defect family):
      - a row whose description is EMPTY is skipped — a blank title can
        never persist (the old path stored 150 blank-titled rows across
        the pack and those junk rows then blocked the derive_issues
        backfill);
      - overlong descriptions get a crafted ≤80-char display title
        (nlp.titlecraft) with the full text preserved in `rationale`;
      - `kind` ('client' | 'assessment_qa'), canonical `status`
        (OPEN/RESOLVED), `opened_on`/`resolved_on` dates, per-cap `caps`
        JSONB and the composed `dma_impact` line all persist so the
        Context register + heatmap overlay can attribute DMA impact;
      - `linked_subcap_ids` keeps only P-code entries (category or
        subcap grain — the heatmap SQL prefix-expands category codes).
    """
    from app.services.parsers.package_csvs import canonical_issue_status

    out: list[dict[str, Any]] = []
    for iss in issues:
        desc = (iss.description or "").strip()
        if not desc:
            continue  # untitleable — never persist a blank title
        if len(desc) <= 200:
            title = desc[:1000]
            rat = iss.cap_formula
        else:
            try:
                from app.services.nlp import make_title
                title = make_title(desc, 80) or desc[:200]
            except Exception:
                title = desc[:200]
            rat = desc if not iss.cap_formula \
                else f"{desc} — {iss.cap_formula}"
        status = canonical_issue_status(getattr(iss, "status", None))
        resolved_on = _iso_or_none(getattr(iss, "resolved_on", None))
        if status is None and resolved_on is not None:
            status = "RESOLVED"
        caps = getattr(iss, "caps", None) or {}
        out.append({
            "rid": run_id, "eid": entity_id,
            "iid": iss.issue_id[:16], "title": title,
            "sev": _severity_to_alert(iss.severity),
            "rat": rat,
            "od": _iso_or_none(getattr(iss, "opened_on", None)),
            "rd": resolved_on,
            "st": status,
            "kind": getattr(iss, "kind", None) or "client",
            "impact": getattr(iss, "dma_impact", None),
            "caps": json.dumps(caps) if caps else None,
            "ls": [
                a for a in iss.affected_categories
                if re.match(r"^P[1-4]C", a)
            ],
            "sp": iss.type,
        })
    return out


_REC_PLATFORM_GUESS = {
    "salesforce": "salesforce",
    "data cloud": "salesforce",
    "fsc": "salesforce",
    "financial services cloud": "salesforce",
    "service cloud": "salesforce",
    "sales cloud": "salesforce",
    "marketing cloud": "salesforce",
    "experience cloud": "salesforce",
    "einstein": "salesforce",
    "agentforce": "salesforce",
    "ncino": "ncino",
    "databricks": "databricks",
    "tableau": "tableau",
    "twilio": "twilio",
    "mulesoft": "salesforce",
}


def _infer_platform_id(title: str, ownership: str | None) -> str | None:
    """Best-effort: scrape the rec title for a known platform keyword.
    Falls back to None — the rec still renders, just without platform
    grouping on D4."""
    t = (title + " " + (ownership or "")).lower()
    for kw, pid in _REC_PLATFORM_GUESS.items():
        if kw in t:
            return pid
    return None


# ── analyst-recommendation-driven fit fields (2026-07-15 rework) ──────────
# The fit engine now reads the analyst's recommendations directly. These
# helpers normalise the fields it scores on (priority, integration effort)
# from the recommendation prose, which is why the values must be computed at
# ingest and persisted (migration 062).

def _priority_rank(priority: str | None) -> int | None:
    """Normalise the analyst's free-text priority to a sortable rank where
    LOWER = more urgent (leads the sequence). The corpus mixes P0/P1…,
    CRITICAL/HIGH/MEDIUM/LOW, NOW/URGENT, and bare 1-7 ranks."""
    s = str(priority or "").strip().upper()
    if not s:
        return None
    if "IMMEDIATE" in s or "URGENT" in s or re.search(r"\bNOW\b", s):
        return 0
    m = re.search(r"\bP(\d)\b", s)          # P0..P9
    if m:
        return int(m.group(1))
    if "CRITICAL" in s:
        return 0
    if "HIGH" in s:
        return 1
    if "MEDIUM" in s or "MODERATE" in s:
        return 3
    if "LOW" in s:
        return 5
    m = re.match(r"(\d{1,2})\b", s)         # bare "1".."13" rank
    if m:
        return min(int(m.group(1)), 9)
    return None


# External systems a Zennify solution must integrate with — the presence +
# count of these is the integration-effort signal. Named, so the card can
# surface WHICH systems (not just a band).
_INTEGRATION_SYSTEMS: tuple[tuple[str, str], ...] = (
    (r"\bfis\b|codeconnect", "FIS"), (r"\bfiserv\b", "Fiserv"),
    (r"\bjack henry\b|symitar|silverlake", "Jack Henry"), (r"\bncr\b", "NCR"),
    (r"\bhubspot\b", "HubSpot"), (r"\bsnowflake\b", "Snowflake"),
    (r"\bazure\b", "Azure"), (r"\baws\b", "AWS"), (r"\bgoogle cloud\b|\bgcp\b", "GCP"),
    (r"\bcetera\b", "Cetera"), (r"\bzoominfo\b", "ZoomInfo"),
    (r"\bworkday\b", "Workday"), (r"\bsap\b", "SAP"), (r"\boracle\b", "Oracle"),
    (r"open banking|\bapi\b|integration layer|middleware", "APIs / open banking"),
    (r"\bdna\b|core banking|\bcore\b system|servicing core", "core banking"),
    (r"data warehouse|data lake|lakehouse", "data warehouse/lake"),
    (r"\bmulesoft\b|anypoint", "MuleSoft"),
)


def _extract_integration_systems(*texts: str | None) -> list[str]:
    """Named external systems the recommendation must integrate with, deduped
    + order-preserved. Drives the integration-effort factor + the card's
    'integrates with …' line."""
    blob = " ".join(t for t in texts if t)
    if not blob.strip():
        return []
    out: list[str] = []
    for pat, name in _INTEGRATION_SYSTEMS:
        if re.search(pat, blob, re.I) and name not in out:
            out.append(name)
    return out


def _effort_band(n_systems: int, has_prereqs: bool) -> str:
    """Coarse integration-effort band from the count of external systems + a
    sequencing prerequisite. HIGH effort is a headwind the fit engine discounts
    (a lower-effort quick win can lead), and the band renders on the card."""
    score = n_systems + (1 if has_prereqs else 0)
    if score >= 3:
        return "HIGH"
    if score >= 1:
        return "MEDIUM"
    return "LOW"


def _rec_strategic_objectives(rec: Any) -> list[str]:
    """The client strategic objectives a rec serves (SO-alignment factor).
    Structured field when present; else None. Cleaned of E-ID/marker noise."""
    sos = getattr(rec, "strategic_objectives", None) or []
    out: list[str] = []
    for so in sos:
        s = re.sub(r"\s*\[E-[^\]]*\]", "", str(so)).strip()
        if s:
            out.append(s[:160])
    return out[:6]


def _rec_evidence_ids(rec: Any) -> list[str]:
    """Grounding E-IDs for a rec (evidence-strength factor). Prefers the
    structured root_cause.evidence_ids; falls back to E-IDs mined from the
    root_cause prose."""
    rc = rec.root_cause or {}
    ids = list(rc.get("evidence_ids") or [])
    if not ids:
        prose = " ".join(str(rc.get(k, "")) for k in
                         ("evidence_detail", "gap_description", "proof_of_gap"))
        ids = re.findall(r"\bE-\d{2,}\b", prose)
    # dedup order-preserved
    return list(dict.fromkeys(str(x) for x in ids if x))[:12]


def _rec_description(rec: Any) -> str:
    """Compose a description from the rich rec structure.

    Three observed shapes:
      - Alma canonical (recommendations_detail.json):
            root_cause.gap_description, solution.description
      - Odlum variant (recommendations_register.json):
            root_cause.finding (no solution.description; top-level
            zennify_solution / zennify_alignment fields)
      - DOCX-extracted (report_recommendations.py):
            root_cause.gap_description (mapped from `[ROOT CAUSE]`
            sub-block prose), solution.description
    Tolerant of all three so the persisted description column carries
    real content for every real-fixture rec, not just Alma + DOCX.
    """
    parts: list[str] = []
    rc = rec.root_cause or {}
    # Try `gap_description` first (Alma + DOCX), fall back to `finding`
    # (Odlum variant). Both carry the same intent.
    root_text = rc.get("gap_description") or rc.get("finding")
    if root_text:
        parts.append(root_text)
    sol = rec.solution or {}
    sol_text = sol.get("description")
    if sol_text:
        parts.append(sol_text)
    # Odlum-variant: top-level `zennify_solution` carries the solution
    # statement when `solution.description` is absent. Use getattr +
    # `model_dump()` fallback so the Pydantic `extra='allow'` fields
    # are reachable.
    if not sol_text:
        # `RecommendationRow.model_dump()` surfaces `extra='allow'` fields;
        # `getattr` works for declared fields but not for extras in
        # Pydantic v2.
        extras = (
            rec.model_dump() if hasattr(rec, "model_dump") else {}
        )
        zs = extras.get("zennify_solution")
        if isinstance(zs, str) and zs:
            parts.append(zs)
        elif isinstance(zs, dict):
            zs_text = zs.get("description") or zs.get("text")
            if zs_text:
                parts.append(zs_text)
    if rec.cross_pillar_unlock:
        parts.append(f"Cross-pillar unlock: {rec.cross_pillar_unlock}")
    return "\n\n".join(parts) or rec.title


def _layer_for_tech(category: str | None) -> str:
    """Best-effort: map a tech category onto one of our 4 layers. The keyword
    table was widened (2026-06-23) past the Explorium vocabulary to the
    category names real packages actually use, so fewer entries fall through to
    the 'application' catch-all."""
    cat = (category or "").lower()
    if any(k in cat for k in (
        "infra", "cloud", "compute", "database", "storage", "network",
        "data lake", "data warehouse", "warehouse", "lakehouse", "hosting",
        "on-prem", "on prem", "server", "core system",
    )):
        return "foundation"
    if any(k in cat for k in (
        "platform", "core banking", "crm", "loan origination", "origination",
        "integration", "api", "middleware", "esb", "ipaas", "servicing",
        "digital banking", "banking platform", "lending",
    )):
        return "platform"
    if any(k in cat for k in (
        "ai", "analytics", "ml", "intelligence", "data science", "bi ",
        "business intelligence", "reporting", "model", "genai", "llm",
        "personalization", "data platform",
    )):
        return "intelligence"
    return "application"


_PILLAR_FALLBACK_NAMES = {
    "P1": "Strategic Posture & Governance",
    "P2": "Customer Engagement",
    "P3": "Operational Excellence",
    "P4": "Data & Technology Foundation",
}


def _pillar_from_subcap(subcap_id: str) -> str | None:
    """Extract the pillar prefix (P1..P4) from a subcap_id like 'P1C1.1.1'."""
    m = re.match(r"^(P[1-4])", subcap_id)
    return m.group(1) if m else None


def _category_from_subcap(subcap_id: str) -> str | None:
    """Extract the category prefix (P1C1) from a subcap_id like 'P1C1.1.1'."""
    m = re.match(r"^(P[1-4]C\d+)", subcap_id)
    return m.group(1) if m else None


def _l1_from_subcap(subcap_id: str) -> str | None:
    """Extract the L1 capability prefix (P1C1.1) from a subcap_id like
    'P1C1.1.1'. Strips any trailing :T<n> tier suffix that some workbooks
    emit (e.g. 'P1C1.1.1:T2')."""
    s = re.sub(r":?[Tt]\d+$", "", subcap_id)
    m = re.match(r"^(P[1-4]C\d+\.\d+)", s)
    return m.group(1) if m else None


async def _bootstrap_catalogue_from_workbook(
    session: AsyncSession,
    *,
    catalog_version: str,
    parsed_subcap_ids: set[str],
    pkg: Any,
    warnings: list[str],
) -> int:
    """Seed `ccg_subcaps` + parent FK rows from the scoring workbook
    taxonomy itself, so the catalogue resolver can serve subcaps without
    a separate `ccg_loader` run.

    Operator mandate (2026-06): "No v5 catalogue will be uploaded. Just
    use the scoring toolkits that are there during the backfill. No
    error message." Each row in the scoring workbook *is* the canonical
    declaration of a subcap for that catalogue version — we mirror it
    into ccg_subcaps so the resolver returns ResolvedSubcap on the
    first pass and the run stays ACTIVE end-to-end with no manual
    catalogue-loader step.

    Insert order is parent-first to satisfy the composite FK chain:
      ccg_catalog_versions  (exists; stub row inserted earlier)
      → ccg_pillars         (one per pillar prefix referenced)
      → ccg_categories      (one per category prefix referenced)
      → ccg_l1_capabilities (one per L1 prefix referenced)
      → ccg_subcaps         (one per subcap_id)

    Names + descriptions are derived from `pkg.pillar_scores`,
    `pkg.category_scores`, and the subcap_score `rationale` when
    available; fall back to deterministic placeholders so all NOT NULL
    columns satisfy. Idempotent — every INSERT carries
    `ON CONFLICT DO NOTHING`, so re-ingest of the same package + a
    parallel real `ccg_loader` run can coexist.

    Returns the count of `ccg_subcaps` rows actually inserted (zero
    when every row already existed).
    """
    # ── Build name lookups from the package's own pillar/category rows ──
    pillar_names: dict[str, str] = dict(_PILLAR_FALLBACK_NAMES)
    for ps in (pkg.pillar_scores or []):
        if ps.pillar_id and ps.pillar_name:
            pillar_names[ps.pillar_id] = ps.pillar_name

    category_names: dict[str, str] = {}
    category_pillar: dict[str, str] = {}
    for cs in (pkg.category_scores or []):
        if cs.category_id:
            category_names[cs.category_id] = cs.category_name or cs.category_id
            category_pillar[cs.category_id] = cs.pillar_id or _pillar_from_subcap(cs.category_id) or ""

    subcap_rationales: dict[str, str] = {}
    subcap_names: dict[str, str] = {}
    for sc in (pkg.subcap_scores or []):
        if sc.subcap_id:
            if sc.rationale:
                subcap_rationales[sc.subcap_id] = sc.rationale
            # `name` is supplied by the scoring workbook's SubCap_Name
            # column when present (WSFS shape, all real packages from
            # 2026-05 onwards). When absent (ALMA-shape CSV without
            # SubCap_Name), we fall back to a placeholder so downstream
            # FE drawer copy stays sane even without the name.
            if getattr(sc, "name", None):
                subcap_names[sc.subcap_id] = sc.name

    # Derive L1 names from the workbook subcap names when possible —
    # the L1 prefix groups N subcaps; we take the most common shared
    # prefix of their names as the L1 capability name when ≥2 children
    # share a recognizable prefix. Otherwise fall back to "Capability
    # {l1_id}". Idempotent — re-ingest picks the same name.
    from collections import Counter

    def _common_prefix(names: list[str]) -> str | None:
        if not names:
            return None
        # Strip trailing parens, dashes, document/strategy/policy/etc.
        # to find a stable shared root.
        words: list[list[str]] = []
        for n in names:
            n = re.sub(r"\s*\(.*?\)\s*$", "", n)
            tokens = [t for t in re.split(r"[\s/]+", n.strip()) if t]
            if tokens:
                words.append(tokens)
        if len(words) < 2:
            return None
        common: list[str] = []
        for cols in zip(*words, strict=False):
            if len(set(cols)) == 1:
                common.append(cols[0])
            else:
                break
        if not common:
            # Fall back to the first 2 tokens of the longest-name child —
            # provides a sane "Customer Engagement", "Data Foundation"
            # style label.
            longest = max(names, key=len)
            tokens = [t for t in re.split(r"\s+", longest) if t]
            return " ".join(tokens[:3]) if tokens else None
        return " ".join(common)

    l1_to_subcaps: dict[str, list[str]] = {}
    for sid in parsed_subcap_ids:
        l1 = _l1_from_subcap(sid)
        if l1:
            l1_to_subcaps.setdefault(l1, []).append(sid)
    l1_names: dict[str, str] = {}
    for l1, sids in l1_to_subcaps.items():
        child_names = [subcap_names[s] for s in sids if s in subcap_names]
        prefix = _common_prefix(child_names)
        if prefix and len(prefix) > 3:
            l1_names[l1] = prefix
    # Suppress unused-import lint
    _ = Counter

    # ── Collect prefixes referenced by the parsed subcap_ids ────────────
    pillar_refs: set[str] = set()
    category_refs: set[tuple[str, str]] = set()   # (category_id, pillar_id)
    l1_refs: set[tuple[str, str]] = set()         # (l1_id, category_id)
    subcap_specs: list[tuple[str, str]] = []      # (subcap_id, l1_id)

    for sid in parsed_subcap_ids:
        pillar = _pillar_from_subcap(sid)
        cat = _category_from_subcap(sid)
        l1 = _l1_from_subcap(sid)
        if not pillar or not cat or not l1:
            # Subcap_id doesn't conform to the P{n}C{m}.{p}.{q} convention —
            # skip; the resolver will return SubcapNotFound, the unresolved
            # counter will tick, but we don't fabricate a row from a
            # malformed ID.
            continue
        pillar_refs.add(pillar)
        category_refs.add((cat, pillar))
        l1_refs.add((l1, cat))
        subcap_specs.append((sid, l1))

    if not subcap_specs:
        return 0

    # Batched (Part 12.4): the four parent-first upsert loops collapse to
    # one executemany per level (~700 fewer round-trips per bootstrap);
    # ON CONFLICT semantics unchanged.
    # ── Pillars ─────────────────────────────────────────────────────────
    _pillar_rows = [
        {
            "v": catalog_version,
            "pid": pillar,
            "n": pillar_names.get(pillar, f"Pillar {pillar[-1]}"),
            "d": (
                f"Auto-bootstrapped from scoring workbook for "
                f"{catalog_version}. Replace with curated copy when "
                f"ccg_loader runs for this version."
            ),
        }
        for pillar in sorted(pillar_refs)
    ]
    if _pillar_rows:
        await session.execute(
            text(
                """
                INSERT INTO ccg_pillars (
                    version, pillar_id, name, description,
                    category_count, l1_capability_count, subcap_count
                ) VALUES (
                    :v, :pid, :n, :d, 0, 0, 0
                )
                ON CONFLICT (version, pillar_id) DO NOTHING
                """
            ),
            _pillar_rows,
        )

    # ── Categories ──────────────────────────────────────────────────────
    _cat_rows = [
        {
            "v": catalog_version,
            "cid": cat,
            "pid": category_pillar.get(cat) or pillar,
            "n": category_names.get(cat) or f"Category {cat}",
        }
        for cat, pillar in sorted(category_refs)
    ]
    if _cat_rows:
        await session.execute(
            text(
                """
                INSERT INTO ccg_categories (
                    version, category_id, pillar_id, name
                ) VALUES (
                    :v, :cid, :pid, :n
                )
                ON CONFLICT (version, category_id) DO NOTHING
                """
            ),
            _cat_rows,
        )

    # ── L1 capabilities ─────────────────────────────────────────────────
    _l1_rows = [
        {
            "v": catalog_version,
            "lid": l1,
            "cid": cat,
            # Prefer the workbook-derived L1 name (common prefix
            # across child subcap names) so the FE drawer shows
            # "Customer Servicing" instead of "Capability P2C1.1".
            "n": l1_names.get(l1) or f"Capability {l1}",
        }
        for l1, cat in sorted(l1_refs)
    ]
    if _l1_rows:
        await session.execute(
            text(
                """
                INSERT INTO ccg_l1_capabilities (
                    version, l1_id, category_id, name
                ) VALUES (
                    :v, :lid, :cid, :n
                )
                ON CONFLICT (version, l1_id) DO NOTHING
                """
            ),
            _l1_rows,
        )

    # ── Subcaps ─────────────────────────────────────────────────────────
    # Single multi-row INSERT via jsonb_to_recordset so `rowcount` still
    # reports how many rows were ACTUALLY inserted (the executemany API
    # can't aggregate per-bind rowcounts). subcap_specs derive from a
    # set, so no intra-statement conflict is possible.
    _subcap_rows = []
    for sid, l1 in subcap_specs:
        rationale = subcap_rationales.get(sid) or ""
        description = (
            (rationale[:512] + ("…" if len(rationale) > 512 else ""))
            if rationale
            else f"Auto-bootstrapped from scoring workbook for {catalog_version}."
        )
        # Prefer the workbook's SubCap_Name ("Digital Strategy Document",
        # "Audience Segmentation") over the placeholder. The Salesforce
        # AE-facing FE chips show this verbatim.
        subcap_name = subcap_names.get(sid) or f"Subcap {sid}"
        _subcap_rows.append({
            "sid": sid,
            "lid": l1,
            "n": subcap_name[:255],
            "d": description,
        })
    inserted = 0
    if _subcap_rows:
        result = await session.execute(
            text(
                """
                INSERT INTO ccg_subcaps (
                    version, subcap_id, l1_id, name, description,
                    solution_type, tier, zennify_status
                )
                SELECT :v, r.sid, r.lid, r.n, r.d,
                       'Traditional', 'Core', 'Active'
                FROM jsonb_to_recordset(CAST(:rows AS JSONB))
                     AS r(sid text, lid text, n text, d text)
                ON CONFLICT (version, subcap_id) DO NOTHING
                """
            ),
            {
                "v": catalog_version,
                "rows": json.dumps(_subcap_rows),
            },
        )
        inserted = max(0, int(result.rowcount or 0))

    return inserted


async def persist_package(
    session: AsyncSession, pkg: IngestedPackage,
    *, requester_user_id: str | None = None,
    data_source: str = "MANUAL_BACKFILL",
    drive_folder_id: str | None = None,
    skip_tables: set[str] | None = None,
) -> tuple[str, list[str]]:
    """Persist the package; returns (run_id, warnings). Caller commits.

    `data_source` flags the provenance of the run for the Runs page
    badge and forensics. Common values:
      - `MANUAL_BACKFILL` (default) — admin uploaded the zip
      - `DRIVE_BACKFILL` — `historical_backfill.py` pulled it from
        the Drive folder
      - `DRIVE_CRAWLER` — the periodic crawler picked up a new file
      - `PROJECT_API` — the Claude project posted to /ingest/assessment

    `drive_folder_id` (optional) — the source Drive folder ID, stored
    on `runs.drive_folder_id` so re-runs can dedup by folder.

    `skip_tables` (optional) — Batch 2 selective re-ingest. When
    supplied, the named tables are NOT re-persisted; only the tables
    derived from changed artifacts (per
    ``app.services.artifact_manifest.affected_tables``) re-fire. Used
    by the local + Drive backfill paths to honor the operator
    mandate: "A reingest should strictly be for the changed artifact
    ... If it was a cosmetic change, this can just be dropped."

    Always-on tables that ignore ``skip_tables`` (because they're
    needed for cascading state correctness):
      - `entities` (always upsert to refresh updated_at)
      - `runs` (the run row is the anchor for everything downstream)
      - `ccg_catalog_versions` (FK target stub) and
        `ccg_subcaps_bootstrap` (auto-bootstrap) — both are gated by
        whether the workbook supplied subcaps, NOT by skip_tables.

    Default behaviour (``skip_tables=None``) is identical to pre-Batch
    2: re-persist everything in the package.
    """
    warnings: list[str] = list(pkg.parser_warnings)
    # Defensive: callers may pass a frozenset / None; normalize.
    skip_tables = set() if skip_tables is None else set(skip_tables)

    def _should_persist(table: str) -> bool:
        """Selective re-ingest gate. Tables in ``skip_tables`` skip;
        all others persist as before."""
        return table not in skip_tables

    rm = pkg.run_manifest
    subvertical = _canonical_subvertical(rm.subvertical_code, rm.subvertical_name)
    # Final ladder rung (2026-06-10): when neither the manifest nor the
    # report artifacts carry a mappable subvertical, infer it from the
    # institution NAME — "Hudson Valley Credit Union" / "Sunflower
    # Bank, N.A." / "Farm Credit Mid-America" are unambiguous, and a
    # NULL here blanks every peer-cohort surface. Validated on the full
    # corpus remainder: 10 precise resolutions, ambiguous names
    # (Bridgecrest, TII, Payments Canada, ...) stay honestly NULL.
    if subvertical is None and (rm.institution_name or "").strip():
        subvertical = _canonical_subvertical(None, rm.institution_name)
        if subvertical:
            warnings.append(
                f"subvertical_inferred_from_name:{subvertical}"
            )
    catalog_version = _rubric_version_to_catalog(
        rm.rubric_version or rm.skill_version,
        data_source=data_source,
    )
    evidence_mode = _evidence_mode_to_canonical(rm.evidence_mode)

    # ── Entity upsert ───────────────────────────────────────────────────
    # `drive_folder_id` is persisted on the entity row (UNIQUE index per
    # migration 003) so subsequent backfill runs can detect "I already
    # ingested this Drive folder" without re-parsing every artifact.
    #
    # 2026-05-29 audit fix: prior code keyed solely on display_id
    # (derived from institution_name + run_id). The same Drive folder
    # could land twice as two SEPARATE entities — one per ingest cycle
    # — fragmenting the customer's run history across two rows. The
    # _display_id_for() salt includes the run_id suffix, so even
    # ON CONFLICT (display_id) wouldn't catch a re-ingest with a fresh
    # request_id.
    #
    # New logic: when drive_folder_id is non-empty, FIRST look up
    # existing entities by drive_folder_id (FOR UPDATE to serialize
    # concurrent backfills). If found, reuse that entity_id +
    # display_id; new run rows still go under the existing entity.
    # Only when no drive_folder_id match exists do we fall back to
    # the display_id-based upsert.
    #
    # 2026-06 concurrency hardening: when ingesting 100+ files
    # concurrently, the prior code had a race between the SELECT FOR
    # UPDATE (no row matches → both transactions get NULL) and the
    # subsequent INSERT (both attempt to add the same drive_folder_id
    # → second hits the partial unique index → IntegrityError aborts
    # the whole ingest). We take a transaction-scoped advisory lock
    # keyed on hash(drive_folder_id) BEFORE the lookup so two
    # concurrent ingests for the same folder serialize through entity
    # upsert. Different folders proceed in parallel. The lock is
    # auto-released at COMMIT / ROLLBACK.
    display_id = _display_id_for(
        rm.institution_name, rm.run_id, drive_folder_id=drive_folder_id,
    )
    # Institution-name sanity gate (2026-06-10): a junk resolved name
    # (raw Drive folder ID, "… DMA Engagement FINAL", bare fragment)
    # must never become an AE-visible directory card. Scored content is
    # still persisted, but the entity is parked in the migration-038
    # PENDING_REVIEW admin queue until an admin confirms/fixes the name.
    from app.services.entity_name_sanity import check_institution_name
    name_junk, name_junk_reason = check_institution_name(rm.institution_name)
    if name_junk:
        warnings.append(
            f"institution_name_junk:{name_junk_reason} — entity parked "
            f"in PENDING_REVIEW (admin queue)"
        )
    entity_status = "PENDING_REVIEW" if name_junk else "ACTIVE"
    inferred_src = (
        f"institution_name {rm.institution_name!r} failed sanity "
        f"({name_junk_reason}); folder={drive_folder_id or '(none)'}"
        if name_junk else None
    )
    entity_id = None
    if drive_folder_id:
        # pg_advisory_xact_lock takes a bigint; hash the drive_folder_id
        # string into a 63-bit positive int via hashtext (PG built-in).
        await session.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtext(:dfid)::bigint)"
            ),
            {"dfid": f"dma_entity_upsert:{drive_folder_id}"},
        )
        existing = (await session.execute(
            text(
                "SELECT id, name FROM entities "
                "WHERE drive_folder_id = :dfid FOR UPDATE"
            ),
            {"dfid": drive_folder_id},
        )).first()
        if existing is not None:
            entity_id = existing.id
            # Keep entity metadata fresh — institution name + subvertical
            # may have been corrected since the last backfill. A JUNK
            # incoming name must never clobber a clean existing one
            # (e.g. an admin-corrected name); a CLEAN incoming name may
            # replace a junk one (status transition stays admin-driven).
            existing_junk, _ = check_institution_name(existing.name)
            keep_incoming_name = (not name_junk) or existing_junk
            await session.execute(
                text(
                    "UPDATE entities SET "
                    "    name = CASE WHEN CAST(:keep AS BOOLEAN) THEN :name ELSE name END, "
                    "    subvertical = COALESCE(:sv, subvertical), "
                    "    updated_at = NOW() "
                    "WHERE id = :id"
                ),
                {
                    "name": rm.institution_name,
                    "keep": keep_incoming_name,
                    "sv": subvertical,
                    "id": entity_id,
                },
            )
    if entity_id is None:
        # ON CONFLICT keeps the EXISTING status — a junk re-ingest must
        # never flip an ACTIVE entity to PENDING_REVIEW, and an admin's
        # PENDING_REVIEW→ACTIVE confirm is never undone by a backfill.
        entity_row = (await session.execute(
            text("""
                INSERT INTO entities (name, display_id, subvertical, status,
                                      drive_folder_id, inferred_from_source,
                                      inferred_at)
                VALUES (:name, :did, :sv, :status, :dfid, CAST(:inf_src AS TEXT),
                        CASE WHEN CAST(:inf_src AS TEXT) IS NULL
                             THEN NULL ELSE NOW() END)
                ON CONFLICT (display_id) DO UPDATE
                SET name = CASE WHEN CAST(:keep_name AS BOOLEAN) THEN EXCLUDED.name
                                ELSE entities.name END,
                    subvertical = COALESCE(EXCLUDED.subvertical, entities.subvertical),
                    drive_folder_id = COALESCE(EXCLUDED.drive_folder_id, entities.drive_folder_id),
                    updated_at = NOW()
                RETURNING id
            """),
            {
                "name": rm.institution_name, "did": display_id,
                "sv": subvertical, "dfid": drive_folder_id,
                "status": entity_status, "inf_src": inferred_src,
                "keep_name": not name_junk,
            },
        )).first()
        assert entity_row is not None
        entity_id = entity_row.id

    # ── Firmographics (don't clobber Clay-enriched leadership) ─────────
    # Selective-reingest gate (Batch 2): UPDATE-only block (the
    # firmographics row is created lazily). Skip when client_profile
    # / 00_parameters didn't change in the diff.
    if pkg.firmographics is not None and not _should_persist("firmographics"):
        warnings.append("selective_reingest_skip:firmographics")
    if pkg.firmographics is not None and _should_persist("firmographics"):
        f = pkg.firmographics
        leadership_blob = (
            [p.model_dump() for p in f.leadership] if f.leadership else None
        )
        # leadership is JSONB; asyncpg requires a string (see the
        # comment + identical pattern around line 426 for top_findings).
        # Pre-serialize + CAST AS JSONB sidesteps the "'list' object has
        # no attribute 'encode'" DataError that the raw list hit when
        # the AlmaBank fixture replayed through the live `/ingest/package`
        # endpoint (2026-06 deployment QA).
        ldr_json = json.dumps(leadership_blob) if leadership_blob is not None else None

        # 2026-06-06 Batch 6 (migration 027): pack the parser-extracted
        # string-form firmographics into parsed_facts JSONB. Pydantic
        # `model_dump()` surfaces both declared and `extra='allow'`
        # fields. Rather than a brittle hardcoded key allowlist (which
        # silently dropped every NEW extra the parsers learned to emit —
        # e.g. the flat financial_baseline.json fields total_deposits /
        # roe / efficiency_ratio / net_income / sub_vertical), we persist
        # EVERYTHING that lacks a dedicated column, so future parser
        # extras survive ingest automatically. Fields with their own
        # column (or special handling) are excluded to avoid duplication.
        firm_dict = f.model_dump()
        parsed_facts = firmographics_parsed_facts(firm_dict)
        parsed_facts_json = json.dumps(parsed_facts) if parsed_facts else None

        # F5c (2026-06-07): narrative_md is the analyst-prose paragraph
        # from `04_reports/*_Client_Profile_Research_Report.docx` (Entity
        # Profile section). Migration 018 added the TEXT column. We use
        # `COALESCE(EXCLUDED.narrative_md, firmographics.narrative_md)`
        # so a re-ingest with a missing narrative won't clobber an
        # earlier-stored value, and re-ingest with a fresh narrative
        # will update.
        narrative_md = getattr(f, "narrative_md", None) or None
        # D5: multi-year financial series + sentiment grid. COALESCE so a
        # parse that lacks them never clobbers Clay-synced sentiment, and the
        # parser fills them when Clay hasn't.
        fh_blob = getattr(f, "financial_highlights", None) or None
        fh_json = json.dumps(fh_blob) if fh_blob else None
        sent_blob = getattr(f, "sentiment", None) or None
        sent_json = json.dumps(sent_blob) if sent_blob else None

        await session.execute(
            text("""
                INSERT INTO firmographics (
                    entity_id, primary_regulator, leadership, hq_address,
                    parsed_facts, narrative_md, financial_highlights, sentiment
                ) VALUES (
                    :eid, :reg, CAST(:ldr AS JSONB), :hq,
                    CAST(:pf AS JSONB), :narrative,
                    -- financial_highlights is NOT NULL DEFAULT '{}'; a parse
                    -- that lacks it must coalesce to '{}' on the INSERT path
                    -- (passing NULL overrides the default + aborts the ingest).
                    COALESCE(CAST(:fh AS JSONB), '{}'::jsonb),
                    CAST(:sent AS JSONB)
                )
                ON CONFLICT (entity_id) DO UPDATE
                SET primary_regulator = COALESCE(EXCLUDED.primary_regulator,
                                                  firmographics.primary_regulator),
                    leadership = COALESCE(EXCLUDED.leadership, firmographics.leadership),
                    hq_address = COALESCE(EXCLUDED.hq_address, firmographics.hq_address),
                    parsed_facts = COALESCE(EXCLUDED.parsed_facts, firmographics.parsed_facts),
                    narrative_md = COALESCE(EXCLUDED.narrative_md, firmographics.narrative_md),
                    -- Only overwrite when the new parse actually carries data:
                    -- an empty '{}' must NOT clobber a prior populated/Clay-synced
                    -- value (mirrors the COALESCE no-clobber intent of the others).
                    financial_highlights = CASE
                        WHEN EXCLUDED.financial_highlights <> '{}'::jsonb
                            THEN EXCLUDED.financial_highlights
                        ELSE firmographics.financial_highlights
                    END,
                    sentiment = COALESCE(EXCLUDED.sentiment, firmographics.sentiment),
                    updated_at = NOW()
            """),
            {
                "eid": entity_id,
                # 2026-06-07 corpus: `primary_regulator` is VARCHAR(64).
                # The C9 entity_profile parser can extract long values
                # (e.g. Amalgamated / Kitsap ship a multi-agency
                # regulator string) that overflow the column ->
                # StringDataRightTruncation aborts the whole ingest.
                # Defensive-truncate (hq_address is TEXT, no cap needed).
                "reg": (
                    (f.primary_regulator or "")[:64] or None
                    if f.primary_regulator else None
                ),
                "ldr": ldr_json,
                "hq": f.hq,
                "pf": parsed_facts_json,
                "narrative": narrative_md,
                "fh": fh_json,
                "sent": sent_json,
            },
        )

    # ── D5 Context timeline events (entity-level, derived from facts) ───
    # facts_extractor classified dated evidence facts into timeline events.
    # Idempotent: clear this entity's parser-sourced events (e_id IS NOT
    # NULL) then re-insert. Clay/manual events (e_id NULL) are preserved.
    # Scoped to the `evidence` selective-reingest gate since the events are
    # derived from the same 01_evidence artifacts.
    if _should_persist("evidence"):
        await session.execute(
            text(
                "DELETE FROM timeline_events "
                "WHERE entity_id = :eid AND e_id IS NOT NULL"
            ),
            {"eid": entity_id},
        )
        # 2026-07-02 D5 (Part 8.2): column list extended with the migration-047
        # NLP fields (signal / date_precision / evidence_e_ids / subcap_ids)
        # emitted by facts_extractor + client_profile. getattr defaults keep
        # legacy TimelineEventCandidate producers valid.
        # Batched (Part 12.4): one executemany instead of one round-trip
        # per event; bind order == prior loop order, semantics identical.
        _tev_rows = [
            {
                "eid": entity_id,
                "event_date": tev.event_date,
                "kind": tev.kind[:32],
                "title": tev.title,
                "body": tev.body,
                "url": tev.source_url,
                "e_id": (tev.e_id or "")[:16] or None,
                "signal": (getattr(tev, "signal", None) or "")[:10] or None,
                "date_precision": (
                    (getattr(tev, "date_precision", None) or "")[:20] or None
                ),
                "evidence_e_ids": list(getattr(tev, "evidence_e_ids", None) or []),
                "subcap_ids": list(getattr(tev, "subcap_ids", None) or []),
            }
            for tev in pkg.timeline_events
        ]
        if _tev_rows:
            await session.execute(
                text(
                    """
                    INSERT INTO timeline_events
                        (entity_id, event_date, kind, title, body, source_url,
                         e_id, signal, date_precision, evidence_e_ids, subcap_ids)
                    VALUES (:eid, :event_date, :kind, :title, :body, :url,
                            :e_id, :signal, :date_precision, :evidence_e_ids,
                            :subcap_ids)
                    """
                ),
                _tev_rows,
            )
        if pkg.timeline_events:
            warnings.append(
                f"timeline_events_persisted: {len(pkg.timeline_events)}"
            )

    # ── Run upsert (idempotent on request_id) ──────────────────────────
    # The overall score is recoverable from runs↔subcap_scores at query
    # time; we don't store a denormalized copy on the run row.
    scqa_blob = None  # full SCQA still lives in the DOCX; pkg ingest stores none
    top_findings = [
        {
            "subcap_id": cs.category_id,
            "name": cs.category_name,
            "score": cs.score,
            "peer_median": cs.peer_median,
        }
        for cs in pkg.category_scores
        if cs.peer_median is not None and cs.score - cs.peer_median <= -0.5
    ][:5]
    # Why-now signals (2026-06-10): derive from the package's own DATED
    # timeline events — most recent first, <=24 months lookback, max 4 —
    # matching the prototype's trigger cards (kind pill + body + E-ID)
    # and the frontend WhyNowStrip contract ({tag, body}). The previous
    # placeholder stuffed rm.evidence_mode ("RESEARCH_HANDOFF") into the
    # array, which rendered a junk empty SIGNAL pill on every D1. No
    # recent events => EMPTY list => the frontend shows the honest
    # "signals will populate once the timeline ingests" pending copy.
    from datetime import date as _date
    from datetime import timedelta as _td
    _wn_cutoff = _date.today() - _td(days=730)
    _wn_recent = sorted(
        (
            t for t in (getattr(pkg, "timeline_events", None) or [])
            if getattr(t, "event_date", None)
            and t.event_date >= _wn_cutoff
            and (t.title or "").strip()
        ),
        key=lambda t: t.event_date,
        reverse=True,
    )
    why_now = [
        {
            "tag": (t.kind or "signal").replace("_", " ").upper()[:16],
            "body": t.title.strip()[:240],
            "date": t.event_date.isoformat(),
            **({"e_id": t.e_id} if getattr(t, "e_id", None) else {}),
        }
        for t in _wn_recent[:4]
    ]

    # Self-heal: ensure the FK target in `ccg_catalog_versions` exists
    # before inserting into `runs`. Without this stub-row, Drive
    # backfills that resolve to v5.0 (or any version the operator has
    # not yet loaded via `ccg_loader`) blow up on the
    # `runs_ccg_catalog_version_fkey` constraint. The stub-row is
    # idempotent + a structured warning is appended so the operator
    # sees the catalogue loader still needs to run for that version
    # before scores can resolve.
    cv_stub_row = (await session.execute(
        text(
            "SELECT 1 FROM ccg_catalog_versions WHERE version = :cv"
        ),
        {"cv": catalog_version},
    )).first()
    if cv_stub_row is None:
        await session.execute(
            text(
                """
                INSERT INTO ccg_catalog_versions
                    (version, released_at, source_sha256s, loader_run_id, notes)
                VALUES
                    (:cv, NOW(), CAST(:srcs AS JSONB), gen_random_uuid(), :notes)
                ON CONFLICT (version) DO NOTHING
                """
            ),
            {
                "cv": catalog_version,
                "srcs": json.dumps({"_stub": True}),
                "notes": (
                    f"persist_package_stub:{data_source} "
                    "(catalogue loader has NOT been run for this version)"
                ),
            },
        )
        warnings.append(
            f"catalogue_version_stub_inserted:{catalog_version} — "
            "FK target was missing; persisted as placeholder. Run "
            f"`python -m workers.ccg_loader --version {catalog_version} "
            "--workbooks-dir docs/reference/catalogue/...` to populate "
            "ccg_subcaps rows."
        )

    # Synthesize a stable request_id when the run_manifest doesn't
    # ship one. Without this, every package with an empty
    # rm.run_id (Haventree, Compeer, CI Financials etc. — packages
    # whose manifests omit the run_id field or carry it as "") would
    # collide on the runs.request_id UNIQUE constraint and the second-
    # through-Nth ingest would silently UPSERT onto the FIRST run row,
    # cross-attributing every persistence (subcap_scores, evidence,
    # caps_applied_log, document_sections) to a completely unrelated
    # package. The synthetic id is deterministic per (entity, folder)
    # so re-ingest of the SAME package upserts the same synthetic run
    # row; different packages always get different synthetic ids.
    if not (rm.run_id and rm.run_id.strip()):
        import hashlib
        salt = drive_folder_id or display_id
        synth = hashlib.sha1(
            salt.encode("utf-8"), usedforsecurity=False,
        ).hexdigest()[:12].upper()
        rm = rm.model_copy(update={"run_id": f"SYNTH-{synth}"})
        warnings.append(
            f"synth_run_id:no run_manifest.run_id in source; "
            f"persisting under SYNTH-{synth} keyed on "
            f"{'drive_folder_id' if drive_folder_id else 'display_id'}"
        )

    # 2026-06 concurrency hardening: serialize concurrent ingests with
    # the same request_id (e.g. a re-uploaded package zip arriving from
    # two operator browsers at once). Without this, the FOR UPDATE on
    # a non-existent row doesn't block — both SELECTs return NULL, both
    # attempt INSERT, and the second hits the UNIQUE(request_id)
    # constraint with IntegrityError aborting the whole ingest. The
    # advisory lock makes the second wait for the first to commit;
    # afterwards the second sees the inserted row and takes the UPDATE
    # path. Released at COMMIT/ROLLBACK.
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:rid)::bigint)"),
        {"rid": f"dma_run_upsert:{rm.run_id}"},
    )
    existing = (await session.execute(
        text("SELECT id FROM runs WHERE request_id = :rid FOR UPDATE"),
        {"rid": rm.run_id},
    )).first()
    # C5 (2026-06-07): pre-compute qa_verdict_l1/l2 JSONB blobs.
    # `getattr` so older test-stub `_Pkg` classes pre-dating this
    # schema field work — matches the C10 pattern.
    qa_l2 = getattr(pkg, "qa_verdict", None)
    qa_l2_blob = (
        json.dumps(qa_l2.model_dump()) if qa_l2 is not None else None
    )
    qa_l1 = getattr(pkg, "qa_verdict_l1", None)
    qa_l1_blob = (
        json.dumps(qa_l1.model_dump()) if qa_l1 is not None else None
    )
    # C11 (2026-06-07): pre-compute assumptions_register JSONB blob.
    # `getattr` for the same stub-tolerance reason as qa_verdict_l1/l2.
    assumptions = getattr(pkg, "assumptions_register", None) or []
    assumptions_blob = (
        json.dumps([a.model_dump() for a in assumptions])
        if assumptions
        else None
    )
    # C7 (2026-06-07): pre-compute audit_logs JSONB blob. Same getattr
    # pattern; envelope object's model_dump() serializes both
    # reasoning_chain + contradictions lists.
    audit_logs = getattr(pkg, "audit_logs", None)
    audit_logs_blob = (
        json.dumps(audit_logs.model_dump())
        if audit_logs is not None
        else None
    )
    # Run-identity fields (migration 039). The wireframe RUN DATE is the
    # assessment date — never the ingest wall-clock (QA 2026-06-11 found
    # the whole backfilled corpus stamped with the ingest day). Fallback
    # chain: run_manifest → run-id date segment → MANIFEST.package_date.
    # getattr: same stub-tolerance as qa_verdict_l1/l2 above (quarantine
    # tests drive persist with minimal manifest stubs).
    _manifest = getattr(pkg, "manifest", None)
    assessment_date, date_source = compute_assessment_date(
        getattr(rm, "assessment_date", None),
        rm.run_id,
        getattr(_manifest, "package_date", None),
    )
    overall_score = (
        getattr(rm, "overall_score", None)
        or getattr(_manifest, "overall_score", None)
    )
    if overall_score is not None and not (1.0 <= float(overall_score) <= 5.0):
        # Out-of-band value (a 0 placeholder or a 0-100 scale leak):
        # drop it so the read-side keeps the pillar-mean derivation.
        overall_score = None
    if existing is not None:
        run_id = existing.id
        await session.execute(
            text("""
                UPDATE runs SET
                    status='ACTIVE',
                    ccg_catalog_version=:cv,
                    evidence_mode=:em,
                    scqa=CAST(:scqa AS JSONB),
                    top_findings=CAST(:tf AS JSONB),
                    why_now_signals=CAST(:wn AS JSONB),
                    parser_warnings=CAST(:pw AS JSONB),
                    qa_verdict_l1=CAST(:qal1 AS JSONB),
                    qa_verdict_l2=CAST(:qal2 AS JSONB),
                    assumptions_register=CAST(:asm AS JSONB),
                    audit_logs=CAST(:aud AS JSONB),
                    assessment_date=:adate,
                    assessment_date_source=:adsrc,
                    overall_score=:oscore,
                    completed_at=NOW(),
                    updated_at=NOW()
                WHERE id=:rid
            """),
            {
                "cv": catalog_version, "em": evidence_mode,
                "adate": assessment_date, "adsrc": date_source,
                "oscore": overall_score,
                "scqa": scqa_blob,
                # JSONB columns: asyncpg requires a string (it calls
                # .encode() on the value). Passing a Python list/dict
                # raises "AttributeError: 'list' object has no attribute
                # 'encode'". json.dumps + CAST AS JSONB sidesteps this.
                "tf": json.dumps(top_findings),
                "wn": json.dumps(why_now),
                "pw": json.dumps(warnings),
                "qal1": qa_l1_blob,
                "qal2": qa_l2_blob,
                "asm": assumptions_blob,
                "aud": audit_logs_blob,
                "rid": run_id,
            },
        )
    else:
        new = (await session.execute(
            text("""
                INSERT INTO runs (
                    entity_id, request_id, data_source, evidence_mode,
                    status, ccg_catalog_version, scqa, top_findings,
                    why_now_signals, parser_warnings,
                    qa_verdict_l1, qa_verdict_l2, assumptions_register,
                    audit_logs,
                    assessment_date, assessment_date_source, overall_score,
                    started_at, completed_at
                ) VALUES (
                    :eid, :rid, :ds, :em, 'ACTIVE',
                    :cv, CAST(:scqa AS JSONB), CAST(:tf AS JSONB), CAST(:wn AS JSONB),
                    CAST(:pw AS JSONB),
                    CAST(:qal1 AS JSONB), CAST(:qal2 AS JSONB),
                    CAST(:asm AS JSONB),
                    CAST(:aud AS JSONB),
                    :adate, :adsrc, :oscore,
                    NOW(), NOW()
                ) RETURNING id
            """),
            {
                "eid": entity_id, "rid": rm.run_id, "em": evidence_mode,
                "ds": data_source,
                "adate": assessment_date, "adsrc": date_source,
                "oscore": overall_score,
                "cv": catalog_version, "scqa": scqa_blob,
                # JSONB columns require encoded strings under asyncpg.
                "tf": json.dumps(top_findings),
                "wn": json.dumps(why_now),
                "pw": json.dumps(warnings),
                "qal1": qa_l1_blob,
                "qal2": qa_l2_blob,
                "asm": assumptions_blob,
                "aud": audit_logs_blob,
            },
        )).first()
        assert new is not None
        run_id = new.id

    # Supersede prior ACTIVE runs for this entity.
    await session.execute(
        text("""
            UPDATE runs SET status='SUPERSEDED', superseded_by_run_id=:new
            WHERE entity_id=:eid AND status='ACTIVE' AND id <> :new
        """),
        {"eid": entity_id, "new": run_id},
    )

    # ── Subcap scores (resolved through catalogue version aliases) ─────
    # Self-heal contract: when the package references a catalogue version
    # (e.g. v5.5) that isn't loaded yet, bootstrap a minimal `ccg_subcaps`
    # row PER subcap_id the scoring workbook actually emitted. The
    # operator's mandate: "No v5 catalogue will be uploaded. Just use the
    # scoring tooling already there during the backfill. No error
    # message." The scoring workbook is self-describing — every row IS
    # the canonical taxonomy for that version. We populate ccg_subcaps
    # from the workbook so resolve_subcap returns ResolvedSubcap on the
    # first pass and the run stays ACTIVE end-to-end with no operator
    # intervention. Pillar/category foreign keys are also auto-stubbed
    # from the prefix on each subcap_id. Idempotent — re-ingest of the
    # same package is a no-op via ON CONFLICT DO NOTHING.
    parsed_subcap_ids = {sc.subcap_id for sc in pkg.subcap_scores if sc.subcap_id}
    bootstrap_ran = False
    if parsed_subcap_ids:
        existing_count = (await session.execute(
            text(
                "SELECT COUNT(*) FROM ccg_subcaps "
                "WHERE version = :cv AND subcap_id = ANY(:ids)"
            ),
            {"cv": catalog_version, "ids": list(parsed_subcap_ids)},
        )).scalar()
        # If catalogue is empty (or sparse) for this version, bootstrap
        # from the workbook's own taxonomy. Sufficient threshold = 90% —
        # otherwise we assume the catalogue was deliberately curated and
        # leave it alone (operator may want explicit ccg_loader control).
        if (existing_count or 0) < int(len(parsed_subcap_ids) * 0.9):
            inserted = await _bootstrap_catalogue_from_workbook(
                session,
                catalog_version=catalog_version,
                parsed_subcap_ids=parsed_subcap_ids,
                pkg=pkg,
                warnings=warnings,
            )
            bootstrap_ran = inserted > 0
            if bootstrap_ran:
                # Suppress the earlier `catalogue_version_stub_inserted`
                # warning — auto-bootstrap means the catalogue is now
                # populated with real rows from the workbook, not a
                # bare placeholder.
                warnings[:] = [
                    w for w in warnings
                    if not w.startswith("catalogue_version_stub_inserted:")
                ]
                # Emit the structured auto-bootstrap warning so
                # downstream observers (admin Diagnostics + import audit
                # + CI test_catalogue_empty_triggers_workbook_auto_bootstrap)
                # can detect that the workbook-taxonomy fallback fired
                # for this run. Required by the 2026-06 operator mandate:
                # "No v5 catalogue will be uploaded. Just use the scoring
                # toolkits during the backfill."
                warnings.append(
                    f"catalogue_auto_bootstrapped:{inserted} ccg_subcaps "
                    f"rows seeded from scoring workbook taxonomy for "
                    f"{catalog_version} (no ccg_loader run required)."
                )

    resolver = CatalogueResolver(session)
    inserted_scores = 0
    # Selective-reingest gate (Batch 2): when the scoring artifact is
    # unchanged in this re-ingest, skip the heavy score-loop UPSERT.
    # Catalogue bootstrap above already returned 0 inserts (same set
    # of subcap_ids); the resolver below isn't even needed. We jump
    # past the loop to the recommendations / peer / platform blocks.
    skip_scores = not _should_persist("subcap_scores")
    if skip_scores:
        warnings.append(
            "selective_reingest_skip:subcap_scores (scoring artifact "
            "unchanged since prior run)"
        )
    # Pre-compute evidence count per subcap so we can flag "thin
    # evidence" subcaps inline. Subcaps with fewer than 2 evidence
    # rows show a "Thin evidence" outline on D3 Heatmap + drive the
    # D6 Health alerts. This is the wireframe contract — operator
    # asked for "the app flags the evidence thin subcaps".
    THIN_EVIDENCE_THRESHOLD = 2
    evidence_count_per_subcap: dict[str, int] = {}
    for ev in pkg.evidence:
        for sid in (ev.subcap_mappings or []):
            evidence_count_per_subcap[sid] = evidence_count_per_subcap.get(sid, 0) + 1

    unresolved = 0
    not_applicable = 0
    score_iter = [] if skip_scores else pkg.subcap_scores
    broadcast_inserted = 0
    broadcast_categories_seen: set[str] = set()
    pillar_level_dropped = 0
    category_with_no_children = 0
    # Batched direct-hit prefetch (Part 12.4): the resolver ran ONE
    # SELECT per subcap row (~700 round-trips/package). Fetch every
    # direct (version, subcap_id) hit in a single query; only misses
    # (alias-bridge / drifted ids) still walk the resolver ladder.
    _direct_hits: dict[str, ResolvedSubcap] = {}
    _wanted_ids = list({
        sc.subcap_id for sc in score_iter if sc.subcap_id
    })
    if _wanted_ids:
        _hit_rows = (await session.execute(
            text(
                """
                SELECT version, subcap_id, l1_id, name, description,
                       solution_type, tier
                FROM ccg_subcaps
                WHERE version = :cv AND subcap_id = ANY(:ids)
                """
            ),
            {"cv": catalog_version, "ids": _wanted_ids},
        )).all()
        for _hr in _hit_rows:
            _direct_hits[_hr.subcap_id] = ResolvedSubcap(
                version=_hr.version,
                subcap_id=_hr.subcap_id,
                l1_id=_hr.l1_id,
                name=_hr.name,
                description=_hr.description,
                solution_type=_hr.solution_type,
                tier=_hr.tier,
            )
    # Rows collected for the two executemany flushes below (bind order ==
    # prior per-row order, so UPSERT last-write-wins semantics hold).
    _broadcast_param_rows: list[dict] = []
    _direct_param_rows: list[dict] = []
    for sc in score_iter:
        resolved = _direct_hits.get(sc.subcap_id) or await resolver.resolve_subcap(
            sc.subcap_id, catalog_version,
        )
        if isinstance(resolved, SubcapNotFound):
            # ── Batch 3: shallow catalogue alias bridge ───────────────
            # Detect category-shaped IDs (P1C1, P2C3.4) and broadcast
            # the parent's score to the catalogue's child subcap_ids.
            # Pure-helper derives the broadcast category (None when
            # the id is pillar-level or malformed); we look up
            # children in v<catalog_version> and persist one row per
            # child with data_source='shallow_broadcast'.
            broadcast_cat = derive_broadcast_category(sc.subcap_id)
            if broadcast_cat is None:
                # Pillar-level / malformed -- the prior behavior was
                # silent drop; surface explicitly for the operator.
                from app.services.catalogue_alias_bridge import (
                    is_pillar_level,
                )
                if is_pillar_level(sc.subcap_id):
                    pillar_level_dropped += 1
                else:
                    unresolved += 1
                continue
            # Validate parent score is in [1, 5] before broadcasting --
            # never broadcast a Score=0 N/A row.
            try:
                _parent_score = float(sc.score)
            except (TypeError, ValueError):
                _parent_score = 0.0
            if _parent_score < 1.0 or _parent_score > 5.0:
                not_applicable += 1
                continue
            children = await get_category_children(
                session,
                version=catalog_version,
                category_id=broadcast_cat,
            )
            if not children:
                # Catalogue doesn't have this category at this version --
                # legitimate unresolved (no child set to broadcast to).
                category_with_no_children += 1
                unresolved += 1
                continue
            rows = build_broadcast_rows(
                parent_score=_parent_score,
                parent_band=_to_band(_parent_score),
                parent_confidence=_conf_to_float(sc.confidence),
                parent_rationale=sc.rationale,
                parent_caps_applied=sc.caps_applied,
                parent_category_id=broadcast_cat,
                children_ids=children,
            )
            for br in rows:
                # Bridge-broadcast UPSERT params; flushed as ONE
                # executemany after the loop (data_source distinguishes
                # these rows from direct subcaps for the UI disclosure).
                _broadcast_param_rows.append({
                    "rid": run_id, "eid": entity_id,
                    "sid": br.subcap_id,
                    "src": broadcast_cat,
                    "alias": catalog_version,
                    "score": float(br.score),
                    "band": br.band,
                    "conf": br.confidence,
                    "rat": br.rationale,
                    "cap": bool(br.caps_applied),
                    "cr": br.caps_applied,
                    "thin": br.is_thin_evidence,
                    "ds": br.data_source,
                    "pcat": br.parent_category_id,
                })
                broadcast_inserted += 1
            broadcast_categories_seen.add(broadcast_cat)
            continue
        # Skip "not applicable" subcaps. Some real fixtures (e.g. Payments
        # Canada, which is an FMI) ship a Score=0, Confidence=N/A row for
        # each catalogue subcap that doesn't apply to the entity's
        # business model (38 rows for Payments Canada, all with a rationale
        # like "FMI overlay N/A — retail vulnerable consumer concept
        # inapplicable to FMI"). subcap_scores_score_chk enforces
        # score BETWEEN 1.0 AND 5.0 so persisting 0 would abort the
        # whole ingest; the right semantic is "this subcap is N/A for
        # this entity" → skip the row and record the count in
        # parser_warnings so the operator can audit the gap. The catalogue
        # resolver still has the subcap; the heatmap simply has no score
        # cell for it (rendered as null/dash, not as a 0-score).
        try:
            _score_f = float(sc.score)
        except (TypeError, ValueError):
            _score_f = 0.0
        if _score_f < 1.0 or _score_f > 5.0:
            not_applicable += 1
            continue
        source_id = sc.subcap_id if resolved.was_aliased else None
        ev_count = evidence_count_per_subcap.get(sc.subcap_id, 0) \
            + (evidence_count_per_subcap.get(source_id, 0) if source_id else 0)
        is_thin = ev_count < THIN_EVIDENCE_THRESHOLD
        _direct_param_rows.append({
            "rid": run_id, "eid": entity_id,
            "sid": resolved.subcap_id, "src": source_id,
            "alias": resolved.aliased_from_version,
            "score": _score_f, "band": _to_band(_score_f),
            "conf": _conf_to_float(sc.confidence), "rat": sc.rationale,
            "cap": bool(sc.caps_applied), "cr": sc.caps_applied,
            "thin": is_thin,
        })
        inserted_scores += 1

    # ── Batched flushes (Part 12.4) ──────────────────────────────────
    # Two executemany statements replace the prior ~700 single-row
    # UPSERT round-trips per package. Bind order preserves the loop's
    # last-write-wins ON CONFLICT semantics exactly.
    if _broadcast_param_rows:
        await session.execute(
            text("""
                INSERT INTO subcap_scores (
                    run_id, entity_id, subcap_id,
                    source_subcap_id, alias_resolved_from,
                    score, band, confidence, rationale,
                    cap_applied, cap_reason, is_thin_evidence,
                    data_source, parent_category_id
                ) VALUES (
                    :rid, :eid, :sid, :src, :alias,
                    :score, :band, :conf, :rat,
                    :cap, :cr, :thin, :ds, :pcat
                )
                ON CONFLICT (run_id, subcap_id) DO UPDATE SET
                    score = EXCLUDED.score,
                    band = EXCLUDED.band,
                    confidence = EXCLUDED.confidence,
                    rationale = EXCLUDED.rationale,
                    cap_applied = EXCLUDED.cap_applied,
                    cap_reason = EXCLUDED.cap_reason,
                    is_thin_evidence = EXCLUDED.is_thin_evidence,
                    data_source = EXCLUDED.data_source,
                    parent_category_id = EXCLUDED.parent_category_id
            """),
            _broadcast_param_rows,
        )
    if _direct_param_rows:
        await session.execute(
            text("""
                INSERT INTO subcap_scores (
                    run_id, entity_id, subcap_id, source_subcap_id,
                    alias_resolved_from, score, band, confidence, rationale,
                    cap_applied, cap_reason, is_thin_evidence,
                    data_source
                ) VALUES (
                    :rid, :eid, :sid, :src, :alias, :score, :band, :conf,
                    :rat, :cap, :cr, :thin, 'direct'
                )
                ON CONFLICT (run_id, subcap_id) DO UPDATE SET
                    score = EXCLUDED.score,
                    band = EXCLUDED.band,
                    confidence = EXCLUDED.confidence,
                    rationale = EXCLUDED.rationale,
                    cap_applied = EXCLUDED.cap_applied,
                    cap_reason = EXCLUDED.cap_reason,
                    is_thin_evidence = EXCLUDED.is_thin_evidence,
                    data_source = EXCLUDED.data_source
            """),
            _direct_param_rows,
        )
    if broadcast_inserted:
        warnings.append(
            f"shallow_alias_bridge:{broadcast_inserted} subcap_scores rows "
            f"broadcast from {len(broadcast_categories_seen)} category-"
            f"level parents ({', '.join(sorted(broadcast_categories_seen))})"
            f" -- bot pipeline should re-emit at subcap depth for full "
            f"fidelity; UI surfaces 'broadcast' disclosure via "
            f"data_source='shallow_broadcast'"
        )
    if pillar_level_dropped:
        warnings.append(
            f"pillar_level_scores_dropped:{pillar_level_dropped} P[1-4]-"
            f"shaped score rows cannot be broadcast to subcaps (too "
            f"coarse). Bot pipeline must emit at category or subcap depth."
        )
    if category_with_no_children:
        warnings.append(
            f"shallow_alias_no_children:{category_with_no_children} "
            f"category-shaped IDs had no matching catalogue children at "
            f"version {catalog_version} (catalogue may need ccg_loader "
            f"run for this version)"
        )
    # Peer-median broadcast (2026-06-10): the corpus benchmarks peers at
    # CATEGORY level (pkg.category_scores.peer_median → peer_benchmarks);
    # subcap_scores.peer_median stayed NULL corpus-wide, so the D1 pillar
    # peer ticks, D3 peer overlay and delta arrows all rendered empty
    # (dash placeholder). Broadcast each category's peer median (and the derived gap)
    # onto its subcap rows — same shallow-broadcast philosophy as the
    # alias bridge: the value IS the category-level cohort median,
    # surfaced at subcap grain.
    if not skip_scores:
        _cat_peer = {
            cs.category_id: cs.peer_median
            for cs in (pkg.category_scores or [])
            if cs.peer_median is not None and cs.category_id
        }
        # Batched (Part 12.4): one UPDATE joined against the category→
        # median map instead of one UPDATE per category (~20/package).
        if _cat_peer:
            await session.execute(
                text(
                    "UPDATE subcap_scores s SET "
                    "    peer_median = m.pm, "
                    "    peer_gap = ROUND((s.score - m.pm)::numeric, 2) "
                    "FROM jsonb_to_recordset(CAST(:rows AS JSONB)) "
                    "     AS m(cat text, pm numeric) "
                    "WHERE s.run_id = :rid AND s.peer_median IS NULL "
                    "  AND (s.parent_category_id = m.cat "
                    "       OR split_part(s.subcap_id, '.', 1) = m.cat)"
                ),
                {
                    "rid": run_id,
                    "rows": json.dumps([
                        {"cat": _cat_id, "pm": float(_pm)}
                        for _cat_id, _pm in _cat_peer.items()
                    ]),
                },
            )

    if not_applicable:
        # Observation-only — see the docstring in the loop body above.
        warnings.append(
            f"subcap_not_applicable_skipped:{not_applicable} "
            f"rows had score outside [1,5] (typically Score=0 + "
            f"Confidence=N/A 'overlay inapplicable' rows from "
            f"subvertical-specific catalogue subcaps that don't apply "
            f"to this entity)"
        )
    if unresolved:
        # 2026-05-28 H8 hotfix: stronger structured warning so import
        # audit + admin UI can distinguish "a few aliases missing" from
        # "catalogue is empty / placeholder-only".
        #
        # 2026-06 operator mandate update: when the workbook itself
        # supplied the taxonomy and we auto-bootstrapped, an `unresolved`
        # tail here means the auto-bootstrap dropped a few malformed IDs
        # (no P{n}C{m}.{p}.{q} match) — NOT a missing catalogue loader.
        # We emit a lower-severity warning + skip the PENDING_REVIEW
        # gate so AEs see real data instead of an empty-heatmap stall.
        parsed_count = len(pkg.subcap_scores)
        if bootstrap_ran:
            warnings.append(
                f"catalogue_auto_bootstrapped_with_skips:{unresolved}/"
                f"{parsed_count} subcap IDs skipped (likely malformed "
                f"IDs in the scoring workbook); rest persisted under "
                f"{catalog_version}."
            )
        else:
            warnings.append(
                f"catalogue_unresolved:{unresolved}/{parsed_count} "
                f"subcaps unresolved against {catalog_version}"
            )
            if parsed_count > 0 and unresolved == parsed_count:
                warnings.append(
                    f"catalogue_empty_for_version: ZERO of {parsed_count} "
                    f"parsed subcaps resolved against {catalog_version}. "
                    f"Likely the catalogue loader has not populated "
                    f"ccg_subcaps rows for this version (placeholder "
                    f"ccg_catalog_versions row only). Run the ccg_loader "
                    f"job with --version={catalog_version} and the "
                    f"correct --workbooks-dir before this package can "
                    f"surface scores."
                )
                # 2026-05-29 finalization — v5 catalogue gate. When EVERY
                # parsed subcap is unresolved AND auto-bootstrap did not
                # run (or did not insert anything), the run carries zero
                # usable scores. PENDING_REVIEW gates it out of
                # customer-facing surfaces while leaving it visible to
                # the admin import audit. An operator clears the gate
                # by running ccg_loader for the named version, then
                # re-ingesting the package (idempotent via request_id
                # UPSERT).
                await session.execute(
                    text(
                        "UPDATE runs SET status='PENDING_REVIEW', "
                        "parser_warnings=CAST(:pw AS JSONB), "
                        "updated_at=NOW() WHERE id=:rid"
                    ),
                    {
                        "rid": run_id,
                        "pw": json.dumps(warnings),
                    },
                )

    # ── Evidence (via dedup decision engine) ──────────────────────────
    # Selective-reingest gate (Batch 2): evidence is the dedup TRIPLE
    # (evidence_index + evidence_run_links + dedup_audit) maintained
    # together by the 5-branch state machine. The artifact_manifest
    # mapping always emits the triple as a unit when 01_evidence/*
    # changed, so we gate on the canonical evidence_index name.
    if _should_persist("evidence_index"):
        await _persist_evidence(
            session, run_id=run_id, entity_id=entity_id, pkg=pkg,
            assessment_date=assessment_date,
        )
    else:
        warnings.append(
            "selective_reingest_skip:evidence (01_evidence artifacts "
            "unchanged since prior run)"
        )

    # ── Issue register ─────────────────────────────────────────────────
    issue_iter = [] if not _should_persist("issue_register") \
        else pkg.issue_register
    if not _should_persist("issue_register") and pkg.issue_register:
        warnings.append("selective_reingest_skip:issue_register")
    # Batched (Part 12.4): one executemany for the whole register.
    _issue_rows = issue_register_params(run_id, entity_id, issue_iter)
    if _issue_rows:
        await session.execute(
            text("""
                INSERT INTO issue_register (
                    run_id, entity_id, issue_id, title, severity,
                    rationale, opened_on, resolved_on, status, kind,
                    dma_impact, caps, linked_subcap_ids, source_path
                ) VALUES (
                    :rid, :eid, :iid, :title, :sev,
                    :rat, :od, :rd, :st, :kind,
                    :impact, CAST(:caps AS JSONB), :ls, :sp
                )
                ON CONFLICT (run_id, issue_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    severity = EXCLUDED.severity,
                    rationale = EXCLUDED.rationale,
                    opened_on = EXCLUDED.opened_on,
                    resolved_on = EXCLUDED.resolved_on,
                    status = EXCLUDED.status,
                    kind = EXCLUDED.kind,
                    dma_impact = EXCLUDED.dma_impact,
                    caps = EXCLUDED.caps,
                    linked_subcap_ids = EXCLUDED.linked_subcap_ids
            """),
            _issue_rows,
        )

    # ── C10 (2026-06-07): caps_applied_log persistence ─────────────────
    # DELETE-then-INSERT per run_id for idempotent re-ingest, matching
    # the document_sections / focus_areas pattern above. Requires
    # migration 028 to have been applied; failure raises and aborts
    # the ingest transaction (consistent with the firmographics
    # persistence pattern — the operator runs the migration and
    # re-ingests).
    # `getattr` tolerates test stubs (`_Pkg` in
    # test_concurrent_ingest_safeguards) that pre-date this schema
    # addition and don't carry the field. Production `IngestedPackage`
    # always has it via Pydantic default `Field(default_factory=list)`.
    caps_applied_log = getattr(pkg, "caps_applied_log", None) or []
    # Selective-reingest gate (Batch 2): caps_applied_log is
    # DELETE-then-INSERT per run_id. Skip atomically (skip BOTH DELETE
    # and INSERT) so the prior run's caps remain intact.
    if caps_applied_log and not _should_persist("caps_applied_log"):
        warnings.append("selective_reingest_skip:caps_applied_log")
        caps_applied_log = []
    if caps_applied_log:
        await session.execute(
            text("DELETE FROM caps_applied_log WHERE run_id = :rid"),
            {"rid": run_id},
        )
        # Batched (Part 12.4): one executemany (Calprivate ships 115 caps).
        await session.execute(
            text("""
                INSERT INTO caps_applied_log (
                    run_id, entity_id, log_id, subcap_id,
                    cap_type, trigger_condition, cap_ceiling,
                    trigger_evidence, affected_categories,
                    severity, date_applied, recalc_verified
                ) VALUES (
                    :rid, :eid, :lid, :sid, :ct, :tc, :cc,
                    :te, :ac, :sv, :da, :rv
                )
            """),
            [
                {
                    "rid": run_id,
                    "eid": entity_id,
                    "lid": (cap.log_id or "")[:64],
                    "sid": (cap.subcap_id or "")[:64],
                    "ct": (cap.cap_type[:64] if cap.cap_type else None),
                    "tc": cap.trigger_condition,
                    "cc": (cap.cap_ceiling[:32] if cap.cap_ceiling else None),
                    "te": list(cap.trigger_evidence or []),
                    "ac": list(cap.affected_categories or []),
                    "sv": (cap.severity[:32] if cap.severity else None),
                    "da": (cap.date_applied[:32] if cap.date_applied else None),
                    "rv": (cap.recalc_verified[:32]
                           if cap.recalc_verified else None),
                }
                for cap in caps_applied_log
            ],
        )

    # ── Recommendations ────────────────────────────────────────────────
    # Selective-reingest gate (Batch 2): UPSERT block; safe to skip.
    rec_iter = [] if not _should_persist("recommendations") \
        else pkg.recommendations
    if not _should_persist("recommendations") and pkg.recommendations:
        warnings.append("selective_reingest_skip:recommendations")
    # Batched (Part 12.4): one executemany for the whole rec set.
    from app.services import platform_products as _pp
    _rec_rows: list[dict] = []
    for rec in rec_iter:
        platform_id = _infer_platform_id(rec.title, rec.ownership)
        desc = _rec_description(rec)
        rc = rec.root_cause or {}
        sol = rec.solution or {}
        scoring_impact = str(rc.get("scoring_impact", "") or "")
        # Deficient subcaps the rec addresses. Catch BOTH leaf (P#C#.#.#) and
        # category (P#C#) refs from scoring_impact — the corpus mostly cites
        # category grain, which the prior leaf-only regex missed (15/599).
        target_subcaps = re.findall(r"P[1-4]C\d+(?:\.\d+)*", scoring_impact)
        target_subcaps = list(dict.fromkeys(target_subcaps))
        # analyst-driven fit fields (migration 062): the SPECIFIC product the
        # analyst named, else a Salesforce-family product implied by the rec's
        # DOMAIN (outcome-worded / capability-code titles carry no product name
        # but a clear domain). Fully-empty recs resolve to None (residual).
        zennify_product = (_pp.primary_product(rec.title, desc)
                           or _pp.infer_product_from_domain(f"{rec.title}\n{desc}"))
        priority_rank = _priority_rank(getattr(rec, "priority", None))
        strategic_objectives = _rec_strategic_objectives(rec)
        integration_systems = _extract_integration_systems(
            sol.get("scoping_note"), sol.get("approach"), desc)
        prereq = [str(x)[:16] for x in
                  (getattr(rec, "prerequisite_rec_ids", None) or [])]
        effort_band = _effort_band(len(integration_systems), bool(prereq))
        evidence_ids = _rec_evidence_ids(rec)
        _rec_rows.append({
            "rid": run_id, "eid": entity_id,
            # Template markers ([[ZENNIFY]]) are presentation noise
            # in a third of the corpus' rec titles — strip at persist
            # so D4 cards + the rec modal read as analyst copy (same
            # cleaner the insight builders use).
            "rcid": rec.id[:16],
            "title": _strip_markers(rec.title) or rec.title,
            "desc": desc,
            "ts": target_subcaps, "pid": platform_id,
            "prereq": prereq,
            "zp": zennify_product,
            "pr": priority_rank,
            # strategic objectives + integration systems are JSONB — serialise.
            "so": json.dumps(strategic_objectives) if strategic_objectives else None,
            "eff": effort_band,
            "eids": evidence_ids,
        })
    if _rec_rows:
        await session.execute(
            text("""
                INSERT INTO recommendations (
                    run_id, entity_id, rec_id, title, description,
                    target_subcap_ids, platform_id, prerequisite_rec_ids,
                    zennify_product, priority_rank, strategic_objectives,
                    effort_band, root_cause_e_ids
                ) VALUES (
                    :rid, :eid, :rcid, :title, :desc, :ts, :pid, :prereq,
                    :zp, :pr, CAST(:so AS jsonb), :eff, :eids
                )
                ON CONFLICT (run_id, rec_id) DO UPDATE SET
                    title = EXCLUDED.title,
                    description = EXCLUDED.description,
                    target_subcap_ids = EXCLUDED.target_subcap_ids,
                    platform_id = EXCLUDED.platform_id,
                    prerequisite_rec_ids = EXCLUDED.prerequisite_rec_ids,
                    zennify_product = EXCLUDED.zennify_product,
                    priority_rank = EXCLUDED.priority_rank,
                    strategic_objectives = EXCLUDED.strategic_objectives,
                    effort_band = EXCLUDED.effort_band,
                    root_cause_e_ids = EXCLUDED.root_cause_e_ids
            """),
            _rec_rows,
        )

    # ── Peer benchmarks (category-level aggregated to per-subcap median) ──
    # The packages emit category-level peer medians (P1C1 etc.), not
    # subcap-level. We persist the category rows verbatim into
    # peer_benchmarks keyed by the category_id, and the D3 heatmap
    # aggregator broadens by category at read time.
    # Selective-reingest gate (Batch 2): UPSERT block; safe to skip.
    if not _should_persist("peer_benchmarks"):
        if subvertical and pkg.category_scores:
            warnings.append("selective_reingest_skip:peer_benchmarks")
    elif subvertical:
        # Batched (Part 12.4): one executemany for the category medians.
        _peer_rows = [
            {
                "sv": subvertical, "sid": cs.category_id,
                # 2026-06-09 fix: store the PEER median (cs.peer_median),
                # not the assessed entity's own score (cs.score). The
                # prior value mislabelled this entity's score as the
                # cohort median, so tech-drift (patterns.py) + RAG
                # cohort lookups compared an entity against itself.
                "cv": catalog_version, "m": cs.peer_median,
                "p25": cs.peer_p25, "p75": cs.peer_p75,
                "n": len(pkg.peers) or 4,
            }
            for cs in pkg.category_scores
            if cs.peer_median is not None
        ]
        if _peer_rows:
            await session.execute(
                text("""
                    INSERT INTO peer_benchmarks (
                        subvertical, subcap_id, ccg_catalog_version, median, p25, p75, n
                    ) VALUES (:sv, :sid, :cv, :m, :p25, :p75, :n)
                    ON CONFLICT (subvertical, subcap_id, ccg_catalog_version)
                    DO UPDATE SET median=EXCLUDED.median, p25=EXCLUDED.p25,
                                  p75=EXCLUDED.p75, n=EXCLUDED.n,
                                  computed_at=NOW()
                """),
                _peer_rows,
            )

    # ── Catalogue platform tags (promote D4 addressability to ingest) ──
    # `subcap_scores.platform_tags` drives BOTH the tech subcap-linker
    # (below) and `_persist_platform_scores` (the D4 fit scorer). Packages
    # rarely ship tags, so without this step they stay empty until the
    # post-ingest `apply_catalogue_platforms` derive job runs — leaving
    # every D4 platform card at INSUFFICIENT_EVIDENCE and the tech
    # drilldown subcap-less. Source the per-subcap L3 platform names from
    # the catalogue (`ccg_subcaps.l3_platforms`) and map them onto the
    # five scored platforms, run-scoped + fill-when-empty (package-shipped
    # tags stay authoritative). Idempotent; gated to the score-bearing
    # artifacts so a tech-only selective re-ingest keeps prior tags.
    if _should_persist("subcap_scores") or _should_persist("platform_scores"):
        await apply_platform_tags_for_run(
            session, run_id=run_id, catalog_version=catalog_version,
        )

    # ── Tech stack (Explorium) ─────────────────────────────────────────
    # Selective-reingest gate (Batch 2): UPSERT block; safe to skip.
    ts_iter = [] if not _should_persist("tech_stack_entries") \
        else pkg.tech_stack
    if not _should_persist("tech_stack_entries") and pkg.tech_stack:
        warnings.append("selective_reingest_skip:tech_stack_entries")
    for ts in ts_iter:
        tech_id = re.sub(r"[^A-Za-z0-9]+", "_",
                         f"{ts.vendor}_{ts.product or ts.category or ''}")[:64]
        # Evidence + subcap grounding, promoted from clean_techstack.py so
        # the tech drilldown is evidence-grounded AT INGEST (was ~94%/81%
        # empty across the corpus). Evidence is already persisted above and
        # platform_tags were just applied, so both links resolve now.
        evidence_e_ids = await link_evidence_for_vendor(
            session, entity_id=entity_id, vendor=ts.vendor,
        )
        linked_subcap_ids = await link_subcaps_for_vendor(
            session, run_id=run_id, family=family_for_vendor(ts.vendor),
        )
        # Prototype-aligned status enum (DETECTED|CONFIRMED|CONFIRMED_REMOVED):
        # honour the parser's read of the source's deployment column, then
        # upgrade an inferred DETECTED to CONFIRMED when we just linked real
        # evidence for the vendor this run (deployment corroborated).
        status = getattr(ts, "status", None) or "DETECTED"
        if status == "DETECTED" and evidence_e_ids:
            status = "CONFIRMED"
        l3_id = getattr(ts, "l3_id", None) or l3_for_tech(ts.vendor, ts.product, ts.category)
        await session.execute(
            text("""
                INSERT INTO tech_stack_entries (
                    entity_id, tech_id, vendor, product, layer, status, source,
                    l3_id, evidence_e_ids, linked_subcap_ids
                ) VALUES (
                    :eid, :tid, :v, :p, :l, :st, :src,
                    :l3, CAST(:ev AS varchar[]), CAST(:sb AS varchar[])
                )
                ON CONFLICT (entity_id, tech_id) DO UPDATE SET
                    vendor=EXCLUDED.vendor, product=EXCLUDED.product,
                    layer=EXCLUDED.layer, status=EXCLUDED.status,
                    -- l3_id: keep a prior non-NULL link if this run can't resolve one.
                    l3_id=COALESCE(EXCLUDED.l3_id, tech_stack_entries.l3_id),
                    -- Preserve prior grounding when a re-ingest computes
                    -- empty (e.g. the evidence isn't present this run).
                    evidence_e_ids=CASE
                        WHEN cardinality(EXCLUDED.evidence_e_ids) = 0
                        THEN tech_stack_entries.evidence_e_ids
                        ELSE EXCLUDED.evidence_e_ids END,
                    linked_subcap_ids=CASE
                        WHEN cardinality(EXCLUDED.linked_subcap_ids) = 0
                        THEN tech_stack_entries.linked_subcap_ids
                        ELSE EXCLUDED.linked_subcap_ids END
            """),
            {
                "eid": entity_id, "tid": tech_id,
                "v": ts.vendor[:128], "p": (ts.product or ts.vendor)[:255],
                # Part 9.1: honour the taxonomy sanitizer's layer_hint (one
                # of the 4 canonical layers by construction) before falling
                # back to the category keyword map.
                "l": (ts.layer if ts.layer in (
                    "foundation", "platform", "application", "intelligence",
                ) else _layer_for_tech(ts.category)),
                "st": status, "src": (ts.source or "Explorium")[:64],
                "l3": (l3_id or None), "ev": evidence_e_ids, "sb": linked_subcap_ids,
            },
        )

    # ── Platform scores (deterministic fit + readiness, persisted) ─────
    # Compute Fit Score + Readiness Index for the 5 documented platforms
    # NOW so they survive across requests (no on-demand recomputation),
    # support cross-user reads, and feed the intelligence_builder's
    # `platform_story` surface. See ADR 0004 (persistence tiers).
    # Selective-reingest gate (Batch 2): platforms derive from subcap
    # scores + tech stack; skip when neither changed.
    if _should_persist("platform_scores"):
        inserted_platforms = await _persist_platform_scores(
            session,
            run_id=run_id,
            entity_id=entity_id,
        )
    else:
        warnings.append("selective_reingest_skip:platform_scores")
        inserted_platforms = 0

    # ── Document sections + lineage (from 04_reports/*.docx) ───────────
    # The DOCX narrative drives every "narrative" subfield on the
    # entity endpoints — D1 SCQA, D2 IC explanations, D4 recommendation
    # copy, D5 trend overlays, D6 data-gap descriptions. We persist
    # each section once per run and emit lineage rows linking subcaps /
    # E-IDs / pillar deep-dives that the section mentions.
    # Selective-reingest gate (Batch 2): the section-triple
    # (document_sections + document_lineage + document_evidence_items)
    # is maintained together by _persist_document_sections. Skip
    # atomically.
    if _should_persist("document_sections"):
        inserted_sections = await _persist_document_sections(
            session, run_id=run_id, entity_id=entity_id, pkg=pkg,
        )
    else:
        warnings.append("selective_reingest_skip:document_sections")
        inserted_sections = 0

    # ── Insight cards (from section_analysis_#.json top_findings) ──────
    # D2 InsightCard grid + modal consume insight_cards; previously the
    # table was never written. DELETE-then-INSERT per run_id (idempotent).
    if _should_persist("document_sections"):
        inserted_insights = await _persist_insight_cards(
            session, run_id=run_id, entity_id=entity_id, pkg=pkg,
        )
        if inserted_insights:
            warnings.append(f"insight_cards_persisted: {inserted_insights}")
    else:
        inserted_insights = 0

    # ── Focus areas (from 04_reports/*Client_Profile*.docx) ────────────
    # 2026-05-29 finalization: focus_areas were extracted by the
    # client_profile parser since 2026-05 but only the count was
    # logged — the table stayed empty in production. Now persisted
    # idempotently per run (DELETE-then-INSERT pattern, matching
    # _persist_document_sections).
    # Selective-reingest gate (Batch 2): focus_areas is DELETE-INSERT;
    # skip atomically.
    if _should_persist("focus_areas"):
        inserted_focus_areas = await _persist_focus_areas(
            session, run_id=run_id, entity_id=entity_id, pkg=pkg,
        )
    else:
        warnings.append("selective_reingest_skip:focus_areas")
        inserted_focus_areas = 0

    # ── Self-improvement: flush parser observations ────────────────────
    # `pkg.parser_observations` is populated by sub-parsers (today:
    # `parse_per_pillar_sheets`) with structural surprises — column
    # headers outside the static ALIASES dict, sheet-name variants,
    # subcap-ID formats outside the known regex. Persisting them gives
    # the operator (or a future nightly auto-PR job) a queue to drain
    # by promoting recurring variants into the source-code ALIASES on
    # the next deploy. Best-effort: a write failure here NEVER blocks
    # ingest (the observations table may not exist on an older PG
    # that hasn't been migrated to 026 yet).
    observations_persisted = 0
    if getattr(pkg, "parser_observations", None):
        try:
            from app.services.parser_observations import (
                record_parser_observation,
            )
            for obs in pkg.parser_observations[:200]:
                kind = str(obs.get("kind") or "unknown")
                value = str(obs.get("value") or "")
                if not value:
                    continue
                ctx = obs.get("sample_context") or {}
                parser_name = (
                    ctx.get("parser") if isinstance(ctx, dict) else None
                ) or "unknown"
                await record_parser_observation(
                    session,
                    parser_name=str(parser_name),
                    observation_kind=kind,
                    observed_value=value,
                    canonical_guess=(
                        str(obs.get("canonical_guess"))
                        if obs.get("canonical_guess") else None
                    ),
                    sample_context=ctx if isinstance(ctx, dict) else None,
                    run_id=str(run_id),
                )
                observations_persisted += 1
        except Exception as e:
            log.info(
                "parser_observations.flush_failed",
                run_id=str(run_id),
                err=type(e).__name__,
                err_msg=str(e)[:200],
            )

    # Thin-evidence alert derivation (QA 2026-06-11: the alerts table
    # had no producer — every alert surface rendered empty). Same
    # transaction as the rest of the persist; the caller commits.
    # Best-effort: a derivation failure must never wedge an ingest.
    alerts_inserted = 0
    try:
        alert_counters = await derive_thin_evidence_alerts(
            session, run_id=str(run_id), entity_id=str(entity_id),
        )
        alerts_inserted = alert_counters["alerts_inserted"]
    except Exception as e:
        warnings.append(f"alerts_producer_failed:{type(e).__name__}")
        log.info(
            "alerts_producer.failed",
            run_id=str(run_id),
            err=type(e).__name__, err_msg=str(e)[:200],
        )

    log.info(
        "package.persisted",
        run_id=rm.run_id, db_run_id=str(run_id),
        scores=inserted_scores, evidence=len(pkg.evidence),
        recs=len(pkg.recommendations), peers=len(pkg.peers),
        tech=len(pkg.tech_stack),
        platforms=inserted_platforms,
        sections=inserted_sections,
        focus_areas=inserted_focus_areas,
        observations=observations_persisted,
        alerts=alerts_inserted,
    )
    return str(run_id), warnings


def _fact_field(fact: Any, key: str) -> str:
    """Tolerant fact-field read: FactItem attr or plain-dict key."""
    v = getattr(fact, key, None)
    if v is None and isinstance(fact, dict):
        v = fact.get(key)
    return str(v).strip() if v else ""


def _excerpt_from_facts(ev: Any, max_chars: int = 300) -> str | None:
    """Compose an excerpt from the row's extracted ``facts[]`` when the
    source carried no verbatim excerpt.

    Corpus measurement (2026-07 stress test): 91% of evidence_index.json
    rows ship rich fact text but only ~15% of persisted rows had a real
    excerpt — the rest fell to the '(no excerpt)' placeholder, capping
    AE-facing depth on every surface (heatmap synthesis, EvidenceDrawer,
    RAG grounding, insight evidence tabs). Join the first 1-2 facts'
    text and sentence-clip to ~300 chars; '(no excerpt)' remains only
    when facts are genuinely absent/empty.
    """
    texts: list[str] = []
    for fact in (getattr(ev, "facts", None) or []):
        t = _fact_field(fact, "text")
        if t:
            texts.append(t)
        if len(texts) == 2:
            break
    if not texts:
        return None
    joined = " ".join(texts)
    try:
        # Lazy import: keeps the worker-image import graph lean; the
        # clipper itself degrades to its regex tier without spaCy.
        from app.services.nlp.segment import clip_sentences
        clipped = clip_sentences(joined, max_chars)
    except Exception:
        clipped = ""
    return clipped or joined[:max_chars].strip() or None


def _claim_label_from_facts(ev: Any) -> str | None:
    """First non-empty fact claim_label (FACT/INFERENCE/…) — used as the
    claim_type fallback when the row has no signal_direction."""
    for fact in (getattr(ev, "facts", None) or []):
        label = _fact_field(fact, "claim_label")
        if label:
            return label
    return None


async def _persist_evidence(
    session: AsyncSession,
    *,
    run_id: Any,
    entity_id: Any,
    pkg: Any,
    assessment_date: Any = None,
) -> None:
    """Persist evidence rows through the dedup decision engine.

    State-branch contract (the 5 dedup_audit action values):

      kept                 → first sighting of content_hash → INSERT
                              evidence_index + evidence_run_links
                              (first_seen_in_run=True) + dedup_audit row.
      dedup_same_entity    → content_hash already exists for this entity
                              → LINK existing evidence_id to the current
                              run via evidence_run_links
                              (first_seen_in_run=False) + dedup_audit.
                              evidence_index row count unchanged.
      cross_entity_kept    → content_hash exists for a DIFFERENT entity
                              → INSERT a NEW evidence_index row scoped
                              to current entity + link + audit. Two rows
                              now share the same content_hash, one per
                              owning entity. The legacy news-article
                              shared between two clients case.
      tier_upgrade         → content_hash + same entity, but incoming
                              tier is STRONGER (lower number).
                              UPDATE existing.tier → incoming.tier;
                              insert evidence_run_links + dedup_audit
                              with before/after in reason.
      duplicate_within_run → content_hash already seen earlier in THIS
                              same run's CSV → skip; audit-row only,
                              kept_evidence_id is the prior copy from
                              this same run.

    Idempotency: re-uploading the same package yields the same
    content_hash for every row; the engine returns dedup_same_entity for
    each one — evidence_index row count unchanged; evidence_run_links
    doubles (one new row per (existing_evidence, current_run)); dedup_audit
    grows by N rows. Defense-in-depth: the legacy (run_id, e_id) UNIQUE
    constraint on evidence_index is still in place and the code below
    never triggers it (we only INSERT a new evidence_index row when
    branch is `kept` or `cross_entity_kept`).
    """
    from uuid import uuid4

    from app.services.evidence_dedup import (
        ExistingEvidence,
        IncomingEvidence,
        compute_content_hash,
        decide,
    )

    if not pkg.evidence:
        return

    # ── Batched prefetch (Part 12.4) ────────────────────────────────────
    # The prior implementation ran up to TWO dedup-lookup SELECTs per
    # evidence row (~200+ round-trips/package). One DISTINCT ON query per
    # scope (same-entity / other-entity) fetches the EARLIEST matching
    # row per content_hash — identical to the old per-hash
    # `ORDER BY created_at ASC LIMIT 1` semantics.
    prepared: list[tuple[Any, list[str], Any, str, str, str]] = []
    for ev in pkg.evidence:
        # Filter ENTITY_PROFILE and non-subcap sentinels from linked list.
        # 2026-06-07 corpus: also enforce the `linked_subcap_ids`
        # VARCHAR(32)[] column width — some JSON-evidence variants
        # (SL Green 525-char, Kitsap 55-char) carry free text that starts
        # with `P1C…` and passes the shape regex but overflows the column,
        # aborting the ingest with StringDataRightTruncation.
        linked = [
            s for s in ev.subcap_mappings
            if re.match(r"^P[1-4]C\d", s) and len(s) <= 32
        ]
        # `evidence_index.e_id` is VARCHAR(16); bound a malformed long id
        # (Sunflower 58-char) so it doesn't truncate-error.
        e_id_bounded = str(ev.e_id)[:16] if ev.e_id else ev.e_id
        # Excerpt ladder (2026-07 stress-test fix): verbatim excerpt →
        # composed from the row's facts[] → '(no excerpt)' only when the
        # source genuinely carries neither. claim_type gets the same
        # treatment (signal_direction → first fact's claim_label).
        excerpt = (ev.excerpt or "").strip() \
            or _excerpt_from_facts(ev) or "(no excerpt)"
        claim = ev.signal_direction or _claim_label_from_facts(ev) \
            or "EVIDENCE"
        content_hash = compute_content_hash(
            source_url=ev.source_url,
            claim_type=claim,
            excerpt=excerpt,
        )
        prepared.append(
            (ev, linked, e_id_bounded, excerpt, claim, content_hash),
        )

    all_hashes = list({p[5] for p in prepared})
    same_map: dict[str, ExistingEvidence] = {}
    other_map: dict[str, ExistingEvidence] = {}
    for scope_same, target in ((True, same_map), (False, other_map)):
        op = "=" if scope_same else "<>"
        rows = (await session.execute(
            text(
                f"""
                SELECT DISTINCT ON (content_hash)
                       id::text AS evidence_id,
                       entity_id::text AS entity_id,
                       tier, content_hash
                  FROM evidence_index
                 WHERE content_hash = ANY(:hashes)
                   AND entity_id {op} CAST(:eid AS uuid)
                 ORDER BY content_hash, created_at ASC
                """
            ),
            {"hashes": all_hashes, "eid": str(entity_id)},
        )).all()
        for r in rows:
            target[r.content_hash] = ExistingEvidence(
                evidence_id=r.evidence_id, entity_id=r.entity_id,
                # NULL tier stays None (honest-absent; dedup treats it as
                # weakest) — the old `or 8` fabricated a tier.
                tier=int(r.tier) if r.tier is not None else None,
                content_hash=r.content_hash,
            )
    # Existing (run_id, e_id) rows — a re-ingest with CHANGED content
    # hits the ON CONFLICT (run_id, e_id) DO UPDATE path; the row keeps
    # its ORIGINAL id, so links must reference that id (never a fresh
    # client-generated one).
    _run_eid_rows = (await session.execute(
        text(
            "SELECT e_id, id::text AS id FROM evidence_index "
            "WHERE run_id = :rid"
        ),
        {"rid": run_id},
    )).all()
    run_eids: dict[str, str] = {r.e_id: r.id for r in _run_eid_rows}

    seen_hashes: set[str] = set()
    seen_hash_to_eid: dict[str, str] = {}
    # Pending flush buffers — one executemany per table after the loop.
    pending_inserts: dict[str, dict] = {}      # key: e_id (or synth key)
    pending_links: list[dict] = []
    pending_tier_updates: list[dict] = []
    pending_audits: list[dict] = []

    def _queue_insert(
        ev: Any, linked: list[str], e_id_bounded: Any,
        excerpt: str, claim: str, content_hash: str,
    ) -> str:
        """Queue one evidence_index INSERT; returns the row id the flush
        will materialize (existing id on (run_id, e_id) conflict)."""
        key = e_id_bounded if e_id_bounded else f"__none__{uuid4()}"
        if e_id_bounded and e_id_bounded in run_eids:
            new_id = run_eids[e_id_bounded]     # DO UPDATE keeps this id
        elif key in pending_inserts:
            new_id = pending_inserts[key]["id"]  # in-batch DO UPDATE twin
        else:
            new_id = str(uuid4())
        pending_inserts[key] = {
            "id": new_id,
            "rid": run_id, "eid": entity_id,
            "e": e_id_bounded,
            "sname": ev.source_name, "surl": ev.source_url,
            "exc": excerpt,
            "ct": claim[:32],
            # Canonical tier or NULL (evidence_index.tier is nullable per
            # migration 059; the check enforces [1, 7] OR NULL). The
            # normalize call is the last line of defense for hand-built
            # stubs that bypass EvidenceRow's validator.
            "tier": _normalize_tier(ev.tier),
            # recency = age of the evidence at assessment time (months) —
            # complete + stable freshness signal (not wall-clock drift).
            "rec": _recency_months(
                _publish_date_or_none(ev.publish_date), assessment_date,
            ),
            "pub": _publish_date_or_none(ev.publish_date),
            "linked": linked,
            "ch": content_hash,
        }
        return new_id

    for ev, linked, e_id_bounded, excerpt, claim, content_hash in prepared:
        incoming = IncomingEvidence(
            e_id=e_id_bounded,
            source_url=ev.source_url,
            claim_type=claim,
            excerpt=excerpt,
            tier=_normalize_tier(ev.tier),
            entity_id=str(entity_id),
            run_id=str(run_id),
        )
        existing_same = same_map.get(content_hash)
        existing_other = None
        if existing_same is None:
            existing_other = other_map.get(content_hash)

        decision = decide(
            incoming,
            existing_same_entity=existing_same,
            existing_other_entity=existing_other,
            seen_in_this_run=content_hash in seen_hashes,
        )

        kept_evidence_id: str | None = None

        if decision.action in ("kept", "cross_entity_kept"):
            # First sighting (or same hash owned by a DIFFERENT entity —
            # a new row scoped to THIS entity either way).
            kept_evidence_id = _queue_insert(
                ev, linked, e_id_bounded, excerpt, claim, content_hash,
            )
            pending_links.append(
                {"e": kept_evidence_id, "rid": run_id, "fs": True},
            )
            seen_hashes.add(content_hash)
            seen_hash_to_eid[content_hash] = kept_evidence_id

        elif decision.action == "dedup_same_entity":
            kept_evidence_id = decision.kept_evidence_id
            if kept_evidence_id:
                pending_links.append(
                    {"e": kept_evidence_id, "rid": run_id, "fs": False},
                )

        elif decision.action == "tier_upgrade":
            kept_evidence_id = decision.kept_evidence_id
            # decide() only emits tier_upgrade with a canonical incoming
            # tier; normalize is belt-and-suspenders for hand-built stubs.
            new_tier = _normalize_tier(decision.upgraded_tier_to)
            if kept_evidence_id and new_tier is not None:
                pending_tier_updates.append(
                    {"new_tier": new_tier, "eid": kept_evidence_id},
                )
                pending_links.append(
                    {"e": kept_evidence_id, "rid": run_id, "fs": False},
                )
                # Mirror the old read-your-own-writes behavior: a second
                # row with this hash must see the upgraded tier.
                if content_hash in same_map:
                    same_map[content_hash] = ExistingEvidence(
                        evidence_id=same_map[content_hash].evidence_id,
                        entity_id=same_map[content_hash].entity_id,
                        tier=new_tier,
                        content_hash=content_hash,
                    )

        elif decision.action == "duplicate_within_run":
            # Already seen earlier in this same run — skip.
            kept_evidence_id = seen_hash_to_eid.get(content_hash)

        # Always write a dedup_audit row.
        pending_audits.append({
            "rid": run_id, "se": str(ev.e_id)[:32],
            "ke": kept_evidence_id or "",
            "act": decision.action, "rsn": decision.reason[:1000],
            "ch": content_hash,
        })

    # ── Flush (Part 12.4): 4 executemany statements replace the prior
    # per-row INSERT/UPDATE round-trips. Order matters: evidence rows
    # first (links + audits FK them), then tier updates, links, audits.
    if pending_inserts:
        await session.execute(
            text(
                """
                INSERT INTO evidence_index (
                    id, run_id, entity_id, e_id, source_name, source_url,
                    excerpt, claim_type, tier, recency_months,
                    published_date, linked_subcap_ids, content_hash
                ) VALUES (
                    CAST(:id AS uuid), :rid, :eid, :e, :sname, :surl,
                    :exc, :ct, :tier, :rec,
                    :pub, :linked, :ch
                )
                ON CONFLICT (run_id, e_id) DO UPDATE SET
                    source_name = EXCLUDED.source_name,
                    source_url = EXCLUDED.source_url,
                    excerpt = EXCLUDED.excerpt,
                    tier = EXCLUDED.tier,
                    published_date = EXCLUDED.published_date,
                    linked_subcap_ids = EXCLUDED.linked_subcap_ids,
                    content_hash = EXCLUDED.content_hash
                """
            ),
            list(pending_inserts.values()),
        )
    if pending_tier_updates:
        await session.execute(
            text(
                """
                UPDATE evidence_index
                   SET tier = :new_tier
                 WHERE id = CAST(:eid AS uuid)
                """
            ),
            pending_tier_updates,
        )
    if pending_links:
        await session.execute(
            text(
                """
                INSERT INTO evidence_run_links (
                    evidence_id, run_id, first_seen_in_run, surfaces_in_run
                ) VALUES (
                    CAST(:e AS uuid), :rid, :fs, '{}'
                )
                ON CONFLICT (evidence_id, run_id) DO NOTHING
                """
            ),
            pending_links,
        )
    if pending_audits:
        await session.execute(
            text(
                """
                INSERT INTO dedup_audit (
                    run_id, source_e_id, kept_evidence_id, action, reason,
                    content_hash
                ) VALUES (
                    :rid, :se,
                    CASE WHEN :ke = '' THEN NULL ELSE CAST(:ke AS uuid) END,
                    :act, :rsn, :ch
                )
                """
            ),
            pending_audits,
        )


async def _lookup_existing_evidence(
    session: AsyncSession, *, content_hash: str, entity_id: Any, same_entity: bool,
):
    """Return an ExistingEvidence dataclass or None."""
    from app.services.evidence_dedup import ExistingEvidence

    if same_entity:
        sql = """
            SELECT id::text AS evidence_id, entity_id::text AS entity_id,
                   tier, content_hash
              FROM evidence_index
             WHERE content_hash = :ch
               AND entity_id = CAST(:eid AS uuid)
             ORDER BY created_at ASC
             LIMIT 1
        """
        params = {"ch": content_hash, "eid": str(entity_id)}
    else:
        sql = """
            SELECT id::text AS evidence_id, entity_id::text AS entity_id,
                   tier, content_hash
              FROM evidence_index
             WHERE content_hash = :ch
               AND entity_id <> CAST(:eid AS uuid)
             ORDER BY created_at ASC
             LIMIT 1
        """
        params = {"ch": content_hash, "eid": str(entity_id)}
    row = (await session.execute(text(sql), params)).first()
    if row is None:
        return None
    return ExistingEvidence(
        evidence_id=row.evidence_id, entity_id=row.entity_id,
        tier=int(row.tier) if row.tier is not None else None,
        content_hash=row.content_hash,
    )


async def _insert_evidence_row(
    session: AsyncSession, *, run_id: Any, entity_id: Any, ev: Any,
    linked: list[str], excerpt: str, content_hash: str,
    assessment_date: Any = None,
) -> str:
    """INSERT one evidence_index row and return its UUID as str.

    Falls back to ON CONFLICT (run_id, e_id) DO UPDATE as defense-in-depth.
    """
    row = (
        await session.execute(
            text(
                """
                INSERT INTO evidence_index (
                    run_id, entity_id, e_id, source_name, source_url,
                    excerpt, claim_type, tier, recency_months,
                    published_date, linked_subcap_ids, content_hash
                ) VALUES (
                    :rid, :eid, :e, :sname, :surl, :exc, :ct, :tier, :rec,
                    :pub, :linked, :ch
                )
                ON CONFLICT (run_id, e_id) DO UPDATE SET
                    source_name = EXCLUDED.source_name,
                    source_url = EXCLUDED.source_url,
                    excerpt = EXCLUDED.excerpt,
                    tier = EXCLUDED.tier,
                    published_date = EXCLUDED.published_date,
                    linked_subcap_ids = EXCLUDED.linked_subcap_ids,
                    content_hash = EXCLUDED.content_hash
                RETURNING id::text AS id
                """
            ),
            {
                # Column widths (migration 003): e_id VARCHAR(16),
                # claim_type VARCHAR(32). Bound both defensively so a
                # malformed long id (Sunflower 58-char) or claim string
                # can't abort the ingest with StringDataRightTruncation.
                "rid": run_id, "eid": entity_id,
                "e": (str(ev.e_id)[:16] if ev.e_id else ev.e_id),
                "sname": ev.source_name, "surl": ev.source_url,
                "exc": excerpt,
                "ct": (ev.signal_direction or "EVIDENCE")[:32],
                # Canonical tier or NULL. EvidenceRow's validator already
                # normalizes, but a hand-built stub (tests) or future
                # non-schema path could carry a raw out-of-taxonomy tier;
                # this is the last line of defense — honest NULL, never a
                # clamped/fabricated value.
                "tier": _normalize_tier(ev.tier),
                # recency = age of the evidence at assessment time (months), so
                # the freshness signal is complete + stable (not wall-clock drift).
                "rec": _recency_months(_publish_date_or_none(ev.publish_date), assessment_date),
                "pub": _publish_date_or_none(ev.publish_date),
                "linked": linked,
                "ch": content_hash,
            },
        )
    ).first()
    return row.id if row else ""


async def _link_evidence_to_run(
    session: AsyncSession, *, evidence_id: str, run_id: Any, first_seen: bool,
) -> None:
    """UPSERT evidence_run_links row (first_seen_in_run sticky on True)."""
    await session.execute(
        text(
            """
            INSERT INTO evidence_run_links (
                evidence_id, run_id, first_seen_in_run, surfaces_in_run
            ) VALUES (
                CAST(:e AS uuid), :rid, :fs, '{}'
            )
            ON CONFLICT (evidence_id, run_id) DO NOTHING
            """
        ),
        {"e": evidence_id, "rid": run_id, "fs": first_seen},
    )


async def _insert_dedup_audit(
    session: AsyncSession, *, run_id: Any, source_e_id: str,
    kept_evidence_id: str | None, action: str, reason: str,
    content_hash: str,
) -> None:
    await session.execute(
        text(
            """
            INSERT INTO dedup_audit (
                run_id, source_e_id, kept_evidence_id, action, reason,
                content_hash
            ) VALUES (
                :rid, :se,
                CASE WHEN :ke = '' THEN NULL ELSE CAST(:ke AS uuid) END,
                :act, :rsn, :ch
            )
            """
        ),
        {
            "rid": run_id, "se": source_e_id[:32],
            "ke": kept_evidence_id or "",
            "act": action, "rsn": reason[:1000], "ch": content_hash,
        },
    )


_VALID_INSIGHT_SEVERITY = frozenset({"critical", "high", "medium", "low"})


def _clean_e_ids(raw: Any) -> list[str]:
    """Normalize a linked_e_ids list for the varchar(16)[] column.

    Real corpus defect (Sunflower Bank, 2026-06-10): one array element
    arrived as a comma-joined blob of fact refs
    ('E-009:F1, E-009:F2, E-016:F1, …', 58 chars) — asyncpg raised
    StringDataRightTruncationError and the WHOLE package failed persist
    (the only scored fixture that didn't ingest). Split each element on
    commas/semicolons, strip whitespace, drop empties, truncate to the
    column width, and dedupe preserving order.
    """
    out: list[str] = []
    seen: set[str] = set()
    for item in (raw or []):
        for part in str(item).replace(";", ",").split(","):
            v = part.strip()[:16]
            if v and v not in seen:
                seen.add(v)
                out.append(v)
    return out


async def _persist_insight_cards(
    session: AsyncSession,
    *,
    run_id: Any,
    entity_id: Any,
    pkg: Any,
) -> int:
    """Persist `pkg.insight_cards` into the `insight_cards` table.

    Idempotent: DELETE by run_id then INSERT. Rows with an invalid
    severity or empty linked_subcap_id (the NOT NULL anchor) are skipped
    defensively so a malformed finding can't abort the whole ingest.
    """
    cards = getattr(pkg, "insight_cards", None)
    # Always clear stale rows for this run so a re-ingest that now yields
    # fewer/zero insights doesn't leak the previous run's cards.
    await session.execute(
        text("DELETE FROM insight_cards WHERE run_id = :rid"),
        {"rid": run_id},
    )
    if not cards:
        return 0
    # Batched (Part 12.4): one executemany for the whole card set.
    _card_rows: list[dict] = []
    for c in cards:
        sev = (c.severity or "").lower()
        if not c.linked_subcap_id:
            # `linked_subcap_id` is the NOT NULL anchor — a card without it
            # genuinely cannot be inserted, so this is the one case we skip.
            continue
        if sev not in _VALID_INSIGHT_SEVERITY:
            # Clamp an unrecognised severity to a safe valid value instead of
            # dropping the card. A stray severity (e.g. a new deriver label not
            # yet threaded through the DB CHECK `insight_cards_severity_chk`)
            # must never silently empty an entity's Insights surface and fail
            # the completeness gate / block the deploy.
            log.warning("insight_card.severity_clamped",
                        ic_id=getattr(c, "ic_id", None), severity=c.severity)
            sev = "medium"
        _card_rows.append({
            "rid": run_id, "eid": entity_id,
            "ic": c.ic_id[:16], "sev": sev, "t": c.title,
            "what": c.what_text or "", "why": c.why_text or "",
            "sw": c.so_what_text or "", "sub": c.linked_subcap_id[:32],
            "eids": _clean_e_ids(c.linked_e_ids),
            # The rec this card was derived from (D2 callout); None for
            # section-analysis / category-gap derived cards.
            "src": (c.source_rec_id[:16]
                    if getattr(c, "source_rec_id", None) else None),
        })
    if _card_rows:
        await session.execute(
            text(
                """
                INSERT INTO insight_cards (
                    run_id, entity_id, ic_id, severity, title,
                    what_text, why_text, so_what_text, linked_subcap_id,
                    linked_e_ids, source_rec_id
                ) VALUES (
                    :rid, :eid, :ic, :sev, :t, :what, :why, :sw, :sub,
                    CAST(:eids AS varchar[]), :src
                )
                ON CONFLICT (run_id, ic_id) DO NOTHING
                """
            ),
            _card_rows,
        )
    return len(_card_rows)


async def _persist_document_sections(
    session: AsyncSession,
    *,
    run_id: Any,
    entity_id: Any,
    pkg: Any,
) -> int:
    """Persist `pkg.report_sections` rows into document_sections +
    document_lineage + document_evidence_items.

    State-branch contract:
      - no_sections     → no DOCX in the package → returns 0; no rows written.
      - re_ingest       → existing rows for this run_id are deleted first
                          so an idempotent re-ingest doesn't accumulate
                          duplicate sections.
      - lineage_full    → every section gets one lineage row per pillar /
                          subcap_id / E-ID mentioned.
      - lineage_partial → no subcap/E-ID matches; only the pillar lineage
                          for pillar_deep_dive_* kinds is emitted.

    Idempotency: we DELETE by run_id then INSERT. This is safer than
    UPSERT here because (run_id, ordinal) is the natural key but
    re-parsing the DOCX with a different ordinal layout would otherwise
    leak stale rows.
    """
    if not getattr(pkg, "report_sections", None):
        return 0

    # Wipe prior rows for this run so re-ingest is idempotent.
    await session.execute(
        text("DELETE FROM document_sections WHERE run_id = :rid"),
        {"rid": run_id},
    )

    # Batched (Part 12.4): section ids are generated CLIENT-side so the
    # section / lineage / evidence-item triple flushes as three
    # executemany statements instead of ~3 round-trips per section.
    from uuid import uuid4

    _sec_rows: list[dict] = []
    _lineage_rows: list[dict] = []
    _ev_item_rows: list[dict] = []
    pillar_map = {
        "pillar_deep_dive_p1": "P1",
        "pillar_deep_dive_p2": "P2",
        "pillar_deep_dive_p3": "P3",
        "pillar_deep_dive_p4": "P4",
    }
    for s in pkg.report_sections:
        section_id = str(uuid4())
        _sec_rows.append({
            "id": section_id,
            "rid": run_id, "eid": entity_id,
            "kind": s.kind, "ord": s.ordinal,
            "h": s.heading or None, "body": s.body,
            "pg": s.page_number,
            "sp": s.source_path or "unknown.docx",
        })

        # Lineage: pillar_id (for pillar deep-dives), subcap_id (when
        # mentioned), E-ID (when mentioned), plus a section-kind-keyed
        # lineage row so section_routing can pick by kind.
        lineage_inserts: list[tuple[str, str]] = [
            ("section_kind", s.kind),
        ]
        if s.kind in pillar_map:
            lineage_inserts.append(("pillar_id", pillar_map[s.kind]))
        for sid in (s.subcap_ids_mentioned or []):
            lineage_inserts.append(("subcap_id", sid))
        for e in (s.e_ids_mentioned or []):
            lineage_inserts.append(("e_id", e))
        _lineage_rows.extend(
            {"sid": section_id, "tt": tt, "tr": tr[:64]}
            for tt, tr in lineage_inserts
        )

        # document_evidence_items — one row per cited E-ID for the
        # EvidenceDrawer cross-reference.
        _ev_item_rows.extend(
            {"sid": section_id, "e": e[:16]}
            for e in (s.e_ids_mentioned or [])
        )

    if _sec_rows:
        await session.execute(
            text(
                """
                INSERT INTO document_sections (
                    id, run_id, entity_id, section_kind, ordinal,
                    heading, body, page_number, source_path
                ) VALUES (
                    CAST(:id AS uuid), :rid, :eid, :kind, :ord,
                    :h, :body, :pg, :sp
                )
                """
            ),
            _sec_rows,
        )
    if _lineage_rows:
        await session.execute(
            text(
                """
                INSERT INTO document_lineage (
                    section_id, target_type, target_ref
                ) VALUES (CAST(:sid AS uuid), :tt, :tr)
                """
            ),
            _lineage_rows,
        )
    if _ev_item_rows:
        await session.execute(
            text(
                """
                INSERT INTO document_evidence_items (
                    section_id, e_id, quoted_excerpt
                ) VALUES (CAST(:sid AS uuid), :e, NULL)
                """
            ),
            _ev_item_rows,
        )

    return len(_sec_rows)


async def _persist_focus_areas(
    session: AsyncSession,
    *,
    run_id: Any,
    entity_id: Any,
    pkg: Any,
) -> int:
    """Persist `pkg.focus_areas` rows into the focus_areas table
    (migration 018 schema, reconciled in 023).

    Schema (migration 018 / 023):
        title TEXT NOT NULL,
        verbatim_quote TEXT NOT NULL,
        source_path TEXT,
        page_number INTEGER,
        involved_subcap_ids TEXT[] NOT NULL DEFAULT '{}',

    State-branch contract:
      - no_focus_areas → pkg.focus_areas empty → returns 0; no rows
                         written (silent; not every DMA package ships
                         a Client_Profile DOCX).
      - re_ingest      → existing rows for this run_id are DELETEd
                         first so an idempotent re-ingest doesn't
                         accumulate duplicate focus areas. Matches
                         the pattern in _persist_document_sections.

    Idempotency: DELETE by run_id then INSERT — re-parsing the same
    package re-creates the same rows without unique-constraint
    surprises. The natural key here would be (run_id, title) but
    titles can repeat across multiple DOCX shapes ("Top Findings"
    vs "Critical Gaps"), so we don't enforce uniqueness; DELETE
    handles dedup.
    """
    rows = getattr(pkg, "focus_areas", None) or []
    if not rows:
        return 0

    await session.execute(
        text("DELETE FROM focus_areas WHERE run_id = :rid"),
        {"rid": run_id},
    )

    # Batched (Part 12.4): one executemany for the whole set.
    _fa_rows = [
        {
            "rid": run_id,
            "eid": entity_id,
            "title": fa.title,
            "vq": fa.verbatim_quote,
            # source_path is NOT NULL in the reconciled schema (migration
            # 023). The Client Profile parser leaves it None when no
            # E-ID column / source regex matched — fall back to a
            # sentinel so the row persists instead of 500ing the whole
            # ingest. Surfaced by the AlmaBank live ingest replay in
            # the 2026-06 deployment QA.
            "sp": fa.source_path or "(unknown)",
            "pg": fa.page_number,
            # Pass a Python list directly — asyncpg encodes it as
            # TEXT[] (matches issue_register.linked_subcap_ids
            # pattern at L605). Empty list is fine — column has
            # NOT NULL DEFAULT '{}' (migration 018 L297).
            "isids": list(fa.involved_subcap_ids or []),
        }
        for fa in rows
    ]
    if _fa_rows:
        await session.execute(
            text(
                """
                INSERT INTO focus_areas (
                    run_id, entity_id, title, verbatim_quote,
                    source_path, page_number, involved_subcap_ids
                ) VALUES (
                    :rid, :eid, :title, :vq, :sp, :pg, :isids
                )
                """
            ),
            _fa_rows,
        )

    return len(_fa_rows)


async def publish_post_commit(
    *,
    db_run_id: str,
    entity_id: Any,
    request_id: str,
    ccg_catalog_version: str,
    is_rerun: bool = False,
    parent_request_id: str | None = None,
    publisher=None,
) -> tuple[bool, str | None, str | None]:
    """Fire `dma.ingest.completed` to Pub/Sub. Best-effort.

    State branches (see module docstring): publish_succeeds /
    publish_fails_topic_missing / publish_fails_auth_missing /
    publish_disabled_in_dev / publish_timeout. Caller commits BEFORE
    invoking this; we never gate ingest success on publish success.

    `publisher` is the injectable awaitable (defaults to
    ``pubsub_publisher.publish_ingest_completed``) so tests can stub.
    """
    from datetime import UTC, datetime

    from app.services.pubsub_publisher import (
        IngestCompletedEnvelope,
        publish_ingest_completed,
    )

    envelope = IngestCompletedEnvelope(
        run_id=str(db_run_id),
        entity_id=str(entity_id),
        request_id=request_id,
        ccg_catalog_version=ccg_catalog_version,
        completed_at=datetime.now(tz=UTC).isoformat(),
        is_rerun=is_rerun,
        parent_request_id=parent_request_id,
    )
    pub = publisher or publish_ingest_completed
    try:
        result = await pub(envelope)
    except Exception as e:
        # Never raise from a fire-and-forget publish.
        log.warning("pubsub.publish.outer_failed", err=str(e), run_id=request_id)
        result = (False, None, "outer_error")

    # ── Synthesis-cache invalidation ─────────────────────────────────
    # A new run for this entity invalidates the entity's prior cache
    # rows lazily (RERUN_INVALIDATE_ALL gate). Best-effort: if the
    # cache DB is down OR the synthesis_cache module isn't deployed
    # yet, log + continue — ingest never wedges on audit-layer issues.
    #
    # State branches:
    #   cache_present  → entity rows tagged invalidated; next read
    #                    sees CACHE_HIT_INVALIDATED + re-synthesizes.
    #   cache_empty    → mark_invalidated returns 0; no-op.
    #   cache_down     → safe wrapper logs; returns 0; ingest proceeds.
    try:
        from app.services.synthesis_cache_db import (
            resolve_entity_display_id,
            safe_mark_invalidated,
        )
        from app.services.synthesis_orchestrator import (
            build_invalidation_for_new_run,
        )
        # A rerun re-scores the WHOLE entity, so invalidate the entity-level
        # rows AND every one of its subcap rows. Subcap rows are keyed
        # ``{display_id}:{subcap_id}:…`` so we invalidate by display_id PREFIX
        # (2026-07-14 audit: the prior affected_subcap_ids=None left every
        # per-subcap narrative/enrichment stale until a catalogue bump).
        display_id = resolve_entity_display_id(str(entity_id))
        specs = build_invalidation_for_new_run(
            entity_id=str(entity_id),
            entity_display_id=display_id,
        )
        for spec in specs:
            safe_mark_invalidated(spec)
    except Exception as e:
        # Defense in depth — even the wrapper's import could fail.
        log.warning(
            "synthesis_cache.invalidate_after_ingest_failed",
            err=str(e), entity_id=str(entity_id),
        )

    # ── PRD §17 feedback loop ────────────────────────────────────────
    # Write the 5 feedback files back to the entity's Drive folder so
    # the next bot iteration can incorporate Insights-side decisions
    # (thin-evidence flagging, freshness alerts, narrative overrides,
    # waivers). Best-effort: any failure surfaces an audit row +
    # warning but never blocks ingest.
    #
    # State branches (returned in audit_log.after_json):
    #   drive_folder_unknown   → entity has no drive_folder_id
    #   dev_skip               → env != prod/staging (local dev)
    #   upload_ok              → all 5 files accepted by Drive
    #   upload_failed          → at least one upload errored
    #   drive_perms_missing    → SA lost write access (re-share folder)
    try:
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.database import get_engine
        engine = get_engine()
        async with engine.connect() as conn:
            row = await conn.execute(
                text(
                    "SELECT drive_folder_id FROM entities WHERE id = :eid"
                ),
                {"eid": str(entity_id)},
            )
            mapping = row.mappings().first()
            drive_folder_id = mapping["drive_folder_id"] if mapping else None
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as fb_session:
            await write_drive_feedback(
                session=fb_session,
                db_run_id=str(db_run_id),
                entity_id=str(entity_id),
                drive_folder_id=drive_folder_id,
            )
            await fb_session.commit()
    except Exception as e:
        # Outer guard — ingest is committed, do not raise.
        log.warning(
            "drive_feedback.outer_wiring_failed",
            run_id=request_id, err=str(e)[:240],
        )

    return result


async def write_drive_feedback(
    *,
    session: Any,
    db_run_id: str,
    entity_id: Any,
    drive_folder_id: str | None,
    env: str | None = None,
    drive_upserter=None,
) -> dict[str, Any]:
    """Phase 0 feedback loop — PRD §17. Writes the 5 feedback files
    back to the entity's Drive folder so the next bot iteration can
    incorporate Insights-side decisions.

    Best-effort: any failure surfaces a warning + audit_log row but
    never blocks ingest. Caller invokes from publish_post_commit as a
    sibling to the Pub/Sub fan-out.

    Returns the state-dict from `FeedbackWriteResult.model_dump()` so
    the caller can write it straight into the audit_log after_json
    column.
    """
    try:
        from app.config import get_settings
        from app.services.drive_feedback import write_feedback_files
        settings = get_settings()
        effective_env = env or getattr(settings, "env", "prod")
        result = await write_feedback_files(
            session=session,
            db_run_id=str(db_run_id),
            entity_id=str(entity_id),
            drive_folder_id=drive_folder_id,
            env=effective_env,
            drive_upserter=drive_upserter,
        )
        payload = result.model_dump()
        log.info(
            "drive_feedback.complete",
            run_id=str(db_run_id), state=payload.get("state"),
            written=len(payload.get("written") or []),
            failed=len(payload.get("failed") or []),
        )
        # Best-effort audit row. Failures here don't escalate.
        try:
            # audit_log canonical column shape (migration 006):
            #   action, resource_type, resource_id, actor_email,
            #   before_json, after_json
            await session.execute(
                text(
                    """
                    INSERT INTO audit_log (
                        action, resource_type, resource_id,
                        actor_email, before_json, after_json
                    ) VALUES (
                        'drive_feedback_written', 'run', :rid,
                        'system', NULL, CAST(:after AS JSONB)
                    )
                    """
                ),
                {
                    "rid": str(db_run_id),
                    "after": json.dumps(payload),
                },
            )
        except Exception as audit_err:
            log.warning(
                "drive_feedback.audit_write_failed",
                err=str(audit_err)[:200],
            )
        return payload
    except Exception as e:
        log.warning(
            "drive_feedback.outer_failed",
            run_id=str(db_run_id), err=str(e)[:240],
        )
        return {"state": "upload_failed", "error_kind": type(e).__name__,
                "error_message": str(e)[:200]}


def _conf_to_float(s: str | None) -> float | None:
    if not s:
        return None
    table = {"HIGH": 0.9, "MEDIUM": 0.6, "MED": 0.6, "LOW": 0.3}
    return table.get(s.strip().upper())


def _recency_months(pub, ref) -> int | None:
    """Months between a published date and the reference (assessment) date.
    Populates evidence_index.recency_months so freshness banding has an explicit
    age signal (not just published_date), frozen at assessment time."""
    from datetime import date, datetime
    if not pub:
        return None
    r = ref
    if isinstance(r, str):
        try:
            r = datetime.fromisoformat(r[:10]).date()
        except ValueError:
            r = None
    if not isinstance(r, date):
        r = date.today()
    return max(0, (r.year - pub.year) * 12 + (r.month - pub.month))


def _publish_date_or_none(v: str | None):
    """Tolerant date parse — '2024', '2024-06', '2024-06-30' all valid."""
    if not v:
        return None
    s = v.strip()
    if not s:
        return None
    from datetime import date
    parts = s.split("-")
    try:
        y = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 1
        d = int(parts[2]) if len(parts) > 2 else 1
        return date(y, m, d)
    except (ValueError, IndexError):
        return None


async def _persist_platform_scores(
    session: Any,
    *,
    run_id: Any,
    entity_id: Any,
) -> int:
    """Compute Fit Score + Readiness Index + prereq snapshot for the 5
    documented platforms and persist them to `platform_scores`.

    Idempotent via UNIQUE (run_id, platform_id): a re-ingest UPSERTs.

    Returns the number of platform rows written.

    Why persist at ingest time:
      1. Cross-user reads stay fast (no LLM/heavy compute on hot path).
      2. The intelligence_builder.platform_story surface joins
         platform_scores; without persisted rows it would always 404.
      3. Audit / forensic value — we can see exactly what fit score the
         AE saw when they made a decision, even if the underlying
         catalogue or insight severities change later.
    """
    # From app.services.platform_display, NOT app.routers.platforms:
    # the router imports fastapi, which the workers image does not
    # install (2026-06-10: that import crashed every Drive folder
    # persist with ModuleNotFoundError on the live backfill job).
    from app.services.platform_display import PLATFORM_DISPLAY
    from app.services.platform_fit import (
        SubcapForFit,
        compute_platform_fit,
    )
    from app.services.platform_prerequisites import prerequisites_for
    from app.services.readiness_index import (
        aggregate_readiness,
        evaluate_prereq,
    )

    # Reconstruct fit inputs from the persisted subcap_scores. This is
    # the same shape the API endpoint builds — we just do it once at
    # ingest instead of every request.
    sc_rows = (
        await session.execute(
            text(
                """
                SELECT s.subcap_id, s.score, s.platform_tags
                FROM subcap_scores s
                WHERE s.run_id = :rid
                """
            ),
            {"rid": run_id},
        )
    ).all()

    if not sc_rows:
        return 0

    # Insight severities per subcap → drives `priority_weight`.
    # `insight_cards` has `linked_subcap_id` (single, per migration 004),
    # not `affected_subcap_ids` (array). Read the singleton column so the
    # platform-fit aggregator gets accurate severity buckets per subcap.
    insight_rows = (
        await session.execute(
            text(
                """
                SELECT severity, linked_subcap_id AS sid
                FROM insight_cards
                WHERE run_id = :rid AND linked_subcap_id IS NOT NULL
                """
            ),
            {"rid": run_id},
        )
    ).all()
    sev_by_subcap: dict[str, list[str]] = {}
    for r in insight_rows:
        sev = (r.severity or "medium").lower()
        sev_by_subcap.setdefault(r.sid, []).append(sev)

    fit_inputs = [
        SubcapForFit(
            subcap_id=r.subcap_id,
            current_score=float(r.score) if r.score is not None else 0.0,
            platform_ids=list(r.platform_tags or []),
            linked_insight_severities=sev_by_subcap.get(r.subcap_id, []),
        )
        for r in sc_rows
    ]
    scores_by_subcap = {r.subcap_id: float(r.score or 0.0) for r in sc_rows}

    platform_ids = list(PLATFORM_DISPLAY.keys())
    fit_rows = compute_platform_fit(fit_inputs, platform_ids)

    inserted = 0
    for fit in fit_rows:
        prereq_specs = prerequisites_for(fit.platform_id)
        prereq_checks = [
            evaluate_prereq(
                name=str(p["name"]),
                required_subcap_id=str(p["required_subcap_id"]),
                threshold=float(p["threshold"]),
                scores_by_subcap=scores_by_subcap,
            )
            for p in prereq_specs
        ]
        readiness = aggregate_readiness(prereq_checks)
        state = "READY" if fit.addressable_subcap_ids else "INSUFFICIENT_EVIDENCE"
        await session.execute(
            text(
                """
                INSERT INTO platform_scores (
                    run_id, entity_id, platform_id, fit_score,
                    readiness_index, prerequisite_checks,
                    addressable_subcap_ids, state, computed_at
                ) VALUES (
                    :rid, :eid, :pid, :fit, :readiness,
                    CAST(:prereqs AS JSONB),
                    CAST(:asids AS VARCHAR[]),
                    :state, NOW()
                )
                ON CONFLICT (run_id, platform_id) DO UPDATE SET
                    fit_score = EXCLUDED.fit_score,
                    readiness_index = EXCLUDED.readiness_index,
                    prerequisite_checks = EXCLUDED.prerequisite_checks,
                    addressable_subcap_ids = EXCLUDED.addressable_subcap_ids,
                    state = EXCLUDED.state,
                    computed_at = NOW()
                """
            ),
            {
                "rid": run_id,
                "eid": entity_id,
                "pid": fit.platform_id,
                "fit": fit.fit_score,
                "readiness": readiness,
                "prereqs": json.dumps(prereq_specs),
                "asids": fit.addressable_subcap_ids,
                "state": state,
            },
        )
        inserted += 1

    return inserted
