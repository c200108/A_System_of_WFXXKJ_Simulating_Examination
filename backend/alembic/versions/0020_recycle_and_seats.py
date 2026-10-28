"""数据回收站 + 班级上机座次表

- recycle_items：删掉的东西先放 7 天，可还原，过期才真删
- classes.seat_file / seat_name：每个班的上机座次表（图片或 Excel）

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

LONG_TEXT = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("classes")}
    with op.batch_alter_table("classes") as batch:
        if "seat_file" not in cols:
            batch.add_column(sa.Column("seat_file", sa.String(255), nullable=False, server_default=""))
        if "seat_name" not in cols:
            batch.add_column(sa.Column("seat_name", sa.String(128), nullable=False, server_default=""))

    if "recycle_items" not in insp.get_table_names():
        op.create_table(
            "recycle_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("detail", sa.String(255), nullable=False),
            sa.Column("payload", LONG_TEXT, nullable=False),
            sa.Column("deleted_by", sa.Integer(),
                      sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("deleted_by_name", sa.String(64), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_recycle_items_kind", "recycle_items", ["kind"])
        op.create_index("ix_recycle_items_deleted_by", "recycle_items", ["deleted_by"])
        op.create_index("ix_recycle_items_expires_at", "recycle_items", ["expires_at"])


def downgrade() -> None:
    op.drop_table("recycle_items")
    with op.batch_alter_table("classes") as batch:
        batch.drop_column("seat_name")
        batch.drop_column("seat_file")
