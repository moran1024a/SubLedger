"""Convert legacy cycles without touching existing bills or reminder records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0004_general_cycles"
down_revision = "0003_notification_attempts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("bill_plans", sa.Column("cycle_interval", mysql.INTEGER(unsigned=True), nullable=False, server_default="1"))
    op.execute("UPDATE bill_plans SET cycle_interval = CASE cycle_type WHEN 'quarterly' THEN 3 WHEN 'custom_days' THEN cycle_days ELSE 1 END WHERE cycle_type IN ('monthly', 'quarterly', 'yearly', 'custom_days', 'once')")
    op.execute("UPDATE bill_plans SET cycle_type = CASE cycle_type WHEN 'monthly' THEN 'month' WHEN 'quarterly' THEN 'month' WHEN 'yearly' THEN 'year' WHEN 'custom_days' THEN 'day' ELSE cycle_type END, cycle_days = NULL")


def downgrade():
    raise RuntimeError("General cycles are not understood by older releases; restore the pre-upgrade backup")
