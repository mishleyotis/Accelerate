"""Catalogue tier: the 21 ccg_* tables (Backend Schema §08)

Every row is keyed on its version, so a bump adds rows rather than
mutating them. Four tables are specified in full by the Backend Schema
(ccg_versions, ccg_subcaps, ccg_aliases, ccg_value_chains); the rest are
named there and their column contracts come from the v7.0 pillar-workbook
tab schemas ("Zennify Capability Mapping Visualized Schema", §05 — the
data stage 0.4 loads). Workbook FORMULA columns (mapped-subcap counts,
linkage health, Zennify_Effective_Status cascades) and denormalised name
copies are deliberately NOT stored — they are recomputable from the
matrix tables and the subcap register (invariant 8). The completeness
profile and toggle-cascade simulation ARE stored: the workbook is their
source of truth, not this database.

Grants: all three service roles read the catalogue (role matrix §03);
nobody but the owner (svc_migrate — the 0.4 loader runs as dmai-migrate)
writes it.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-04
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABLES: dict[str, str] = {
    # ── Specified in full by the Backend Schema ────────────────────────
    "ccg_versions": """
        version        TEXT PRIMARY KEY,
        loaded_at      TIMESTAMPTZ,
        cell_count     INTEGER,            -- 851 in the current version
        category_count INTEGER,            -- 17
        is_current     BOOLEAN             -- exactly one TRUE (partial unique below)
    """,
    "ccg_subcaps": """
        subcap_id         TEXT,
        version           TEXT,
        capability_id     TEXT,             -- grain level 3
        category_id       TEXT,             -- grain level 2
        pillar_id         TEXT,             -- grain level 1
        name              TEXT,             -- the CANONICAL name; never copy from prose
        weight            NUMERIC(5,4),
        l3_platform_areas TEXT[],
        l4_features       TEXT[],
        PRIMARY KEY (subcap_id, version)
    """,
    "ccg_aliases": """
        from_subcap_id TEXT,
        from_version   TEXT,
        to_subcap_id   TEXT,
        to_version     TEXT,
        reason         TEXT,               -- renamed · split · merged · retired
        PRIMARY KEY (from_subcap_id, from_version)
    """,
    "ccg_value_chains": """
        chain_id     TEXT,
        version      TEXT,
        sub_vertical TEXT,                 -- chains differ by sub-vertical
        name         TEXT,
        stage_order  SMALLINT,             -- order is meaning
        PRIMARY KEY (chain_id, version)
    """,
    # ── Column contracts from the v7.0 workbook tab schemas ────────────
    "ccg_maturity_descriptors": """
        version   TEXT,
        subcap_id TEXT,
        band      TEXT CHECK (band IN ('M1','M2','M3','M4','M5')),
        -- rubric levels of the scoring workbook, NOT band_t: the four-band
        -- rule (invariant 6) governs the app's display bands over raw
        -- scores; the catalogue's M1–M5 narratives are assessment source
        narrative TEXT,
        features  TEXT,
        PRIMARY KEY (version, subcap_id, band)
    """,
    "ccg_l3_platforms": """
        version               TEXT,
        l3_id                 TEXT,
        vendor                TEXT,
        platform_name         TEXT,
        category              TEXT,
        description           TEXT,
        setup_path            TEXT,
        prerequisites         TEXT,
        detailed_capabilities TEXT,
        PRIMARY KEY (version, l3_id)
    """,
    "ccg_l4_features": """
        id                  BIGSERIAL PRIMARY KEY,
        version             TEXT,
        subcap_id           TEXT,
        l3_id               TEXT,
        feature_name        TEXT,
        vendor              TEXT,
        feature_type        TEXT,
        customization_level TEXT,
        reference_url       TEXT
    """,
    "ccg_agents": """
        version     TEXT,
        agent_id    TEXT,                  -- AF-{NNN} / AGT-{shortname} / FM-AGENT-{ROLE}
        agent_name  TEXT,
        lob         TEXT,
        workflow    TEXT,
        status      TEXT,
        source_type TEXT,
        parent_l3   TEXT,
        description TEXT,
        source_url  TEXT,
        usage_note  TEXT,
        PRIMARY KEY (version, agent_id)
    """,
    "ccg_constructs": """
        version            TEXT,
        construct_name     TEXT,
        vendor             TEXT,
        description        TEXT,
        syntax_hint        TEXT,
        docs_url           TEXT,
        used_in_l4_features TEXT,
        top_subcap_ids     TEXT,
        PRIMARY KEY (version, construct_name)
    """,
    "ccg_products": """
        version            TEXT,
        vendor             TEXT,
        product_name       TEXT,
        product_code       TEXT,
        category           TEXT,
        description        TEXT,
        licensing_model    TEXT,
        sub_vertical_fit   TEXT,
        maturity_hint      TEXT,
        reference_url      TEXT,
        source_type        TEXT,
        anchor_note        TEXT,
        subcaps_referenced TEXT,
        PRIMARY KEY (version, vendor, product_name)
    """,
    "ccg_offerings": """
        version            TEXT,
        offering_id        TEXT,           -- OFF-{shortname}
        offering_name      TEXT,
        category           TEXT,
        wrap_around        BOOLEAN,
        status             TEXT,
        overview           TEXT,
        industry_challenge TEXT,
        outcomes           TEXT,
        core_capabilities  TEXT,
        tiers              TEXT,
        primary_vendors    TEXT,
        l3_platforms_used  TEXT,
        target_personas    TEXT,
        reference_url      TEXT,
        source_evidence    TEXT,
        source_doc_section TEXT,
        PRIMARY KEY (version, offering_id)
    """,
    "ccg_data_products": """
        version             TEXT,
        module_id           TEXT,          -- DP-{category}.{n}
        category            TEXT,
        module_name         TEXT,
        description         TEXT,
        typical_pairing     TEXT,
        validation_strength TEXT,
        reference_url       TEXT,
        source_doc_section  TEXT,
        PRIMARY KEY (version, module_id)
    """,
    "ccg_offering_subcap_matrix": """
        version                TEXT,
        offering_id            TEXT,
        subcap_id              TEXT,
        mapping_rationale      TEXT,
        maturity_lift          TEXT,       -- "M{x} → M{y}"
        capabilities_addressing TEXT,
        reference_url          TEXT,
        PRIMARY KEY (version, offering_id, subcap_id)
    """,
    "ccg_dataproduct_subcap_matrix": """
        version           TEXT,
        module_id         TEXT,
        subcap_id         TEXT,
        mapping_rationale TEXT,
        maturity_lift     TEXT,
        reference_url     TEXT,
        PRIMARY KEY (version, module_id, subcap_id)
    """,
    "ccg_user_stories": """
        id               BIGSERIAL PRIMARY KEY,
        version          TEXT,
        story_key        TEXT,
        subcap_id        TEXT,
        source_type      TEXT,
        source_ref       TEXT,
        use_case_ids     TEXT,
        l4_features_used TEXT,
        match_confidence NUMERIC(3,2),
        UNIQUE (version, story_key, subcap_id)
    """,
    "ccg_cross_pillar_stories": """
        id                  BIGSERIAL PRIMARY KEY,
        version             TEXT,
        pillar_id           TEXT,           -- the pillar this row reinforces (per-pillar tab)
        story_key           TEXT,
        origin_pillar       TEXT,
        origin_subcap_id    TEXT,
        origin_l1_capability TEXT,
        themes              TEXT,
        confidence_level    TEXT,           -- HIGH / MEDIUM / LOW
        story_title         TEXT,
        story_summary       TEXT,
        linked_subcap_ids   TEXT,
        linked_offerings    TEXT,
        source_reference    TEXT
    """,
    "ccg_theme_subcap_mapping": """
        version           TEXT,
        theme             TEXT,             -- one of the 8 fixed cross-pillar themes
        subcap_id         TEXT,
        mapping_rationale TEXT,
        reference_note    TEXT,
        PRIMARY KEY (version, theme, subcap_id)
    """,
    "ccg_subcap_completeness": """
        version             TEXT,
        subcap_id           TEXT,
        stories_count       INTEGER,
        l4_count            INTEGER,
        maturity_complete   SMALLINT,       -- 0/1: all five rubric narratives present
        l3_count            INTEGER,
        usecase_count       INTEGER,
        offering_count      INTEGER,
        mapped_offerings    TEXT,
        dataproduct_count   INTEGER,
        mapped_dataproducts TEXT,
        themes              TEXT,
        crosspillar_stories INTEGER,
        core_score          SMALLINT,       -- max 5
        extended_score      SMALLINT,       -- max 3
        total_score         SMALLINT,       -- max 8
        narrative           TEXT,
        PRIMARY KEY (version, subcap_id)
    """,
    "ccg_toggle_cascade": """
        version                    TEXT,
        subcap_id                  TEXT,
        user_stories_inactive      INTEGER,
        l4_features_inactive       INTEGER,
        maturity_rows_inactive     INTEGER,
        l3_references_affected     INTEGER,
        offering_mappings_inactive INTEGER,
        dataproduct_mappings_inactive INTEGER,
        theme_mappings_inactive    INTEGER,
        coverage_rows_inactive     INTEGER,
        xp_stories_partial         INTEGER,
        xp_stories_inactive        INTEGER,
        offerings_partial          INTEGER,
        dataproducts_partial       INTEGER,
        total_cascade_footprint    INTEGER,
        cascade_severity           TEXT,    -- HIGH / MEDIUM / LOW / MINIMAL
        PRIMARY KEY (version, subcap_id)
    """,
    "ccg_vc_mapping": """
        version            TEXT,
        subcap_id          TEXT,
        subvertical_code   TEXT,            -- RB · CU · CL · CIB · FC · AM · RIA · IC · IB
        value_chain_stages TEXT[],
        phase_categories   TEXT,
        coverage_note      TEXT,
        PRIMARY KEY (version, subcap_id, subvertical_code)
    """,
    "ccg_qa_gates": """
        version   TEXT,
        pillar_id TEXT,
        gate_id   TEXT,                     -- {Batch}.G{NN}
        category  TEXT,
        title     TEXT,
        status    TEXT,                     -- PASS / PARTIAL / DEFERRED
        detail    TEXT,
        PRIMARY KEY (version, pillar_id, gate_id)
    """,
}


def upgrade() -> None:
    for name, body in TABLES.items():
        op.execute(f"CREATE TABLE {name} ({body})")
    # Exactly one current catalogue version.
    op.execute(
        "CREATE UNIQUE INDEX ccg_versions_current_uq ON ccg_versions ((TRUE)) WHERE is_current"
    )
    # Catalogue resolution and grain drilling (Backend Schema §09 indexes).
    op.execute("CREATE INDEX ccg_subcaps_version_category ON ccg_subcaps (version, category_id)")
    op.execute("CREATE INDEX ccg_l4_features_version_subcap ON ccg_l4_features (version, subcap_id)")
    op.execute("CREATE INDEX ccg_xp_stories_version_pillar ON ccg_cross_pillar_stories (version, pillar_id)")
    # Role matrix §03: every service reads the catalogue; only the owner
    # (svc_migrate, which runs the 0.4 loader) writes it.
    for name in TABLES:
        op.execute(f"GRANT SELECT ON {name} TO svc_api, svc_mcp, svc_worker")
    op.execute("GRANT USAGE ON SEQUENCE ccg_l4_features_id_seq TO svc_migrate")
    op.execute("GRANT USAGE ON SEQUENCE ccg_user_stories_id_seq TO svc_migrate")
    op.execute("GRANT USAGE ON SEQUENCE ccg_cross_pillar_stories_id_seq TO svc_migrate")


def downgrade() -> None:
    for name in reversed(list(TABLES)):
        op.execute(f"DROP TABLE IF EXISTS {name}")
