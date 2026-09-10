"""教师个人资料字段、反馈回复表与点赞表

原来一条反馈只有一个 reply 字段，谁回复就把前一个人的话覆盖掉。
改成独立的回复表，多位老师各回各的；旧数据搬进新表，不丢。

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---- 教师个人资料 ----
    op.add_column("users", sa.Column("grade_class", sa.String(128), nullable=False, server_default=""))
    op.add_column("users", sa.Column("contact", sa.String(64), nullable=False, server_default=""))

    # ---- 反馈回复 ----
    op.create_table(
        "feedback_replies",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("feedback_id", sa.Integer, sa.ForeignKey("feedbacks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("author", sa.String(64), nullable=False, server_default=""),
        sa.Column("is_admin", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index("ix_feedback_replies_feedback_id", "feedback_replies", ["feedback_id"])

    # 旧的单条答复搬过来，署名写「管理员」—— 当初就只有管理端能答复
    op.execute(
        """
        INSERT INTO feedback_replies (feedback_id, user_id, author, is_admin, content, created_at)
        SELECT id, NULL, '管理员', 1, reply,
               COALESCE(replied_at, created_at)
        FROM feedbacks
        WHERE reply IS NOT NULL AND reply <> ''
        """
    )
    op.drop_column("feedbacks", "reply")
    op.drop_column("feedbacks", "replied_at")

    # ---- 点赞 ----
    op.create_table(
        "feedback_likes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("feedback_id", sa.Integer, sa.ForeignKey("feedbacks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("feedback_id", "user_id", name="uq_feedback_like"),
    )
    op.create_index("ix_feedback_likes_feedback_id", "feedback_likes", ["feedback_id"])
    op.create_index("ix_feedback_likes_user_id", "feedback_likes", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_likes_user_id", table_name="feedback_likes")
    op.drop_index("ix_feedback_likes_feedback_id", table_name="feedback_likes")
    op.drop_table("feedback_likes")

    op.add_column("feedbacks", sa.Column("reply", sa.Text, nullable=True))
    op.add_column("feedbacks", sa.Column("replied_at", sa.DateTime, nullable=True))
    # 回滚只能保留最早的一条回复，多出来的会丢——这是拆表不可逆的部分。
    # 不要给被 UPDATE 的表起别名：SQLite 不认 `UPDATE t alias SET ...`。
    op.execute(
        """
        UPDATE feedbacks
        SET reply = (
                SELECT r.content FROM feedback_replies r
                WHERE r.feedback_id = feedbacks.id ORDER BY r.id LIMIT 1
            ),
            replied_at = (
                SELECT r.created_at FROM feedback_replies r
                WHERE r.feedback_id = feedbacks.id ORDER BY r.id LIMIT 1
            )
        """
    )
    op.drop_index("ix_feedback_replies_feedback_id", table_name="feedback_replies")
    op.drop_table("feedback_replies")

    op.drop_column("users", "contact")
    op.drop_column("users", "grade_class")
