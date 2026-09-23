"""app_meta：这台机器自己的几项状态（键值对）

第一项是 time_offset_applied：config.yaml 的 time.offset_hours（服务器时钟校正）改了之后，
已有记录的时间要一起挪 —— 挪没挪、挪到了多少，得记在库里，不然每次重启都会再挪一遍。
见 app/clock.py。

不跟着数据导出导入：它说的是这台机器的时钟，不是数据。

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_meta",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(255), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_table("app_meta")
