"""024 — widen job_executions.trigger_source CHECK to allow 'post_commit'.

Revision ID: 024_post_commit_trigger
Revises: 023_focus_areas_reconcile

Context
=======
Migration 020 created `job_executions` with a CHECK constraint
restricting `trigger_source` to {'admin_ui','scheduler','pubsub','cli'}.
The 2026-05-29 QA audit added a new trigger path —
`app/services/post_commit_workers.dispatch_post_commit_workers` —
that fires the embedder + intelligence_recompute jobs immediately after
every successful ingest commit. Audit-trail clarity wants those rows
filterable distinct from admin-button-triggered rows
(`trigger_source='admin_ui'`) and from any future Pub/Sub-push consumer
(`trigger_source='pubsub'`), so this migration adds `'post_commit'` as
the 5th allowed value.

Without this migration, the post_commit_workers inserts violate the
CHECK and the dispatch path silently swallows the error → ingest still
returns 201 but no derived-data jobs run, exactly the symptom Fix-D
was meant to close.
"""
from __future__ import annotations

from alembic import op

revision = "024_post_commit_trigger"
down_revision = "023_focus_areas_reconcile"
branch_labels = None
depends_on = None

ALLOWED_OLD = "('admin_ui','scheduler','pubsub','cli')"
ALLOWED_NEW = "('admin_ui','scheduler','pubsub','cli','post_commit')"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE job_executions "
        "DROP CONSTRAINT IF EXISTS ck_job_executions_trigger_source"
    )
    op.execute(
        "ALTER TABLE job_executions "
        f"ADD CONSTRAINT ck_job_executions_trigger_source "
        f"CHECK (trigger_source IN {ALLOWED_NEW})"
    )


def downgrade() -> None:
    # Pre-flight: rows with trigger_source='post_commit' violate the
    # narrower constraint. Either backfill them to 'pubsub' (closest
    # semantic match — both are event-driven, non-operator-initiated)
    # or refuse to downgrade. Backfill is safer for replay scenarios.
    op.execute(
        "UPDATE job_executions SET trigger_source='pubsub' "
        "WHERE trigger_source='post_commit'"
    )
    op.execute(
        "ALTER TABLE job_executions "
        "DROP CONSTRAINT IF EXISTS ck_job_executions_trigger_source"
    )
    op.execute(
        "ALTER TABLE job_executions "
        f"ADD CONSTRAINT ck_job_executions_trigger_source "
        f"CHECK (trigger_source IN {ALLOWED_OLD})"
    )
