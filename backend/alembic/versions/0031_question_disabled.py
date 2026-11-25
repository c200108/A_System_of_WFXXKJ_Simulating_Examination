"""题库「停用」（2.27.0）：questions.is_disabled。停用的题还在题库里、能再启用，组卷抽不到它

Revision ID: 0031
Revises: 0030
"""

import sqlalchemy as sa
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("questions")}
    if "is_disabled" not in cols:
        with op.batch_alter_table("questions") as t:
            t.add_column(sa.Column("is_disabled", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("questions") as t:
        t.drop_column("is_disabled")
