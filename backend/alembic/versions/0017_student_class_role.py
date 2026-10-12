"""学生增加「班干部」一列

- class_role：班长 / 组长 / 空。

（这一版起草时还加过一列 pinyin 给拼音登录用，后来改回中文姓名登录，拼音整个去掉了。
已经跑过那一版 0017 的库，由 0018 把 pinyin 列删掉。）

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "students",
        sa.Column("class_role", sa.String(8), nullable=False, server_default=""),
    )


def downgrade() -> None:
    with op.batch_alter_table("students") as batch:
        batch.drop_column("class_role")
