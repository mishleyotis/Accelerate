"""A promoted run can be taken off the client surface without being deleted

## Why this exists

A run was promoted whose top band rests on an archetype rather than on
evidence, and the only way to stop serving it was `UPDATE runs SET
is_active = FALSE`. That is not suppression. `serving_directory` selects
every run with a non-null `promoted_at`, so the row stays in the view and
`/v1/directory` keeps publishing the client's name, slug, sub-vertical
and a run entry whose `status` reads `SUPERSEDED` — while every page under
it 404s. The client is still listed; it just cannot be opened. "Back to
one client" was false: it was one client and one named ghost.

Withdrawal is the missing state. It is deliberately NOT deletion:

  * The serving rows stay. Promoted staging rows are retained (invariant 3)
    so a page can be re-produced and re-promoted without re-synthesising
    five, and the same is true of the promoted rows themselves — the run
    comes back by being fixed, not by being rebuilt.
  * The reason is recorded on the run, not in a chat log. A run that
    vanished for a reason nobody can read is a run that will come back for
    no reason anybody can read either.
  * Annotations, alerts and evidence are untouched. They are records of
    what people and gates did, and withdrawing a run does not un-do them.

## The alert question, answered by not answering it

`heatmap_alerts.status` is open · resolved · waived, and every one of those
is a statement about the FINDING. There is no value meaning "the run this
belongs to is not being served", and inventing one by writing `waived`
would fabricate a human decision — `waived` is something a person does, and
it is recorded in `alert_actions` with their name on it.

So the alert rows are left exactly as they are. They leave the queue
because `alerts.queue` joins `serving_directory`, which no longer carries
the run; they return, still open, still unactioned, when the run does.
The transition is the view's, and nothing has to be undone to reverse it.

## Reversal is a promote, not a second tool

`withdrawn_at` is cleared by `promote_run` (see apps/mcp/dma_mcp/promote.py).
There is no `restore_run`, on purpose: a run was withdrawn because what it
served was wrong, and the only honest way back onto a client's screen is a
promotion that passes the gates again. A restore tool would be a way to
un-withdraw without fixing anything, which is the failure mode this state
exists to prevent.

## Shape

Expand only. One enum value, three nullable columns, and the 0015/0031
rebuild of `serving_directory` with one predicate added. Nothing is
dropped, nothing is rewritten, re-running is a no-op.

Revision ID: 0042
Revises: 0041
Create Date: 2026-08-09
"""
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


# 0031's view body, verbatim, plus the withdrawal predicate. The body cannot
# be altered in place — a materialised view is rebuilt or it is not changed —
# so it is carried here whole rather than patched, exactly as 0031 carried
# 0015's.
_VIEW_BODY = """
        SELECT e.id            AS entity_id,
               e.display_id,
               e.legal_name,
               e.sub_vertical,
               e.size_tier,
               r.id            AS run_id,
               r.request_id,
               r.run_seq,
               r.is_active,
               enum_label(r.status) AS run_status,
               r.composite,
               r.scored_cells,
               r.catalogue_cells,
               r.ccg_catalog_version,
               r.completed_at,
               r.promoted_at,
               os.pillars,
               (SELECT count(*) FROM heatmap_alerts a
                 WHERE a.run_id = r.id AND a.status = 'open') AS open_alerts,
               ad.assessment_date,
               ad.basis         AS assessment_date_basis,
               ad.source_field  AS assessment_date_source,
               (ad.assessment_date + INTERVAL '6 months')::date AS refresh_due_date
          FROM runs r
          JOIN entities e ON e.id = r.entity_id
          LEFT JOIN overview_scores os ON os.run_id = r.id
          LEFT JOIN run_manifest rm ON rm.run_id = r.id
          CROSS JOIN LATERAL run_assessment_date(rm.payload -> 'manifest',
                                                 r.request_id) ad
         WHERE r.promoted_at IS NOT NULL
           AND r.withdrawn_at IS NULL
"""

_WITHDRAWN_PREDICATE = "           AND r.withdrawn_at IS NULL\n"
_PRE_0042_BODY = _VIEW_BODY.replace(_WITHDRAWN_PREDICATE, "")
# A .replace() that matches nothing returns the string unchanged and says so
# to nobody — which would make the downgrade a no-op that reports success.
# 0029 shipped a SQL literal defect of exactly this family; assert at import.
assert _PRE_0042_BODY != _VIEW_BODY, (
    "0042: the withdrawal predicate did not match the view body verbatim, so "
    "downgrade() would rebuild the view WITH the predicate it claims to remove")

_REFRESH_FN = """
        CREATE FUNCTION refresh_serving_directory() RETURNS void
          LANGUAGE sql SECURITY DEFINER
          SET search_path = public
          AS 'REFRESH MATERIALIZED VIEW serving_directory'
"""


def _rebuild(body: str) -> None:
    """0031's rebuild, verbatim in shape: the refresh function depends on the
    view, so it is dropped first and recreated after, with the same grants."""
    op.execute("DROP FUNCTION IF EXISTS refresh_serving_directory()")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS serving_directory")
    op.execute(f"CREATE MATERIALIZED VIEW serving_directory AS {body}")
    op.execute("CREATE UNIQUE INDEX serving_directory_run ON serving_directory (run_id)")
    op.execute("CREATE INDEX serving_directory_entity "
               "ON serving_directory (entity_id, run_seq DESC)")
    op.execute("GRANT SELECT ON serving_directory TO svc_api")
    op.execute(_REFRESH_FN)
    op.execute("REVOKE ALL ON FUNCTION refresh_serving_directory() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION refresh_serving_directory() TO svc_mcp")


def upgrade() -> None:
    # PostgreSQL 12+ permits ADD VALUE inside a transaction block provided the
    # new label is not USED in the same transaction. Nothing below writes it —
    # the view reads `enum_label(r.status)`, which never names a literal — so
    # this is safe under Alembic's wrapping transaction.
    op.execute("ALTER TYPE run_status_t ADD VALUE IF NOT EXISTS 'WITHDRAWN'")

    # Three columns, all nullable, all on the ingested tier's `runs` row.
    # `withdrawn_reason` has no length cap in DDL; the connector enforces a
    # floor instead, because the failure this guards against is an empty
    # reason, not a long one.
    op.execute("""
        ALTER TABLE runs
          ADD COLUMN IF NOT EXISTS withdrawn_at     TIMESTAMPTZ,
          ADD COLUMN IF NOT EXISTS withdrawn_reason TEXT,
          ADD COLUMN IF NOT EXISTS withdrawn_by     TEXT
    """)
    op.execute("COMMENT ON COLUMN runs.withdrawn_at IS "
               "'Set when a promoted run is taken off the client surface. "
               "Non-null removes the run from serving_directory, which is "
               "the only window svc_api reads, so the entity stops being "
               "listed as well as stopping being openable. Cleared by "
               "promote_run: a withdrawn run returns by being re-promoted.'")
    op.execute("COMMENT ON COLUMN runs.withdrawn_reason IS "
               "'Why, in prose, recorded on the run rather than in a "
               "transcript. Required by the connector at a 30-character "
               "floor.'")

    # A withdrawn run must be findable without scanning: the corpus sweep and
    # the weekly rectification both ask which runs are currently withheld.
    op.execute("CREATE INDEX IF NOT EXISTS runs_withdrawn "
               "ON runs (withdrawn_at) WHERE withdrawn_at IS NOT NULL")

    _rebuild(_VIEW_BODY)


def downgrade() -> None:
    # The enum value stays: PostgreSQL cannot drop an enum label, and a
    # downgrade that leaves it is honest about that rather than pretending.
    _rebuild(_PRE_0042_BODY)
    op.execute("DROP INDEX IF EXISTS runs_withdrawn")
    op.execute("ALTER TABLE runs DROP COLUMN IF EXISTS withdrawn_by")
    op.execute("ALTER TABLE runs DROP COLUMN IF EXISTS withdrawn_reason")
    op.execute("ALTER TABLE runs DROP COLUMN IF EXISTS withdrawn_at")
