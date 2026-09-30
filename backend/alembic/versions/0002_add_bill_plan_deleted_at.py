"""add bill plan deletion marker

Revision ID: 0002_add_bill_plan_deleted_at
Revises: 0001_initial_schema
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0002_add_bill_plan_deleted_at"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "bill_plans",
        sa.Column("deleted_at", mysql.DATETIME(fsp=6), nullable=True),
    )


def downgrade() -> None:
    raise RuntimeError("0.1.2 bill plan deletions require restoring the pre-upgrade database backup")
