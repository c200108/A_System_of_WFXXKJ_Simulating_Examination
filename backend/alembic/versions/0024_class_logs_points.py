"""课堂情况日志 class_logs + 课堂加减分 student_points

- class_logs：在线座次右边的「课堂日志」，每次上机记一条（请假缺勤、设备问题……），跟着班级走
- student_points：在线座次右键学生「加分 / 减分」，一笔一行，总分相加

Revision ID: 0024
Revises: 0023
"""

import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    tables = set(insp.get_table_names())
    if "class_logs" not in tables:
        _create_logs()
    if "student_points" not in tables:
        op.create_table(
            "student_points",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
            sa.Column("delta", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(64), nullable=False, server_default=""),
            sa.Column("author_name", sa.String(64), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_student_points_class_id", "student_points", ["class_id"])
        op.create_index("ix_student_points_student_id", "student_points", ["student_id"])


def _create_logs() -> None:
    op.create_table(
        "class_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lesson_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(64), nullable=False, server_default=""),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("author_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_class_logs_class_id", "class_logs", ["class_id"])


def downgrade() -> None:
    op.drop_index("ix_student_points_student_id", table_name="student_points")
    op.drop_index("ix_student_points_class_id", table_name="student_points")
    op.drop_table("student_points")
    op.drop_index("ix_class_logs_class_id", table_name="class_logs")
    op.drop_table("class_logs")
