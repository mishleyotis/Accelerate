"""032 — caps_applied_log: widen unique to (run_id, log_id, subcap_id)

Per the 2026-06-07 corpus-stress finding: a single cap event (`cap_id`
in the source CSV) can cascade across many subcaps when the source
fixture uses the *per-(cap x subcap)* layout (Pentegra Retirement
Services / Pentegra Retirement — 198 rows, all sharing ``cap_id=SEV-001``
across 198 distinct ``affected_id`` subcaps). The current
``ux_caps_applied_log_run_logid UNIQUE (run_id, log_id)`` index
treats two distinct cap-subcap rows as duplicates and aborts the
*entire ingest transaction* with a UniqueViolationError.

The natural row identity is the cap event AND the subcap it caps:
``(run_id, log_id, subcap_id)``. The 4 prior fixtures (Alma /
Calprivate / Nicola / Odlum) all have unique ``(log_id, subcap_id)``
pairs, so the widened constraint is a strict superset of the old
one — no data loss, no migration of existing rows needed.

Idempotent: drops the narrow index if present, creates the wide one
if not. Safe to re-run.
"""
from alembic import op

revision = "032_caps_log_widen_unique"
down_revision = "031_runs_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_caps_applied_log_run_logid")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            ux_caps_applied_log_run_logid_subcap
        ON caps_applied_log (run_id, log_id, subcap_id)
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ux_caps_applied_log_run_logid_subcap"
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_caps_applied_log_run_logid
        ON caps_applied_log (run_id, log_id)
        """
    )
