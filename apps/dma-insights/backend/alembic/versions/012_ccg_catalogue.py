"""012 — Capability catalogue (ccg_*) — full v7-shaped tables, version-scoped

Revision ID: 012_ccg_catalogue
Revises: 011_prompts_state_focus
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "012_ccg_catalogue"
down_revision = "011_prompts_state_focus"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----- versions registry -----
    op.create_table(
        "ccg_catalog_versions",
        sa.Column("version", sa.String(16), primary_key=True),
        sa.Column("released_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("source_sha256s", postgresql.JSONB, nullable=False),
        sa.Column("loader_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("frozen_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("notes", sa.Text),
    )

    op.create_table(
        "ccg_loader_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("loader_started_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("loader_finished_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("source_files", postgresql.JSONB, nullable=False),
        sa.Column("parse_warnings", postgresql.JSONB),
        sa.Column("validation_report", postgresql.JSONB),
        sa.Column("diff_vs_prior_version", postgresql.JSONB),
        sa.Column("admin_approved_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("admin_approved_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("status", sa.String(16), nullable=False, server_default="STAGING"),
        sa.CheckConstraint(
            "status IN ('STAGING','AWAITING_APPROVAL','APPLIED','REJECTED')",
            name="ccg_loader_runs_status_chk",
        ),
    )

    # ----- pillars / categories / l1 / subcaps -----
    op.create_table(
        "ccg_pillars",
        sa.Column("version", sa.String(16),
                  sa.ForeignKey("ccg_catalog_versions.version", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("pillar_id", sa.String(8), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("category_count", sa.Integer, nullable=False),
        sa.Column("l1_capability_count", sa.Integer, nullable=False),
        sa.Column("subcap_count", sa.Integer, nullable=False),
        sa.PrimaryKeyConstraint("version", "pillar_id"),
    )

    op.create_table(
        "ccg_categories",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("category_id", sa.String(16), nullable=False),
        sa.Column("pillar_id", sa.String(8), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("version", "category_id"),
        sa.ForeignKeyConstraint(["version", "pillar_id"],
                                ["ccg_pillars.version", "ccg_pillars.pillar_id"],
                                ondelete="CASCADE"),
    )

    op.create_table(
        "ccg_l1_capabilities",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("l1_id", sa.String(64), nullable=False),
        sa.Column("category_id", sa.String(16), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("version", "l1_id"),
        sa.ForeignKeyConstraint(["version", "category_id"],
                                ["ccg_categories.version", "ccg_categories.category_id"],
                                ondelete="CASCADE"),
    )

    op.create_table(
        "ccg_subcaps",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("l1_id", sa.String(64), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("solution_type", sa.String(16), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("personas", postgresql.ARRAY(sa.Text)),
        sa.Column("l3_platforms", postgresql.ARRAY(sa.Text)),
        sa.Column("use_cases", sa.Text),
        sa.Column("story_refs", sa.Text),
        sa.Column("zennify_status", sa.String(16), nullable=False, server_default="Active"),
        sa.PrimaryKeyConstraint("version", "subcap_id"),
        sa.ForeignKeyConstraint(["version", "l1_id"],
                                ["ccg_l1_capabilities.version",
                                 "ccg_l1_capabilities.l1_id"],
                                ondelete="CASCADE"),
        sa.CheckConstraint(
            "solution_type IN ('Traditional','Hybrid','Headless')",
            name="ccg_subcaps_solution_type_chk",
        ),
    )
    op.create_index("ix_ccg_subcaps_tier", "ccg_subcaps", ["version", "tier"])
    op.create_index("ix_ccg_subcaps_solution", "ccg_subcaps", ["version", "solution_type"])

    op.create_table(
        "ccg_maturity_descriptors",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("band", sa.CHAR(2), nullable=False),
        sa.Column("narrative", sa.Text, nullable=False),
        sa.Column("features", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("version", "subcap_id", "band"),
        sa.ForeignKeyConstraint(["version", "subcap_id"],
                                ["ccg_subcaps.version", "ccg_subcaps.subcap_id"],
                                ondelete="CASCADE"),
        sa.CheckConstraint("band IN ('M1','M2','M3','M4','M5')",
                           name="ccg_maturity_band_chk"),
    )

    # ----- supporting catalogue tables -----
    op.create_table(
        "ccg_l3_platforms",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("l3_id", sa.String(64), nullable=False),
        sa.Column("vendor", sa.Text, nullable=False),
        sa.Column("platform_name", sa.Text, nullable=False),
        sa.Column("category", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("setup_path", sa.Text),
        sa.Column("prerequisites", sa.Text),
        sa.Column("detailed_capabilities", sa.Text),
        sa.PrimaryKeyConstraint("version", "l3_id"),
    )

    op.create_table(
        "ccg_l4_features",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("l3_id", sa.String(64), nullable=False),
        sa.Column("feature_name", sa.Text, nullable=False),
        sa.Column("vendor", sa.Text),
        sa.Column("feature_type", sa.Text),
        sa.Column("customization_level", sa.Text),
        sa.Column("reference_url", sa.Text),
        sa.PrimaryKeyConstraint("version", "subcap_id", "l3_id", "feature_name"),
    )
    op.create_index("ix_ccg_l4_features_subcap", "ccg_l4_features",
                    ["version", "subcap_id"])

    op.create_table(
        "ccg_user_stories",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("story_key", sa.String(64), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("source_type", sa.String(32)),
        sa.Column("source_ref", sa.String(256)),
        sa.Column("use_case_ids", sa.Text),
        sa.Column("l4_features_used", sa.Text),
        sa.Column("match_confidence", sa.Numeric(4, 3)),
        sa.PrimaryKeyConstraint("version", "story_key"),
    )
    op.create_index("ix_ccg_user_stories_subcap", "ccg_user_stories",
                    ["version", "subcap_id"])

    op.create_table(
        "ccg_product_catalog",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("vendor", sa.Text, nullable=False),
        sa.Column("component_name", sa.Text, nullable=False),
        sa.Column("l3_platform_area", sa.Text),
        sa.Column("component_type", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("source_type", sa.Text),
        sa.Column("reference_url", sa.Text),
        sa.Column("lob", sa.Text),
        sa.PrimaryKeyConstraint("version", "vendor", "component_name"),
    )

    op.create_table(
        "ccg_agentforce_agents",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("agent_id", sa.String(64), nullable=False),
        sa.Column("agent_name", sa.Text, nullable=False),
        sa.Column("lob", sa.Text),
        sa.Column("workflow", sa.Text),
        sa.Column("status", sa.Text),
        sa.Column("source_type", sa.Text),
        sa.Column("parent_l3", sa.String(64)),
        sa.Column("description", sa.Text),
        sa.PrimaryKeyConstraint("version", "agent_id"),
    )

    op.create_table(
        "ccg_platform_constructs",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("construct_name", sa.String(128), nullable=False),
        sa.Column("vendor", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("syntax_hint", sa.Text),
        sa.Column("docs_url", sa.Text),
        sa.Column("used_in_l4_features", sa.Text),
        sa.PrimaryKeyConstraint("version", "construct_name"),
    )

    op.create_table(
        "ccg_productized_offerings",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("offering_id", sa.String(64), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("category", sa.Text),
        sa.Column("wrap_around", sa.Text),
        sa.Column("status", sa.Text),
        sa.Column("overview", sa.Text),
        sa.Column("industry_challenge", sa.Text),
        sa.Column("outcomes", sa.Text),
        sa.PrimaryKeyConstraint("version", "offering_id"),
    )

    op.create_table(
        "ccg_data_products",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("module_id", sa.String(64), nullable=False),
        sa.Column("category", sa.Text),
        sa.Column("module_name", sa.Text, nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("typical_pairing", sa.Text),
        sa.Column("validation_strength", sa.Text),
        sa.Column("reference_url", sa.Text),
        sa.Column("source_doc_section", sa.Text),
        sa.PrimaryKeyConstraint("version", "module_id"),
    )

    op.create_table(
        "ccg_offering_subcap_matrix",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("offering_id", sa.String(64), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("mapping_rationale", sa.Text),
        sa.Column("maturity_lift", sa.String(32)),
        sa.Column("capabilities_addressing", sa.Text),
        sa.Column("reference_url", sa.Text),
        sa.PrimaryKeyConstraint("version", "offering_id", "subcap_id"),
    )
    op.create_index("ix_ccg_offering_subcap", "ccg_offering_subcap_matrix",
                    ["version", "subcap_id"])

    op.create_table(
        "ccg_dataproduct_subcap_matrix",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("module_id", sa.String(64), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("mapping_rationale", sa.Text),
        sa.Column("maturity_lift", sa.String(32)),
        sa.Column("reference_url", sa.Text),
        sa.Column("zennify_effective_status", sa.String(16)),
        sa.PrimaryKeyConstraint("version", "module_id", "subcap_id"),
    )
    op.create_index("ix_ccg_dataproduct_subcap", "ccg_dataproduct_subcap_matrix",
                    ["version", "subcap_id"])

    op.create_table(
        "ccg_cross_pillar_stories",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("story_key", sa.String(64), nullable=False),
        sa.Column("origin_pillar", sa.String(8), nullable=False),
        sa.Column("origin_subcap_id", sa.String(32), nullable=False),
        sa.Column("origin_l1_capability", sa.Text),
        sa.Column("target_pillar", sa.String(8), nullable=False),
        sa.Column("themes", postgresql.ARRAY(sa.Text)),
        sa.Column("theme_count", sa.Integer),
        sa.PrimaryKeyConstraint("version", "story_key", "target_pillar"),
    )

    op.create_table(
        "ccg_theme_subcap_mapping",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("theme", sa.Text, nullable=False),
        sa.Column("pillar_id", sa.String(8), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("mapping_rationale", sa.Text),
        sa.Column("cross_pillar_story_count", sa.Integer),
        sa.Column("zennify_effective_status", sa.String(16)),
        sa.PrimaryKeyConstraint("version", "theme", "subcap_id"),
    )

    op.create_table(
        "ccg_subcap_xpillar_coverage",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("total_xpillar_stories", sa.Integer, nullable=False, server_default="0"),
        sa.Column("p1_stories", sa.Integer, nullable=False, server_default="0"),
        sa.Column("p2_stories", sa.Integer, nullable=False, server_default="0"),
        sa.Column("p3_stories", sa.Integer, nullable=False, server_default="0"),
        sa.Column("p4_stories", sa.Integer, nullable=False, server_default="0"),
        sa.Column("themes_contributing", postgresql.ARRAY(sa.Text)),
        sa.Column("linked_offerings", postgresql.ARRAY(sa.Text)),
        sa.PrimaryKeyConstraint("version", "subcap_id"),
    )

    op.create_table(
        "ccg_subcap_completeness",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("stories_count", sa.Integer),
        sa.Column("l4_count", sa.Integer),
        sa.Column("maturity_count", sa.Integer),
        sa.Column("l3_count", sa.Integer),
        sa.Column("core_score", sa.Integer),
        sa.Column("extended_score", sa.Integer),
        sa.Column("total_score", sa.Integer),
        sa.PrimaryKeyConstraint("version", "subcap_id"),
    )

    op.create_table(
        "ccg_toggle_cascade",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("user_stories_inactive", sa.Integer),
        sa.Column("l4_features_inactive", sa.Integer),
        sa.Column("maturity_rows_inactive", sa.Integer),
        sa.Column("l3_references_affected", sa.Integer),
        sa.Column("offering_mappings_inactive", sa.Integer),
        sa.Column("severity", sa.String(16)),
        sa.Column("direct_cascade_summary", sa.Text),
        sa.PrimaryKeyConstraint("version", "subcap_id"),
    )

    # ----- 9 subverticals + value-chain mapping -----
    op.create_table(
        "ccg_subverticals",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("display_order", sa.SmallInteger, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.CheckConstraint(
            "status IN ('active','pending_admin_review','archived')",
            name="ccg_subverticals_status_chk",
        ),
    )
    # seed the 9 canonical subverticals
    op.execute(
        """
        INSERT INTO ccg_subverticals (code, name, display_order, status) VALUES
          ('RB',  'Retail Banking',                  1, 'active'),
          ('CU',  'Credit Unions',                   2, 'active'),
          ('CL',  'Commercial Lending',              3, 'active'),
          ('CIB', 'Corp & Investment Banking',       4, 'active'),
          ('FC',  'Farm Credit / Ag Lending',        5, 'active'),
          ('AM',  'Asset & Wealth Management',       6, 'active'),
          ('RIA', 'RIA / Broker-Dealer',             7, 'active'),
          ('IC',  'Insurance Carriers',              8, 'active'),
          ('IB',  'Insurance Brokerages',            9, 'active')
        """
    )

    op.create_table(
        "ccg_vc_mapping",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("subcap_id", sa.String(32), nullable=False),
        sa.Column("subvertical_code", sa.String(8), nullable=False),
        sa.Column("value_chain_stages", postgresql.ARRAY(sa.Text), nullable=False),
        sa.PrimaryKeyConstraint("version", "subcap_id", "subvertical_code"),
        sa.ForeignKeyConstraint(["subvertical_code"], ["ccg_subverticals.code"]),
    )
    op.create_index("ix_ccg_vc_mapping_subv", "ccg_vc_mapping",
                    ["version", "subvertical_code"])

    op.create_table(
        "ccg_qa_gates",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("gate_id", sa.String(64), nullable=False),
        sa.Column("category", sa.Text),
        sa.Column("gate", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("detail", sa.Text),
        sa.PrimaryKeyConstraint("version", "gate_id"),
        sa.CheckConstraint(
            "status IN ('PASS','PARTIAL','DEFERRED','FAIL')",
            name="ccg_qa_gates_status_chk",
        ),
    )

    op.create_table(
        "ccg_plan_revisions",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("rev_seq", sa.Integer, nullable=False),
        sa.Column("batch", sa.Text),
        sa.Column("lesson", sa.Text),
        sa.Column("update_text", sa.Text),
        sa.Column("status", sa.String(16)),
        sa.PrimaryKeyConstraint("version", "rev_seq"),
    )

    # ----- alias bridge between catalogue versions -----
    op.create_table(
        "ccg_subcap_aliases",
        sa.Column("prior_version", sa.String(16), nullable=False),
        sa.Column("prior_subcap_id", sa.String(32), nullable=False),
        sa.Column("current_version", sa.String(16), nullable=False),
        sa.Column("current_subcap_id", sa.String(32), nullable=False),
        sa.Column("migration_action", sa.String(32), nullable=False),
        sa.Column("migration_notes", sa.Text),
        sa.PrimaryKeyConstraint("prior_version", "prior_subcap_id", "current_version"),
        sa.CheckConstraint(
            "migration_action IN ('MIGRATED','RENAMED','SPLIT','MERGED','DROPPED',"
            "'l1_id_promoted')",
            name="ccg_subcap_aliases_action_chk",
        ),
    )
    op.create_index("ix_ccg_subcap_aliases_current", "ccg_subcap_aliases",
                    ["current_version", "current_subcap_id"])

    op.create_table(
        "ccg_dropped_stories",
        sa.Column("version", sa.String(16), nullable=False),
        sa.Column("source_type", sa.Text),
        sa.Column("issue_key", sa.String(64), nullable=False),
        sa.Column("project", sa.Text),
        sa.Column("summary", sa.Text),
        sa.Column("reason_dropped", sa.Text),
        sa.PrimaryKeyConstraint("version", "issue_key"),
    )

    # ----- subvertical adjacency (admin-editable) -----
    op.create_table(
        "ccg_subvertical_adjacency",
        sa.Column("from_code", sa.String(8),
                  sa.ForeignKey("ccg_subverticals.code", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("to_code", sa.String(8),
                  sa.ForeignKey("ccg_subverticals.code", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("weight", sa.Numeric(3, 2), nullable=False),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("notes", sa.Text),
        sa.PrimaryKeyConstraint("from_code", "to_code"),
        sa.CheckConstraint("weight >= 0.0 AND weight <= 1.0",
                           name="ccg_adjacency_weight_chk"),
    )
    # Seed defaults: 1.0 self, 0.6 within affinity cluster, 0.3 otherwise.
    # Clusters: retail-lending {RB,CU,CL,FC}, wealth {AM,RIA}, insurance {IC,IB},
    # CIB standalone. CIB shares 0.6 with CL (close commercial relationship).
    op.execute(
        """
        WITH codes AS (SELECT code FROM ccg_subverticals),
             pairs AS (
               SELECT a.code AS from_code, b.code AS to_code FROM codes a CROSS JOIN codes b
             )
        INSERT INTO ccg_subvertical_adjacency (from_code, to_code, weight, notes)
        SELECT
          from_code,
          to_code,
          CASE
            WHEN from_code = to_code THEN 1.00
            WHEN (from_code IN ('RB','CU','CL','FC')
                  AND to_code IN ('RB','CU','CL','FC')) THEN 0.60
            WHEN (from_code IN ('AM','RIA') AND to_code IN ('AM','RIA')) THEN 0.60
            WHEN (from_code IN ('IC','IB') AND to_code IN ('IC','IB')) THEN 0.60
            WHEN (from_code = 'CIB' AND to_code = 'CL')
              OR (from_code = 'CL' AND to_code = 'CIB') THEN 0.60
            ELSE 0.30
          END AS weight,
          'Seeded by migration 012' AS notes
        FROM pairs
        """
    )


def downgrade() -> None:
    op.drop_table("ccg_subvertical_adjacency")
    op.drop_table("ccg_dropped_stories")
    op.drop_index("ix_ccg_subcap_aliases_current", table_name="ccg_subcap_aliases")
    op.drop_table("ccg_subcap_aliases")
    op.drop_table("ccg_plan_revisions")
    op.drop_table("ccg_qa_gates")
    op.drop_table("ccg_vc_mapping")
    op.drop_table("ccg_subverticals")
    op.drop_table("ccg_toggle_cascade")
    op.drop_table("ccg_subcap_completeness")
    op.drop_table("ccg_subcap_xpillar_coverage")
    op.drop_table("ccg_theme_subcap_mapping")
    op.drop_table("ccg_cross_pillar_stories")
    op.drop_table("ccg_dataproduct_subcap_matrix")
    op.drop_table("ccg_offering_subcap_matrix")
    op.drop_table("ccg_data_products")
    op.drop_table("ccg_productized_offerings")
    op.drop_table("ccg_platform_constructs")
    op.drop_table("ccg_agentforce_agents")
    op.drop_table("ccg_product_catalog")
    op.drop_table("ccg_user_stories")
    op.drop_table("ccg_l4_features")
    op.drop_table("ccg_l3_platforms")
    op.drop_table("ccg_maturity_descriptors")
    op.drop_table("ccg_subcaps")
    op.drop_table("ccg_l1_capabilities")
    op.drop_table("ccg_categories")
    op.drop_table("ccg_pillars")
    op.drop_table("ccg_loader_runs")
    op.drop_table("ccg_catalog_versions")
