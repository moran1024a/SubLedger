"""Add private rule groups and persistent display order without changing bills."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0005_plan_groups"
down_revision = "0004_general_cycles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bill_plan_groups",
        sa.Column("id", mysql.BIGINT(unsigned=True), primary_key=True, autoincrement=True),
        sa.Column("user_id", mysql.INTEGER(unsigned=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("sort_order", mysql.INTEGER(unsigned=True), nullable=False, server_default="0"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("user_id", "name", name="uq_bill_plan_groups_user_name"),
        mysql_engine="InnoDB", mysql_charset="utf8mb4",
    )
    op.create_index("ix_bill_plan_groups_user_order", "bill_plan_groups", ["user_id", "sort_order"])
    op.add_column("bill_plans", sa.Column("group_id", mysql.BIGINT(unsigned=True), nullable=True))
    op.create_foreign_key("fk_bill_plans_group_id", "bill_plans", "bill_plan_groups", ["group_id"], ["id"])
    op.add_column("bill_plans", sa.Column("sort_order", mysql.INTEGER(unsigned=True), nullable=False, server_default="0"))
    op.create_index("ix_bill_plans_user_group_order", "bill_plans", ["user_id", "group_id", "sort_order"])
    op.execute("INSERT INTO bill_plan_groups (user_id, name, sort_order, is_default) SELECT id, '未分组', 0, 1 FROM users")
    # A window query preserves the previous ID-descending order in one MySQL update.
    op.execute("""UPDATE bill_plans AS plans
        JOIN (SELECT id, ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY id DESC) - 1 AS position
              FROM bill_plans) AS ranked ON plans.id = ranked.id
        SET plans.sort_order = ranked.position""")


def downgrade():
    raise RuntimeError("Rule grouping and order require restoring the pre-upgrade backup")
