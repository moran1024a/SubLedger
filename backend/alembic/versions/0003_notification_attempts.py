"""Notification attempt metadata and explicit retry state."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0003_notification_attempts"
down_revision = "0002_add_bill_plan_deleted_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notification_records", sa.Column("attempt_count", mysql.INTEGER(unsigned=True), nullable=False, server_default="0"))
    op.add_column("notification_records", sa.Column("last_attempt_at", mysql.DATETIME(fsp=6), nullable=True))
    op.add_column("notification_records", sa.Column("next_retry_at", mysql.DATETIME(fsp=6), nullable=True))
    op.add_column("notification_records", sa.Column("error_code", sa.String(64), nullable=True))
    op.execute("UPDATE notification_records SET attempt_count = retry_count + CASE WHEN status IN ('sent', 'sending') THEN 1 ELSE 0 END")
    # Historical attempt times are unknown; never invent them or reset successes.
    op.execute("UPDATE notification_records SET status = 'unknown', error_code = 'DELIVERY_UNKNOWN' WHERE status = 'sending'")
    op.execute("UPDATE notification_records SET status = 'retry_wait', next_retry_at = scheduled_at WHERE status = 'failed' AND retry_count < 3")


def downgrade() -> None:
    raise RuntimeError("Notification retry semantics changed; restore the pre-upgrade backup to roll back")
