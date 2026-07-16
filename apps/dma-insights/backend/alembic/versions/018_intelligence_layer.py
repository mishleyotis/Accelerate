"""018 — customer intelligence layer: content-hash dedup, evidence
run links, freshness banding, customer_intelligence_profiles,
dedup_audit.

Revision ID: 018_intelligence_layer
Revises: 017_section_embeddings

Adds the persistent per-customer intelligence layer required by the
"deep customization at the customer level" user mandate:

  - `evidence_index.content_hash` — SHA256(url + claim_type + normalize(excerpt))
    used by the dedup service. Backfilled on upgrade.
  - `evidence_index.is_stale` GENERATED — true when published_date is
    older than 3 years OR recency_months > 36.
  - `evidence_index.freshness_band` GENERATED — one of
    current / aging / dated / stale (NULL band when no date and no
    recency_months — surfaced to the UI as "undated").
  - `evidence_run_links` — many-to-many between dedup-canonical
    evidence rows and runs that cite them (post-dedup tracking).
  - `dedup_audit` — one row per dedup decision (kept / dedup /
    cross_entity_kept / tier_upgrade).
  - `customer_intelligence_profiles` — the per-entity persistent
    rollup with maturity history, archetype history, recurring
    themes, persistent gaps, summary embedding + summary markdown.
  - `firmographics` columns: `narrative_md`, `leadership` JSONB,
    `financial_highlights` JSONB. (Created if firmographics table
    exists in the live env; this migration is no-op safe when the
    columns already exist.)
  - `focus_areas` — verbatim source-quote table for the
    Client_Profile parser to populate.

State-branch contract:
  - content_hash backfill is idempotent — re-running computes the
    same value for identical excerpts.
  - is_stale / freshness_band are STORED generated columns; the
    DB maintains them on every UPDATE.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "018_intelligence_layer"
down_revision = "017_section_embeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── evidence_index: content_hash + freshness ──────────────────────
    op.execute("""
        ALTER TABLE evidence_index
            ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)
    """)
    # Backfill from existing rows (idempotent — same input → same hash).
    # Uses pgcrypto's digest() if available; the migration assumes the
    # pgcrypto extension was enabled in 001_extensions.
    op.execute("""
        UPDATE evidence_index
        SET content_hash = encode(
            digest(
                COALESCE(source_url, '') || '|' ||
                COALESCE(claim_type, '') || '|' ||
                lower(regexp_replace(
                    COALESCE(LEFT(excerpt, 500), ''),
                    '\\s+', ' ', 'g'
                )),
                'sha256'
            ),
            'hex'
        )
        WHERE content_hash IS NULL
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evidence_content_hash "
        "ON evidence_index (content_hash)"
    )

    # is_stale + freshness_band — maintained by trigger, NOT a STORED
    # generated column. Postgres requires GENERATED ALWAYS AS
    # expressions to be IMMUTABLE; CURRENT_DATE is STABLE (depends on
    # transaction time), so the GENERATED variant fails at ALTER TABLE
    # with `generation expression is not immutable` (psycopg
    # InvalidObjectDefinition). The trigger pattern lets us use
    # CURRENT_DATE safely because triggers fire per-row at write time,
    # not as part of the table definition.
    #
    # Drift contract: rows don't auto-update as the wall clock ticks.
    # A daily Cloud Scheduler job (see DEPLOYMENT.md §28b) re-runs
    # `SELECT refresh_evidence_freshness()` to recompute bands for
    # rows whose absolute timestamps crossed a 1y/2y/3y boundary.
    # In practice, the rate of evidence rows changing band per day is
    # tiny (only rows whose published_date crosses the threshold
    # today), so a daily refresh is sufficient.
    op.execute("""
        ALTER TABLE evidence_index
            ADD COLUMN IF NOT EXISTS is_stale BOOLEAN NOT NULL DEFAULT FALSE
    """)
    op.execute("""
        ALTER TABLE evidence_index
            ADD COLUMN IF NOT EXISTS freshness_band VARCHAR(8)
                NOT NULL DEFAULT 'undated'
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION compute_evidence_freshness_band(
            p_published_date DATE,
            p_recency_months INTEGER
        ) RETURNS VARCHAR(8) AS $$
        BEGIN
            IF p_published_date IS NULL AND p_recency_months IS NULL THEN
                RETURN 'undated';
            END IF;
            IF (p_published_date IS NOT NULL
                AND p_published_date >= (CURRENT_DATE - INTERVAL '1 years'))
               OR (p_recency_months IS NOT NULL AND p_recency_months <= 12)
            THEN
                RETURN 'current';
            END IF;
            IF (p_published_date IS NOT NULL
                AND p_published_date >= (CURRENT_DATE - INTERVAL '2 years'))
               OR (p_recency_months IS NOT NULL AND p_recency_months <= 24)
            THEN
                RETURN 'aging';
            END IF;
            IF (p_published_date IS NOT NULL
                AND p_published_date >= (CURRENT_DATE - INTERVAL '3 years'))
               OR (p_recency_months IS NOT NULL AND p_recency_months <= 36)
            THEN
                RETURN 'dated';
            END IF;
            RETURN 'stale';
        END;
        $$ LANGUAGE plpgsql STABLE
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION evidence_freshness_trigger()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.is_stale := (
                (NEW.published_date IS NOT NULL
                 AND NEW.published_date < (CURRENT_DATE - INTERVAL '3 years'))
                OR (NEW.recency_months IS NOT NULL AND NEW.recency_months > 36)
            );
            NEW.freshness_band := compute_evidence_freshness_band(
                NEW.published_date, NEW.recency_months
            );
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        DROP TRIGGER IF EXISTS trg_evidence_freshness ON evidence_index
    """)
    op.execute("""
        CREATE TRIGGER trg_evidence_freshness
            BEFORE INSERT OR UPDATE OF published_date, recency_months
            ON evidence_index
            FOR EACH ROW
            EXECUTE FUNCTION evidence_freshness_trigger()
    """)
    # Backfill existing rows so the new columns are populated rather
    # than relying on the DEFAULT. Cheap — single UPDATE.
    op.execute("""
        UPDATE evidence_index
        SET is_stale = (
            (published_date IS NOT NULL
             AND published_date < (CURRENT_DATE - INTERVAL '3 years'))
            OR (recency_months IS NOT NULL AND recency_months > 36)
        ),
        freshness_band = compute_evidence_freshness_band(
            published_date, recency_months
        )
    """)
    # Maintenance helper for the Cloud Scheduler daily refresh.
    op.execute("""
        CREATE OR REPLACE FUNCTION refresh_evidence_freshness()
        RETURNS INTEGER AS $$
        DECLARE
            n_changed INTEGER;
        BEGIN
            WITH updated AS (
                UPDATE evidence_index
                SET is_stale = (
                        (published_date IS NOT NULL
                         AND published_date < (CURRENT_DATE - INTERVAL '3 years'))
                        OR (recency_months IS NOT NULL AND recency_months > 36)
                    ),
                    freshness_band = compute_evidence_freshness_band(
                        published_date, recency_months
                    )
                WHERE freshness_band IS DISTINCT FROM
                      compute_evidence_freshness_band(published_date, recency_months)
                RETURNING 1
            )
            SELECT COUNT(*) INTO n_changed FROM updated;
            RETURN n_changed;
        END;
        $$ LANGUAGE plpgsql
    """)

    # ── evidence_run_links ────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS evidence_run_links (
            evidence_id UUID NOT NULL
                REFERENCES evidence_index(id) ON DELETE CASCADE,
            run_id UUID NOT NULL
                REFERENCES runs(id) ON DELETE CASCADE,
            first_seen_in_run BOOLEAN NOT NULL DEFAULT TRUE,
            surfaces_in_run TEXT[] NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (evidence_id, run_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_evidence_run_links_run "
        "ON evidence_run_links (run_id)"
    )

    # ── dedup_audit ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS dedup_audit (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            source_e_id VARCHAR(32) NOT NULL,
            kept_evidence_id UUID
                REFERENCES evidence_index(id) ON DELETE SET NULL,
            action VARCHAR(24) NOT NULL,
            reason TEXT,
            content_hash VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (action IN (
                'kept', 'dedup_same_entity', 'cross_entity_kept',
                'duplicate_within_run', 'tier_upgrade'
            ))
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dedup_audit_run "
        "ON dedup_audit (run_id, action)"
    )

    # ── customer_intelligence_profiles ───────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS customer_intelligence_profiles (
            entity_id UUID PRIMARY KEY
                REFERENCES entities(id) ON DELETE CASCADE,

            first_dma_at TIMESTAMPTZ NOT NULL,
            latest_dma_at TIMESTAMPTZ NOT NULL,
            total_runs INTEGER NOT NULL DEFAULT 0,

            total_evidence_count INTEGER NOT NULL DEFAULT 0,
            unique_evidence_count INTEGER NOT NULL DEFAULT 0,
            median_evidence_age_months NUMERIC(5,1),
            stale_evidence_pct NUMERIC(5,2),

            maturity_history JSONB NOT NULL DEFAULT '[]'::jsonb,
            maturity_velocity NUMERIC(6,3),

            archetype_history JSONB NOT NULL DEFAULT '[]'::jsonb,

            recurring_themes TEXT[] NOT NULL DEFAULT '{}',
            emerging_themes TEXT[] NOT NULL DEFAULT '{}',

            persistent_gap_subcap_ids TEXT[] NOT NULL DEFAULT '{}',
            closed_gap_subcap_ids TEXT[] NOT NULL DEFAULT '{}',

            tech_stack_additions JSONB NOT NULL DEFAULT '[]'::jsonb,
            tech_stack_removals JSONB NOT NULL DEFAULT '[]'::jsonb,

            intelligence_summary_md TEXT,
            summary_embedding vector(768),
            summary_grounding_evidence_ids TEXT[]
                NOT NULL DEFAULT '{}',

            computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            computed_for_run_id UUID
                REFERENCES runs(id) ON DELETE SET NULL,
            catalogue_version VARCHAR(16) NOT NULL
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cust_profiles_latest "
        "ON customer_intelligence_profiles (latest_dma_at DESC)"
    )

    # ── focus_areas (Client Profile parser) ──────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS focus_areas (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
            entity_id UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            verbatim_quote TEXT NOT NULL,
            source_path TEXT,
            page_number INTEGER,
            involved_subcap_ids TEXT[] NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_focus_areas_entity "
        "ON focus_areas (entity_id, run_id)"
    )

    # ── firmographics columns (table may exist in live env) ──────────
    # Make optional — only ADD if the table exists.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = 'firmographics'
            ) THEN
                BEGIN
                    ALTER TABLE firmographics
                        ADD COLUMN IF NOT EXISTS narrative_md TEXT;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END;
                BEGIN
                    ALTER TABLE firmographics
                        ADD COLUMN IF NOT EXISTS leadership JSONB
                            NOT NULL DEFAULT '[]'::jsonb;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END;
                BEGIN
                    ALTER TABLE firmographics
                        ADD COLUMN IF NOT EXISTS financial_highlights JSONB
                            NOT NULL DEFAULT '{}'::jsonb;
                EXCEPTION WHEN duplicate_column THEN NULL;
                END;
            END IF;
        END
        $$
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS focus_areas")
    op.execute("DROP TABLE IF EXISTS customer_intelligence_profiles")
    op.execute("DROP TABLE IF EXISTS dedup_audit")
    op.execute("DROP TABLE IF EXISTS evidence_run_links")
    op.execute("DROP TRIGGER IF EXISTS trg_evidence_freshness ON evidence_index")
    op.execute("DROP FUNCTION IF EXISTS evidence_freshness_trigger()")
    op.execute("DROP FUNCTION IF EXISTS refresh_evidence_freshness()")
    op.execute("DROP FUNCTION IF EXISTS compute_evidence_freshness_band(DATE, INTEGER)")
    op.execute("ALTER TABLE evidence_index DROP COLUMN IF EXISTS freshness_band")
    op.execute("ALTER TABLE evidence_index DROP COLUMN IF EXISTS is_stale")
    op.execute("ALTER TABLE evidence_index DROP COLUMN IF EXISTS content_hash")
