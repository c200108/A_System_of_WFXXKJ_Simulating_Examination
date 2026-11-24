"""签到按机器号自动认座（2.26.0）：seat_bindings 绑座表；checkin_entries 加 how / host；
client_online 加学生端报的电脑名 host、内网 IP lan_ip

Revision ID: 0029
Revises: 0028
"""

import sqlalchemy as sa
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def _add(table: str, *columns: sa.Column) -> None:
    have = {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}
    todo = [c for c in columns if c.name not in have]
    if todo:
        with op.batch_alter_table(table) as t:
            for c in todo:
                t.add_column(c)


def upgrade() -> None:
    if "seat_bindings" not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            "seat_bindings",
            sa.Column("device", sa.String(80), primary_key=True),
            sa.Column("seat", sa.String(16), nullable=False),
            sa.Column("host", sa.String(64), nullable=False, server_default=""),
            sa.Column("lan_ip", sa.String(64), nullable=False, server_default=""),
            sa.Column("bound_by", sa.String(64), nullable=False, server_default=""),
            sa.Column("at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("ix_seat_bindings_seat", "seat_bindings", ["seat"])
    _add("checkin_entries",
         sa.Column("how", sa.String(8), nullable=False, server_default="pick"),
         sa.Column("host", sa.String(64), nullable=False, server_default=""))
    _add("client_online",
         sa.Column("host", sa.String(64), nullable=False, server_default=""),
         sa.Column("lan_ip", sa.String(64), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("client_online") as t:
        t.drop_column("lan_ip")
        t.drop_column("host")
    with op.batch_alter_table("checkin_entries") as t:
        t.drop_column("host")
        t.drop_column("how")
    op.drop_table("seat_bindings")
