"""答卷分数可以带小数（2.29.0）

按题型组的卷子每题平均赋分：40 题每题 2.5 分，答对单数题总分就是 x.5。
exam_submissions 的 score / objective_score / objective_total / subjective_score / subjective_total
从整数改成浮点，原来的整数分原样保留。

Revision ID: 0033
Revises: 0032
"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

COLS = ("score", "objective_score", "objective_total", "subjective_score", "subjective_total")


def upgrade() -> None:
    with op.batch_alter_table("exam_submissions") as t:
        for c in COLS:
            t.alter_column(c, existing_type=sa.Integer(), type_=sa.Float(),
                           existing_nullable=False, existing_server_default="0")


def downgrade() -> None:
    with op.batch_alter_table("exam_submissions") as t:
        for c in COLS:
            t.alter_column(c, existing_type=sa.Float(), type_=sa.Integer(),
                           existing_nullable=False, existing_server_default="0")
