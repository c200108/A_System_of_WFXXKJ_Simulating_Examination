"""课堂签到（2.24.0）：seat_tabs 在线座次附加工作表、checkins 签到、checkin_entries 签到记录、
client_online 学生桌面端在线心跳

Revision ID: 0027
Revises: 0026
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

BIG = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")


def upgrade() -> None:
    have = set(sa.inspect(op.get_bind()).get_table_names())
    if "seat_tabs" not in have:
        op.create_table(
            "seat_tabs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(32), nullable=False),
            sa.Column("sheet", BIG, nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_seat_tabs_class_id", "seat_tabs", ["class_id"])
    if "checkins" not in have:
        op.create_table(
            "checkins",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("class_id", sa.Integer(), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False),
            sa.Column("tab_id", sa.Integer(), sa.ForeignKey("seat_tabs.id", ondelete="SET NULL"), nullable=True),
            sa.Column("started_by", sa.String(64), nullable=False, server_default=""),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ends_at", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_checkins_class_id", "checkins", ["class_id"])
        op.create_index("ix_checkins_ends_at", "checkins", ["ends_at"])
    if "checkin_entries" not in have:
        op.create_table(
            "checkin_entries",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("checkin_id", sa.Integer(), sa.ForeignKey("checkins.id", ondelete="CASCADE"), nullable=False),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False),
            sa.Column("seat", sa.String(16), nullable=False),
            sa.Column("device", sa.String(80), nullable=False),
            sa.Column("ip", sa.String(64), nullable=False, server_default=""),
            sa.Column("at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("checkin_id", "student_id", name="uq_checkin_student"),
            sa.UniqueConstraint("checkin_id", "seat", name="uq_checkin_seat"),
            sa.UniqueConstraint("checkin_id", "device", name="uq_checkin_device"),
        )
        op.create_index("ix_checkin_entries_checkin_id", "checkin_entries", ["checkin_id"])
    if "client_online" not in have:
        op.create_table(
            "client_online",
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("last_seen", sa.DateTime(), nullable=False),
            sa.Column("device", sa.String(80), nullable=False, server_default=""),
            sa.Column("ip", sa.String(64), nullable=False, server_default=""),
        )
        op.create_index("ix_client_online_last_seen", "client_online", ["last_seen"])


def downgrade() -> None:
    op.drop_table("client_online")
    op.drop_table("checkin_entries")
    op.drop_table("checkins")
    op.drop_table("seat_tabs")
