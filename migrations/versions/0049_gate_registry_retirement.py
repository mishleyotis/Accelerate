"""A gate removed from the code kept answering as a live rule in production.

The build owner removed the open alert ceiling on 2026-08-16. `SG-AC1` was
deleted from `gates.GATES`, the refusal was deleted from `promote_run`, tests
asserted its absence, the connector was deployed, and `verify_deployed.py`
reported every module byte-identical to a local build of HEAD.

`explain_gate("SG-AC1")` then returned the full definition, `on_failure:
"block"`, from production.

`gate_registry` is a TABLE. `ensure_gate_registry` seeds it with
`INSERT … ON CONFLICT DO UPDATE` — purely additive, so it can create a gate
and change a gate and can never retire one. Every check that passed was
reading the Python dict; nothing read the row. A producer looking up why it
had been refused would have found a live blocking gate that no longer exists
in any code path, and repaired against it.

    RULE_HELD_IN_TWO_PLACES_DRIFTS, with the second place in the database and
    only the first place under test.

WHY THIS IS RETIREMENT AND NOT DELETION. `gate_results` carries a foreign key
onto `gate_registry(gate_id)`: every gate outcome ever recorded against a run
points here. Deleting the row would either fail on the constraint or, with a
cascade, destroy the record of gates that ran — and a gate's history is
evidence about a promoted run, not scaffolding. So the row stays, reachable,
and gains a date that says it no longer runs.

`explain_gate` reports `retired_at` and rewrites `on_failure` to `retired`, so
the answer to "what does this gate do to me" is "nothing, since 2026-08-16"
rather than "block". The definition and the threshold history stay readable,
which is the point of keeping the row at all: an old verdict naming SG-AC1
remains explicable.

Expand only. The column is nullable with no default, so every existing row
reads as live — which is correct, because they are.
"""
from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE gate_registry
          ADD COLUMN IF NOT EXISTS retired_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN gate_registry.retired_at IS
          'When this gate stopped being enforced. NULL means live. Set by '
          'ensure_gate_registry for any gate_id absent from the code registry, '
          'cleared if it returns. The row is retained rather than deleted '
          'because gate_results references it and a gate outcome recorded '
          'against a run is evidence.'
        """
    )
    # Retire what the code no longer defines, without needing the app to run.
    # Named explicitly rather than computed, because a migration cannot import
    # the connector's registry and a migration that guessed would be worse
    # than one that states its subject.
    op.execute(
        """
        UPDATE gate_registry
           SET retired_at = COALESCE(retired_at, TIMESTAMPTZ '2026-08-16 00:00:00+00')
         WHERE gate_id = 'SG-AC1'
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE gate_registry DROP COLUMN IF EXISTS retired_at")
