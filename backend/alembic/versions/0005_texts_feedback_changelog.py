"""打字文本库、需求反馈、更新日志

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------- 打字练习文本 ----------
    op.create_table(
        "typing_texts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("difficulty", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="自定义"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_hash", name="uq_typing_texts_hash"),
    )
    op.create_index("ix_typing_texts_mode", "typing_texts", ["mode"])
    op.create_index("ix_typing_texts_difficulty", "typing_texts", ["difficulty"])
    op.create_index("ix_typing_texts_is_active", "typing_texts", ["is_active"])
    op.create_index("ix_typing_texts_pick", "typing_texts", ["mode", "difficulty", "is_active"])

    # ---------- 需求反馈 ----------
    op.create_table(
        "feedbacks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("author", sa.String(length=64), nullable=False),
        sa.Column("contact", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("category", sa.String(length=16), nullable=False, server_default="建议"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reply", sa.Text(), nullable=False),
        sa.Column("replied_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feedbacks_category", "feedbacks", ["category"])
    op.create_index("ix_feedbacks_is_public", "feedbacks", ["is_public"])
    op.create_index("ix_feedbacks_created_at", "feedbacks", ["created_at"])

    # ---------- 更新日志 ----------
    op.create_table(
        "changelog_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("released_on", sa.Date(), nullable=False),
        sa.Column("change_type", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_changelog_entries_version", "changelog_entries", ["version"])
    op.create_index("ix_changelog_entries_released_on", "changelog_entries", ["released_on"])
    op.create_index("ix_changelog_entries_change_type", "changelog_entries", ["change_type"])
    op.create_index("ix_changelog_version", "changelog_entries", ["version", "sort_order"])


def downgrade() -> None:
    op.drop_table("changelog_entries")
    op.drop_table("feedbacks")
    op.drop_table("typing_texts")
