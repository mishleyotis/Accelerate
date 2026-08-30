"""0034 — the findings memory: what went wrong, how it was measured, what was
changed about it, and whether the change held.

A build that keeps producing the same class of defect is not learning. This
revision is where the learning is kept, and the connector (`dma_mcp/memory.py`)
is the only thing that writes it.

## Why the connector, and why an embedding at write time is not invariant 1

The connector already bundles the 384-dim encoder in-image for V4 grounding; the
database already has `vector`, `pg_trgm` and HNSW indexes created at migration;
and the connector is already the only component permitted to write. Nothing new
has to be built or granted for a finding to arrive embedded.

Invariant 1 forbids a model call ON THE SERVING REQUEST PATH. A finding is
embedded when it is RECORDED, inside the connector, exactly as V4 embeds at
submit — never while a client is looking at a page. `search_findings` runs an
index scan against a vector the caller supplies or that was stored at write time.
An index scan is not a model call. If that distinction is ever used to justify
embedding something on the serving path, it has been misread: the rule is the
serving path never touches the encoder, and this revision does not change it.

## The six tables

**memory_defect_classes** — the taxonomy, and the reason it is a foreign key.
A memory rots when three agents file the same defect under three synonyms. The
class is therefore a reference, not free text: an unknown class is refused with
the list of known ones, and a genuinely new class may be created only by DEFINING
it (title, description, `tell` — how it presents — and `probe` — the command or
query that detects it). You may invent a class; you may not invent one silently.

**memory_findings** — one row per DEFECT, not per report. Deduplicated by content
hash exactly as `register_evidence` dedups evidence, so the same defect reported
by three QA agents is one finding with three sightings.

`measurement` is NOT NULL with a length floor. A finding that cannot say how it
was measured is an opinion, and the schema makes it hard to store one. The floor
is 30 characters — enough that "it broke" fails and a command, a query, an HTTP
status with a URL, or a count with its denominator passes.

`status` may only reach RESOLVED with a `resolved_by` refinement: closing a
finding requires naming the change that closed it. That is the constraint the
recurrence signal is built on — without it, "did the fix hold?" has no subject.

**memory_finding_sightings** — every report of a finding, including the first.
A sighting after a refinement carries `after_refinement`, which is what makes it
a RECURRENCE: a fix that did not hold is more informative than one that did, and
it is recorded against the fix by name. `source_ref` is the caller's idempotency
token (an annotation id, a CI run id), so ingesting the same reviewer verdict
twice adds one sighting, not two.

**memory_refinements** — what changed, in which skill, agent or component, with
the commit sha. `memory_refinements_locatable` requires either a `commit_sha` or
a `change_ref`: a refinement nobody can locate is a claim, not a change.

**memory_refinement_findings** — the many-to-many. One refinement usually answers
several findings; one finding is sometimes attacked twice.

**memory_reviewer_verdicts** — where the web app's Accept/Reject pair lands.
One row per annotation, UNIQUE on `annotation_id`, so the consumer can be re-run
for free. It is not a copy of `annotations`: it carries the CARD'S OWN TEXT and
its `r_layer` as they were when the verdict was cast, because a re-promotion
rewrites the card and a verdict against text that no longer exists teaches
nothing about what was actually rejected. `memory_reviewer_verdicts_reject_lands`
requires a REJECT to name the finding it raised — a rejection that produced no
finding is a verdict that went nowhere, which is the exact failure this whole
revision exists to end.

## Counts are computed, never stored (invariant 8)

`sightings`, `recurrences`, `age_days` and a refinement's `held` are all views
over the two source tables. A stored sighting count would drift the first time a
row was inserted by anything other than the tool that increments it, and the
whole value of this store is that its numbers can be trusted.

## Indexes

Plain `CREATE INDEX`, not CONCURRENTLY: these tables are created empty in this
same transaction, so there is nothing to lock and nothing to block. HNSW is
created once here, at migration, per the charter — m=16, ef_construction=64,
`vector_cosine_ops`, matching every other vector index in this database.

Revision ID: 0034
Revises: 0033
Create Date: 2026-08-08
"""
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

# Kept in one place because three tables enumerate them and a test asserts the
# connector's vocabularies are the same list.
SEVERITIES = ("BLOCKER", "MAJOR", "MINOR", "INFO")
STATUSES = ("OPEN", "INVESTIGATING", "RESOLVED", "RECURRED", "WONTFIX", "DUPLICATE")
RAISERS = ("QA_AGENT", "REVIEWER", "GATE", "USER", "BUILD_AGENT", "TEST", "MONITOR")
TARGET_KINDS = ("SKILL", "AGENT", "COMPONENT", "GATE", "TEST", "SCHEMA", "DOC",
                "PROCESS")


def _in(col, values):
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE memory_defect_classes (
          class_id    TEXT PRIMARY KEY,   -- SCREAMING_SNAKE, stable, cited by findings
          title       TEXT NOT NULL,      -- one line, human
          description TEXT NOT NULL,      -- what the class IS
          -- How it PRESENTS. The tell is what a reader actually sees when the
          -- defect is live, which is the only part of a class an agent can
          -- match against a symptom it is holding.
          tell        TEXT NOT NULL,
          -- How to CHECK. A command, a query or a request that returns a
          -- number. A class with no probe cannot be swept for, so it can only
          -- ever be rediscovered by accident.
          probe       TEXT NOT NULL,
          created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          created_by  TEXT
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE memory_refinements (
          id            BIGSERIAL PRIMARY KEY,
          refinement_id TEXT NOT NULL UNIQUE,   -- REF-0001; the SERVER allocates it
          target_kind   TEXT NOT NULL,
          -- The thing that changed, named the way its owner names it:
          -- `skill:dma-surface-production`, `agent:rectifier`, `CG-13`,
          -- `apps/mcp/dma_mcp/promote.py`.
          target        TEXT NOT NULL,
          change        TEXT NOT NULL,          -- what was changed, in prose
          rationale     TEXT,                   -- why this change and not another
          commit_sha    TEXT,
          -- For a change with no commit: a skill version, an artefact URL, a
          -- Cowork session id. One of the two is required.
          change_ref    TEXT,
          -- The gate added in response, so the memory holds the fix beside the
          -- defect rather than in a different system.
          gate_added    TEXT,
          verification  TEXT,                   -- the test or probe that proves it
          applied_by    TEXT NOT NULL,
          applied_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT memory_refinements_kind CHECK ({_in('target_kind', TARGET_KINDS)}),
          CONSTRAINT memory_refinements_locatable
            CHECK (commit_sha IS NOT NULL OR change_ref IS NOT NULL)
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE memory_findings (
          id             BIGSERIAL PRIMARY KEY,
          finding_id     TEXT NOT NULL UNIQUE,  -- MEM-0001; the SERVER allocates it
          -- Dedup key. Same discipline as evidence_index.content_hash: the same
          -- defect reported six times is one row, six sightings.
          content_hash   TEXT NOT NULL UNIQUE,
          title          TEXT NOT NULL,         -- one line; what is wrong
          observed       TEXT NOT NULL,         -- what was actually seen
          -- HOW IT WAS MEASURED. Required, with a length floor: a finding that
          -- cannot say how it was measured is an opinion.
          measurement    TEXT NOT NULL,
          measured_value TEXT,                  -- the number/status itself
          expected       TEXT,                  -- what it should have been
          -- WHERE. component is required; the rest narrow it.
          component      TEXT NOT NULL,         -- api · mcp · web · worker · migrations · infra · skill:x · agent:x
          file_path      TEXT,
          surface        TEXT,                  -- Surface Specification id (H4, H1, ...)
          gate_id        TEXT,                  -- when the finding IS a verdict
          defect_class   TEXT NOT NULL REFERENCES memory_defect_classes(class_id),
          severity       TEXT NOT NULL,
          status         TEXT NOT NULL DEFAULT 'OPEN',
          raised_by_kind TEXT NOT NULL,
          raised_by      TEXT NOT NULL,         -- the agent, gate or person by name
          run_id         UUID REFERENCES runs(id),
          entity_id      UUID REFERENCES entities(id),
          -- The reviewer verdict this finding came from, when it came from one.
          annotation_id  BIGINT REFERENCES annotations(id),
          fix_hint       TEXT,
          duplicate_of   TEXT REFERENCES memory_findings(finding_id),
          resolved_at    TIMESTAMPTZ,
          resolved_by    TEXT REFERENCES memory_refinements(refinement_id),
          first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
          last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
          -- Written by the connector at RECORD time with the same bundled
          -- 384-dim model V4 uses. NULL is a legal state: no encoder in the
          -- image means the lexical paths still answer.
          embedding      vector(384),
          embedding_model TEXT,
          search_tsv     tsvector GENERATED ALWAYS AS (
                           to_tsvector('english',
                             coalesce(title, '') || ' ' ||
                             coalesce(observed, '') || ' ' ||
                             coalesce(measurement, '') || ' ' ||
                             coalesce(component, '') || ' ' ||
                             coalesce(defect_class, ''))) STORED,
          CONSTRAINT memory_findings_severity CHECK ({_in('severity', SEVERITIES)}),
          CONSTRAINT memory_findings_status CHECK ({_in('status', STATUSES)}),
          CONSTRAINT memory_findings_raiser CHECK ({_in('raised_by_kind', RAISERS)}),
          -- An opinion cannot be stored as a finding.
          CONSTRAINT memory_findings_measured
            CHECK (length(btrim(measurement)) >= 30),
          -- Closing a finding requires naming the change that closed it.
          CONSTRAINT memory_findings_resolution_named
            CHECK (status <> 'RESOLVED'
                   OR (resolved_by IS NOT NULL AND resolved_at IS NOT NULL)),
          CONSTRAINT memory_findings_duplicate_named
            CHECK (status <> 'DUPLICATE' OR duplicate_of IS NOT NULL),
          CONSTRAINT memory_findings_dim
            CHECK (embedding IS NULL OR vector_dims(embedding) = 384),
          CONSTRAINT memory_findings_model
            CHECK (embedding IS NULL OR embedding_model IS NOT NULL)
        )
        """
    )

    op.execute(
        f"""
        CREATE TABLE memory_finding_sightings (
          id               BIGSERIAL PRIMARY KEY,
          finding_id       TEXT NOT NULL REFERENCES memory_findings(finding_id)
                                ON DELETE CASCADE,
          reported_by_kind TEXT NOT NULL,
          reported_by      TEXT NOT NULL,
          observed_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
          -- The chat, Cowork session or CI job that saw it. Free text: the loop
          -- spans sessions and none of them is a row in this database.
          session_ref      TEXT,
          -- The caller's idempotency token for THIS sighting (an annotation id,
          -- a CI run id). Unique per finding when present, so replaying an
          -- ingest adds nothing.
          source_ref       TEXT,
          measurement      TEXT,
          measured_value   TEXT,
          note             TEXT,
          run_id           UUID REFERENCES runs(id),
          entity_id        UUID REFERENCES entities(id),
          annotation_id    BIGINT REFERENCES annotations(id),
          -- Set when this sighting is a RECURRENCE: the refinement that was
          -- believed to have closed the finding and did not hold.
          after_refinement TEXT REFERENCES memory_refinements(refinement_id),
          CONSTRAINT memory_sightings_reporter CHECK ({_in('reported_by_kind', RAISERS)})
        )
        """
    )

    op.execute(
        """
        CREATE TABLE memory_refinement_findings (
          refinement_id TEXT NOT NULL REFERENCES memory_refinements(refinement_id)
                             ON DELETE CASCADE,
          finding_id    TEXT NOT NULL REFERENCES memory_findings(finding_id)
                             ON DELETE CASCADE,
          -- ADDRESSES: this change was made because of that finding.
          -- CLOSES:    this change is the one that resolved it.
          relation      TEXT NOT NULL DEFAULT 'ADDRESSES',
          linked_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (refinement_id, finding_id),
          CONSTRAINT memory_refinement_findings_relation
            CHECK (relation IN ('ADDRESSES', 'CLOSES'))
        )
        """
    )

    op.execute(
        """
        CREATE TABLE memory_reviewer_verdicts (
          id                BIGSERIAL PRIMARY KEY,
          -- One row per annotation, exactly once. This is the ingestion
          -- cursor's own record: UNIQUE is what makes re-running the consumer
          -- free.
          annotation_id     BIGINT NOT NULL UNIQUE REFERENCES annotations(id),
          action            TEXT NOT NULL,
          note              TEXT,
          actor_email       TEXT NOT NULL,
          entity_display_id TEXT,
          entity_id         UUID REFERENCES entities(id),
          run_id            UUID REFERENCES runs(id),
          ic_id             TEXT NOT NULL,
          -- The claim the reviewer was judging, copied at ingestion. NOT a
          -- duplicate of insight_cards: a re-promotion rewrites the card, and
          -- a verdict against text that no longer exists teaches nothing about
          -- what was actually rejected.
          card_title        TEXT,
          card_text         TEXT,
          card_severity     TEXT,
          card_claim_label  TEXT,
          card_subcap_id    TEXT,
          -- The recorded reasoning the reviewer accepted or rejected. This is
          -- the whole point of capturing the verdict at all: a reject against
          -- an r_layer says which REASONING failed, not just which card.
          r_layer           JSONB,
          -- Set for a REJECT: the finding this verdict raised or added to.
          finding_id        TEXT REFERENCES memory_findings(finding_id),
          verdict_at        TIMESTAMPTZ NOT NULL,
          ingested_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT memory_reviewer_verdicts_action
            CHECK (action IN ('ACCEPT', 'REJECT')),
          -- A reject that raised no finding is a verdict that taught nothing.
          CONSTRAINT memory_reviewer_verdicts_reject_lands
            CHECK (action <> 'REJECT' OR finding_id IS NOT NULL)
        )
        """
    )

    # ── indexes ────────────────────────────────────────────────────────
    op.execute("CREATE INDEX memory_findings_open_idx ON memory_findings "
               "(status, component, severity)")
    op.execute("CREATE INDEX memory_findings_class_idx ON memory_findings "
               "(defect_class, status)")
    op.execute("CREATE INDEX memory_findings_seen_idx ON memory_findings "
               "(last_seen_at DESC)")
    op.execute("CREATE INDEX memory_findings_annotation_idx ON memory_findings "
               "(annotation_id) WHERE annotation_id IS NOT NULL")
    op.execute("CREATE INDEX memory_findings_tsv ON memory_findings "
               "USING gin (search_tsv)")
    op.execute("CREATE INDEX memory_findings_trgm ON memory_findings "
               "USING gin (title gin_trgm_ops)")
    op.execute(
        """
        CREATE INDEX memory_findings_hnsw ON memory_findings
          USING hnsw (embedding vector_cosine_ops)
          WITH (m = 16, ef_construction = 64)
        """
    )
    op.execute("CREATE INDEX memory_sightings_finding_idx "
               "ON memory_finding_sightings (finding_id, observed_at DESC)")
    op.execute("CREATE UNIQUE INDEX memory_sightings_source_uq "
               "ON memory_finding_sightings (finding_id, source_ref) "
               "WHERE source_ref IS NOT NULL")
    op.execute("CREATE INDEX memory_sightings_recurrence_idx "
               "ON memory_finding_sightings (after_refinement) "
               "WHERE after_refinement IS NOT NULL")
    op.execute("CREATE INDEX memory_sightings_annotation_idx "
               "ON memory_finding_sightings (annotation_id) "
               "WHERE annotation_id IS NOT NULL")
    op.execute("CREATE INDEX memory_verdicts_card_idx "
               "ON memory_reviewer_verdicts (entity_display_id, ic_id, "
               "verdict_at DESC)")
    op.execute("CREATE INDEX memory_verdicts_run_idx "
               "ON memory_reviewer_verdicts (run_id, action)")

    # ── computed views (invariant 8: counts are never stored) ──────────
    op.execute(
        """
        CREATE VIEW memory_finding_state AS
        SELECT f.finding_id, f.title, f.component, f.file_path, f.surface,
               f.gate_id, f.defect_class, f.severity, f.status,
               f.raised_by_kind, f.raised_by, f.measurement, f.measured_value,
               f.fix_hint, f.resolved_by, f.resolved_at, f.annotation_id,
               f.first_seen_at, f.last_seen_at,
               count(s.id)                                        AS sightings,
               count(s.id) FILTER (WHERE s.after_refinement IS NOT NULL)
                                                                  AS recurrences,
               max(s.observed_at) FILTER (WHERE s.after_refinement IS NOT NULL)
                                                                  AS last_recurrence_at,
               (EXTRACT(EPOCH FROM (now() - f.first_seen_at)) / 86400)::int
                                                                  AS age_days
          FROM memory_findings f
          LEFT JOIN memory_finding_sightings s ON s.finding_id = f.finding_id
         GROUP BY f.finding_id, f.title, f.component, f.file_path, f.surface,
                  f.gate_id, f.defect_class, f.severity, f.status,
                  f.raised_by_kind, f.raised_by, f.measurement, f.measured_value,
                  f.fix_hint, f.resolved_by, f.resolved_at, f.annotation_id,
                  f.first_seen_at, f.last_seen_at
        """
    )
    op.execute(
        """
        CREATE VIEW memory_refinement_outcome AS
        SELECT r.refinement_id, r.target_kind, r.target, r.change, r.gate_added,
               r.commit_sha, r.change_ref, r.applied_by, r.applied_at,
               count(DISTINCT l.finding_id)                       AS findings_addressed,
               count(DISTINCT s.finding_id)
                 FILTER (WHERE s.observed_at > r.applied_at)      AS findings_recurred,
               max(s.observed_at) FILTER (WHERE s.observed_at > r.applied_at)
                                                                  AS last_recurrence_at,
               -- HELD is computed, never asserted: a refinement holds while no
               -- finding it addressed has been sighted since it was applied.
               (count(DISTINCT s.finding_id)
                  FILTER (WHERE s.observed_at > r.applied_at) = 0) AS held
          FROM memory_refinements r
          LEFT JOIN memory_refinement_findings l
                 ON l.refinement_id = r.refinement_id
          LEFT JOIN memory_finding_sightings s
                 ON s.finding_id = l.finding_id
         GROUP BY r.refinement_id, r.target_kind, r.target, r.change,
                  r.gate_added, r.commit_sha, r.change_ref, r.applied_by,
                  r.applied_at
        """
    )

    # ── grants, in the same revision as the tables ─────────────────────
    tables = ("memory_defect_classes", "memory_findings",
              "memory_finding_sightings", "memory_refinements",
              "memory_refinement_findings", "memory_reviewer_verdicts")
    for t in tables:
        # The connector is the only writer — the same posture as every other
        # table in this database (invariant 2).
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO svc_mcp")
        # The API reads: a future surface renders the memory, and a read adds
        # no content.
        op.execute(f"GRANT SELECT ON {t} TO svc_api")
    for seq in ("memory_findings_id_seq", "memory_finding_sightings_id_seq",
                "memory_refinements_id_seq",
                "memory_reviewer_verdicts_id_seq"):
        op.execute(f"GRANT USAGE ON SEQUENCE {seq} TO svc_mcp")
    for v in ("memory_finding_state", "memory_refinement_outcome"):
        op.execute(f"GRANT SELECT ON {v} TO svc_mcp, svc_api")

    conn = op.get_bind()
    present = conn.exec_driver_sql(
        """SELECT tablename FROM pg_tables
            WHERE schemaname = 'public' AND tablename LIKE 'memory\\_%'
            ORDER BY 1""").fetchall()
    print(f"VERIFY 0034 memory tables={[r[0] for r in present]}", flush=True)
    idx = conn.exec_driver_sql(
        """SELECT indexname FROM pg_indexes
            WHERE schemaname = 'public' AND tablename LIKE 'memory\\_%'
            ORDER BY 1""").fetchall()
    print(f"VERIFY 0034 memory indexes={len(idx)} {[r[0] for r in idx]}",
          flush=True)
    views = conn.exec_driver_sql(
        """SELECT viewname FROM pg_views
            WHERE schemaname = 'public' AND viewname LIKE 'memory\\_%'
            ORDER BY 1""").fetchall()
    print(f"VERIFY 0034 memory views={[r[0] for r in views]}", flush=True)


def downgrade() -> None:
    for v in ("memory_refinement_outcome", "memory_finding_state"):
        op.execute(f"DROP VIEW IF EXISTS {v}")
    for t in ("memory_reviewer_verdicts", "memory_refinement_findings",
              "memory_finding_sightings", "memory_findings",
              "memory_refinements", "memory_defect_classes"):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
