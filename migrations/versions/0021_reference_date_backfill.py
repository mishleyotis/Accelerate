"""0021 — backfill the date the whole recency ladder hangs from.

`evidence_index.reference_date` is set by `register_evidence` from the run's
`runs.completed_at`, and `age_months` is GENERATED from the two:

    age_months = (reference_date - published_date) in months, or NULL

So a run with no `completed_at` gives every one of its evidence rows a NULL
`reference_date`, a NULL `age_months`, and therefore `recency_band =
UNVERIFIED` — regardless of how many of those rows carry a real publication
date.

## What this was measured on

Baxter Credit Union, run `DMA-ASM-BCU-20260330-0001`, served through the API:

    evidence rows                126
      carrying published_date     51
      banded UNVERIFIED          126      <- every single one
      reference_date set           0

A `FACT` chip then rendered beside an "unverified" recency label on the same
row, which a reader correctly reads as a contradiction — and it was the defect
reported from the client-facing pages ("why is something tagged fact then have
an unverified tag?").

## Why a migration rather than a re-scan

The worker now resolves the date at scan time, including from the run's own
request id (`_stated_completed_at` → `_request_id_date`): the corpus names every
run `DMA-ASM-<ENTITY>-<YYYYMMDD>-<seq>`, so the id states the date as plainly as
a manifest field. That fix only helps runs scanned AFTER it landed. Runs already
ingested keep their NULL, and a re-scan is idempotent by design — an unchanged
tree creates nothing — so it will not revisit them.

This is therefore a one-time data repair over the ingested tier, and it is
deliberately narrow:

  · `runs.completed_at` is set ONLY where it is NULL and ONLY from the run's own
    `request_id`, by the same `-YYYYMMDD-` pattern the worker uses. No inference,
    no "today", no borrowing another run's date.
  · `evidence_index` is ENTITY-grained — dedup is on (entity_id, content_hash)
    and there is no run_id on the row — so the run is resolved in two rungs:
    the run that CITES the row (`evidence_subcap_links.run_id`, earliest where
    several do), else the entity's sole dated run. An entity with two dated runs
    is left NULL rather than aged against an assessment that never saw the row.
    A row that already carries a reference_date is left exactly as it is.
  · `age_months` and `recency_band` need no action: `age_months` is GENERATED and
    recomputes itself, and the band follows the age.

Nothing is overwritten, so re-running is a no-op. The VERIFY lines are the
production proof.
"""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None

# The worker's own pattern (apps/worker/dma_worker/persist.py::_REQ_ID_DATE),
# as a POSIX regex: the YYYYMMDD token in DMA-ASM-<ENTITY>-YYYYMMDD-<seq>.
_REQ_ID_DATE = r'-(\d{8})-\d+$'


def upgrade() -> None:
    conn = op.get_bind()

    before = conn.exec_driver_sql("""
        SELECT count(*) FILTER (WHERE reference_date IS NULL),
               count(*) FILTER (WHERE recency_band = 'UNVERIFIED'),
               count(*) FILTER (WHERE published_date IS NOT NULL),
               count(*)
          FROM evidence_index
    """).fetchone()
    print(f"VERIFY 0021 before: reference_date NULL={before[0]} "
          f"UNVERIFIED={before[1]} dated={before[2]} rows={before[3]}")

    # 1 · the run's own request id, and nothing else
    runs = conn.exec_driver_sql(f"""
        UPDATE runs
           SET completed_at = to_date(substring(request_id FROM '{_REQ_ID_DATE}'),
                                      'YYYYMMDD')
         WHERE completed_at IS NULL
           AND request_id ~ '{_REQ_ID_DATE}'
        RETURNING id, request_id, completed_at
    """).fetchall()
    for r in runs:
        print(f"VERIFY 0021 run: {r[1]} -> completed_at={r[2]}")
    print(f"VERIFY 0021 runs dated from request_id: {len(runs)}")

    # 2 · that date onto the evidence rows, where none is set.
    #
    # `evidence_index` is ENTITY-grained — dedup is on (entity_id, content_hash),
    # so one annual report cited by two runs is one row and there is no run_id to
    # read. `register_evidence` sets reference_date from the run it was called
    # with; that run is not recorded on the row. So it is resolved here, in two
    # rungs, and only where the answer is unambiguous:
    #
    #   a  the run that LINKS the row (`evidence_subcap_links.run_id` is
    #      run-scoped). Where several runs link it, the EARLIEST — a row cannot
    #      have been registered later than the first run that cited it.
    #   b  failing that, the entity's own run, but ONLY where the entity has
    #      exactly ONE dated run. With two, the row could belong to either and
    #      picking one would age it against an assessment that never saw it.
    #
    # Anything still unresolved stays NULL and is counted. A NULL here bands
    # UNVERIFIED, which is wrong but visible; a guessed date reads as measured.
    by_link = conn.exec_driver_sql("""
        UPDATE evidence_index e
           SET reference_date = src.dated
          FROM (SELECT k.e_id, min(r.completed_at) AS dated
                  FROM evidence_subcap_links k
                  JOIN runs r ON r.id = k.run_id
                 WHERE r.completed_at IS NOT NULL
                 GROUP BY k.e_id) src
         WHERE e.e_id = src.e_id
           AND e.reference_date IS NULL
        RETURNING e.e_id
    """).fetchall()
    print(f"VERIFY 0021 dated from the run that cites them: {len(by_link)}")

    by_entity = conn.exec_driver_sql("""
        UPDATE evidence_index e
           SET reference_date = one.dated
          FROM (SELECT entity_id, min(completed_at) AS dated
                  FROM runs
                 WHERE completed_at IS NOT NULL
                 GROUP BY entity_id
                HAVING count(*) FILTER (WHERE completed_at IS NOT NULL) = 1) one
         WHERE e.entity_id = one.entity_id
           AND e.reference_date IS NULL
        RETURNING e.e_id
    """).fetchall()
    print(f"VERIFY 0021 dated from a sole run on the entity: {len(by_entity)}")

    left = conn.exec_driver_sql("""
        SELECT count(*) FROM evidence_index WHERE reference_date IS NULL
    """).fetchone()[0]
    print(f"VERIFY 0021 still undated (entity has several runs, or none "
          f"dated): {left}")

    after = conn.exec_driver_sql("""
        SELECT count(*) FILTER (WHERE reference_date IS NULL),
               count(*) FILTER (WHERE recency_band = 'UNVERIFIED'),
               count(*) FILTER (WHERE age_months IS NOT NULL),
               count(*)
          FROM evidence_index
    """).fetchone()
    print(f"VERIFY 0021 after: reference_date NULL={after[0]} "
          f"UNVERIFIED={after[1]} age_months set={after[2]} rows={after[3]}")

    bands = conn.exec_driver_sql("""
        SELECT recency_band::text, count(*) FROM evidence_index
         GROUP BY 1 ORDER BY 2 DESC
    """).fetchall()
    print("VERIFY 0021 bands: " + ", ".join(f"{b}={n}" for b, n in bands))


def downgrade() -> None:
    """Not reversible in a way that means anything.

    Clearing every reference_date would also clear the ones registration set
    correctly, and there is no record of which rows this migration touched. The
    forward direction only ever fills a NULL from the run's own request id, so
    re-running is a no-op and there is nothing to undo.
    """
    pass
