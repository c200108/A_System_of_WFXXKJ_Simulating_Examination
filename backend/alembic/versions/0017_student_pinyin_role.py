"""学生增加「拼音」和「班干部」两列，已有学生的拼音当场补上

- pinyin：姓名的拼音全拼，学生端拼音登录认的就是它；
- class_role：班长 / 组长 / 空。

已有的学生在这里一次性按姓名算好拼音，升级完就能用拼音登录，老师不用重新导名单。

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column("pinyin", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "students",
        sa.Column("class_role", sa.String(8), nullable=False, server_default=""),
    )
    op.create_index("ix_students_pinyin", "students", ["pinyin"])

    from app.services.pinyin import name_pinyin

    conn = op.get_bind()
    students = sa.table("students", sa.column("id", sa.Integer),
                        sa.column("name", sa.String), sa.column("pinyin", sa.String))
    rows = conn.execute(sa.select(students.c.id, students.c.name)).all()
    for sid, name in rows:
        py = name_pinyin(name or "")
        if py:
            conn.execute(students.update().where(students.c.id == sid).values(pinyin=py))


def downgrade() -> None:
    op.drop_index("ix_students_pinyin", table_name="students")
    with op.batch_alter_table("students") as batch:
        batch.drop_column("class_role")
        batch.drop_column("pinyin")
