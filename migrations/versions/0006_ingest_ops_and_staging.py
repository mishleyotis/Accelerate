"""Ingest-ops (3) + Staging tier (3)

Ingest-ops columns encode TRD §07's recorded behaviours: every file the
scan encounters is recorded (including skipped/test-case exclusions, with
the rule that fired); classification carries artefact kind + source
priority; the dedup loser is retained and marked, never deleted; artefact
bytes are retained in object storage (gcs_uri) for excerpt verification;
every parse anomaly is a parser observation (unparseable cell, unverified
excerpt, unresolved cell id, artefact disagreement), surfaced on D7.
Exact shapes finalise with the stage 1.x worker (expand–migrate).

Staging is Backend Schema §05 verbatim: written by the connector at
submit, read at promote, invisible to the API by grant — svc_mcp holds
the only staging DML; svc_api and svc_worker have no grant of any kind.

Also adds the document_sections.artefact_id FK deferred from 0005
(import_files now exists, so no FK ever pointed at a missing table).

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-04
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Ingest ops ──────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE import_scans (
          id            BIGSERIAL PRIMARY KEY,
          started_at    TIMESTAMPTZ,
          finished_at   TIMESTAMPTZ,
          folders_seen  INTEGER,
          files_seen    INTEGER,
          files_new     INTEGER,          -- the diff against previous scans
          files_changed INTEGER,
          runs_created  INTEGER,          -- 0 on an unchanged tree (idempotency)
          status        TEXT,             -- running · succeeded · failed
          error         TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE import_files (
          artefact_id     TEXT PRIMARY KEY,
          scan_id         BIGINT REFERENCES import_scans(id),
          drive_file_id   TEXT,
          name            TEXT,
          mime_type       TEXT,
          checksum        TEXT,            -- drives the unchanged-tree diff
          size_bytes      BIGINT,
          classified_kind TEXT,            -- against the artefact registry
          source_priority SMALLINT,        -- TRD §07 artefact priority 1-5
          excluded        BOOLEAN,         -- test cases excluded, recorded
          exclusion_rule  TEXT,            -- the rule that fired
          dedup_loser     BOOLEAN,         -- marked, never deleted
          dedup_rule      TEXT,            -- which of the four ordered rules
          entity_id       UUID REFERENCES entities(id),
          run_id          UUID REFERENCES runs(id),
          gcs_uri         TEXT,            -- retained bytes; excerpt verification reads them
          first_seen_at   TIMESTAMPTZ,
          last_seen_at    TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE parser_observations (
          id          BIGSERIAL PRIMARY KEY,
          run_id      UUID REFERENCES runs(id),
          artefact_id TEXT REFERENCES import_files(artefact_id),
          kind        TEXT,   -- unparseable_cell · unverified_excerpt ·
                              -- unresolved_cell_id · artefact_disagreement · ...
          detail      JSONB,  -- both ids on a resolution failure, both figures on a disagreement
          occurred_at TIMESTAMPTZ
        )
        """
    )
    # Deferred from 0005 — the FK target now exists.
    op.execute(
        """
        ALTER TABLE document_sections
          ADD CONSTRAINT document_sections_artefact_fk
          FOREIGN KEY (artefact_id) REFERENCES import_files(artefact_id)
        """
    )

    # ── Staging (§05 verbatim) ──────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE run_claims (
          run_id           UUID PRIMARY KEY REFERENCES runs(id),
          held_by          TEXT,            -- session identifier
          claimed_at       TIMESTAMPTZ,
          expires_at       TIMESTAMPTZ,     -- a dead session cannot block a run permanently
          producer_version TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE submissions (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          run_id           UUID REFERENCES runs(id),
          page             page_t,
          payload          JSONB,            -- the full page payload as submitted
          status           submission_status_t,
          provenance       provenance_t,
          producer_version TEXT,
          contract_version TEXT,             -- the payload shape this validated against
          submitted_by     TEXT,             -- the service credential, never a user
          submitted_at     TIMESTAMPTZ,
          superseded_at    TIMESTAMPTZ,      -- NULL while live
          superseded_by    UUID REFERENCES submissions(id),
          promoted_at      TIMESTAMPTZ       -- set by promote_run
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX submissions_live_uq
          ON submissions (run_id, page)
          WHERE superseded_at IS NULL
        """
    )
    op.execute(
        """
        CREATE TABLE submission_verdicts (
          id            BIGSERIAL PRIMARY KEY,
          submission_id UUID REFERENCES submissions(id),
          status        submission_status_t,
          reasons       JSONB,   -- [{gate_id, section, path, message, severity}]
          warnings      JSONB,   -- non-blocking
          counts        JSONB,   -- {sections, cited_claims, e_ids_used, new_mints}
          evaluated_at  TIMESTAMPTZ
        )
        """
    )
    op.execute("CREATE INDEX submission_verdicts_submission ON submission_verdicts (submission_id)")

    # ── Grants ──────────────────────────────────────────────────────────
    for t in ("import_scans", "import_files", "parser_observations"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO svc_worker")
    op.execute("GRANT USAGE ON SEQUENCE import_scans_id_seq TO svc_worker")
    op.execute("GRANT USAGE ON SEQUENCE parser_observations_id_seq TO svc_worker")
    # Excerpt verification resolves artefact bytes through import_files.
    op.execute("GRANT SELECT ON import_files TO svc_mcp")

    # Staging: the connector only. No grant of any kind to svc_api (the
    # boundary) or svc_worker.
    for t in ("run_claims", "submissions", "submission_verdicts"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO svc_mcp")
    op.execute("GRANT USAGE ON SEQUENCE submission_verdicts_id_seq TO svc_mcp")


def downgrade() -> None:
    for t in ("submission_verdicts", "submissions", "run_claims"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
    op.execute("ALTER TABLE document_sections DROP CONSTRAINT IF EXISTS document_sections_artefact_fk")
    for t in ("parser_observations", "import_files", "import_scans"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
