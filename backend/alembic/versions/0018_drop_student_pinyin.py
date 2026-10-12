"""去掉学生的「拼音」列

学生登录改回「班级 + 中文姓名 + 密码」，拼音不再用。起草版的 0017 加过 pinyin 列和索引，
跑过那一版的库在这里删掉；没跑过的库什么都不用做。

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
    insp = sa.inspect(op.get_bind())
    if "pinyin" not in {c["name"] for c in insp.get_columns("students")}:
        return
    if "ix_students_pinyin" in {i["name"] for i in insp.get_indexes("students")}:
        op.drop_index("ix_students_pinyin", table_name="students")
    with op.batch_alter_table("students") as batch:
        batch.drop_column("pinyin")


def downgrade() -> None:
    pass
