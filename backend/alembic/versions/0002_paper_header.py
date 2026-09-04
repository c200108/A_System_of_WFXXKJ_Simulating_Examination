"""试卷抬头（学校/时长/卷号）与打乱后的题目快照

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("papers") as batch:
        batch.add_column(sa.Column("school", sa.String(length=128), nullable=False, server_default=""))
        batch.add_column(sa.Column("duration", sa.String(length=16), nullable=False, server_default=""))
        batch.add_column(sa.Column("code", sa.String(length=32), nullable=False, server_default=""))

    with op.batch_alter_table("paper_items") as batch:
        # 不能写 server_default=""：MySQL 禁止 TEXT/BLOB 列带默认值（错误 1101），
        # 而且它的 DDL 不支持回滚，一旦在这里失败，前面几列已经加上、版本号却没推进，
        # 重启后会卡在「Duplicate column name」的死循环里。
        # 默认值由 models.py 的 default="" 在 Python 侧给出，已有行会自动填空串。
        batch.add_column(sa.Column("snapshot_json", sa.Text(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("paper_items") as batch:
        batch.drop_column("snapshot_json")

    with op.batch_alter_table("papers") as batch:
        batch.drop_column("code")
        batch.drop_column("duration")
        batch.drop_column("school")
