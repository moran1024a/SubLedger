"""Schedule rule endings and distinguish automatic endings from manual deletion."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0006_plan_endings"
down_revision = "0005_plan_groups"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("bill_plans", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("bill_plans", sa.Column("ended_at", mysql.DATETIME(fsp=6), nullable=True))
    op.create_index("ix_bill_plans_user_end", "bill_plans", ["user_id", "end_date"])
    op.execute("UPDATE bill_plans SET end_date = first_due_date WHERE cycle_type = 'once' AND deleted_at IS NULL")
    # Legacy disabled recurring rules have no reliable disabled_at timestamp.
    # The lifecycle job fixes their next due date in each account's time zone.


def downgrade():
    raise RuntimeError("Automatic rule endings require restoring the pre-upgrade backup")
