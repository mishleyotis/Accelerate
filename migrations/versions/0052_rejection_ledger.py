"""0052 — a refused payload gets a name, a queue and a way back.

THE HOLE THIS CLOSES. A submission that fails validation is stored with
status FAIL and SUPERSEDES the passing row for that page. After that:

  * `get_run_progress` shows it, but only for the LIVE row of ONE run, and
    only if somebody asks about that run;
  * nothing lists it across the corpus, so a producer session that ended
    leaves no trace anything is outstanding;
  * the next session has no way to know a page was refused, which gate
    refused it, or whether the repair it is about to attempt is the fourth
    attempt at the same reason.

Measured on this build: a heatmap resubmit dropped `cell_evidence`, failed
CG-01, superseded a PASS, and sat refused for a day with nothing anywhere
saying so. Two more pages refused on ET-07 and ET-09 the same way. Every one
was found by a human reading a verdict, and each would have stayed refused
indefinitely if nobody had.

WHAT THIS ADDS. One row per (run, page, gate_id, path) the moment a
submission is refused, carrying a STABLE `rejection_id` that survives every
resubmission of that page. The id is the thing the brief asks for: a refined
copy is submitted against the same page, and the row it clears is the row it
was opened against, so "did the repair land" is answerable without comparing
payloads.

Rows CLOSE by evidence, never by assertion: when a later submission for the
same page passes, every open rejection on that page whose gate no longer
fires is closed with the submission that closed it. A gate that still fires
stays open with its attempt count incremented, which is how "this is the
fourth attempt at the same reason" becomes visible instead of being
rediscovered.

Retained, never deleted. A refusal is evidence about a run.
"""
from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS rejection_ledger (
          rejection_id     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          run_id           uuid NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
          page             page_t NOT NULL,
          section          text,
          gate_id          text NOT NULL,
          path             text NOT NULL DEFAULT '',
          severity         text NOT NULL DEFAULT 'block',
          message          text NOT NULL,
          -- The submission that OPENED it and the one that CLOSED it. Both
          -- are kept: "which payload was refused" and "which payload fixed
          -- it" are different questions and a producer asks both.
          -- ON DELETE SET NULL on both, and it matters: a rejection is
          -- evidence about a RUN, and a foreign key onto `submissions` with
          -- no action makes this table a VETO on deleting a submission. The
          -- same shape bit `facet_promotion_state` a migration earlier, where
          -- the ledger silently made a run undeletable. The ticket outlives
          -- the payload that opened it; the pointer is provenance and is
          -- allowed to go null.
          opened_by        uuid REFERENCES submissions(id) ON DELETE SET NULL,
          opened_at        timestamptz NOT NULL DEFAULT now(),
          closed_by        uuid REFERENCES submissions(id) ON DELETE SET NULL,
          closed_at        timestamptz,
          -- Every time the same gate refuses the same path again. A count
          -- climbing past two is the signal that the repair is not landing
          -- and the producer is looping.
          attempts         integer NOT NULL DEFAULT 1,
          last_seen_at     timestamptz NOT NULL DEFAULT now(),
          producer_version text,
          -- CLOSED is `closed_at`, and only that. `closed_by` is provenance:
          -- which submission cleared it, which is almost always known and is
          -- not what makes the row closed. Tying the two together made a
          -- close with no submission behind it — an operator clearing a
          -- ticket, a repair that arrived by another route — impossible to
          -- record at all, which would push it outside the ledger and back
          -- into the dark this table exists to end.
          CONSTRAINT rejection_closer_has_a_time
            CHECK (closed_by IS NULL OR closed_at IS NOT NULL)
        )""")
    # One OPEN row per (run, page, gate, path). A second refusal on the same
    # reason increments `attempts` rather than opening a second ticket, so the
    # queue length means "distinct things wrong" and not "times we tried".
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS rejection_open_uq
          ON rejection_ledger (run_id, page, gate_id, path)
       WHERE closed_at IS NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS rejection_open_idx
                    ON rejection_ledger (opened_at DESC) WHERE closed_at IS NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS rejection_run_idx
                    ON rejection_ledger (run_id, page)""")

    # The queue a scheduled producer session reads to know what is
    # outstanding, across every run, without asking about any run in
    # particular — the read that did not exist.
    op.execute("""
        CREATE OR REPLACE VIEW open_rejections AS
        SELECT r.rejection_id, r.run_id, e.display_id, e.legal_name,
               r.page, r.section, r.gate_id, r.path, r.severity, r.message,
               r.attempts, r.opened_at, r.last_seen_at, r.producer_version,
               (now() - r.opened_at) AS open_for
          FROM rejection_ledger r
          JOIN runs ru ON ru.id = r.run_id
          JOIN entities e ON e.id = ru.entity_id
         WHERE r.closed_at IS NULL
         ORDER BY r.attempts DESC, r.opened_at""")

    op.execute("GRANT SELECT, INSERT, UPDATE ON rejection_ledger TO svc_mcp")
    op.execute("GRANT SELECT ON rejection_ledger, open_rejections TO svc_api")
    op.execute("GRANT SELECT ON open_rejections TO svc_mcp")

    for sql, label in (
        ("SELECT count(*) FROM rejection_ledger", "rejection_ledger rows"),
        ("SELECT count(*) FROM open_rejections", "open_rejections rows"),
    ):
        rows = op.get_bind().execute(__import__("sqlalchemy").text(sql)).scalar()
        print(f"VERIFY 0052 {label}: {rows}")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS open_rejections")
    op.execute("DROP TABLE IF EXISTS rejection_ledger")
