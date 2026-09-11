"""学生账号表，以及考试的班级定向、成绩与打字记录的账号关联

学生和教师分成两张表：字段不同，权限也完全不同，合表靠 role 区分
迟早会有某处忘了判角色。

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "students",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("student_no", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("student_class", sa.String(64), nullable=False, server_default=""),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_students_student_no", "students", ["student_no"], unique=True)
    op.create_index("ix_students_name", "students", ["name"])
    op.create_index("ix_students_student_class", "students", ["student_class"])
    op.create_index("ix_students_class_no", "students", ["student_class", "student_no"])

    # 考试按班级定向。留空 = 所有班都能在学生平台看到；
    # 凭链接直接答题的老路子不受它影响。
    op.add_column(
        "exams",
        sa.Column("target_classes", sa.String(255), nullable=False, server_default=""),
    )

    # 学生平台上交的卷子和练的字记到账号上；匿名来的仍然是 NULL。
    #
    # 这里必须走 batch_alter_table：SQLite 不支持 ALTER TABLE ADD CONSTRAINT，
    # 直接 create_foreign_key 会抛 NotImplementedError。batch 模式在 SQLite 上
    # 用"建新表-搬数据-改名"实现，在 MySQL 上就是普通的 ALTER，两边都能跑。
    for table, fk_name in (
        ("exam_submissions", "fk_submission_student"),
        ("typing_records", "fk_typing_student"),
    ):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("student_id", sa.Integer, nullable=True))
            batch.create_foreign_key(
                fk_name, "students", ["student_id"], ["id"], ondelete="SET NULL"
            )
        op.create_index(f"ix_{table}_student_id", table, ["student_id"])


def downgrade() -> None:
    for table, fk_name in (
        ("typing_records", "fk_typing_student"),
        ("exam_submissions", "fk_submission_student"),
    ):
        # 三步都放在 batch 里，顺序不能改：
        # MySQL 会按顺序发 ALTER —— 外键还在时删不掉它依赖的索引（报 1553）；
        # SQLite 是整表重建 —— 索引不先摘掉，重建时会去引用一个已经没有的列。
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(fk_name, type_="foreignkey")
            batch.drop_index(f"ix_{table}_student_id")
            batch.drop_column("student_id")

    op.drop_column("exams", "target_classes")

    op.drop_index("ix_students_class_no", table_name="students")
    op.drop_index("ix_students_student_class", table_name="students")
    op.drop_index("ix_students_name", table_name="students")
    op.drop_index("ix_students_student_no", table_name="students")
    op.drop_table("students")
