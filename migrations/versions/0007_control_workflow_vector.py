"""Control & audit (7) + Workflow (5) + Vector (2)

Backend Schema §07 (gate registry/results/threshold history, identity
quarantine, dedup audit, run links, audit log), §11 (the four per-person
workflow tables + idempotency_keys per TRD §19 verbatim DDL), §12 (the
vector tier: embeddings + centroids, HNSW created once here at migration
— the graph then grows incrementally per run, off the critical path).

alert_actions.alert_id references heatmap_alerts, which lands in the
serving-tier revision; the FK is added there (same deferred-FK pattern as
document_sections→import_files) so no FK ever points at a missing table.

Grant notes beyond the §03 matrix, each tied to a documented read path:
- api SELECT on gate_registry + gate_results — H5/Health composes the
  gates[] array (SG results incl. NOT_RUN) from them at read (QA B-03).
- api SELECT on evidence_run_links — the §10 evidence-drawer query counts
  seen_in_runs.
- api writes on user_workspace / saved_searches / idempotency_keys — the
  workflow tier is per-person state and the API is the only user-facing
  service; the invariant-2 write boundary concerns CONTENT (annotations +
  alert actions are still the only content-adjacent writes, both behind
  Idempotency-Key). Tighten at stage 4 if the auth flow lands differently.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-04
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Control & audit ─────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE gate_registry (
          gate_id           TEXT PRIMARY KEY,   -- prefixed by family; the prefix is part of the id
          family            gate_family_t,
          name              TEXT,
          plain_label       TEXT,               -- REQUIRED for safeguard gates: 8-18 words
          what_it_checks    TEXT,
          why_it_exists     TEXT,
          threshold_kind    TEXT,               -- per_client_rate · absolute · boolean
          threshold_value   NUMERIC,            -- rates, not counts
          on_failure        TEXT,               -- block · disclose · trigger · fail_build
          is_client_visible BOOLEAN             -- TRUE only for the safeguard family
        )
        """
    )
    op.execute(
        """
        CREATE TABLE gate_results (
          id             BIGSERIAL PRIMARY KEY,
          run_id         UUID REFERENCES runs(id),
          gate_id        TEXT REFERENCES gate_registry(gate_id),
          result         gate_result_t,          -- never default to PASS
          not_run_reason TEXT,
          detail         JSONB,                  -- the measurement, so a client-visible gate can state a number
          evaluated_at   TIMESTAMPTZ,
          CONSTRAINT not_run_needs_reason
            CHECK (result <> 'NOT_RUN' OR not_run_reason IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE gate_threshold_history (
          id                    BIGSERIAL PRIMARY KEY,
          gate_id               TEXT REFERENCES gate_registry(gate_id),
          changed_from          NUMERIC,
          changed_to            NUMERIC,        -- for corpus gates never greater; enforced in CI (Gate B)
          reason                TEXT,           -- REQUIRED: an unexplained ceiling is one nobody trusts
          measured_at_n_clients INTEGER,
          changed_at            TIMESTAMPTZ,
          changed_by            TEXT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE identity_quarantine (
          id                BIGSERIAL PRIMARY KEY,
          run_id            UUID REFERENCES runs(id),
          entity_id         UUID REFERENCES entities(id),
          surface_id        TEXT,               -- which of the 38 surfaces it would have appeared on
          field_path        TEXT,               -- the JSON path within the section
          attempted_value   TEXT,               -- kept for diagnosis; NEVER rendered
          failed_assertion  TEXT,               -- legal_name · regulator · footprint · source_domain · magnitude
          quarantine_reason TEXT,               -- rendered as the provenance note beside the dash
          occurred_at       TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE evidence_dedup_audit (
          id           BIGSERIAL PRIMARY KEY,
          e_id         TEXT REFERENCES evidence_index(e_id),
          content_hash TEXT,
          branch       dedup_branch_t,
          matched_e_id TEXT,                    -- the existing row, where one was matched
          occurred_at  TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE evidence_run_links (
          e_id        TEXT REFERENCES evidence_index(e_id),
          run_id      UUID REFERENCES runs(id),
          surface_ids TEXT[],                   -- powers the seen-in-N-runs chip
          PRIMARY KEY (e_id, run_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE audit_log (
          id          BIGSERIAL PRIMARY KEY,
          actor       TEXT,     -- service credential or user
          action      TEXT,     -- promotions, claim acquisitions, threshold changes, ...
          target      TEXT,
          before_json JSONB,
          after_json  JSONB,
          occurred_at TIMESTAMPTZ
        )
        """
    )

    # ── Workflow (per-person state; nothing here reaches a serving table) ─
    op.execute(
        """
        CREATE TABLE annotations (
          id          BIGSERIAL PRIMARY KEY,
          user_id     UUID REFERENCES users(id),
          entity_id   UUID REFERENCES entities(id),
          run_id      UUID REFERENCES runs(id),
          anchor_kind TEXT,   -- insight_card · finding · cell · recommendation · issue
          anchor_id   TEXT,
          body        TEXT,
          created_at  TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE alert_actions (
          id          BIGSERIAL PRIMARY KEY,
          alert_id    BIGINT,                   -- FK to heatmap_alerts added in the serving revision
          user_id     UUID REFERENCES users(id),
          action      alert_action_t,
          rationale   TEXT,                     -- REQUIRED on waive (enforced below)
          run_id      UUID REFERENCES runs(id), -- the action stays attached to its run
          occurred_at TIMESTAMPTZ,
          CONSTRAINT waive_needs_rationale
            CHECK (action <> 'waived' OR rationale IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE user_workspace (
          user_id          UUID REFERENCES users(id),
          entity_id        UUID REFERENCES entities(id),
          last_run_id      UUID REFERENCES runs(id),   -- defaults the URL pin
          last_tab         TEXT,
          audience_pref    TEXT,                        -- internal or customer, per entity
          kpi_strip_config JSONB,                       -- view preference, not content
          insight_grouping TEXT,                        -- priority · pillar · theme
          updated_at       TIMESTAMPTZ,
          PRIMARY KEY (user_id, entity_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE saved_searches (
          id         BIGSERIAL PRIMARY KEY,
          user_id    UUID REFERENCES users(id),
          name       TEXT,
          query      JSONB,     -- the full filter set, so the result is reproducible
          created_at TIMESTAMPTZ
        )
        """
    )
    # TRD §19 verbatim: a replay returns the ORIGINAL response; same key +
    # different body is a 409.
    op.execute(
        """
        CREATE TABLE idempotency_keys (
          key          UUID PRIMARY KEY,
          user_id      UUID NOT NULL,
          request_hash TEXT NOT NULL,
          status_code  SMALLINT NOT NULL,
          response     JSONB NOT NULL,
          created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # ── Vector tier (§12) — build-time grounding only, never serving ────
    op.execute(
        """
        CREATE TABLE bundle_embeddings (
          id              BIGSERIAL PRIMARY KEY,
          run_id          UUID REFERENCES runs(id) ON DELETE CASCADE,  -- embeddings die with their run
          scope_kind      scope_t,
          scope_id        TEXT,                 -- P4C1.2.1 · P4C1 · P4 · NULL for run scope
          source_kind     TEXT,                 -- evidence · report_section · score_rationale
          source_ref      TEXT,                 -- traceability back to a real row
          chunk_index     SMALLINT,             -- sentence-window chunking, 60-120 tokens, 20% overlap
          content         TEXT,                 -- retained, so a flagged field can be told what it matched
          embedding       vector(384) NOT NULL, -- L2-normalised at write
          embedding_model TEXT NOT NULL,        -- pinned; a mixed-model index returns plausible nonsense
          created_at      TIMESTAMPTZ,
          CONSTRAINT emb_dim_384 CHECK (vector_dims(embedding) = 384)
        )
        """
    )
    # HNSW, not IVFFlat — incremental, no training pass; created ONCE here.
    op.execute(
        """
        CREATE INDEX bundle_emb_hnsw ON bundle_embeddings
          USING hnsw (embedding vector_cosine_ops)
          WITH (m = 16, ef_construction = 64)
        """
    )
    op.execute("CREATE INDEX bundle_emb_run ON bundle_embeddings (run_id, scope_kind, scope_id)")
    op.execute(
        """
        CREATE TABLE bundle_centroids (
          run_id     UUID REFERENCES runs(id),
          scope_kind scope_t,
          scope_id   TEXT NOT NULL DEFAULT '',  -- '' stands for the run scope in the key
          centroid   vector(384) NOT NULL,      -- mean of the normalised members, renormalised
          member_n   INTEGER NOT NULL,          -- below five the check abstains
          threshold  REAL NOT NULL,             -- per scope; tightens as the scope narrows
          PRIMARY KEY (run_id, scope_kind, scope_id)
        )
        """
    )

    # ── Grants ──────────────────────────────────────────────────────────
    control = ["gate_registry", "gate_results", "gate_threshold_history",
               "identity_quarantine", "evidence_dedup_audit",
               "evidence_run_links", "audit_log"]
    for t in control:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO svc_mcp")
    for seq in ("gate_results_id_seq", "gate_threshold_history_id_seq",
                "identity_quarantine_id_seq", "evidence_dedup_audit_id_seq",
                "audit_log_id_seq"):
        op.execute(f"GRANT USAGE ON SEQUENCE {seq} TO svc_mcp")
    op.execute("GRANT SELECT ON gate_registry, gate_results, evidence_run_links TO svc_api")
    # The worker also audits state changes it makes (scans, run creation).
    op.execute("GRANT INSERT ON audit_log TO svc_worker")
    op.execute("GRANT USAGE ON SEQUENCE audit_log_id_seq TO svc_worker")

    workflow = ["annotations", "alert_actions", "user_workspace",
                "saved_searches", "idempotency_keys"]
    for t in workflow:
        op.execute(f"GRANT SELECT ON {t} TO svc_api")
    op.execute("GRANT INSERT ON annotations TO svc_api")
    op.execute("GRANT INSERT ON alert_actions TO svc_api")
    op.execute("GRANT INSERT, UPDATE ON user_workspace TO svc_api")
    op.execute("GRANT INSERT, DELETE ON saved_searches TO svc_api")
    op.execute("GRANT INSERT ON idempotency_keys TO svc_api")
    for seq in ("annotations_id_seq", "alert_actions_id_seq", "saved_searches_id_seq"):
        op.execute(f"GRANT USAGE ON SEQUENCE {seq} TO svc_api")

    # Vector: worker writes at ingest (parse/embed batch); mcp reads for V4
    # and refreshes centroids at submit when needed.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON bundle_embeddings TO svc_worker")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON bundle_centroids TO svc_worker")
    op.execute("GRANT USAGE ON SEQUENCE bundle_embeddings_id_seq TO svc_worker")
    op.execute("GRANT SELECT ON bundle_embeddings, bundle_centroids TO svc_mcp")


def downgrade() -> None:
    for t in ("bundle_centroids", "bundle_embeddings", "idempotency_keys",
              "saved_searches", "user_workspace", "alert_actions", "annotations",
              "audit_log", "evidence_run_links", "evidence_dedup_audit",
              "identity_quarantine", "gate_threshold_history", "gate_results",
              "gate_registry"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
