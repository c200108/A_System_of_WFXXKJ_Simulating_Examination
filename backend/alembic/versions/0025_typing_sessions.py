"""typing_sessions：计分打字练习的一次性会话（服务端出文本、记时间、只能交一次）

Revision ID: 0025
Revises: 0024
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None

BIG = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")


def upgrade() -> None:
    if "typing_sessions" in set(sa.inspect(op.get_bind()).get_table_names()):
        return
    op.create_table(
        "typing_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=True),
        sa.Column("student_name", sa.String(64), nullable=False),
        sa.Column("student_class", sa.String(64), nullable=False),
        sa.Column("module", sa.String(16), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False, server_default=""),
        sa.Column("target", BIG, nullable=False),
        sa.Column("time_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("progress", BIG, nullable=False),
        sa.Column("checks", BIG, nullable=False),
        sa.Column("last_progress_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("void_reason", sa.String(200), nullable=False, server_default=""),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_typing_sessions_student_id", "typing_sessions", ["student_id"])
    op.create_index("ix_typing_sessions_created_at", "typing_sessions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_typing_sessions_created_at", table_name="typing_sessions")
    op.drop_index("ix_typing_sessions_student_id", table_name="typing_sessions")
    op.drop_table("typing_sessions")
