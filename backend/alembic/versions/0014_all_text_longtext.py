"""其余 TEXT 列也改成 LONGTEXT —— 机房版的数据导进来不会撞 64 KB

机房版（Win7，SQLite）和服务器（MySQL）要能互相导数据。SQLite 的 TEXT 没有长度
上限，MySQL 的 TEXT 只有 65535 **字节**（中文一个字 3 字节，两万来字就满）。
机房里建的题目、仿真任务、导入记录只要有一条超了，导进服务器就是 1406
「Data too long」—— 而且整个导入是一个事务，一条超了整批回滚，一行都进不去。

0013 已经把答卷那两列改了，这里把剩下的全部改掉，两边容量一致。
LONGTEXT 和 TEXT 对短内容的存储、查询没有区别。

**只动 MySQL**：SQLite 上本来就没有上限，ALTER 反而要重建表。
每一列原来能不能为空照原样保留（manual_json、images 两列是可空的）。

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

# (表, 列, 可不可以为空) —— 可空性照 MySQL 上现在的样子，改类型时不能顺手改掉它
COLUMNS = (
    ("questions", "stem", False),
    ("questions", "answer", False),
    ("options", "content", False),
    ("papers", "config_json", False),
    ("paper_items", "snapshot_json", False),
    ("exam_submissions", "manual_json", True),
    ("import_logs", "detail_json", False),
    ("typing_texts", "content", False),
    ("feedbacks", "content", False),
    ("feedbacks", "images", True),
    ("feedback_replies", "content", False),
    ("changelog_entries", "content", False),
    ("sim_tasks", "env_json", False),
    ("sim_tasks", "checks_json", False),
)


def upgrade() -> None:
    if op.get_bind().dialect.name != "mysql":
        return
    for table, name, nullable in COLUMNS:
        op.alter_column(table, name, existing_type=sa.Text(), type_=LONGTEXT(),
                        existing_nullable=nullable)


def downgrade() -> None:
    """退回 TEXT。**超过 65535 字节的内容会在这一步报错或被截断**，
    所以降级前先确认没有大内容，或者先用 data-export.sh 导一份。"""
    if op.get_bind().dialect.name != "mysql":
        return
    for table, name, nullable in COLUMNS:
        op.alter_column(table, name, existing_type=LONGTEXT(), type_=sa.Text(),
                        existing_nullable=nullable)
