"""教师端「API」板块：收第三方教学网页的数据（2.16.0）

- data_apis：老师建的接收接口（名称、描述、公开编号、写入/读取密钥、接收设置）
- data_records：收到的每条数据（原始 JSON + 拆出来的学生、活动、得分、来源网页）
- data_record_items：逐题作答和评价维度，按题、按维度统计用

Revision ID: 0022
Revises: 0021
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None

LONG = sa.Text().with_variant(LONGTEXT, "mysql")


def upgrade() -> None:
    names = set(sa.inspect(op.get_bind()).get_table_names())
    if "data_apis" not in names:
        op.create_table(
            "data_apis",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("description", LONG, nullable=False),
            sa.Column("template", sa.String(16), nullable=False),
            sa.Column("key", sa.String(24), nullable=False),
            sa.Column("write_token", sa.String(64), nullable=False),
            sa.Column("read_token", sa.String(64), nullable=False, server_default=""),
            sa.Column("status", sa.String(8), nullable=False),
            sa.Column("accept_from", sa.DateTime(), nullable=True),
            sa.Column("accept_until", sa.DateTime(), nullable=True),
            sa.Column("allowed_origins", sa.String(1000), nullable=False, server_default=""),
            sa.Column("dedupe", sa.String(8), nullable=False),
            sa.Column("allow_get", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("public_summary", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("class_ids", sa.String(255), nullable=False, server_default=""),
            sa.Column("field_meta", LONG, nullable=False),
            sa.Column("record_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_received_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_data_apis_owner_id", "data_apis", ["owner_id"])
        op.create_index("ix_data_apis_key", "data_apis", ["key"], unique=True)
    if "data_records" not in names:
        op.create_table(
            "data_records",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("api_id", sa.Integer(), sa.ForeignKey("data_apis.id", ondelete="CASCADE"), nullable=False),
            sa.Column("client_id", sa.String(64), nullable=True),
            sa.Column("type", sa.String(32), nullable=False),
            sa.Column("activity_id", sa.String(64), nullable=False),
            sa.Column("activity_name", sa.String(128), nullable=False),
            sa.Column("page", sa.String(255), nullable=False),
            sa.Column("student_no", sa.String(64), nullable=False),
            sa.Column("student_name", sa.String(64), nullable=False),
            sa.Column("class_name", sa.String(64), nullable=False),
            sa.Column("student_id", sa.Integer(), sa.ForeignKey("students.id", ondelete="SET NULL"), nullable=True),
            sa.Column("target_no", sa.String(64), nullable=False),
            sa.Column("target_name", sa.String(64), nullable=False),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("max_score", sa.Float(), nullable=True),
            sa.Column("comment", LONG, nullable=False),
            sa.Column("payload", LONG, nullable=False),
            sa.Column("source_ip", sa.String(64), nullable=False),
            sa.Column("device_id", sa.String(80), nullable=False),
            sa.Column("origin", sa.String(255), nullable=False),
            sa.Column("user_agent", sa.String(255), nullable=False),
            sa.Column("flag", sa.String(8), nullable=False),
            sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("submitted_at", sa.DateTime(), nullable=True),
            sa.Column("received_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("api_id", "client_id", name="uq_data_records_client"),
        )
        op.create_index("ix_data_records_api_id", "data_records", ["api_id"])
        op.create_index("ix_data_records_api_time", "data_records", ["api_id", "received_at"])
        op.create_index("ix_data_records_type", "data_records", ["type"])
        op.create_index("ix_data_records_page", "data_records", ["page"])
        op.create_index("ix_data_records_student_no", "data_records", ["student_no"])
        op.create_index("ix_data_records_student_id", "data_records", ["student_id"])
    if "data_record_items" not in names:
        op.create_table(
            "data_record_items",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("record_id", sa.Integer(), sa.ForeignKey("data_records.id", ondelete="CASCADE"), nullable=False),
            sa.Column("api_id", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(8), nullable=False),
            sa.Column("item", sa.String(64), nullable=False),
            sa.Column("answer", sa.String(255), nullable=False),
            sa.Column("correct", sa.Boolean(), nullable=True),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("max_score", sa.Float(), nullable=True),
            sa.Column("time_ms", sa.Integer(), nullable=True),
        )
        op.create_index("ix_data_record_items_record_id", "data_record_items", ["record_id"])
        op.create_index("ix_data_record_items_api_id", "data_record_items", ["api_id"])


def downgrade() -> None:
    op.drop_table("data_record_items")
    op.drop_table("data_records")
    op.drop_table("data_apis")
