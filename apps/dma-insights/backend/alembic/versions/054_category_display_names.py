"""054 - backfill v7.0 category display names (heatmap grid labels)

The v7.0 pillar workbooks carry NO category display-name column — the
``Category`` column IS the id (P1C1) — so ``ccg_categories.name``
loaded blank for all 17 v7.0 categories and every surface that joins
it (heatmap grid column labels, drilled category headers, category
synthesis titles) fell back to the bare mono id. The all-94
prototype-parity capture flagged it: the wireframe labels cells
"P1C1 · Digital Strategy"; production showed "P1C1" alone.

Names are derived from each category's REAL v7.0 L1 composition (e.g.
P3C2's L1s are Fraud Detection / Investigation / Intelligence — NOT
the prototype mock's "Loan Origination"), mirrored from
``workers/ccg_loader/parsers.CATEGORY_DISPLAY_NAMES`` which now
derives them at catalogue load. This migration covers DBs whose
catalogue was loaded before that change.

Idempotent + honest: only fills rows whose name is NULL / '' / the
bare id — an explicit workbook-supplied name is never overwritten.
"""
from alembic import op

revision = "054_category_display_names"
down_revision = "053_platform_fit_breakdown"
branch_labels = None
depends_on = None

# Keep in lock-step with workers/ccg_loader/parsers.CATEGORY_DISPLAY_NAMES.
_NAMES = {
    "P1C1": "Digital Strategy",
    "P1C2": "Governance & Risk",
    "P1C3": "Innovation Operating Model",
    "P1C4": "Talent, Culture & Change",
    "P1C5": "ESG & Community",
    "P2C1": "Marketing & Demand",
    "P2C2": "Onboarding & Origination",
    "P2C3": "Service & Support",
    "P2C4": "Personalisation & Deepening",
    "P3C1": "Process Automation",
    "P3C2": "Fraud & Operational Risk",
    "P3C3": "Compliance Operations",
    "P3C4": "Resilience & Third-Party Risk",
    "P4C1": "Data Foundation",
    "P4C2": "Analytics & AI",
    "P4C3": "Architecture & Cloud",
    "P4C4": "Security & Trust",
}


def upgrade() -> None:
    # ALL loaded versions (v2.3/v2.4/v5.5/v6.3/v7.0) share the same 17
    # category ids and the same no-name-column workbook shape — clients
    # pinned to an older catalogue version get the same labels (the
    # rendered sweep found 17 clients still id-only under a v7.0-only
    # backfill). Guarded on empty-name, so an explicit name always wins.
    values = ", ".join(
        f"('{cid}', '{name.replace(chr(39), chr(39) * 2)}')"
        for cid, name in _NAMES.items()
    )
    op.execute(
        f"""
        UPDATE ccg_categories SET name = v.n
        FROM (VALUES {values}) AS v(cid, n)
        WHERE ccg_categories.category_id = v.cid
          AND (ccg_categories.name IS NULL
               OR ccg_categories.name = ''
               OR ccg_categories.name = ccg_categories.category_id)
        """
    )


def downgrade() -> None:
    # Restoring blanks would re-break the grid labels; the guarded
    # upgrade is safe to leave in place. No-op by design.
    pass
