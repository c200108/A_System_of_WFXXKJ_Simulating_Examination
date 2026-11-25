"""学生端：凭链接里的 token 取卷、交卷。**不需要登录**。

这一整个文件都不引用任何鉴权依赖，也不返回任何答案字段：
取卷走 strip_answers()，判分在服务端做，答案永远不出后端。
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Exam, ExamSubmission, SchoolClass, Student
from ..schemas import SubmitIn, SubmitOut, TakePaperOut
from ..services import throttle
from ..services.paper import num, show
from ..services.exam import (
    exam_duration,
    grade,
    group_items,
    load_draw_items,
    load_items,
    strip_answers,
    submission_scores,
    wants_shuffle,
)
from ..services.exam_rules import check_submit, find_draw, items_for, make_draw, rank_of

# 防爆破（2.28.0）：免登录的接口按 IP 限次。
# 取卷：一分钟 30 次（每次都可能重抽一套题、写一行库）；姓名核对不上：10 分钟 20 次（防挨个试名字）
TAKE_PER_MIN = 30
ROSTER_FAILS = 20
ROSTER_WINDOW = 600

router = APIRouter(prefix="/api/take", tags=["学生答题"])


def _submit_out(exam, result: dict, sub=None) -> SubmitOut:
    """交卷后给学生看什么。

    操作题要老师看，所以这里先报客观题那一段，并说清还有几分等着评阅 ——
    不说的话学生会以为自己只考了七十分。老师批完，分数在「我的考试」里自动更新。
    """
    out = SubmitOut(submitted=True, message="交卷成功")
    if not exam.show_score:
        out.message = "交卷成功，成绩由老师统一公布"
        if exam.show_answer:
            out.detail = result["detail"]
        return out

    out.score = result["score"]
    if sub is not None:
        # 这份成绩在全部交卷同学里排第几（每人取最高分）
        out.rank, out.rank_total = rank_of(exam, sub)
    out.right_count = result["right_count"]
    out.objective_count = result["objective_count"]
    out.objective_score = result["objective_score"]
    out.objective_total = result["objective_total"]
    out.subjective_total = result["subjective_total"]
    out.full_score = result["full_score"]
    out.pending_manual = result["pending_manual"]
    if result["pending_manual"]:
        out.message = (
            f"交卷成功。客观题 {result['objective_score']} 分已经算好，"
            f"还有 {result['subjective_total']} 分的操作题要老师评阅，"
            "批完后在「我的考试」里就能看到总分。"
        )
    if exam.show_answer:
        out.detail = result["detail"]
    return out


def _open_exam(db: Session, token: str) -> Exam:
    exam = db.scalar(select(Exam).where(Exam.token == token))
    if not exam:
        raise HTTPException(status_code=404, detail="链接无效，请向老师确认")
    if not exam.is_open:
        raise HTTPException(status_code=403, detail="这场考试已经关闭")
    return exam


@router.get("/{token}/live", summary="考试中途改了的设置（学生端每 60 秒问一次）")
def take_live(token: str, db: Session = Depends(get_db)):
    """老师在考试**进行中**改的开关，答题页拿不到 —— 取卷那一刻读过一次就不再问了。
    这里只回那几个会中途变的、学生端要跟着变的：允许提前交卷、考试是否还开着。
    不含题目和答案，按口令免登录查，和取卷同一个准入。"""
    exam = db.scalar(select(Exam).where(Exam.token == token))
    if not exam:
        raise HTTPException(status_code=404, detail="链接无效，请向老师确认")
    return {"early_submit": bool(exam.early_submit), "is_open": bool(exam.is_open)}


def _exam_classes(db: Session, exam: Exam) -> list[SchoolClass]:
    """这场考试能选的班：有在用学生的班；老师指定了班级的只列那几个。"""
    used = select(Student.class_id).where(Student.is_active.is_(True), Student.class_id.is_not(None))
    rows = list(db.scalars(
        select(SchoolClass).where(SchoolClass.is_active.is_(True), SchoolClass.id.in_(used))
        .order_by(SchoolClass.grade, SchoolClass.sort_order, SchoolClass.name)
    ))
    wanted = [c.strip() for c in (exam.target_classes or "").split(",") if c.strip()]
    if wanted:
        rows = [c for c in rows if c.display in wanted]
    return rows


@router.get("/{token}/classes", summary="答题页的班级下拉（不用登录）")
def take_classes(token: str, db: Session = Depends(get_db)):
    """网页答题（2.27.0）不再让学生随手写班级：从这里选，交卷时按名单核对姓名。
    只给班级 id 和名字，不给名单。"""
    exam = _open_exam(db, token)
    return [{"id": c.id, "display": c.display} for c in _exam_classes(db, exam)]


def _match_roster(db: Session, exam: Exam, body: SubmitIn) -> tuple[Student | None, str, str]:
    """网页答题：选的班 + 填的姓名 → 名单里的那位同学。对不上就交不了卷。

    返回 (学生, 姓名, 班级名)。同一个班里有重名的，挂不到具体账号上，但照样收卷（成绩表里有姓名班级）。
    """
    name = body.student_name.strip()
    cls = db.get(SchoolClass, body.class_id) if body.class_id else None
    if cls is None or cls.id not in {c.id for c in _exam_classes(db, exam)}:
        raise HTTPException(status_code=400, detail="请先选择自己的班级")
    hits = list(db.scalars(select(Student).where(
        Student.class_id == cls.id, Student.name == name, Student.is_active.is_(True))))
    if not hits:
        raise HTTPException(
            status_code=400,
            detail=f"「{cls.display}」的名单里没有「{name}」。请检查班级和姓名有没有选错、写错（姓名要写全名），"
                   "还是不对请询问老师。卷子还在，改好再交。",
        )
    return (hits[0] if len(hits) == 1 else None), name, cls.display


@router.get("/{token}", response_model=TakePaperOut, summary="学生取卷（不含答案）")
def take_paper(token: str, request: Request, draw: str = "", db: Session = Depends(get_db)):
    """开了乱序的卷子：每次取卷重抽一套（按题型卷）/ 答题页重新打乱（六大题卷），刷新就换。
    带着临时保存时记下的 draw 来取，给回同一套 —— 临时保存后刷新，题目和作答都不变。"""
    exam = _open_exam(db, token)
    who = throttle.ip_of(request)
    throttle.check(db, "take_paper", f"{exam.id}:{who}", TAKE_PER_MIN, 60, "刷新太频繁了")
    # 带了 draw 且还在：同一套；没带、或记下的那份过期清掉了：重新抽一套
    got = find_draw(db, exam, draw) or make_draw(db, exam)
    if got is not None:
        items = load_draw_items(db, exam, json.loads(got.items_json or "[]"))
    else:
        items = load_items(db, exam.paper)
    throttle.hit(db, "take_paper", f"{exam.id}:{who}")
    db.commit()
    groups = strip_answers(group_items(items))
    return TakePaperOut(
        title=exam.title,
        school=exam.paper.school,
        duration=exam_duration(exam),
        code=exam.paper.code,
        total=len(items),
        full_score=show(sum(num(it.get("score")) for it in items)),
        early_submit=bool(exam.early_submit),
        shuffle=wants_shuffle(exam.paper),
        draw=got.key if got is not None else "",
        groups=groups,
    )


@router.post("/{token}/submit", response_model=SubmitOut, summary="学生交卷，后端判分")
def submit(token: str, body: SubmitIn, request: Request, db: Session = Depends(get_db)):
    exam = _open_exam(db, token)
    ip = throttle.ip_of(request)

    if not body.student_name.strip():
        raise HTTPException(status_code=400, detail="请先填写姓名")

    no = body.student_no.strip()
    # 学生端 exe 是账号登录后交卷，带着学号 —— 照旧按学号认人（下面那段）。
    # 网页答题页（2.27.0）不带学号：必须选班级，姓名要在这个班的名单里，不然交不上。
    # 都没有（老页面、手搓的请求）不收，免得名字乱写也能交上
    roster_hit = None
    if not no:
        if body.class_id is None:
            raise HTTPException(status_code=400, detail="请先选择班级、填写姓名再交卷")
        # 挨个试名字的：核对不上的次数按 IP 限住
        throttle.check(db, "take_roster", f"{exam.id}:{ip}", ROSTER_FAILS, ROSTER_WINDOW,
                       "姓名核对失败次数太多，请找老师确认班级和姓名")
        try:
            roster_hit, name, cls_name = _match_roster(db, exam, body)
        except HTTPException:
            throttle.hit(db, "take_roster", f"{exam.id}:{ip}")
            db.commit()
            raise
        body.student_name, body.student_class = name, cls_name

    # 重考次数、交卷频率（老师在考试设置里定）。超了不收，答题页原样留着
    if roster_hit is not None:
        check_submit(db, exam, student_id=roster_hit.id)
    elif no:
        check_submit(db, exam, student_no=no)
    else:
        check_submit(db, exam, name=body.student_name.strip(), cls=body.student_class.strip())

    # 答的是哪一套：重抽过的按那一套判，没有就是原卷
    items, draw_key = items_for(db, exam, body.draw)
    result = grade(items, body.answers)

    # **认领到学生账号上。** 这个接口是免登录的（网页链接、机房 exe 都走它），
    # 但交上来的学号如果在名单里，就把这份卷子挂到那个账号名下 —— 否则学生在
    # 自己的「我的考试」里看不到自己刚交的卷：列表还显示「开始考试」，回看也
    # 说"你还没交过这场考试"。挂不上（校外链接、学号写错）就照旧留空，
    # 成绩表里仍然有学号姓名，老师照样看得见。
    mine = db.scalar(select(Student).where(Student.student_no == no)) if no else roster_hit

    sub = ExamSubmission(
        exam_id=exam.id,
        student_id=mine.id if mine else None,
        student_name=body.student_name.strip(),
        student_class=body.student_class.strip(),
        student_no=no or (roster_hit.student_no if roster_hit else ""),
        answers_json=json.dumps(body.answers, ensure_ascii=False),
        detail_json=json.dumps(result["detail"], ensure_ascii=False),
        draw_key=draw_key,
        **submission_scores(result),
    )
    db.add(sub)
    db.commit()
    db.refresh(exam)

    return _submit_out(exam, result, sub)
