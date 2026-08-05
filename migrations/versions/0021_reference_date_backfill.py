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
  · `evidence_index.reference_date` is then backfilled ONLY where NULL, ONLY for
    those runs, and ONLY from that run's `completed_at`. A row that already
    carries a reference_date is left exactly as it is.
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

    # 2 · that date onto the run's own evidence rows, where none is set
    filled = conn.exec_driver_sql("""
        UPDATE evidence_index e
           SET reference_date = r.completed_at
          FROM runs r
         WHERE e.run_id = r.id
           AND e.reference_date IS NULL
           AND r.completed_at IS NOT NULL
        RETURNING e.e_id
    """).fetchall()
    print(f"VERIFY 0021 evidence rows given a reference_date: {len(filled)}")

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
