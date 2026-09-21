"""答卷的两列 JSON 改成 LONGTEXT

学生在机房交卷，服务器回 500，界面上是「答卷已存到本机，但没能上传」。

原因：一道 win 操作题交上来的终态是**整个考试文件夹的快照**，一场考试里
win 题有好几道，每道都带一份；detail_json 里还要把学生的作答回抄一遍。
实测 93 个对象的考场 + 11 道操作题 → answers_json 90 KB、detail_json 108 KB，
而 **MySQL 的 TEXT 上限是 65535 字节**，超了报 1406「Data too long」。

SQLite 的 TEXT 没有长度上限，所以开发机和测试全绿 —— 这件事只在正式库上发生，
而且发生在学生点「交卷」的那一刻。两列都改成 LONGTEXT（4 GB）。

**只动 MySQL**：SQLite 上这两列本来就没有上限，ALTER 反而要重建表。

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

COLUMNS = ("answers_json", "detail_json")


def upgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    for name in COLUMNS:
        op.alter_column("exam_submissions", name,
                        existing_type=sa.Text(), type_=LONGTEXT(),
                        existing_nullable=False)


def downgrade() -> None:
    """退回 TEXT。**超过 65535 字节的答卷会在这一步被 MySQL 截断**，
    所以降级前先确认没有大答卷，或者先把它们导出来。"""
    if op.get_bind().dialect.name != "mysql":
        return
    for name in COLUMNS:
        op.alter_column("exam_submissions", name,
                        existing_type=LONGTEXT(), type_=sa.Text(),
                        existing_nullable=False)
