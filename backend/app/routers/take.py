"""学生端：凭链接里的 token 取卷、交卷。**不需要登录**。

这一整个文件都不引用任何鉴权依赖，也不返回任何答案字段：
取卷走 strip_answers()，判分在服务端做，答案永远不出后端。
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Exam, ExamSubmission
from ..schemas import SubmitIn, SubmitOut, TakePaperOut
from ..services.exam import (
    grade,
    group_items,
    load_items,
    strip_answers,
    submission_scores,
)

router = APIRouter(prefix="/api/take", tags=["学生答题"])


def _submit_out(exam, result: dict) -> SubmitOut:
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


@router.get("/{token}", response_model=TakePaperOut, summary="学生取卷（不含答案）")
def take_paper(token: str, db: Session = Depends(get_db)):
    exam = _open_exam(db, token)
    items = load_items(db, exam.paper)
    groups = strip_answers(group_items(items))
    return TakePaperOut(
        title=exam.title,
        school=exam.paper.school,
        duration=exam.paper.duration,
        code=exam.paper.code,
        total=len(items),
        full_score=sum(int(it.get("score") or 0) for it in items),
        groups=groups,
    )


@router.post("/{token}/submit", response_model=SubmitOut, summary="学生交卷，后端判分")
def submit(token: str, body: SubmitIn, db: Session = Depends(get_db)):
    exam = _open_exam(db, token)

    if not body.student_name.strip():
        raise HTTPException(status_code=400, detail="请先填写姓名")

    # 同一学号默认只能交一次，避免反复试答案
    if body.student_no.strip() and not exam.allow_retake:
        dup = db.scalar(
            select(ExamSubmission).where(
                ExamSubmission.exam_id == exam.id,
                ExamSubmission.student_no == body.student_no.strip(),
            )
        )
        if dup:
            raise HTTPException(status_code=409, detail="这个学号已经交过卷了，如需重考请联系老师")

    items = load_items(db, exam.paper)
    result = grade(items, body.answers)

    sub = ExamSubmission(
        exam_id=exam.id,
        student_name=body.student_name.strip(),
        student_class=body.student_class.strip(),
        student_no=body.student_no.strip(),
        answers_json=json.dumps(body.answers, ensure_ascii=False),
        detail_json=json.dumps(result["detail"], ensure_ascii=False),
        **submission_scores(result),
    )
    db.add(sub)
    db.commit()

    return _submit_out(exam, result)
