"""教师端：发布考试、查成绩、导出。全部需要登录。

**考试是按人隔离的**，分「看得到」和「改得动」两层：

    谁          看得到                        改得动
    管理员      全部                          全部
    老师        自己发的 + 管理员发的         只有自己发的

管理员发的多半是全校统考，老师要能查自己班的成绩，但不该能动那份卷子的
开关，更不该删掉。别的老师发的考试仍然互相看不见。

三个函数管这件事：`_visible`（列表）、`_can_edit`（判权限）、`_get`（取单个）。
每个接口都得从它们拿考试对象，不要再自己 db.get(Exam, ...)。
看不到的一律回 404 而不是 403 —— 连"这个 id 存在"都不告诉；
看得到但改不动的回 403，并说清为什么。
"""

import io
import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from openpyxl import Workbook
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import clock
from ..database import get_db
from ..deps import get_current_user
from ..models import Exam, ExamSubmission, Paper, SchoolClass, Student, User
from ..routers.classes import owned_class_ids
from ..schemas import ExamCreate, ExamOut, ExamUpdate, IdsIn, ManualGradeIn, SubmissionOut
from ..services.analysis import analyze
from ..siteconfig import site
from ..services.exam import (
    apply_manual,
    group_items,
    has_scores,
    load_items,
    new_token,
    question_stats,
)

router = APIRouter(prefix="/api/exams", tags=["考试"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _to_out(exam: Exam, db: Session | None = None) -> ExamOut:
    item = ExamOut.model_validate(exam)
    subs = exam.submissions
    item.submission_count = len(subs)
    item.avg_score = round(sum(s.score for s in subs) / len(subs), 1) if subs else None
    item.full_score = max((s.objective_total + s.subjective_total for s in subs), default=0)
    # 还有几份卷子的操作题没批完。graded_at 只在**全批完**时才落，
    # 所以这个数不会因为批了一半就归零（见 grade_manual）。
    item.ungraded_count = sum(
        1 for s in subs if s.subjective_total > 0 and s.graded_at is None
    )

    # 存的是班级名（历史数据不受改名影响），界面上要回填下拉得换成 id
    names = [c.strip() for c in (exam.target_classes or "").split(",") if c.strip()]
    if names and db is not None:
        rows = db.scalars(select(SchoolClass)).all()
        by_name = {c.display: c.id for c in rows}
        item.target_class_ids = [by_name[n] for n in names if n in by_name]
    return item


def _resolve_targets(db: Session, user: User, class_ids: list[int]) -> str:
    """把要发的班算成一串班级名存起来。

    规则：
    - 管理员不选班 = 发给全体学生（存空串）；
    - 老师不选班 = 发给自己名下的全部班；
    - 老师选了班，必须都是自己名下的，选到别人的班直接拒绝。

    存班级名而不是 id，是为了让历史考试不受班级改名／删班的影响 ——
    这一点和成绩单里冗余存班级名是同一个道理。
    """
    owned = owned_class_ids(db, user)

    if user.role != "admin":
        if not owned:
            raise HTTPException(
                status_code=400,
                detail="你名下还没有班级，没法发考试。请管理员在「班级」页面把班分给你。",
            )
        wanted = set(class_ids) if class_ids else set(owned)
        outside = wanted - owned
        if outside:
            rows = db.scalars(select(SchoolClass).where(SchoolClass.id.in_(outside))).all()
            names = "、".join(c.display for c in rows) or "某些班"
            raise HTTPException(
                status_code=403, detail=f"「{names}」不是你带的班，只能给自己的班发考试"
            )
    else:
        if not class_ids:
            return ""  # 管理员不选 = 全体学生
        wanted = set(class_ids)

    rows = db.scalars(
        select(SchoolClass).where(SchoolClass.id.in_(wanted))
    ).all()
    if not rows:
        raise HTTPException(status_code=400, detail="选中的班级都不存在了，刷新看看")
    return ",".join(sorted(c.display for c in rows))


def _admin_ids(db: Session):
    """管理员的 user id 子查询。管理员发的考试全校老师都看得到。"""
    return select(User.id).where(User.role == "admin")


def _visible(stmt, user: User, db: Session):
    """看得到哪些考试。

    - 管理员：全部；
    - 老师：自己发的 + **管理员发的**（后者只能看成绩，改不了也删不了）。

    别人发的考试仍然互相看不到 —— 隔离的是老师之间，不是老师和管理员之间。
    """
    if user.role == "admin":
        return stmt
    return stmt.where(
        or_(Exam.created_by == user.id, Exam.created_by.in_(_admin_ids(db)))
    )


def _can_edit(db: Session, exam: Exam, user: User) -> bool:
    """能不能改这场考试。管理员都能改；老师只能改自己发的。

    管理员发的考试老师看得到，但改不了 —— 全校统考的开关不该让任课老师动。
    """
    return user.role == "admin" or exam.created_by == user.id


def _get(db: Session, exam_id: int, user: User, *, edit: bool = False) -> Exam:
    """取一场考试。

    edit=True 时要求有修改权，没有就 403 并说清为什么；
    edit=False 只要求看得到，看不到一律 404（连"这个 id 存在"都不告诉）。
    """
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="考试不存在")

    if user.role != "admin":
        owner = db.get(User, exam.created_by) if exam.created_by else None
        visible = exam.created_by == user.id or (owner and owner.role == "admin")
        if not visible:
            raise HTTPException(status_code=404, detail="考试不存在")

    if edit and not _can_edit(db, exam, user):
        raise HTTPException(
            status_code=403,
            detail="这是管理员发布的考试，你可以查看成绩，但不能修改设置或删除。",
        )
    return exam


@router.post("", response_model=ExamOut, summary="把一份存档试卷发布成考试")
def create_exam(
    body: ExamCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    paper = db.get(Paper, body.paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在，请先在组卷页勾选「把这套卷子存档」")
    if not paper.items:
        raise HTTPException(status_code=400, detail="这份试卷没有题目")

    exam = Exam(
        paper_id=paper.id,
        title=body.title or paper.title,
        token=new_token(),
        is_open=body.is_open,
        allow_retake=body.allow_retake,
        show_score=body.show_score,
        show_answer=body.show_answer,
        target_classes=_resolve_targets(db, user, body.target_class_ids),
        created_by=user.id,
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return _to_out(exam, db)


@router.get("", response_model=list[ExamOut], summary="考试列表")
def list_exams(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(_visible(select(Exam), user, db).order_by(Exam.id.desc())).all()

    # 老师的列表里现在混着管理员发的考试，所以两边都要标出「谁发的」，
    # 否则老师分不清哪几场是自己的、哪几场只能看
    owner_ids = {e.created_by for e in rows if e.created_by}
    owners = (
        {u.id: u for u in db.scalars(select(User).where(User.id.in_(owner_ids)))}
        if owner_ids
        else {}
    )

    out = []
    for e in rows:
        item = _to_out(e, db)
        owner = owners.get(e.created_by or 0)
        item.owner_name = (owner.name or owner.username) if owner else "未知"
        item.can_edit = _can_edit(db, e, user)
        out.append(item)
    return out


@router.get("/{exam_id}", response_model=ExamOut, summary="考试详情")
def get_exam(exam_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _to_out(_get(db, exam_id, user), db)


@router.patch("/{exam_id}", response_model=ExamOut, summary="改考试设置（开关、是否给学生看分数等）")
def update_exam(
    exam_id: int,
    body: ExamUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = _get(db, exam_id, user, edit=True)
    data = body.model_dump(exclude_unset=True)

    # 改发放范围要重新走一遍归属校验，别让人绕过创建时的限制
    if "target_class_ids" in data:
        exam.target_classes = _resolve_targets(db, user, data.pop("target_class_ids") or [])

    for k, v in data.items():
        setattr(exam, k, v)
    db.commit()
    db.refresh(exam)
    return _to_out(exam, db)


@router.delete("/{exam_id}", summary="删除考试（连同答卷）")
def delete_exam(exam_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.delete(_get(db, exam_id, user, edit=True))
    db.commit()
    return {"ok": True}


class GradeScope:
    """这位老师批得了哪些答卷：**只批自己带的班**，别的班只能看（2.12.1）。

    管理员不设限。答卷认班级两样都看：交卷的学生现在在哪个班（学生调过班也跟着走），
    和答卷上记的班级名（学生账号删了、或者是老数据没挂账号的）。
    一场考试要判断几十份答卷，班级只查一次。
    """

    def __init__(self, db: Session, user: User):
        from .classes import owned_class_ids

        self.db = db
        self.ids = owned_class_ids(db, user)
        self.names = set()
        if self.ids:
            self.names = {c.display for c in db.scalars(select(SchoolClass).where(SchoolClass.id.in_(self.ids)))}

    def allows(self, sub: ExamSubmission) -> bool:
        if self.ids is None:
            return True
        if (sub.student_class or "") in self.names:
            return True
        st = self.db.get(Student, sub.student_id) if sub.student_id else None
        return bool(st and st.class_id in self.ids)


NOT_MY_CLASS = "这份答卷是「{cls}」的，不是你带的班，只能查看；请该班老师批改"


def _sub_out(db: Session, sub: ExamSubmission, grade: "GradeScope | None" = None) -> SubmissionOut:
    item = SubmissionOut.model_validate(sub)
    item.full_score = sub.objective_total + sub.subjective_total
    detail = json.loads(sub.detail_json or "[]")
    # 没设分值的老卷子（subjective_total 为 0）操作题不计分，没什么可阅的 ——
    # 原来这里照样报「阅卷 12」，点进去保存又被拒绝（grade_manual 回 400），是条死路
    item.pending_manual = sum(
        1 for d in detail if d.get("manual") and not d.get("graded")
    ) if sub.subjective_total > 0 else 0
    if sub.graded_by:
        grader = db.get(User, sub.graded_by)
        item.graded_by_name = (grader.name or grader.username) if grader else ""
    item.can_grade = grade.allows(sub) if grade else True
    return item


@router.get("/{exam_id}/submissions", response_model=list[SubmissionOut], summary="成绩列表")
def list_submissions(
    exam_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    exam = _get(db, exam_id, user)
    rows = sorted(exam.submissions, key=lambda s: (-s.score, s.student_no))
    grade = GradeScope(db, user)
    return [_sub_out(db, s, grade) for s in rows]


@router.get("/{exam_id}/submissions/{sub_id}", summary="某个学生的答卷明细")
def submission_detail(
    exam_id: int,
    sub_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exam = _get(db, exam_id, user)  # 先校验这场考试归不归你，再取答卷
    sub = db.get(ExamSubmission, sub_id)
    if not sub or sub.exam_id != exam_id:
        raise HTTPException(status_code=404, detail="答卷不存在")
    items = {it["id"]: it for it in load_items(db, exam.paper)}
    detail = json.loads(sub.detail_json or "[]")
    for d in detail:
        it = items.get(d["id"])
        if it:
            d["stem"] = it["stem"]
            d["options"] = it["options"]
            d["scope"] = it["scope"]

    grader = db.get(User, sub.graded_by) if sub.graded_by else None
    return {
        "id": sub.id,
        "student_name": sub.student_name,
        "student_class": sub.student_class,
        "student_no": sub.student_no,
        "score": sub.score,
        "right_count": sub.right_count,
        "objective_count": sub.objective_count,
        "objective_score": sub.objective_score,
        "objective_total": sub.objective_total,
        "subjective_score": sub.subjective_score,
        "subjective_total": sub.subjective_total,
        "full_score": sub.objective_total + sub.subjective_total,
        "pending_manual": sum(1 for d in detail if d.get("manual") and not d.get("graded"))
        if sub.subjective_total > 0 else 0,
        "graded_by_name": (grader.name or grader.username) if grader else "",
        # 别的班的答卷：看得到，批不了（界面上打分框变只读）
        "can_grade": GradeScope(db, user).allows(sub),
        "graded_at": sub.graded_at,
        "submitted_at": sub.submitted_at,
        "detail": detail,
    }


@router.patch(
    "/{exam_id}/submissions/{sub_id}/manual",
    summary="给这份答卷的主观题赋分（操作题等）",
)
def grade_manual(
    exam_id: int,
    sub_id: int,
    body: ManualGradeIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """老师逐题给操作题打分，总分立刻重算。

    **这里只要"看得到"的权限，不要求"改得动"**：管理员发的全校统考，
    操作题得由各班任课老师自己批 —— 要求改卷权的话这活儿就只能管理员一个人干。
    改的是成绩不是试卷设置，而且每次都记下是谁批的（graded_by），有据可查。

    但**只批自己带的班**（2.12.1）：别的班的答卷看得到、批不了，免得一个老师把全年级的分都改了。
    """
    exam = _get(db, exam_id, user)
    sub = db.get(ExamSubmission, sub_id)
    if not sub or sub.exam_id != exam_id:
        raise HTTPException(status_code=404, detail="答卷不存在")
    if not GradeScope(db, user).allows(sub):
        raise HTTPException(status_code=403, detail=NOT_MY_CLASS.format(cls=sub.student_class or "未填班级"))
    if sub.subjective_total <= 0:
        raise HTTPException(
            status_code=400,
            detail="这份卷子没有要人工评阅的题（2.4.0 之前组的卷子不设分值，按正确率折百分制）",
        )

    detail = json.loads(sub.detail_json or "[]")
    result = apply_manual(detail, body.scores)

    sub.detail_json = json.dumps(result["detail"], ensure_ascii=False)
    sub.manual_json = json.dumps(
        {str(k): int(v) for k, v in body.scores.items()}, ensure_ascii=False
    )
    sub.subjective_score = result["subjective_score"]
    sub.score = sub.objective_score + sub.subjective_score
    sub.graded_by = user.id
    # 只有全批完才算"批过了"，批一半不该让考试列表上的待阅提示消失
    sub.graded_at = clock.now() if result["pending"] == 0 else None
    db.commit()
    db.refresh(sub)

    _ = exam  # 权限校验已在 _get 里做过
    return {
        "ok": True,
        "score": sub.score,
        "objective_score": sub.objective_score,
        "subjective_score": sub.subjective_score,
        "full_score": sub.objective_total + sub.subjective_total,
        "pending_manual": result["pending"],
    }


def _delete_subs(db: Session, exam: Exam, ids: list[int]) -> int:
    """删答卷。只删这场考试自己的 —— 别的考试的 id 混进来一律不认。"""
    rows = db.scalars(select(ExamSubmission).where(
        ExamSubmission.exam_id == exam.id, ExamSubmission.id.in_(ids))).all()
    for sub in rows:
        db.delete(sub)
    db.commit()
    return len(rows)


@router.delete("/{exam_id}/submissions/{sub_id}", summary="删除一份答卷")
def delete_submission(
    exam_id: int, sub_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """删成绩要**改得动**这场考试（自己发的，或者管理员）—— 管理员发的全校统考，
    任课老师能批不能删。删掉之后这个学生可以重新交卷（不允许重考的考试也一样）。"""
    exam = _get(db, exam_id, user, edit=True)
    if not _delete_subs(db, exam, [sub_id]):
        raise HTTPException(status_code=404, detail="答卷不存在")
    return {"ok": True, "deleted": 1}


@router.post("/{exam_id}/submissions/delete", summary="批量删除答卷")
def delete_submissions(
    exam_id: int, body: IdsIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    exam = _get(db, exam_id, user, edit=True)
    if not body.ids:
        raise HTTPException(status_code=400, detail="没选答卷")
    return {"ok": True, "deleted": _delete_subs(db, exam, body.ids)}


@router.get("/{exam_id}/paper", summary="这场考试的样卷（带答案，老师看）")
def exam_paper(exam_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """老师在成绩页一键看卷子：按大题分组，题干、选项、答案、分值、配图。
    答案只在这个教师接口里出现，学生取卷走的是 strip_answers 那条路。"""
    exam = _get(db, exam_id, user)
    groups = group_items(load_items(db, exam.paper))
    no = 0
    out = []
    for g in groups:
        items = []
        for it in g["items"]:
            no += 1
            items.append({
                "no": no, "id": it["id"], "type": it["type"], "stem": it["stem"],
                "options": it.get("options") or [], "answer": it.get("answer") or "",
                "score": int(it.get("score") or 0), "scope": it.get("scope") or "",
                "image_url": it.get("image_url"),
                "sim_kind": (it.get("sim") or {}).get("kind") or "",
                "checks": [c.get("desc") or "" for c in (it.get("sim_checks") or [])
                           if isinstance(c, dict)],
            })
        out.append({"name": g["name"], "score": g["score"], "items": items})
    paper = exam.paper
    return {
        "title": exam.title,
        "paper_title": paper.title if paper else "",
        "school": paper.school if paper else "",
        "duration": paper.duration if paper else "",
        "full_score": sum(g["score"] for g in out),
        "groups": out,
    }


@router.get("/{exam_id}/analysis", summary="成绩分析（可视化页用）")
def exam_analysis(
    exam_id: int,
    classes: str = "",
    students: str = "",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """classes：逗号分隔的班级名，只看这几个班；students：逗号分隔的答卷 id，几个学生对比。
    都不给就是全体参考学生。页面每隔一会儿重新拉一次 —— 老师阅完卷，图跟着变。"""
    exam = _get(db, exam_id, user)
    items = load_items(db, exam.paper)
    everyone = list(exam.submissions)
    want_ids = {int(x) for x in students.split(",") if x.strip().isdigit()}
    want_cls = {x.strip() for x in classes.split(",") if x.strip()}
    if want_ids:
        subs, scope = [s for s in everyone if s.id in want_ids], {"kind": "students"}
    elif want_cls:
        subs, scope = [s for s in everyone if (s.student_class or "未填班级") in want_cls],             {"kind": "classes", "classes": sorted(want_cls)}
    else:
        subs, scope = everyone, {"kind": "all"}
    result = analyze(items, subs, site.exam.pass_score, scope, all_subs=everyone,
                     scored=has_scores(items))
    result["exam"] = {"id": exam.id, "title": exam.title}
    result["pass_line"] = site.exam.pass_score
    result["options"] = {
        "classes": sorted({s.student_class or "未填班级" for s in everyone}),
        "students": [{"sub_id": s.id, "name": s.student_name, "class": s.student_class,
                      "no": s.student_no, "score": s.score}
                     for s in sorted(everyone, key=lambda x: (x.student_class or "", x.student_no or ""))],
    }
    result["updated_at"] = clock.now().isoformat(sep=" ")
    return result


@router.get("/{exam_id}/stats", summary="题目分析：每题正确率")
def exam_stats(exam_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    exam = _get(db, exam_id, user)
    items = load_items(db, exam.paper)
    subs = exam.submissions
    scores = [s.score for s in subs]
    return {
        "submission_count": len(subs),
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "max_score": max(scores) if scores else None,
        "min_score": min(scores) if scores else None,
        "questions": question_stats(exam, items),
    }


@router.get("/{exam_id}/export.xlsx", summary="成绩汇总导出 Excel")
def export_scores(
    exam_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    exam = _get(db, exam_id, user)
    items = load_items(db, exam.paper)
    groups = group_items(items)
    ordered = [it for g in groups for it in g["items"]]
    no_of = {it["id"]: i + 1 for i, it in enumerate(ordered)}

    wb = Workbook()

    full = sum(int(it.get("score") or 0) for it in items)

    ws = wb.active
    ws.title = "成绩汇总"
    ws.append(
        [
            "姓名", "班级", "学号",
            "总分" if full else "得分(百分制)",
            "客观题得分", "客观题满分", "操作题得分", "操作题满分",
            "待评阅", "评阅人", "答对", "客观题数", "交卷时间",
        ]
    )
    for s in sorted(exam.submissions, key=lambda x: (-x.score, x.student_no)):
        pending = sum(
            1 for d in json.loads(s.detail_json or "[]")
            if d.get("manual") and not d.get("graded")
        )
        grader = db.get(User, s.graded_by) if s.graded_by else None
        ws.append(
            [
                s.student_name,
                s.student_class,
                s.student_no,
                s.score,
                s.objective_score,
                s.objective_total,
                s.subjective_score,
                s.subjective_total,
                pending or "",
                (grader.name or grader.username) if grader else "",
                s.right_count,
                s.objective_count,
                s.submitted_at.strftime("%Y-%m-%d %H:%M:%S") if s.submitted_at else "",
            ]
        )
    for col, w in zip("ABCDEFGHIJKLM", [12, 14, 14, 10, 12, 12, 12, 12, 8, 12, 8, 10, 20]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"

    # 第二张表：每题正确率，老师用来讲评
    ws2 = wb.create_sheet("题目分析")
    ws2.append(
        ["题号", "大题", "题型", "难度", "分值", "知识范围", "题干", "答案",
         "答对", "答错", "未答", "正确率%"]
    )
    for st in question_stats(exam, items):
        ws2.append(
            [
                no_of.get(st["id"], ""),
                st["section"],
                st["type"],
                st["difficulty"],
                st["score"] or "",
                st["scope"],
                st["stem"],
                st["answer"],
                st["right"],
                st["wrong"],
                st["blank"],
                st["accuracy"] if st["scorable"] else "",
            ]
        )
    for col, w in zip("ABCDEFGHIJKL", [6, 18, 8, 6, 6, 16, 50, 10, 8, 8, 8, 10]):
        ws2.column_dimensions[col].width = w
    ws2.freeze_panes = "A2"

    # 第三张表：操作题的原始作答，需要人工评阅
    ws3 = wb.create_sheet("主观题作答")
    ws3.append(["姓名", "班级", "学号", "题号", "本题满分", "已给分", "学生作答", "答案要点"])
    for s in exam.submissions:
        for d in json.loads(s.detail_json or "[]"):
            if not d.get("manual"):
                continue
            ws3.append(
                [
                    s.student_name,
                    s.student_class,
                    s.student_no,
                    no_of.get(d["id"], ""),
                    d.get("score", "") or "",
                    d.get("earned", 0) if d.get("graded") else "未评阅",
                    d.get("mine", ""),
                    d.get("answer", ""),
                ]
            )
    for col, w in zip("ABCDEFGH", [12, 14, 14, 6, 10, 10, 60, 60]):
        ws3.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    name = quote(f"{exam.title}_成绩.xlsx")
    return Response(
        content=buf.getvalue(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"},
    )
