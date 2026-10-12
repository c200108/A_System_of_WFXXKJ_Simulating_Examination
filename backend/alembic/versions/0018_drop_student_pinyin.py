"""去掉学生的「拼音」列：登录改回「班级 + 汉字姓名」，不再用拼音

0017 加的 pinyin 列（和它的索引）在这里删掉；class_role（班长 / 组长）保留。

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_students_pinyin", table_name="students")
    with op.batch_alter_table("students") as batch:
        batch.drop_column("pinyin")


def downgrade() -> None:
    op.add_column("students", sa.Column("pinyin", sa.String(64), nullable=False, server_default=""))
    op.create_index("ix_students_pinyin", "students", ["pinyin"])
