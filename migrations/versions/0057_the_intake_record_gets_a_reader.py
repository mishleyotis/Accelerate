"""parser_observations gets a reader, and the grant that lets it read.

AUD-0030: the intake failure record is written durably on every ingest — a
column the parser did not recognise, a score outside the rubric, an absent
peer tab, an evidence index that would not parse — and it had no reader
outside the worker and no grant beyond it. The producer, whose whole job is
to synthesise from that package, could not see what the package failed to
yield, so a surface that renders empty because a COLUMN was not recognised
is indistinguishable from an entity that genuinely has nothing to say. The
producer then writes an absence, and the absence is wrong.

`get_run_progress` now returns the observations grouped by kind, worst first
— the one call a resuming or repairing producer already makes. This revision
carries the grant that call is owed. Grants ship in the same revision as the
consumer (working discipline): an existing table with a NEW consumer is owed
a grant no create-table revision covers.

Read-only, deliberately. The connector must never edit the intake's account
of what it could not read.
"""
from alembic import op

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT ON parser_observations TO svc_mcp")


def downgrade() -> None:
    op.execute("REVOKE SELECT ON parser_observations FROM svc_mcp")
