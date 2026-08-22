"""0026 — the answer index: what this run can answer, and the passages behind it.

An AE opens the intelligence panel, types a question, and nothing happens.
The panel's `ask()` returns immediately in LIVE because the serving path runs
no model (invariant 1) and the prototype's streaming reply is another
institution's fixture prose. So the question box has been accepting input and
discarding it.

The invariant's PURPOSE is that no prose is ever invented while a client is
looking at the page. Retrieval invents nothing: ranking and selecting text a
producer already wrote, already cited and already promoted is a read. These
two tables are how that read becomes cheap enough to feel instant.

## serving_answers — the questions the producer answered in advance

The set of questions an AE asks on each surface is knowable before anyone
asks: the panel enumerates them per surface. So the producer answers them
during synthesis, when a model IS allowed to run, and the answer promotes as
prose with its citations. At request time the panel does a lookup, not an
inference.

Two constraints carry the honesty rules that make this safe to ship:

  · `serving_answers_grounded` — a row states an answer or states why the run
    has none. A row that is blank in both columns is a question the reader
    was invited to ask and then met with a shrug; it cannot be stored.
  · `serving_answers_cited` — an answer with no evidence ids cannot be
    stored. Uncited prose under a client's name is the failure mode this
    whole application is built to prevent, and an answer is the surface most
    likely to be pasted into an email without its page around it.

An honest absence is therefore a first-class row: `answer_md` NULL,
`absence_reason` in the producer's own words, no citations required.

## serving_passages — every promoted passage, verbatim, once

The unanticipated question is answered by returning what the run already
states, ranked, verbatim, cited — never by writing a sentence. That needs the
prose in one place with one row per passage, which is what this table is: the
same text as the six pages, decomposed to the paragraph, with the citations of
the row it came from and the JSON path it lives at (so a reader can be shown
exactly where the answer is on the page).

Three retrieval paths share the one corpus, in order of how much they can be
trusted to be deterministic:

  1. `embedding` + HNSW — semantic nearest neighbour. Written by the connector
     at PROMOTE time with the same bundled 384-dim model V4 grounding already
     uses (L2-normalised, `vector_cosine_ops`, m=16 / ef_construction=64,
     created once, here). An index scan is not a model call, so this serves
     under invariant 1 — but only for a query vector that ALREADY EXISTS,
     which is why `serving_answers.question_embedding` is stored beside the
     question rather than computed when someone clicks it.
  2. `search_tsv` + `ts_rank_cd` — lexical, core Postgres, deterministic, and
     the one path that can serve a question nobody anticipated without a model
     touching the request. `to_tsvector` with a constant regconfig is
     immutable, so the column is GENERATED and cannot drift from its text.
  3. `text gin_trgm_ops` — trigram similarity, for the query that shares no
     lexeme with the corpus (a typo, an abbreviation). pg_trgm is already an
     installed extension (0001).

`embedding_model` is pinned per row and required whenever a vector is present:
a mixed-model index returns plausible nonsense, which is worse than returning
nothing. Rows with no vector simply do not participate in path 1; the lexical
paths still answer, so an un-embedded run degrades to slower ranking rather
than to silence.

## Neither table is a promoted SECTION

Both are run-scoped grain reads, the same shape as `serving_subcaps` and the
evidence store: written by the connector inside the promote transaction,
read by a dedicated endpoint, absent from the 34-writer registry. That
matters — the writer registry's order is load-bearing (invariant 11) and its
length is asserted in two services. An index derived from the six pages is
not a 35th page section, and making it one would put a derived artefact in
the same list as the surfaces it derives from.

Expand-only: two new tables, no column moves, no backfill. A run promoted
before this lands simply has no rows, and the serving path answers from the
promoted sections directly.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-08
"""
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE serving_answers (
          id                 BIGSERIAL PRIMARY KEY,
          run_id             UUID NOT NULL REFERENCES runs(id),
          entity_id          UUID REFERENCES entities(id),
          -- The panel surface the question belongs to, in the panel's own
          -- vocabulary: entity · why_now · subcap_narrative · platform_story
          -- · focus_area. Free text rather than an enum because the surface
          -- list is a front-end concern that moves faster than a type does,
          -- and an unknown surface should serve nothing rather than refuse a
          -- promote.
          surface            TEXT NOT NULL,
          -- The cell, focus area or platform area the question is about.
          -- NULL means the question is about the whole entity.
          scope_id           TEXT,
          -- Stable across runs, so re-promoting one page replaces an answer
          -- instead of duplicating it (invariant 3 keeps staging rows).
          q_id               TEXT NOT NULL,
          question           TEXT NOT NULL,
          -- The lookup key. Generated, so the normalisation cannot drift
          -- between the writer and the reader; lower(btrim()) is immutable.
          question_norm      TEXT GENERATED ALWAYS AS (lower(btrim(question))) STORED,
          rank               SMALLINT,
          -- PROMOTED PROSE. NULL only where the run cannot ground an answer.
          answer_md          TEXT,
          absence_reason     TEXT,
          -- Where on the six pages the answer is also visible, so the panel
          -- can send the reader to the surface rather than end the trail.
          source_page        TEXT,
          source_section     TEXT,
          source_path        TEXT,
          e_ids              TEXT[],
          internal_only      BOOLEAN NOT NULL DEFAULT false,
          question_embedding vector(384),
          promoted_at        TIMESTAMPTZ NOT NULL,
          producer_version   TEXT NOT NULL,
          provenance         provenance_t,
          CONSTRAINT serving_answers_grounded
            CHECK (answer_md IS NOT NULL OR absence_reason IS NOT NULL),
          CONSTRAINT serving_answers_cited
            CHECK (answer_md IS NULL
                   OR (e_ids IS NOT NULL AND cardinality(e_ids) > 0)),
          CONSTRAINT serving_answers_dim
            CHECK (question_embedding IS NULL
                   OR vector_dims(question_embedding) = 384)
        )
        """
    )
    # One answer per question per scope per run. COALESCE rather than a
    # nullable column in the key: NULL scope_id means "the whole entity",
    # which is one scope, not an unknown one — and NULLs do not collide in a
    # unique index, so two entity-wide answers to the same question would
    # both have been accepted.
    op.execute(
        """
        CREATE UNIQUE INDEX serving_answers_uq
          ON serving_answers (run_id, surface, COALESCE(scope_id, ''), q_id)
        """
    )
    op.execute(
        "CREATE INDEX serving_answers_lookup "
        "ON serving_answers (run_id, surface, question_norm)")
    op.execute(
        """
        CREATE INDEX serving_answers_q_hnsw ON serving_answers
          USING hnsw (question_embedding vector_cosine_ops)
          WITH (m = 16, ef_construction = 64)
        """
    )

    op.execute(
        """
        CREATE TABLE serving_passages (
          id               BIGSERIAL PRIMARY KEY,
          run_id           UUID NOT NULL REFERENCES runs(id),
          entity_id        UUID REFERENCES entities(id),
          page             TEXT NOT NULL,
          section          TEXT NOT NULL,
          -- Exactly where this text sits in the promoted payload, e.g.
          -- `cells[12].synthesis`. It is the passage's identity within the
          -- run and the only way to send a reader to the field it came from.
          json_path        TEXT NOT NULL,
          -- What the passage is ABOUT, when the payload says so: a cell, a
          -- card, a recommendation, a focus area, an evidence item. Lets the
          -- panel open the same drilldown the page would.
          anchor_kind      TEXT,
          anchor_id        TEXT,
          -- VERBATIM. This column is never rewritten, never summarised and
          -- never joined to another passage: the whole point of retrieval is
          -- that the reader sees the producer's sentence, not a new one.
          text             TEXT NOT NULL,
          e_ids            TEXT[],
          internal_only    BOOLEAN NOT NULL DEFAULT false,
          embedding        vector(384),
          embedding_model  TEXT,
          promoted_at      TIMESTAMPTZ NOT NULL,
          producer_version TEXT NOT NULL,
          -- Quoted: `text` is also a type name, and an unquoted reference to
          -- it inside an expression is a parse ambiguity waiting for a
          -- Postgres release to resolve differently.
          search_tsv       tsvector GENERATED ALWAYS AS
                             (to_tsvector('english', "text")) STORED,
          CONSTRAINT serving_passages_dim
            CHECK (embedding IS NULL OR vector_dims(embedding) = 384),
          -- A vector with no model name cannot be trusted against the index
          -- it shares with vectors from another model.
          CONSTRAINT serving_passages_model
            CHECK (embedding IS NULL OR embedding_model IS NOT NULL)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX serving_passages_uq "
        "ON serving_passages (run_id, json_path)")
    op.execute("CREATE INDEX serving_passages_run ON serving_passages (run_id)")
    # Created ONCE, at migration, per the charter — not on first write.
    op.execute(
        """
        CREATE INDEX serving_passages_hnsw ON serving_passages
          USING hnsw (embedding vector_cosine_ops)
          WITH (m = 16, ef_construction = 64)
        """
    )
    op.execute(
        "CREATE INDEX serving_passages_tsv ON serving_passages "
        "USING gin (search_tsv)")
    op.execute(
        'CREATE INDEX serving_passages_trgm ON serving_passages '
        'USING gin ("text" gin_trgm_ops)')

    # Grants in the same revision as the table. The API reads; the connector
    # is the only writer (invariant 2).
    for name in ("serving_answers", "serving_passages"):
        op.execute(f"GRANT SELECT ON {name} TO svc_api")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {name} TO svc_mcp")
        op.execute(f"GRANT USAGE ON SEQUENCE {name}_id_seq TO svc_mcp")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS serving_passages")
    op.execute("DROP TABLE IF EXISTS serving_answers")
