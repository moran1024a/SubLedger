"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", mysql.INTEGER(unsigned=True), autoincrement=False, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("currency_code", sa.String(length=8), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "sessions",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_expires_at", "sessions", ["expires_at"])
    op.create_table(
        "bill_plans",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("first_due_date", sa.Date(), nullable=False),
        sa.Column("cycle_type", sa.String(length=32), nullable=False),
        sa.Column("cycle_days", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_bill_plans_user_enabled", "bill_plans", ["user_id", "is_enabled"])
    op.create_table(
        "bill_occurrences",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("plan_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount_snapshot", sa.Numeric(14, 2), nullable=False),
        sa.Column("is_valid", sa.Boolean(), nullable=False),
        sa.Column("invalidated_by_plan_disable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["bill_plans.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "due_date", name="uq_bill_occurrences_plan_due"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_bill_occurrences_user_due", "bill_occurrences", ["user_id", "due_date"])
    op.create_index("ix_bill_occurrences_user_valid_due", "bill_occurrences", ["user_id", "is_valid", "due_date"])
    op.create_table(
        "notification_settings",
        sa.Column("user_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), nullable=False),
        sa.Column("smtp_host", sa.String(length=255), nullable=True),
        sa.Column("smtp_port", mysql.INTEGER(unsigned=True), nullable=True),
        sa.Column("smtp_security", sa.String(length=16), nullable=True),
        sa.Column("smtp_username", sa.String(length=255), nullable=True),
        sa.Column("smtp_password_encrypted", sa.Text(), nullable=True),
        sa.Column("sender_email", sa.String(length=255), nullable=True),
        sa.Column("sender_name", sa.String(length=128), nullable=True),
        sa.Column("recipient_email", sa.String(length=255), nullable=True),
        sa.Column("feishu_enabled", sa.Boolean(), nullable=False),
        sa.Column("feishu_webhook_encrypted", sa.Text(), nullable=True),
        sa.Column("feishu_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("advance_enabled", sa.Boolean(), nullable=False),
        sa.Column("advance_days", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("advance_time", sa.Time(), nullable=False),
        sa.Column("same_day_enabled", sa.Boolean(), nullable=False),
        sa.Column("same_day_time", sa.Time(), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_table(
        "notification_records",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("plan_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("bill_id", mysql.BIGINT(unsigned=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("reminder_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scheduled_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("sent_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("retry_count", mysql.INTEGER(unsigned=True), nullable=False),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.ForeignKeyConstraint(["bill_id"], ["bill_occurrences.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["bill_plans.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "due_date", "channel", "reminder_type", name="uq_notification_business_key"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
    )
    op.create_index("ix_notification_records_user_scheduled", "notification_records", ["user_id", "scheduled_at"])
    op.create_index("ix_notification_records_status_scheduled", "notification_records", ["status", "scheduled_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_records_status_scheduled", table_name="notification_records")
    op.drop_index("ix_notification_records_user_scheduled", table_name="notification_records")
    op.drop_table("notification_records")
    op.drop_table("notification_settings")
    op.drop_index("ix_bill_occurrences_user_valid_due", table_name="bill_occurrences")
    op.drop_index("ix_bill_occurrences_user_due", table_name="bill_occurrences")
    op.drop_table("bill_occurrences")
    op.drop_index("ix_bill_plans_user_enabled", table_name="bill_plans")
    op.drop_table("bill_plans")
    op.drop_index("ix_sessions_expires_at", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("users")
