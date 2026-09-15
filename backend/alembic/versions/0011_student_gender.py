"""学生增加性别

名单模板多一列「性别」，放在最后。选填：老师的名单里没有这一列，
或者某一行没填，都照常建账号，只是这个字段留空。

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # server_default=""：已有的学生没有性别，给空串而不是 NULL，
    # 这样前端不用到处判 null，导出的 Excel 里也是空单元格而不是 "None"
    op.add_column(
        "students",
        sa.Column("gender", sa.String(8), nullable=False, server_default=""),
    )


def downgrade() -> None:
    with op.batch_alter_table("students") as batch:
        batch.drop_column("gender")
