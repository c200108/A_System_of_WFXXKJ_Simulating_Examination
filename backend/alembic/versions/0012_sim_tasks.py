"""仿真操作题

操作题原来只能老师一份份看着给分。新增一张 sim_tasks 表存「仿真任务」：
初始环境（学生打开时看到什么）+ 检查点（每小问一条断言和一档分）。
题目挂上 sim_task_id 之后，学生在网页里把操作做完，服务端按检查点判分。

机器判出来的分只是预填进 manual_json，老师在成绩页仍然能改 —— 所以这张表
加进来不影响任何既有成绩，没挂仿真任务的操作题照旧走人工评阅。

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sim_tasks",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        # win / wps / html
        sa.Column("kind", sa.String(16), nullable=False, index=True),
        sa.Column("title", sa.String(128), nullable=False, server_default=""),
        # 初始环境。学生那边只拿得到这一份
        sa.Column("env_json", sa.Text, nullable=False),
        # 检查点。**等同于答案，永远不发给学生**
        sa.Column("checks_json", sa.Text, nullable=False),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    # 一道操作题挂一个仿真任务。删任务时题目还在，只是退回人工评阅，
    # 所以是 SET NULL 而不是级联删题。
    # 走 batch 模式：SQLite 不支持给已有表 ALTER 加外键（测试库是 SQLite），
    # batch 会复制重建一张表绕过去；MySQL 上就是普通的 ALTER。
    with op.batch_alter_table("questions") as batch:
        batch.add_column(sa.Column("sim_task_id", sa.Integer, nullable=True))
        batch.create_foreign_key(
            "fk_question_sim_task", "sim_tasks", ["sim_task_id"], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    with op.batch_alter_table("questions") as batch:
        batch.drop_column("sim_task_id")
    op.drop_table("sim_tasks")
