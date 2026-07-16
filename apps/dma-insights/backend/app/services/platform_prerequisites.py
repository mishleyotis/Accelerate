"""Platform prerequisite definitions.

For each of the 5 documented platforms (Salesforce / Databricks / Tableau /
Twilio / nCino), this module defines the structured prerequisite checks that
drive the readiness traffic light on the D4 Platform page.

The schema is intentionally lightweight: each prerequisite is
`{name, required_subcap_id, threshold}`. A prereq is MET if the entity's
current score on `required_subcap_id` is >= threshold, PARTIAL if within
0.5, otherwise UNMET. Aggregation: all MET → green, any UNMET → red,
mixed → amber. (See `readiness_index.aggregate_readiness`.)

These prerequisites are persisted into `platform_scores.prerequisite_checks`
at ingest time so the API and UI don't have to recompute them on every
request — and so an analyst editing the DB can see exactly which subcap
threshold drove a particular readiness verdict.

The threshold values are intentionally conservative (M3 = 3.0 — "Established")
based on the v7.0 maturity descriptors. Tuning is admin-editable later.
"""
from __future__ import annotations

# Prerequisite subcap thresholds per platform. The required_subcap_ids
# are v7.0 IDs; if the run is on an older catalogue, the CatalogueResolver
# bridges them via ccg_subcap_aliases at evaluate time.
#
# Picks reflect the practical prereq for a successful Zennify deployment:
#   - Salesforce CRM → needs basic customer-data + sales-process maturity
#   - Databricks Lakehouse → needs data-platform fundamentals
#   - Tableau / analytics → needs governed data + BI literacy
#   - Twilio messaging → needs CX engagement + compliance basics
#   - nCino lending → needs loan-origination + commercial-lending maturity
PLATFORM_PREREQUISITES: dict[str, list[dict[str, str | float]]] = {
    "salesforce": [
        {
            "name": "Customer data foundation",
            "required_subcap_id": "P4C1.1.1",
            "threshold": 3.0,
        },
        {
            "name": "Sales process digitization",
            "required_subcap_id": "P2C1.1.1",
            "threshold": 2.5,
        },
        {
            "name": "Identity & access management",
            "required_subcap_id": "P1C2.2.1",
            "threshold": 2.5,
        },
    ],
    "databricks": [
        {
            "name": "Data lake / lakehouse foundation",
            "required_subcap_id": "P4C1.1.2",
            "threshold": 2.5,
        },
        {
            "name": "Data governance",
            "required_subcap_id": "P4C2.1.1",
            "threshold": 2.5,
        },
        {
            "name": "Cloud infrastructure baseline",
            "required_subcap_id": "P3C1.1.1",
            "threshold": 2.5,
        },
    ],
    "tableau": [
        {
            "name": "Governed reporting layer",
            "required_subcap_id": "P4C2.1.1",
            "threshold": 2.5,
        },
        {
            "name": "BI / analytics literacy",
            "required_subcap_id": "P4C3.1.1",
            "threshold": 2.0,
        },
    ],
    "twilio": [
        {
            "name": "Omnichannel CX baseline",
            "required_subcap_id": "P2C3.1.1",
            "threshold": 2.5,
        },
        {
            "name": "Communications compliance",
            "required_subcap_id": "P1C3.2.1",
            "threshold": 3.0,
        },
    ],
    "ncino": [
        {
            "name": "Loan origination digitization",
            "required_subcap_id": "P3C2.1.1",
            "threshold": 2.5,
        },
        {
            "name": "Commercial lending workflow",
            "required_subcap_id": "P3C2.2.1",
            "threshold": 2.0,
        },
        {
            "name": "Document management",
            "required_subcap_id": "P3C3.1.1",
            "threshold": 2.0,
        },
    ],
}


def prerequisites_for(platform_id: str) -> list[dict[str, str | float]]:
    """Return the prereq spec list for a platform, or [] if unknown.

    The list is safe to JSON-serialise directly into
    `platform_scores.prerequisite_checks` JSONB.
    """
    return PLATFORM_PREREQUISITES.get(platform_id, [])
