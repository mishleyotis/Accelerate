"""The worker may publish the directory it repairs

`serving_directory` is MATERIALISED. A writer that changes a row underneath
it has changed nothing a client can see until `refresh_serving_directory()`
runs, and EXECUTE on that function was granted to `svc_mcp` alone — the
promote and withdraw paths in `apps/mcp`.

WHAT THAT COSTS. `job_main.backfill_composite` repairs `runs.composite` for a
run ingested under a reader that could not find the figure. It commits the
UPDATE and stops. Nothing refreshes the view, so the repaired value sits in
`runs` and the client directory keeps rendering the word "maturity" over an
empty slot until some unrelated promote happens to refresh it. The repair
was written, it was correct, and its result was unpublishable by the role
that runs it — measured 2026-09-04 on goeasy Ltd.
(`DMA-RES-GSY-20260830-0002`), whose four pillar bars resolved beside a
blank composite.

Grant only. No table, view, function or column changes; nothing is dropped
and re-running is a no-op. `svc_mcp` keeps the grant it already had.

The function is SECURITY DEFINER and takes no arguments, so this widens the
worker's authority by exactly one thing: it may ask for the directory to be
rebuilt from what is already committed. It cannot read or write a row it
could not already reach.

Revision ID: 0059
Revises: 0058
Create Date: 2026-09-04
"""
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT EXECUTE ON FUNCTION refresh_serving_directory() "
               "TO svc_worker")


def downgrade() -> None:
    op.execute("REVOKE EXECUTE ON FUNCTION refresh_serving_directory() "
               "FROM svc_worker")
