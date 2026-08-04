"""Ingested tier: 13 tables (Backend Schema §04)

Written once by the parser, read by the Cowork agent through the report
bundle, read-only from the moment the run is queued.

Generated columns come verbatim from the TRD's stored-generated-column
DDL. PostgreSQL forbids a generated column referencing another generated
column, so recency_band inlines the age expression instead of reading
age_months — same arithmetic, one implementation per the doc's intent
(the chain age → band stays unbreakable by an application write).

run_manifest and the five *_raw tables are elided in the Backend Schema
("run_id, its package identifier, its payload columns and an artefact_id")
— they start as (native id, payload JSONB, artefact_id) and expand to
typed columns in the stage 1.3 parser PR (expand–migrate–contract).
document_sections.artefact_id gains its FK when import_files exists
(ingest-ops migration) so no FK ever points at a missing table.

Grants (§03): svc_worker full DML on ingested; svc_mcp SELECT;
svc_api nothing — EXCEPT evidence_index (doubles as the serving table
for heatmap.evidence) and evidence_subcap_links (the §10 evidence-drawer
query joins it), which get SELECT.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-04
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

# The TRD writes age(reference_date, published_date); PostgreSQL resolves
# bare dates through the timestamptz overload whose implicit cast is only
# STABLE, which a generated column rejects. Explicit ::timestamp casts pick
# the immutable overload — identical arithmetic.
AGE_MONTHS_EXPR = """(
  CASE WHEN published_date IS NULL OR reference_date IS NULL THEN NULL
       ELSE (EXTRACT(YEAR  FROM age(reference_date::timestamp, published_date::timestamp))*12
           + EXTRACT(MONTH FROM age(reference_date::timestamp, published_date::timestamp)))::int
  END)"""

# recency_band per TRD, with the age arithmetic inlined (see module doc).
RECENCY_EXPR = f"""(
  CASE WHEN published_date IS NULL OR reference_date IS NULL THEN 'UNVERIFIED'::recency_t
       WHEN {AGE_MONTHS_EXPR} <= 12 THEN 'CURRENT'::recency_t
       WHEN {AGE_MONTHS_EXPR} <= 24 THEN 'RECENT'::recency_t
       WHEN {AGE_MONTHS_EXPR} <= 36 THEN 'DATED'::recency_t
       WHEN {AGE_MONTHS_EXPR} <= 48 THEN 'STALE'::recency_t
       ELSE 'ARCHIVAL'::recency_t END)"""

# claim_type::text in a generated column trips 42P17: PostgreSQL's enum
# I/O conversion is only STABLE. enum_label() below is a declared-immutable
# wrapper — sound because our discipline only ever APPENDS enum values
# (adding a value is a migration; existing labels never change).
CONTENT_HASH_EXPR = r"""(
  encode(digest(coalesce(source_url,'') || '|' ||
                coalesce(enum_label(claim_type),'') || '|' ||
                lower(left(regexp_replace(excerpt,'\s+',' ','g'),500)),
         'sha256'),'hex'))"""

SOURCE_DOMAIN_EXPR = r"""(
  CASE WHEN source_url IS NULL THEN NULL
       ELSE lower(regexp_replace(source_url,
                  '^[A-Za-z]+://(www\.)?([^/:?#]+).*$', '\2'))
  END)"""


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION enum_label(anyenum) RETURNS text
          LANGUAGE sql IMMUTABLE PARALLEL SAFE
          AS 'SELECT $1::text'
        """
    )
    op.execute(
        """
        CREATE TABLE entities (
          id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          display_id           TEXT UNIQUE,      -- URL slug and human-facing handle
          legal_name           TEXT,             -- as the regulator's registry states it
          trading_name         TEXT,
          domain               TEXT,             -- cheapest identity check in the system
          sub_vertical         TEXT,             -- drives peer cohort and toggle cascade
          size_tier            TEXT,             -- expectation adjustment, never evidence adjustment
          primary_regulator    TEXT,             -- a mismatch is an identity error
          jurisdictions        TEXT[],           -- fastest contamination check available
          status               entity_status_t,
          inference_confidence NUMERIC(3,2),     -- low confidence -> PENDING_REVIEW
          owner_user_id        UUID REFERENCES users(id),
          created_at           TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE runs (
          id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          entity_id           UUID REFERENCES entities(id),
          request_id          TEXT,              -- both upstream formats are valid
          run_seq             SMALLINT,          -- 1, 2, 3 ... per entity
          ccg_catalog_version TEXT REFERENCES ccg_versions(version),
          scored_cells        INTEGER,           -- cells THIS run scored
          catalogue_cells     INTEGER,           -- denormalised from the pinned version
          composite           NUMERIC(4,2),      -- mean of the four pillar means, rounded ONCE
          status              run_status_t,
          is_active           BOOLEAN,
          completed_at        TIMESTAMPTZ,
          promoted_at         TIMESTAMPTZ,       -- NULL until promotion
          source_folder_id    TEXT
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX runs_active_uq ON runs (entity_id) WHERE is_active")

    op.execute(
        """
        CREATE TABLE run_manifest (
          run_id      UUID PRIMARY KEY REFERENCES runs(id),
          payload     JSONB,   -- provisional; typed columns land with the 1.3 parser
          artefact_id TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE subcap_scores (
          id                    BIGSERIAL PRIMARY KEY,
          run_id                UUID REFERENCES runs(id),
          subcap_id             TEXT,            -- resolved through the catalogue, never copied from prose
          capability_id         TEXT,            -- grain level 3
          category_id           TEXT,            -- grain level 2
          pillar_id             TEXT,            -- grain level 1
          score                 NUMERIC(4,2),    -- read from the workbook, never re-derived
          confidence            confidence_t,
          peer_median           NUMERIC(4,2),    -- NULL where the peer table lacks it, never imputed
          peer_n                SMALLINT,        -- cohort size actually used; floor of three
          peer_basis            peer_basis_t,
          proxy_disclosure      TEXT,            -- required when peer_basis is a proxy
          delta                 NUMERIC(4,2) GENERATED ALWAYS AS (score - peer_median) STORED,
          linked_evidence_count INTEGER,         -- maintained by the linker
          is_thin_evidence      BOOLEAN GENERATED ALWAYS AS
                                  (COALESCE(linked_evidence_count, 0) < 3) STORED,
          source_cell           TEXT,            -- the workbook cell; grain lock depends on it
          UNIQUE (run_id, subcap_id)
        )
        """
    )
    op.execute("CREATE INDEX subcap_scores_run_category ON subcap_scores (run_id, category_id)")

    op.execute(
        f"""
        CREATE TABLE evidence_index (
          e_id           TEXT PRIMARY KEY,        -- four namespaces, one recogniser
          entity_id      UUID REFERENCES entities(id),
          origin         evidence_origin_t,
          source_name    TEXT,
          source_url     TEXT,
          source_domain  TEXT GENERATED ALWAYS AS {SOURCE_DOMAIN_EXPR} STORED,
          excerpt        TEXT,                    -- verbatim, 50-500 chars, verified at registration
          claim_type     claim_t,
          tier           tier_t,                  -- five rungs, not eight
          published_date DATE,                    -- NULL is legal -> UNVERIFIED, never CURRENT
          reference_date DATE,                    -- the date age is computed against, pinned per run
          age_months     INTEGER GENERATED ALWAYS AS {AGE_MONTHS_EXPR} STORED,
          recency_band   recency_t GENERATED ALWAYS AS {RECENCY_EXPR} STORED,
          ers            NUMERIC(3,2) CONSTRAINT ers_bounded
                           CHECK (ers IS NULL OR ers BETWEEN 1.0 AND 5.0),
          specificity    SMALLINT,
          corroboration  SMALLINT,                -- counted by distinct ORIGIN, not by document
          identity_ok    BOOLEAN,                 -- FALSE excludes from coverage and tier distribution
          identity_note  TEXT,
          content_hash   TEXT GENERATED ALWAYS AS {CONTENT_HASH_EXPR} STORED
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX evidence_dedup_uq ON evidence_index (entity_id, content_hash)")
    op.execute("CREATE INDEX evidence_source_domain ON evidence_index (source_domain)")

    op.execute(
        """
        CREATE TABLE evidence_subcap_links (
          e_id       TEXT REFERENCES evidence_index(e_id),
          subcap_id  TEXT,
          run_id     UUID REFERENCES runs(id),
          link_basis TEXT,                        -- why; substance, not proximity
          PRIMARY KEY (e_id, subcap_id, run_id)
        )
        """
    )
    op.execute("CREATE INDEX evidence_links_subcap_run ON evidence_subcap_links (subcap_id, run_id)")

    op.execute(
        """
        CREATE TABLE peer_scores (
          id        BIGSERIAL PRIMARY KEY,
          run_id    UUID REFERENCES runs(id),
          peer_name TEXT,
          subcap_id TEXT,
          pillar_id TEXT,                         -- pillar-level peer medians feed the hero
          score     NUMERIC(4,2)                  -- NULL triggers the recompute-at-lower-cohort ladder
        )
        """
    )
    op.execute(
        """
        CREATE TABLE document_sections (
          id           BIGSERIAL PRIMARY KEY,
          run_id       UUID REFERENCES runs(id),
          section_kind TEXT,                      -- one of the twelve structured report sections
          pillar_id    TEXT,                      -- NULL for non-pillar sections
          heading      TEXT,
          body         TEXT,
          page         INTEGER,                   -- source page, so a focus-area quote can cite it
          artefact_id  TEXT                       -- FK to import_files added in the ingest-ops revision
        )
        """
    )

    # The five raw tables: run_id, package identifier, payload, artefact_id
    # (Backend Schema §04, elided "same shape"). Typed payload columns land
    # with the stage 1.3 parser.
    for name, native in (
        ("issue_register_raw", "issue_id"),
        ("recommendations_raw", "rec_id"),
        ("techstack_raw", "item_id"),
        ("platform_fits_raw", "fit_id"),
        ("firmographics_raw", "field"),
    ):
        op.execute(
            f"""
            CREATE TABLE {name} (
              id          BIGSERIAL PRIMARY KEY,
              run_id      UUID REFERENCES runs(id),
              {native}    TEXT,
              payload     JSONB,
              artefact_id TEXT
            )
            """
        )

    ingested = [
        "entities", "runs", "run_manifest", "subcap_scores", "evidence_index",
        "evidence_subcap_links", "peer_scores", "document_sections",
        "issue_register_raw", "recommendations_raw", "techstack_raw",
        "platform_fits_raw", "firmographics_raw",
    ]
    for t in ingested:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO svc_worker")
        op.execute(f"GRANT SELECT ON {t} TO svc_mcp")
    for seq in ("subcap_scores_id_seq", "peer_scores_id_seq", "document_sections_id_seq",
                "issue_register_raw_id_seq", "recommendations_raw_id_seq",
                "techstack_raw_id_seq", "platform_fits_raw_id_seq",
                "firmographics_raw_id_seq"):
        op.execute(f"GRANT USAGE ON SEQUENCE {seq} TO svc_worker")
    # evidence_index doubles as the heatmap.evidence serving table; the
    # drawer query joins the links table (§06 map, §10 drawer query).
    op.execute("GRANT SELECT ON evidence_index TO svc_api")
    op.execute("GRANT SELECT ON evidence_subcap_links TO svc_api")
    # The connector registers enrichment evidence (register_evidence) and
    # the promote stamps runs; both write ingested rows through svc_mcp.
    op.execute("GRANT INSERT, UPDATE ON evidence_index TO svc_mcp")
    op.execute("GRANT INSERT ON evidence_subcap_links TO svc_mcp")
    op.execute("GRANT UPDATE ON runs TO svc_mcp")


def downgrade() -> None:
    for t in ("firmographics_raw", "platform_fits_raw", "techstack_raw",
              "recommendations_raw", "issue_register_raw", "document_sections",
              "peer_scores", "evidence_subcap_links", "evidence_index",
              "subcap_scores", "run_manifest", "runs", "entities"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
    op.execute("DROP FUNCTION IF EXISTS enum_label(anyenum)")
