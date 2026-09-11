"""班级表、教师删除权限，以及学生与班级的关联

班级原来只是一串手打的文字，"七(3)班"和"七3班"会变成两个班。
改成一张表之后老师和学生都从下拉里选，并且班级能归属到某位老师。

已有学生的 student_class 会按文字自动建班并挂上去，不用手工补数据。

Revision ID: 0008
Revises: 0007
"""

import re

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

# 从"七年级1班""七(3)班""8年级二班"里把年级和班号拆出来
GRADE_RE = re.compile(r"^\s*([一二三四五六七八九十\d]+\s*年级|[一二三四五六七八九十\d]+)\s*(.*)$")


def _split(display: str) -> tuple[str, str]:
    """把班级全名拆成（年级, 班名）。拆不动就整个当班名，年级留空。"""
    text = (display or "").strip()
    if not text:
        return "", ""
    m = GRADE_RE.match(text)
    if not m:
        return "", text[:32]
    grade, rest = m.group(1).strip(), m.group(2).strip()
    if not grade.endswith("年级"):
        grade += "年级"
    # 去掉包在外面的括号：七(3)班 → 3班
    rest = rest.strip("()（）").strip() or "未命名"
    return grade[:16], rest[:32]


def upgrade() -> None:
    op.create_table(
        "classes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("grade", sa.String(16), nullable=False),
        sa.Column("name", sa.String(32), nullable=False),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("grade", "name", name="uq_class_grade_name"),
    )
    op.create_index("ix_classes_grade", "classes", ["grade"])
    op.create_index("ix_classes_owner_id", "classes", ["owner_id"])
    op.create_index("ix_classes_is_active", "classes", ["is_active"])

    op.add_column(
        "users",
        sa.Column("can_delete", sa.Boolean, nullable=False, server_default=sa.text("0")),
    )

    with op.batch_alter_table("students") as batch:
        batch.add_column(sa.Column("class_id", sa.Integer, nullable=True))
        batch.create_foreign_key(
            "fk_student_class", "classes", ["class_id"], ["id"], ondelete="SET NULL"
        )
    op.create_index("ix_students_class_id", "students", ["class_id"])

    # ---- 把已有学生的班级文字变成真正的班 ----
    conn = op.get_bind()
    names = [
        r[0]
        for r in conn.execute(
            sa.text("SELECT DISTINCT student_class FROM students WHERE student_class <> ''")
        )
    ]
    for i, display in enumerate(sorted(names)):
        grade, name = _split(display)
        if not name:
            continue
        # 同一个年级班号可能由不同写法映射过来，建过就不重复建
        existing = conn.execute(
            sa.text("SELECT id FROM classes WHERE grade = :g AND name = :n"),
            {"g": grade, "n": name},
        ).first()
        if existing:
            cid = existing[0]
        else:
            conn.execute(
                sa.text(
                    "INSERT INTO classes (grade, name, is_active, sort_order) "
                    "VALUES (:g, :n, 1, :o)"
                ),
                {"g": grade, "n": name, "o": i},
            )
            cid = conn.execute(
                sa.text("SELECT id FROM classes WHERE grade = :g AND name = :n"),
                {"g": grade, "n": name},
            ).scalar()

        conn.execute(
            sa.text("UPDATE students SET class_id = :cid WHERE student_class = :d"),
            {"cid": cid, "d": display},
        )


def downgrade() -> None:
    op.drop_index("ix_students_class_id", table_name="students")
    with op.batch_alter_table("students") as batch:
        batch.drop_constraint("fk_student_class", type_="foreignkey")
        batch.drop_column("class_id")

    op.drop_column("users", "can_delete")

    op.drop_index("ix_classes_is_active", table_name="classes")
    op.drop_index("ix_classes_owner_id", table_name="classes")
    op.drop_index("ix_classes_grade", table_name="classes")
    op.drop_table("classes")
