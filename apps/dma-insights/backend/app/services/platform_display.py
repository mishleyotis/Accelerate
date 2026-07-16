"""Static display names + pillar mappings for the 5 documented platforms.

Lives in services (framework-free) rather than `app.routers.platforms`
because the WORKER persist path (`package_persist._persist_platform_scores`)
needs it at ingest time — and `app.routers.*` imports `fastapi`, which the
lean workers image does not install (2026-06-10 live incident: every
Drive folder ingest crashed with `ModuleNotFoundError: No module named
'fastapi'`). The router imports from here; never the other way around
(pinned by tests/test_worker_import_safety.py).
"""
from __future__ import annotations

# `short` mirrors the wireframe PLATFORMS table (docs/wireframe-2026-06/
# src/01_data.js) — the abbreviation rendered in the entity-card top-OSS
# chip ("SF 82"). Keep in lockstep with the prototype.
PLATFORM_DISPLAY: dict[str, dict[str, str]] = {
    "salesforce": {"name": "Salesforce", "pillar": "P2", "short": "SF"},
    "databricks": {"name": "Databricks", "pillar": "P4", "short": "DB"},
    "tableau":    {"name": "Tableau", "pillar": "P4", "short": "TBL"},
    "twilio":     {"name": "Twilio", "pillar": "P2", "short": "TW"},
    "ncino":      {"name": "nCino", "pillar": "P3", "short": "nC"},
}

# Plain-language CAPABILITY descriptor per platform — the semantic target the
# platform-fit engine's cross-encoder scores each candidate sub-capability
# against (platform_fit.compute_platform_fit_v2 semantic_fit_by_platform).
# Keyword tags remain the recall prior; this lets NLP judge whether a platform
# genuinely ADDRESSES a sub-capability rather than trusting a catalogue keyword.
PLATFORM_CAPABILITY: dict[str, str] = {
    "salesforce": (
        "Salesforce customer relationship management: sales, service and "
        "marketing automation, a unified customer 360 profile, case and "
        "opportunity management, personalized cross-channel engagement."),
    "databricks": (
        "Databricks unified data lakehouse: large-scale data engineering, "
        "governed data pipelines, machine learning and advanced analytics on a "
        "single platform for data and AI."),
    "tableau": (
        "Tableau business intelligence: self-service analytics, interactive "
        "dashboards, data visualization and reporting to support "
        "decision-making across the organization."),
    "twilio": (
        "Twilio programmable customer communications: messaging, voice, email "
        "and real-time engagement APIs for omnichannel customer contact and "
        "notifications."),
    "ncino": (
        "nCino cloud banking operating system: loan origination, credit "
        "workflow, account opening, and end-to-end banking operations and "
        "process automation."),
}


def platform_capability(platform_id: str) -> str:
    """Semantic descriptor for a platform_id (empty string when unmapped)."""
    return PLATFORM_CAPABILITY.get(platform_id, "")


def platform_short(platform_id: str) -> str:
    """Wireframe abbreviation for a platform_id; falls back to an
    upper-cased 3-char slice for any unmapped id (forward-compatible
    with catalogue additions)."""
    row = PLATFORM_DISPLAY.get(platform_id)
    if row and row.get("short"):
        return row["short"]
    return (platform_id or "?")[:3].upper()
