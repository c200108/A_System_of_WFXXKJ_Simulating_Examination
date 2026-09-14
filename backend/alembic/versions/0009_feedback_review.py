"""反馈增加审核状态和配图

原来提交完立刻公开，不当内容会在首页上挂一段时间才被发现。
改成先审后发：新提交是 pending，管理员审过才进公开区。

已有数据按原来的 is_public 折算：公开的算已通过，下架的算已拒绝 ——
这样管理员打开页面看到的还是原来那份内容，不会突然全部变成待审。

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("feedbacks", sa.Column("images", sa.Text, nullable=True))
    op.add_column(
        "feedbacks",
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
    )
    op.add_column("feedbacks", sa.Column("reviewed_by", sa.Integer, nullable=True))
    op.add_column("feedbacks", sa.Column("reviewed_at", sa.DateTime, nullable=True))
    op.add_column(
        "feedbacks",
        sa.Column("review_note", sa.String(255), nullable=False, server_default=""),
    )
    op.create_index("ix_feedbacks_status", "feedbacks", ["status"])

    # images 是 JSON 数组，历史行给个空数组，前端不用判 null
    op.execute("UPDATE feedbacks SET images = '[]' WHERE images IS NULL")

    # 老数据折算：在架的当作审核通过，下架的当作已拒绝
    op.execute("UPDATE feedbacks SET status = 'approved' WHERE is_public = 1")
    op.execute("UPDATE feedbacks SET status = 'rejected' WHERE is_public = 0")

    with op.batch_alter_table("feedbacks") as batch:
        batch.create_foreign_key(
            "fk_feedback_reviewer", "users", ["reviewed_by"], ["id"], ondelete="SET NULL"
        )
        batch.drop_index("ix_feedbacks_is_public")
        batch.drop_column("is_public")


def downgrade() -> None:
    op.add_column(
        "feedbacks",
        sa.Column("is_public", sa.Boolean, nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_feedbacks_is_public", "feedbacks", ["is_public"])
    # 只有"已通过"折回在架，待审核的按下架处理 —— 回滚后它们不该直接露出来
    op.execute("UPDATE feedbacks SET is_public = 0 WHERE status <> 'approved'")

    with op.batch_alter_table("feedbacks") as batch:
        batch.drop_constraint("fk_feedback_reviewer", type_="foreignkey")
        batch.drop_index("ix_feedbacks_status")
        batch.drop_column("review_note")
        batch.drop_column("reviewed_at")
        batch.drop_column("reviewed_by")
        batch.drop_column("status")
        batch.drop_column("images")
