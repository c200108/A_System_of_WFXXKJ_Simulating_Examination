"""考试加「允许提前交卷」开关

打开后这场考试不受交卷门槛（考试时间过三分之二、答完三分之二的题）限制，随时能交。
默认关，老考试行为不变。

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    if "early_submit" in {c["name"] for c in insp.get_columns("exams")}:
        return
    with op.batch_alter_table("exams") as batch:
        batch.add_column(sa.Column("early_submit", sa.Boolean(), nullable=False,
                                   server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("exams") as batch:
        batch.drop_column("early_submit")
