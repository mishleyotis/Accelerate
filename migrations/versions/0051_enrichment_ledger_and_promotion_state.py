"""Enrichment ran, promotion did not, and nothing in the system could tell.

THE PATTERN THIS CLOSES, reported by the owner on 2026-08-19 after a third
round of the same defects: "the work was done but it is not showing".

Measured across three rounds on one client. The leadership panel named three
executives with "Email · LinkedIn hidden until enriched" under each. The
technology register served 13 rows while a machine scan had returned 60. The
why-now card carried two triggers. Sentiment carried one bar. In each case
some enrichment had run — in a session, in a different account, in a routine —
and the surface a reader opens did not have it.

    THE WORK AND THE SURFACE HAVE NO SHARED CLOCK.

`enrichment_attempts` (0047) already records the ROUTINE's field-filling loop,
per run and per field. It cannot answer this question, and that is not a
defect in it: it records attempts against fields, and the thing that goes stale
is a FACET of an entity — its leadership, its tech stack — enriched by whatever
route, then promoted or not. An entity-grain scan is not run-bound at all.

So two tables and a view:

  enrichment_ledger        one row per enrichment of one facet, carrying the
                           version, when, by what source, under which account.
  facet_promotion_state    one row per (entity, facet): the version that
                           actually reached the serving tier, and when.
  enrichment_drift         the join, classifying every facet as `current`,
                           `enriched_not_promoted` or `never_enriched`.

The version is a monotone integer per (entity, facet) rather than a timestamp,
because two enrichments in the same second are ordinary and a clock is not an
ordering. It is allocated by the ledger itself (`next_enrichment_version`), so
a caller cannot mint one that collides or one that goes backwards.

WHAT THIS DELIBERATELY DOES NOT DO. It does not block `promote_run`. A promote
that carries five of seven facets forward is better than no promote, and
refusing it would strand the five. The drift is DISCLOSED at promote and
BLOCKS COMPLETION — a client is not "done" while a facet is enriched and
unpromoted, which is the owner's stated rule and the correct place for a
refusal, because "done" is a claim about the whole client and promote is a
claim about one transaction.
"""
from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


#: The facets a client is "done" on. Deliberately a CHECK constraint rather
#: than a lookup table: the set is small, closed, and named in the owner's
#: brief, and a typo'd facet silently creating an eighth one is exactly the
#: drift this table exists to make impossible.
FACETS = ("leadership", "firmographics", "techstack", "sentiment",
          "why_now", "platform_readiness", "peer_scores")


def upgrade() -> None:
    facets = ", ".join(f"'{f}'" for f in FACETS)
    op.execute(f"""
        CREATE TABLE enrichment_ledger (
          id                 BIGSERIAL PRIMARY KEY,
          -- CASCADE: a ledger row is a fact ABOUT this entity and means
          -- nothing without it. A plain reference made these tables a veto
          -- on deleting an entity, which is a safeguard refusing an
          -- operation it has no opinion about.
          entity_id          UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
          -- NULLABLE, and that is the point: a technographic scan of a domain
          -- is a fact about the ENTITY and outlives any one run. A facet
          -- enriched inside a producer session for a specific run names it.
          --
          -- ON DELETE SET NULL, not the default. `run_id` here is PROVENANCE
          -- — which run carried the work — and the fact being recorded is
          -- about the entity's facet. A plain reference made the ledger a
          -- veto on deleting a run: the first suite to exercise both found
          -- `update or delete on table "runs" violates foreign key
          -- constraint`, which is a safeguard refusing an operation it has
          -- no opinion about. Losing the run loses the provenance, which is
          -- honest, and keeps the fact, which is the point.
          run_id             UUID REFERENCES runs(id) ON DELETE SET NULL,
          facet              TEXT NOT NULL,
          enrichment_version BIGINT NOT NULL,
          enriched_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
          -- WHICH TOOL, and WHICH ACCOUNT ran it. The account is in the
          -- owner's brief for a reason: the same scan returned empty twice
          -- under one account and sixty technologies under another, and with
          -- no record of which, the two runs were indistinguishable.
          source             TEXT NOT NULL,
          account            TEXT,
          rows_written       INTEGER,
          note               TEXT,
          CONSTRAINT enrichment_ledger_facet_known CHECK (facet IN ({facets})),
          CONSTRAINT enrichment_ledger_source_stated
            CHECK (source IS NOT NULL AND source <> ''),
          CONSTRAINT enrichment_ledger_version_positive
            CHECK (enrichment_version > 0),
          CONSTRAINT enrichment_ledger_version_unique
            UNIQUE (entity_id, facet, enrichment_version)
        );
        CREATE INDEX enrichment_ledger_facet
          ON enrichment_ledger (entity_id, facet, enrichment_version DESC);

        CREATE TABLE facet_promotion_state (
          -- CASCADE, for the same reason as the ledger above.
          entity_id          UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
          facet              TEXT NOT NULL,
          promoted_version   BIGINT NOT NULL,
          promoted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
          -- Provenance, and deletable. See enrichment_ledger.run_id above.
          run_id             UUID REFERENCES runs(id) ON DELETE SET NULL,
          PRIMARY KEY (entity_id, facet),
          CONSTRAINT facet_promotion_facet_known CHECK (facet IN ({facets}))
        );
    """)

    # The drift classification, computed and never stored — invariant 8. Three
    # states, and each names a DIFFERENT next move, which is the whole reason
    # they are not collapsed into one boolean:
    #
    #   never_enriched         nobody has run this facet. Run it.
    #   enriched_not_promoted  the work exists and the reader cannot see it.
    #                          Promote it. This is the state that produced
    #                          three rounds of "it was done but it is not
    #                          showing".
    #   current                the promoted version is the newest enrichment.
    op.execute(f"""
        CREATE VIEW enrichment_drift AS
        WITH facets AS (SELECT unnest(ARRAY[{facets}]) AS facet),
        latest AS (
          SELECT entity_id, facet,
                 max(enrichment_version) AS enrichment_version,
                 max(enriched_at)        AS enriched_at
            FROM enrichment_ledger
           GROUP BY entity_id, facet
        )
        SELECT e.id                       AS entity_id,
               e.display_id,
               f.facet,
               l.enrichment_version,
               l.enriched_at,
               p.promoted_version,
               p.promoted_at,
               CASE
                 WHEN l.enrichment_version IS NULL THEN 'never_enriched'
                 WHEN p.promoted_version IS NULL
                   OR p.promoted_version < l.enrichment_version
                      THEN 'enriched_not_promoted'
                 ELSE 'current'
               END AS state
          FROM entities e
         CROSS JOIN facets f
          LEFT JOIN latest l
                 ON l.entity_id = e.id AND l.facet = f.facet
          LEFT JOIN facet_promotion_state p
                 ON p.entity_id = e.id AND p.facet = f.facet;
    """)

    # Allocate the next version for a facet, inside the caller's transaction.
    # A function rather than a client-side max(), because two producers
    # enriching the same facet concurrently would both read the same max and
    # both write it, and the unique constraint would then fail the second —
    # correct, but as a driver error rather than an ordering.
    op.execute("""
        CREATE FUNCTION next_enrichment_version(p_entity UUID, p_facet TEXT)
        RETURNS BIGINT LANGUAGE sql AS $$
          SELECT COALESCE(max(enrichment_version), 0) + 1
            FROM enrichment_ledger
           WHERE entity_id = p_entity AND facet = p_facet
        $$;
    """)

    # Grants in the same revision as the table (charter: working discipline).
    #
    #   svc_mcp    writes the ledger on every enrichment and the promotion
    #              state on every promote — it is the only writer of both.
    #   svc_worker writes the ledger too: the scheduled scan enriches without
    #              a connector session.
    #   svc_api    reads only. The drift flag renders in the app; the app
    #              never decides it.
    for role, grant in (("svc_mcp", "SELECT, INSERT, UPDATE"),
                        ("svc_worker", "SELECT, INSERT"),
                        ("svc_api", "SELECT")):
        op.execute(f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                EXECUTE 'GRANT {grant} ON enrichment_ledger TO {role}';
                EXECUTE 'GRANT {grant} ON facet_promotion_state TO {role}';
                EXECUTE 'GRANT SELECT ON enrichment_drift TO {role}';
                EXECUTE 'GRANT EXECUTE ON FUNCTION next_enrichment_version(UUID, TEXT) TO {role}';
              END IF;
            END $$;
        """)
    for role in ("svc_mcp", "svc_worker"):
        op.execute(f"""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                EXECUTE 'GRANT USAGE, SELECT ON SEQUENCE enrichment_ledger_id_seq TO {role}';
              END IF;
            END $$;
        """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS next_enrichment_version(UUID, TEXT)")
    op.execute("DROP VIEW IF EXISTS enrichment_drift")
    op.execute("DROP TABLE IF EXISTS facet_promotion_state")
    op.execute("DROP TABLE IF EXISTS enrichment_ledger")
