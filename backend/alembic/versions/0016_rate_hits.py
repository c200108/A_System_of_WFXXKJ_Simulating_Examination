"""rate_hits：打字交成绩、换文本的限频计数（按「这台电脑」算）

后端开了好几个工作进程，计数放内存里各算各的等于没限，所以落库。
只留最近一小时，不跟着数据导出导入。见 app/services/throttle.py。

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "rate_hits",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("who", sa.String(80), nullable=False),
        sa.Column("at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_rate_hits_lookup", "rate_hits", ["action", "who", "at"])


def downgrade() -> None:
    op.drop_index("ix_rate_hits_lookup", table_name="rate_hits")
    op.drop_table("rate_hits")
