"""签到：一个同学一次签到最多签两台电脑（2.26.0，电脑坏了换一台再签），去掉 checkin_entries 的
（checkin_id, student_id）唯一约束，人数上限由 services/checkin.py 的 PER_STUDENT 管

Revision ID: 0030
Revises: 0029
"""

import sqlalchemy as sa
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    insp = sa.inspect(op.get_bind())
    names = {u["name"] for u in insp.get_unique_constraints("checkin_entries")}
    if "uq_checkin_student" in names:
        with op.batch_alter_table("checkin_entries") as t:
            t.drop_constraint("uq_checkin_student", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("checkin_entries") as t:
        t.create_unique_constraint("uq_checkin_student", ["checkin_id", "student_id"])
