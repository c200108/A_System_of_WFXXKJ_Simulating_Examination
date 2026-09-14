"""题目难度、卷面大题与分值、主观题人工赋分

三件事：
1. questions 增加 difficulty（1~5）。历史题目没有难度，按题型／题干长度／
   知识范围自动估一个初值（和导入、新增题目用的是同一个函数），
   老师在题库页面随时改。
2. paper_items 增加 section（归属大题）和 score（这道题值几分）。
   老卷子这两列是空／0，判分时会自动退回按正确率折百分制的老算法。
3. exam_submissions 拆出客观／主观两段分和人工赋分记录。历史答卷把原来的
   score 当作客观题得分填进去，**不改动任何一条历史成绩**。

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 1. 题目难度 ----------
    op.add_column(
        "questions",
        sa.Column("difficulty", sa.Integer, nullable=False, server_default="3"),
    )
    op.create_index("ix_questions_difficulty", "questions", ["difficulty"])
    _estimate_difficulty()

    # ---------- 2. 卷面大题与分值 ----------
    op.add_column(
        "paper_items",
        sa.Column("section", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "paper_items", sa.Column("score", sa.Integer, nullable=False, server_default="0")
    )

    # ---------- 3. 主客观分 ----------
    for name in ("objective_score", "objective_total", "subjective_score", "subjective_total"):
        op.add_column(
            "exam_submissions",
            sa.Column(name, sa.Integer, nullable=False, server_default="0"),
        )
    op.add_column("exam_submissions", sa.Column("manual_json", sa.Text, nullable=True))
    op.add_column("exam_submissions", sa.Column("graded_by", sa.Integer, nullable=True))
    op.add_column("exam_submissions", sa.Column("graded_at", sa.DateTime, nullable=True))
    op.execute("UPDATE exam_submissions SET manual_json = '{}' WHERE manual_json IS NULL")
    # 老答卷的 score 是百分制正确率，整段算作客观题得分；主观题那两列留 0，
    # 界面上会照旧显示百分制，不会凭空多出一个"待阅"的红点
    op.execute("UPDATE exam_submissions SET objective_score = score")

    with op.batch_alter_table("exam_submissions") as batch:
        batch.create_foreign_key(
            "fk_submission_grader", "users", ["graded_by"], ["id"], ondelete="SET NULL"
        )


def _estimate_difficulty() -> None:
    """给历史题目估难度。

    直接调 services.difficulty，保证和导入、界面新增走同一套规则 ——
    在迁移里复制一份规则的话，两边迟早会不一样。
    """
    from app.services.difficulty import estimate

    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, type, stem, scope FROM questions")
    ).fetchall()
    if not rows:
        return

    counts = conn.execute(
        sa.text("SELECT question_id, COUNT(*) FROM options GROUP BY question_id")
    ).fetchall()
    opt_count = {qid: n for qid, n in counts}

    # 按难度值分组更新，几百道题只发五条 UPDATE
    buckets: dict[int, list[int]] = {}
    for qid, qtype, stem, scope in rows:
        d = estimate(qtype or "", stem or "", scope or "", opt_count.get(qid, 0))
        buckets.setdefault(d, []).append(qid)

    for level, ids in buckets.items():
        for chunk in (ids[i : i + 500] for i in range(0, len(ids), 500)):
            conn.execute(
                sa.text("UPDATE questions SET difficulty = :d WHERE id IN :ids").bindparams(
                    sa.bindparam("ids", expanding=True)
                ),
                {"d": level, "ids": chunk},
            )


def downgrade() -> None:
    with op.batch_alter_table("exam_submissions") as batch:
        batch.drop_constraint("fk_submission_grader", type_="foreignkey")
        batch.drop_column("graded_at")
        batch.drop_column("graded_by")
        batch.drop_column("manual_json")
        batch.drop_column("subjective_total")
        batch.drop_column("subjective_score")
        batch.drop_column("objective_total")
        batch.drop_column("objective_score")

    with op.batch_alter_table("paper_items") as batch:
        batch.drop_column("score")
        batch.drop_column("section")

    with op.batch_alter_table("questions") as batch:
        batch.drop_index("ix_questions_difficulty")
        batch.drop_column("difficulty")
