"""个人云盘（2.25.0）：cloud_accounts 每位老师的 OpenList 账号、分到的空间、实际用量

Revision ID: 0028
Revises: 0027
"""

import sqlalchemy as sa
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())
    if "cloud_accounts" in have:
        return
    op.create_table(
        "cloud_accounts",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("quota_mb", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("folder", sa.String(64), nullable=False, server_default=""),
        sa.Column("login", sa.String(64), nullable=False, server_default=""),
        # Text 列不写 server_default：MySQL 不接受（见 test_migrations.py 开头那次事故）
        sa.Column("password_enc", sa.Text(), nullable=False),
        sa.Column("password_custom", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("used_bytes", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("over_quota", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("checked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("cloud_accounts")
