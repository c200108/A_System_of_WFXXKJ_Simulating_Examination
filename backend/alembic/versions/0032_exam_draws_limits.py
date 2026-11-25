"""考试：每次取卷重抽（exam_draws）、单独的考试时长、重考次数、交卷频率；试卷可隐藏（2.28.0）

- exam_draws：网页链接开了乱序时每次取卷重抽的一套题
- exams.duration / max_attempts / rate_window / rate_max
- exam_submissions.draw_key：答的是哪一套
- papers.is_hidden：从历史试卷里删了、但还有考试在用的卷子只藏起来

Revision ID: 0032
Revises: 0031
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None

LONG_TEXT = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")


def _add(insp, table, col):
    if col.name not in {c["name"] for c in insp.get_columns(table)}:
        with op.batch_alter_table(table) as t:
            t.add_column(col)


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "exam_draws" not in insp.get_table_names():
        op.create_table(
            "exam_draws",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("exam_id", sa.Integer(), sa.ForeignKey("exams.id", ondelete="CASCADE"), nullable=False),
            sa.Column("key", sa.String(24), nullable=False),
            sa.Column("items_json", LONG_TEXT, nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_exam_draws_exam_id", "exam_draws", ["exam_id"])
        op.create_index("ix_exam_draws_key", "exam_draws", ["key"], unique=True)
    _add(insp, "exams", sa.Column("duration", sa.String(16), nullable=False, server_default=""))
    _add(insp, "exams", sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="0"))
    _add(insp, "exams", sa.Column("rate_window", sa.Integer(), nullable=False, server_default="0"))
    _add(insp, "exams", sa.Column("rate_max", sa.Integer(), nullable=False, server_default="0"))
    _add(insp, "exam_submissions", sa.Column("draw_key", sa.String(24), nullable=False, server_default=""))
    _add(insp, "papers", sa.Column("is_hidden", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("papers") as t:
        t.drop_column("is_hidden")
    with op.batch_alter_table("exam_submissions") as t:
        t.drop_column("draw_key")
    with op.batch_alter_table("exams") as t:
        for c in ("rate_max", "rate_window", "max_attempts", "duration"):
            t.drop_column(c)
    op.drop_index("ix_exam_draws_key", table_name="exam_draws")
    op.drop_index("ix_exam_draws_exam_id", table_name="exam_draws")
    op.drop_table("exam_draws")
