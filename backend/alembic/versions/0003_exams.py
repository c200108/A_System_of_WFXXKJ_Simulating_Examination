"""考试发布与学生答卷

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exams",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("paper_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=128), nullable=False),
        sa.Column("token", sa.String(length=32), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_retake", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("show_score", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("show_answer", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_exams_token"),
    )
    op.create_index("ix_exams_paper_id", "exams", ["paper_id"])
    op.create_index("ix_exams_token", "exams", ["token"])

    op.create_table(
        "exam_submissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("student_name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("student_class", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("student_no", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("answers_json", sa.Text(), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False),
        sa.Column("right_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("objective_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("submitted_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["exams.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exam_submissions_exam_id", "exam_submissions", ["exam_id"])
    op.create_index("ix_exam_submissions_student_no", "exam_submissions", ["student_no"])


def downgrade() -> None:
    op.drop_table("exam_submissions")
    op.drop_table("exams")
