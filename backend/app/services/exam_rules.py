"""考试的几条规矩（2.28.0）：每次取卷重抽、重考次数、交卷频率、交卷后的排名。

三个交卷入口（网页链接 /take、学生平台、学生端 exe —— exe 走的也是 /take）共用这里，口径一致。

## 每次取卷重抽（make_draw）

只在**网页链接**、而且试卷开了「选择判断题乱序」时做：
- 按题型组卷的卷子：选择、判断、填空题从原卷同题型、同知识范围（原卷里这种题出现过的范围）的题里
  按原数量重抽，操作题不动；测评卷的范围只有本年级测评题，所以只在本年级里抽。题库不够的位置用原题补。
- 六大题的卷子：每个大题的题有各自的限定（范围、长题干、仿真类别），不重抽，只靠答题页重新打乱顺序。
重抽的这一套记成一份 ExamDraw（key 随机），交卷带着 key 按这一套判分。

## 重考次数、交卷频率（check_submit）

- 不允许重考：一个人只能交 1 次；允许重考：最多 max_attempts 次（0 = 不限）。
- 交卷频率：rate_window 分钟内一个人最多交 rate_max 次（任一为 0 = 不限）。超了回 429，
  说清还要等多久，答题页不刷新、不清空。
「一个人」：学生账号 → 学号 → 班级 + 姓名，按能认出来的最准的那个算。
"""

from __future__ import annotations

import json
import math
import random
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select

from .. import clock
from ..models import Exam, ExamDraw, ExamSubmission
from .exam import load_draw_items, load_items, wants_shuffle

REDRAW_TYPES = ("选择题", "判断题", "填空题")
DRAW_KEEP = timedelta(days=14)


# ---------------------------------------------------------------- 重抽
def make_draw(db, exam: Exam) -> ExamDraw | None:
    """开了乱序的按题型卷子：重抽一套，存下来返回；不该重抽的返回 None。不提交。"""
    from .paper import type_pool

    paper = exam.paper
    if paper is None or not wants_shuffle(paper):
        return None
    conf = json.loads(paper.config_json or "{}")
    if conf.get("by_sections"):
        return None
    base = load_items(db, paper)
    rnd = random.SystemRandom()
    rows = [[it["id"], it.get("section") or it["type"], it.get("score") or 0] for it in base]
    taken = {it["id"] for it in base if it["type"] not in REDRAW_TYPES}
    for qtype in REDRAW_TYPES:
        pos = [i for i, it in enumerate(base) if it["type"] == qtype]
        if not pos:
            continue
        scopes = sorted({base[i]["scope"] for i in pos if base[i].get("scope")})
        pool = [q for q in type_pool(db, qtype, scopes or None, require_answer=True) if q.id not in taken]
        picked = rnd.sample(pool, min(len(pos), len(pool)))
        # 题库不够：缺的位置用原卷的题补（原题没被抽中过的优先）
        rest = [base[i]["id"] for i in pos if base[i]["id"] not in {q.id for q in picked}]
        ids = [q.id for q in picked] + rest[: len(pos) - len(picked)]
        rnd.shuffle(ids)
        for i, qid in zip(pos, ids):
            rows[i][0] = qid
            taken.add(qid)
    draw = ExamDraw(exam_id=exam.id, key=secrets.token_urlsafe(12)[:16], items_json=json.dumps(rows))
    db.add(draw)
    # 顺手清掉两周前、没人交过的老抽卷，表不会越攒越大
    used = select(ExamSubmission.draw_key).where(ExamSubmission.exam_id == exam.id)
    db.execute(delete(ExamDraw).where(ExamDraw.exam_id == exam.id,
                                      ExamDraw.created_at < clock.now() - DRAW_KEEP,
                                      ExamDraw.key.not_in(used)))
    return draw


def find_draw(db, exam: Exam, key: str | None) -> ExamDraw | None:
    key = (key or "").strip()
    if not key:
        return None
    return db.scalar(select(ExamDraw).where(ExamDraw.exam_id == exam.id, ExamDraw.key == key))


def items_for(db, exam: Exam, draw_key: str | None) -> tuple[list[dict], str]:
    """交卷 / 回看用：这份答卷答的是哪一套题。返回 (题目, 认下的 draw key)。"""
    draw = find_draw(db, exam, draw_key)
    if draw is not None:
        return load_draw_items(db, exam, json.loads(draw.items_json or "[]")), draw.key
    return load_items(db, exam.paper), ""


def all_items(db, exam: Exam) -> list[dict]:
    """成绩页、分析、导出用：原卷的题 + 这场考试里交过的各份重抽卷用到的题（按 id 去重）。"""
    out = load_items(db, exam.paper)
    seen = {it["id"] for it in out}
    keys = {s.draw_key for s in exam.submissions if s.draw_key}
    for draw in db.scalars(select(ExamDraw).where(ExamDraw.exam_id == exam.id, ExamDraw.key.in_(keys))) \
            if keys else []:
        for it in load_draw_items(db, exam, json.loads(draw.items_json or "[]")):
            if it["id"] not in seen:
                seen.add(it["id"])
                out.append(it)
    return out


# ---------------------------------------------------------------- 重考次数、交卷频率
def _mine(stmt, *, student_id=None, student_no="", name="", cls=""):
    if student_id:
        return stmt.where(ExamSubmission.student_id == student_id)
    if student_no:
        return stmt.where(ExamSubmission.student_no == student_no)
    return stmt.where(ExamSubmission.student_name == name, ExamSubmission.student_class == cls)


def _span(seconds: int) -> str:
    m, s = divmod(max(1, int(seconds)), 60)
    return (f"{m} 分 {s} 秒" if s else f"{m} 分钟") if m else f"{s} 秒"


def check_submit(db, exam: Exam, *, student_id=None, student_no="", name="", cls="") -> None:
    """交卷前查：交满次数了 409，交得太勤了 429（说清还要等多久）。"""
    base = select(ExamSubmission.submitted_at).where(ExamSubmission.exam_id == exam.id)
    mine = list(db.scalars(_mine(base, student_id=student_id, student_no=student_no,
                                 name=name, cls=cls).order_by(ExamSubmission.submitted_at)))
    limit = 1 if not exam.allow_retake else int(exam.max_attempts or 0)
    if limit and len(mine) >= limit:
        raise HTTPException(
            status_code=409,
            detail=("这场考试你已经交过卷了，如需重考请联系老师" if limit == 1
                    else f"这场考试一个人最多交 {limit} 次，你已经交过卷 {limit} 次了，如需再考请联系老师"),
        )
    window, most = int(exam.rate_window or 0), int(exam.rate_max or 0)
    if window > 0 and most > 0:
        now = clock.now()
        recent = [t for t in mine if t > now - timedelta(minutes=window)]
        if len(recent) >= most:
            wait = math.ceil((recent[-most] + timedelta(minutes=window) - now).total_seconds())
            raise HTTPException(
                status_code=429,
                detail=f"提交次数过多：每 {window} 分钟最多交 {most} 次。请等 {_span(wait)}后再交卷，作答内容都还在。",
                headers={"Retry-After": str(max(1, wait))},
            )


# ---------------------------------------------------------------- 排名
def _who(s: ExamSubmission) -> str:
    if s.student_id:
        return f"id:{s.student_id}"
    if s.student_no:
        return f"no:{s.student_no}"
    return f"nm:{s.student_class}/{s.student_name}"


def rank_of(exam: Exam, sub: ExamSubmission) -> tuple[int, int]:
    """这份答卷的分在全部交卷同学里排第几（每人取最高分）。返回 (名次, 人数)。并列算同一名。"""
    best: dict[str, int] = {}
    for s in exam.submissions:
        k = _who(s)
        best[k] = max(best.get(k, s.score), s.score)
    me = max(best.get(_who(sub), sub.score), sub.score)
    best[_who(sub)] = me
    return 1 + sum(1 for v in best.values() if v > me), len(best)


def people_count(exam: Exam) -> int:
    """交过卷的人数（一个人交几次只算一个）。"""
    return len({_who(s) for s in exam.submissions})
