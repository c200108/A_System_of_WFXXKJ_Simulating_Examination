"""在线座次 + 学困生标记

- classes.seat_sheet：每个班一份「在线座次」表格（JSON：数据、合并单元格、样式、列宽行高）
- students.struggling：学困生标记。只有本班老师和管理员看得到，学生自己的接口不返回

Revision ID: 0023
Revises: 0022
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

LONG_TEXT = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("classes")}
    if "seat_sheet" not in cols:
        with op.batch_alter_table("classes") as batch:
            batch.add_column(sa.Column("seat_sheet", LONG_TEXT, nullable=True))
    cols = {c["name"] for c in insp.get_columns("students")}
    if "struggling" not in cols:
        with op.batch_alter_table("students") as batch:
            batch.add_column(sa.Column("struggling", sa.Boolean(), nullable=False,
                                       server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("students") as batch:
        batch.drop_column("struggling")
    with op.batch_alter_table("classes") as batch:
        batch.drop_column("seat_sheet")
