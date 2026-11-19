"""feedbacks 加置顶：pinned_at、pinned_until（教师端每个页面顶上的黄条只显示置顶的反馈）

Revision ID: 0026
Revises: 0025
"""

import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    cols = {c["name"] for c in sa.inspect(op.get_bind()).get_columns("feedbacks")}
    with op.batch_alter_table("feedbacks") as t:
        if "pinned_at" not in cols:
            t.add_column(sa.Column("pinned_at", sa.DateTime(), nullable=True))
        if "pinned_until" not in cols:
            t.add_column(sa.Column("pinned_until", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("feedbacks") as t:
        t.drop_column("pinned_until")
        t.drop_column("pinned_at")
