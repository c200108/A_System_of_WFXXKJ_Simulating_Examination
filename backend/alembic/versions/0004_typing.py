"""打字训练成绩

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-07
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "typing_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_name", sa.String(length=64), nullable=False),
        sa.Column("student_class", sa.String(length=64), nullable=False),
        sa.Column("module", sa.String(length=16), nullable=False),
        sa.Column("difficulty", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("speed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accuracy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("typed_chars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_typing_records_student_name", "typing_records", ["student_name"])
    op.create_index("ix_typing_records_student_class", "typing_records", ["student_class"])
    op.create_index("ix_typing_records_module", "typing_records", ["module"])
    op.create_index("ix_typing_records_created_at", "typing_records", ["created_at"])
    op.create_index("ix_typing_cls_name", "typing_records", ["student_class", "student_name"])


def downgrade() -> None:
    op.drop_table("typing_records")
