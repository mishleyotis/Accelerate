"""Expand ccg_products to the SHIPPED v7.0 workbook columns

The V7 schema HTML describes 7_Product_Catalogue as {Product_Name,
Product_Code, Category, Licensing_Model, Sub_Vertical_Fit, Maturity_Hint,
...}; the four shipped v7.0 workbooks actually carry {Vendor,
L3_Platform_Area, Component_Name, Component_Type, Description,
Source_Type, Reference_URL, LOB, Workflow, Status, Agent_ID,
P{n}_Relevance_Note}. The shipped data wins (it is what stage 0.4 loads);
the documented-but-unshipped columns stay, nullable, in case a later
catalogue version ships them. Expand only — no contract yet.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-04
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ccg_products
          ADD COLUMN l3_platform_area TEXT,
          ADD COLUMN component_type   TEXT,
          ADD COLUMN lob              TEXT,
          ADD COLUMN workflow         TEXT,
          ADD COLUMN status           TEXT,
          ADD COLUMN agent_id         TEXT
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE ccg_products
          DROP COLUMN IF EXISTS l3_platform_area,
          DROP COLUMN IF EXISTS component_type,
          DROP COLUMN IF EXISTS lob,
          DROP COLUMN IF EXISTS workflow,
          DROP COLUMN IF EXISTS status,
          DROP COLUMN IF EXISTS agent_id
        """
    )
