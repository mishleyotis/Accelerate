"""All enumerated types, created before any table that uses them

Backend Schema §09 names 26 types ("Enumerated types" list). The
Implementation Plan's stage 0.3 line says 22 — the Schema is higher
authority (build charter §Authority order) and its list is what tables
reference, so all 26 are created. Values are taken verbatim from the
Backend Schema table definitions and the TRD:

- recency_t carries UNVERIFIED in addition to the CURRENT–ARCHIVAL ladder:
  the TRD's verbatim recency_band DDL casts a NULL age to
  'UNVERIFIED'::recency_t (invariant 9 — undated is UNVERIFIED, never
  current).
- band_t is FOUR values; M5/Transformational is unreachable and must not
  exist (invariant 6).
- age_band_t/age_status_t are H7's lowercase band / uppercase status pair
  (Surface Spec H7); status is generated from band ONLY.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-04
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# name -> (values, source)
ENUMS: dict[str, tuple[list[str], str]] = {
    "user_role_t": (["AE", "ANALYST", "ADMIN"], "Schema §03 users.role"),
    "entity_status_t": (["ACTIVE", "PENDING_REVIEW", "ARCHIVED", "EXCLUDED"], "Schema §04 entities.status"),
    "run_status_t": (["INGESTED", "CLAIMED", "SYNTHESISING", "STAGED", "PROMOTED", "SUPERSEDED"], "Schema §04 runs.status"),
    "page_t": (["overview", "insights", "heatmap", "platform", "context", "techstack"], "Schema §05 submissions.page"),
    "submission_status_t": (["PASS", "FAIL"], "Schema §05 submissions.status"),
    "provenance_t": (["analyst", "derived", "producer"], "Schema §06 envelope.provenance"),
    "evidence_origin_t": (["package", "producer", "connector", "internal"], "Schema §04 evidence_index.origin"),
    "tier_t": (["T1", "T2", "T3", "T4", "T5"], "Schema §09 — five rungs, not eight"),
    "claim_t": (["FACT", "INFERENCE", "HYPOTHESIS", "CEILING_ESTIMATE"], "Schema §04 evidence_index.claim_type"),
    "recency_t": (["UNVERIFIED", "CURRENT", "RECENT", "DATED", "STALE", "ARCHIVAL"], "TRD stored-generated recency_band DDL; ladder 12/24/36/48mo"),
    "age_band_t": (["current", "aging", "dated", "stale", "undated"], "Surface Spec H7 band vocabulary (12/24/36 boundaries)"),
    "age_status_t": (["FRESH", "AGING", "DATED", "STALE", "UNDATED"], "Surface Spec H7 status, derived from band only"),
    "evidence_level_t": (["L1", "L2", "L3", "L4"], "Schema §06 techstack_items.evidence_level"),
    "confidence_t": (["HIGH", "MEDIUM", "LOW"], "Schema §04 subcap_scores.confidence"),
    "peer_basis_t": (["table", "recomputed", "inferred", "cannot_estimate"], "Schema §04 subcap_scores.peer_basis"),
    "posture_t": (["LEADING", "COMPETING", "LAGGING", "MIXED"], "Schema §06 overview_scores.posture"),
    "basis_t": (["EVIDENCE", "HYBRID", "INFERRED"], "Schema §06 overview_scores.posture_basis"),
    "stack_layer_t": (["OPS", "CUST", "DATA", "INFRA"], "Schema §06 techstack_items.layer — deliberately NOT L2–L5"),
    "stack_status_t": (["CONFIRMED", "INFERRED", "CLAIMED", "ABSENT"], "Schema §06 techstack_items.status — four recomputable counts"),
    "alert_action_t": (["acknowledged", "assigned", "waived", "resolved", "reopened"], "Schema §11 alert_actions.action"),
    "band_t": (["Activating", "Building", "Competing", "Differentiating"], "Schema §09 — four bands, strict less-than on the raw score"),
    "cap_kind_t": (["cap", "uncertainty_band", "qa_hold", "analyst_override"], "Schema §07 assessment_caps.kind"),
    "scope_t": (["cell", "category", "pillar", "run"], "Schema §12 bundle_embeddings.scope_kind"),
    "gate_family_t": (["analytical", "safeguard", "enrichment", "corpus"], "Schema §07 gate_registry.family"),
    "gate_result_t": (["PASS", "FAIL", "NOT_RUN"], "Schema §07 gate_results.result — never default to PASS"),
    "dedup_branch_t": (["kept", "dedup_same_entity", "cross_entity_kept", "duplicate_within_run", "tier_upgrade"], "Schema §07 evidence_dedup_audit.branch"),
}


def upgrade() -> None:
    for name, (values, source) in ENUMS.items():
        vals = ", ".join(f"'{v}'" for v in values)
        op.execute(
            f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT FROM pg_type WHERE typname = '{name}') THEN
                CREATE TYPE {name} AS ENUM ({vals});
              END IF;
            END $$
            """
        )
        op.execute(f"COMMENT ON TYPE {name} IS '{source}'")


def downgrade() -> None:
    for name in reversed(list(ENUMS)):
        op.execute(f"DROP TYPE IF EXISTS {name}")
