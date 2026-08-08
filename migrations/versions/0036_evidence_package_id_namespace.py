"""0036 — a package-local evidence id is a label scoped to one client, and
this is where it finally says so.

## The defect, measured in production on 2026-08-08

Two clients could not be produced at all. Northern Trust's run cites
E-007/009/011/017/018/019/020/021/028/030/031/032 from its own
recommendations; `get_evidence` returned **12 of 12 as `foreign`**, all
belonging to entity 6fd2defa-…. Kitsap Credit Union's 62 research-ledger ids
returned `foreign` too, and — the detail that names the mechanism — not to
ONE other institution but to several: E-016/E-020 to ca5a452d-…, E-055/E-078
/E-084 to f2147ab6-…. Invariant 4 makes `foreign` a halt, so both producers
stopped, correctly.

`evidence_index.e_id` is a global primary key, but package Evidence_Master
ids are workbook-LOCAL: every General-DMA template starts at E-001. The
ingest qualified them with a token folded out of the institution's NAME —
`E-047` stored as `E-{ENT}-047`. A name is not an identity:

    281 ingested runs · 166 entities · 113 distinct tokens
    13 tokens owned by more than one entity, of which:
        UNK       14 entities, 1053 rows      <- no manifest, so no name
        FIRSTNAT   3 entities,  221 rows
        FPCU/HAPO/HVCU/PATELCO/SLG/TCB   2 entities each

`UNK` is the fallback the ingest uses when a package ships no manifest at
all (68 runs). Fourteen institutions ended up writing into one `E-UNK-nnn`
namespace, and 50 entities in the pending set share it by name.

The landing code was not the weak point — it refused to alias across
entities every single time. It had only one escape (`-R{run_seq}`), which
the next manifest-less package with the same run_seq had also taken, so it
ran out and recorded the item as unpersistable:

    evidence_id_collision       12,717 observations across 94 runs
    evidence_unpersistable       5,019 observations across 61 runs
    runs whose entity holds no package evidence at all          50
    entities holding no package evidence at all                 36

Northern Trust: 33 unpersistable, 66 collisions, 0 evidence rows. Kitsap:
69 unpersistable, 138 collisions, 0 evidence rows. So the evidence never
landed for those clients, and the id a citation resolved to was whichever
institution had ingested first. A citation that silently resolved to the
wrong institution would have been far worse than one that halts; the halt
was the system working. What was broken is that the id space was never
namespaced per entity in the first place.

## What this revision adds

`evidence_package_ids` — the mapping from (entity, package-local id) to the
stored row. The entity is IN the primary key, so a lookup is entity-scoped
by construction: there is no query shape over this table that can return
another institution's row. That is the property the token was standing in
for and could not provide.

A separate table rather than a column on `evidence_index` because the
relation is genuinely many-to-one: when two Evidence_Master rows carry the
same content under different local numbers, the dedup keeps one row and both
local ids must still resolve to it (297 such dedups across 14 runs today —
every one of them a citation that resolves to nothing without this table).

The backfill reads the mapping back out of the ids already stored. Where an
entity holds both `E-BCU-006` and its re-mint `E-BCU-006-R2`, the re-mint
wins: it is the same source read again with fuller content, and 0028 already
carries the earlier row's links onto it. Rows the ingest never created
cannot be recovered here — they are re-landed from the source workbooks by
the worker's `EVIDENCE_NAMESPACE=repair` pass, which writes through this
same table.

The index is the table's own primary key, created with it on an empty
relation, so there is nothing for a CONCURRENTLY build to protect.
"""
from alembic import op

revision = "0036"
down_revision = "0032"
branch_labels = None
depends_on = None


# The stored shapes a package id has ever had:
#   E-{TOKEN}-{nnn}                the original qualification
#   E-{TOKEN}-{nnn}-R{run_seq}     a re-mint after a content change (0028)
# The server's own mints (E-CC-nnn) are NOT workbook-local and must never
# acquire a mapping — a bare `E-104` must not resolve onto `E-CC-104`.
_LOCAL_FROM_STORED = r"substring(e_id from '^E-[A-Za-z0-9]+-(\d+)(?:-R\d+)?$')"
_REMINT_RANK = r"COALESCE((substring(e_id from '-R(\d+)$'))::int, 0)"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE evidence_package_ids (
          -- The mapping is subordinate to the row it points at and to the
          -- client that shipped the number, so it goes when either goes: a
          -- local id pointing at an evidence row that no longer exists is a
          -- citation that resolves to nothing while looking like it resolves.
          entity_id        UUID NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
          package_local_id TEXT NOT NULL,   -- verbatim from the workbook: 'E-047'
          e_id             TEXT NOT NULL REFERENCES evidence_index(e_id) ON DELETE CASCADE,
          -- Provenance only: which run first saw this number. The mapping is
          -- ENTITY-grained and outlives any one run, so a deleted run leaves
          -- the mapping standing with its origin unknown rather than removing
          -- a client's ability to cite.
          run_id           UUID REFERENCES runs(id) ON DELETE SET NULL,
          created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (entity_id, package_local_id)
        )
        """
    )
    op.execute(
        "COMMENT ON TABLE evidence_package_ids IS "
        "'Workbook-local evidence ids, scoped to the entity that shipped them. "
        "The entity is in the primary key: a bare E-0NN can resolve to this "
        "client''s row or to nothing, never to another institution''s.'"
    )
    op.execute("CREATE INDEX evidence_package_ids_e_id ON evidence_package_ids (e_id)")

    # Backfill from the ids already stored. One winner per (entity, local):
    # the highest re-mint rank, ties broken by the id itself so the pass is
    # deterministic and re-runnable.
    op.execute(
        f"""
        INSERT INTO evidence_package_ids (entity_id, package_local_id, e_id)
        SELECT entity_id, package_local_id, e_id FROM (
            SELECT entity_id,
                   'E-' || {_LOCAL_FROM_STORED} AS package_local_id,
                   e_id,
                   row_number() OVER (
                     PARTITION BY entity_id, {_LOCAL_FROM_STORED}
                     ORDER BY {_REMINT_RANK} DESC, e_id DESC) AS rank
              FROM evidence_index
             WHERE origin = 'package'
               AND entity_id IS NOT NULL
               AND e_id NOT LIKE 'E-CC-%%'
               AND {_LOCAL_FROM_STORED} IS NOT NULL
        ) ranked
        WHERE rank = 1
        ON CONFLICT DO NOTHING
        """
    )

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON evidence_package_ids TO svc_worker")
    # The connector resolves every citation through it (get_evidence, and the
    # validator that uses the same function); it never mints package ids.
    op.execute("GRANT SELECT ON evidence_package_ids TO svc_mcp")
    # The cell-evidence drawer resolves the same ids on the serving path.
    op.execute("GRANT SELECT ON evidence_package_ids TO svc_api")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS evidence_package_ids")
