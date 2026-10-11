"""学生平台的接口，以及教师端的学生账号管理。

分成两半，鉴权完全不同：
- `/api/student/*` 给学生用，认 `get_current_student`（学生令牌）；
- `/api/students/*` 给老师用，认 `get_current_user`（教师令牌）。

**教师端按班隔离**（2.10.1 起）：管理员看全校；老师只看得到、只管得着**自己名下的班**
（「班级」页面里 owner 是自己的班）的学生 —— 列表、导出、增改、导入、批量操作都一样。
别的班的学生，老师连"有这个人"都看不出来（改、删一律回 404）。班级管理本身不变。
见 `_scope` / `_mine` / `_own_class`。

学生令牌过不了教师接口，教师令牌也过不了学生接口 —— 令牌里带了身份类型，
两边各认各的（见 security.TOKEN_TEACHER / TOKEN_STUDENT）。

学生这边一律看不到答案：取卷仍然走 take.py 那套 strip_answers()，
判分也还是在服务端做。这个文件不 import 任何会吐答案的东西。
"""

import io
import json
import re
from urllib.parse import quote
from pydantic import BaseModel

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from openpyxl import Workbook
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_student, get_current_user
from ..models import Exam, ExamSubmission, SchoolClass, Student, TypingRecord, User
from ..schemas import (
    StudentBatchIn,
    StudentBulkIn,
    StudentCreate,
    StudentExamOut,
    StudentHomeOut,
    StudentOut,
    StudentPasswordChange,
    StudentTokenOut,
    StudentUpdate,
)
from ..security import (
    TOKEN_STUDENT,
    create_access_token,
    hash_password,
    verify_password,
)
from ..routers.classes import owned_class_ids
from ..routers.take import _submit_out as submit_out
from ..services.exam import submission_scores
from ..services import pinyin, roster
from ..services.exam import grade, group_items, load_items, manual_types, strip_answers
# 名单解析和入库都在 services/roster.py，上传表格和粘贴名单共用那一套。
# 这里只保留单个增改用得到的几个小工具。
from ..services.roster import STUDENT_NO_RE, norm_gender

student_api = APIRouter(prefix="/api/student", tags=["学生平台"])
admin_api = APIRouter(prefix="/api/students", tags=["学生账号管理"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PASSWORD_MIN = 6
CLASS_ROLES = ("", "班长", "组长")


# ================================================================ 公共校验
def check_student_no(no: str) -> str:
    value = (no or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="学号不能为空")
    if len(value) > 32:
        raise HTTPException(status_code=400, detail="学号太长，最多 32 位")
    if not STUDENT_NO_RE.match(value):
        raise HTTPException(
            status_code=400, detail="学号只能用字母、数字、下划线、点、减号（不能有空格和中文）"
        )
    return value


def check_student_password(pwd: str) -> str:
    value = pwd or ""
    if len(value) < PASSWORD_MIN:
        raise HTTPException(
            status_code=400, detail=f"密码太短，至少 {PASSWORD_MIN} 位（现在是 {len(value)} 位）"
        )
    if len(value) > 64:
        raise HTTPException(status_code=400, detail="密码太长，最多 64 位")
    if value.strip() != value:
        raise HTTPException(status_code=400, detail="密码开头或结尾有空格，请去掉")
    return value


def resolve_class(db: Session, class_id: int | None) -> SchoolClass | None:
    """班级 id 换成班级对象。给了不存在的 id 就报错，别默默存成未分班。"""
    if class_id is None:
        return None
    row = db.get(SchoolClass, class_id)
    if not row:
        raise HTTPException(status_code=404, detail="选择的班级不存在，刷新页面看看")
    return row


def _scope(db: Session, me: User) -> dict | None:
    """这位老师管得着的班：{班级 id: 班级}。管理员返回 None —— 全校不设限。"""
    ids = owned_class_ids(db, me)
    if ids is None:
        return None
    if not ids:
        return {}
    return {c.id: c for c in db.scalars(select(SchoolClass).where(SchoolClass.id.in_(ids)))}


def _mine(stmt, scope: dict | None):
    """把学生查询收窄到老师自己的班。

    老数据里可能有 class_id 没填、只写了班级名的学生（班级表是 2.3 才有的），
    名字和自己的班对得上的也算。
    """
    if scope is None:
        return stmt
    if not scope:
        return stmt.where(false())
    names = [c.display for c in scope.values()]
    return stmt.where(or_(
        Student.class_id.in_(list(scope)),
        and_(Student.class_id.is_(None), Student.student_class.in_(names)),
    ))


def _in_scope(row: Student, scope: dict | None) -> bool:
    if scope is None:
        return True
    if row.class_id is not None:
        return row.class_id in scope
    return row.student_class in {c.display for c in scope.values()}


NO_CLASS_TIP = "你名下还没有班级。请管理员在「班级」页面把班分给你，之后这里就能管自己班的学生了。"


def _own_class(db: Session, scope: dict | None, class_id: int | None,
               *, required: bool) -> SchoolClass | None:
    """要把学生放进哪个班。老师只能放进自己的班，而且必须选一个 ——
    放进"未分班"的话，他自己马上就看不到这个学生了。"""
    cls = resolve_class(db, class_id)
    if scope is None:
        return cls
    if not scope:
        raise HTTPException(status_code=403, detail=NO_CLASS_TIP)
    if cls is None:
        if required:
            raise HTTPException(status_code=400, detail="请选一个你带的班")
        return None
    if cls.id not in scope:
        raise HTTPException(status_code=403,
                            detail=f"「{cls.display}」不是你带的班，只能管自己班的学生")
    return cls


def initial_password(student_no: str) -> str:
    """初始密码。学号够长就直接用学号，太短则补足到 6 位，保证能通过校验。"""
    return student_no if len(student_no) >= PASSWORD_MIN else (student_no + "123456")[:6]


# 「姓名登录版」学生端（desktop `build.py --name-login`）的初始密码。
# 学号登录那条路不变（初始密码仍是学号）；两边认的是同一个账号，
# 学生改过密码之后，两种登录都只认新密码。
NAME_LOGIN_PASSWORD = "123456"


def still_initial(row: Student) -> bool:
    """这个账号还没改过密码（仍是建号 / 重置时给的那个学号初始密码）。"""
    return verify_password(initial_password(row.student_no), row.password_hash)


def name_login_ok(row: Student, pwd: str) -> bool:
    """姓名登录的密码对不对：没改过密码的账号**只认 123456**（不认学号那个初始密码，
    学号是同学之间都知道的）；改过的认新密码。"""
    if still_initial(row):
        return pwd == NAME_LOGIN_PASSWORD
    return verify_password(pwd, row.password_hash)


def _student_token(row: Student, db: Session) -> StudentTokenOut:
    return StudentTokenOut(
        access_token=create_access_token(row.id, "student", typ=TOKEN_STUDENT),
        student=StudentOut.model_validate(row),
    )


# ================================================================ 学生端
@student_api.post("/login", response_model=StudentTokenOut, summary="学生登录（学号 + 密码）")
def student_login(
    student_no: str = Query(..., description="学号"),
    password: str = Query(..., description="密码"),
    db: Session = Depends(get_db),
):
    row = db.scalar(select(Student).where(Student.student_no == student_no.strip()))
    if not row or not verify_password(password, row.password_hash):
        raise HTTPException(status_code=400, detail="学号或密码不正确")
    if not row.is_active:
        raise HTTPException(status_code=403, detail="账号已停用，请找老师")
    return _student_token(row, db)


def _out(rows) -> list[StudentOut]:
    return [StudentOut.model_validate(r) for r in rows]


class LoginClassOut(BaseModel):
    id: int
    display: str


@student_api.get("/classes", response_model=list[LoginClassOut],
                 summary="登录页的班级下拉（不用登录）")
def login_classes(db: Session = Depends(get_db)):
    """有在用学生的班级。学生拼音登录时先选班，再在这个班里按拼音找人。"""
    used = select(Student.class_id).where(Student.is_active.is_(True),
                                          Student.class_id.is_not(None))
    rows = db.scalars(
        select(SchoolClass).where(SchoolClass.is_active.is_(True), SchoolClass.id.in_(used))
        .order_by(SchoolClass.grade, SchoolClass.sort_order, SchoolClass.name)
    ).all()
    return [LoginClassOut(id=c.id, display=c.display) for c in rows]


def find_account(db: Session, account: str, class_id: int | None = None) -> list[Student]:
    """登录框里填的东西 → 可能是谁。依次认：

    1. 学号；
    2. 拼音全拼（zhangsan）—— 选了班级就只在这个班里找；没选班级（老客户端）
       全校只有一位在用的才认，重了提示先选班级；
    3. 中文姓名（4.10.0 姓名登录版的老 exe 还在机房里用着）。

    同一个班里拼音还重的，提示改填学号。不再有「拼音 + 年级班级」这种账号。
    """
    who = (account or "").strip()
    rows = db.scalars(select(Student).where(Student.student_no == who)).all()
    if rows:
        return list(rows)

    key = re.sub(r"\s+", "", who).lower()
    if key.isascii() and key:
        stmt = select(Student).where(Student.pinyin == key).order_by(Student.id)
        if class_id is not None:
            stmt = stmt.where(Student.class_id == class_id)
        same = db.scalars(stmt).all()
        live = [r for r in same if r.is_active]
        if len(live) > 1:
            detail = (f"这个班里有 {len(live)} 位同学的拼音都是「{key}」，请改填学号登录"
                      if class_id is not None else
                      f"有 {len(live)} 位同学的拼音都是「{key}」，请先选择班级")
            raise HTTPException(status_code=409, detail=detail)
        return list(same)

    stmt = select(Student).where(Student.name == who).order_by(Student.id)
    if class_id is not None:
        stmt = stmt.where(Student.class_id == class_id)
    return list(db.scalars(stmt))


@student_api.post("/login-by-name", response_model=StudentTokenOut,
                  summary="学生登录（班级 + 姓名拼音 + 密码，初始密码 123456）")
def student_login_by_name(
    name: str = Query(..., description="姓名拼音全拼；也认学号、中文姓名"),
    password: str = Query(..., description="密码"),
    class_id: int | None = Query(None, description="登录页选的班级；老客户端不传"),
    db: Session = Depends(get_db),
):
    """给拼音登录（学生端拼音登录版、学生网页）用。账号就是学号登录的那个账号，只是换个认人的办法。

    密码：没改过密码的账号只认 123456；改过的认新密码。填学号时不看班级，学号那个老的
    初始密码也认 —— 学号登录的老规矩不变。

    **中文姓名重名**（4.10.0 的老 exe）：同名的几位里，谁的密码对上就是谁；都还用着
    123456 时分不出是谁，提示改填学号。
    """
    who = (name or "").strip()
    if not who:
        raise HTTPException(status_code=400, detail="请填写姓名拼音")
    rows = find_account(db, who, class_id)
    by_no = bool(rows) and rows[0].student_no == who
    hits = [r for r in rows if name_login_ok(r, password)
            or (by_no and verify_password(password, r.password_hash))]
    if not hits:
        raise HTTPException(status_code=400, detail="班级、拼音或密码不正确" if class_id is not None
                            else "账号或密码不正确")
    active = [r for r in hits if r.is_active]
    if not active:
        raise HTTPException(status_code=403, detail="账号已停用，请找老师")
    if len(active) > 1:
        raise HTTPException(status_code=409,
                            detail=f"有 {len(active)} 位同学叫「{who}」，请改填学号登录")
    return _student_token(active[0], db)


@student_api.get("/me", response_model=StudentOut, summary="当前登录的学生")
def student_me(me: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    return StudentOut.model_validate(me)


@student_api.post("/password", summary="学生改自己的密码")
def student_change_password(
    body: StudentPasswordChange,
    me: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """学号和姓名不给改 —— 那是学校给的身份，改了老师就对不上人了。"""
    # 姓名登录版的学生只知道 123456 —— 没改过密码时它也算原密码（学号照样认）
    if not (verify_password(body.old_password, me.password_hash)
            or (body.old_password == NAME_LOGIN_PASSWORD and still_initial(me))):
        raise HTTPException(status_code=400, detail="原密码不正确")
    pwd = check_student_password(body.new_password)
    if pwd == NAME_LOGIN_PASSWORD:
        raise HTTPException(status_code=400, detail="123456 是大家都知道的初始密码，换一个吧")
    # 初始密码就是学号，所以「别用学号」要放在「和原密码一样」前面判，
    # 否则改密码时永远只看得到后一句，提示不到点子上
    if pwd == me.student_no:
        raise HTTPException(status_code=400, detail="别用学号当密码，同学之间太容易猜到了")
    if verify_password(pwd, me.password_hash):
        raise HTTPException(status_code=400, detail="新密码和原密码一样，换一个吧")
    me.password_hash = hash_password(pwd)
    db.commit()
    return {"ok": True}


def _visible_exams(db: Session, me: Student) -> list[Exam]:
    """学生能看到的考试：开着的，且班级对得上。

    target_classes 留空表示所有班都能看。老师填了班级就只发给那几个班，
    免得学生一进来看到全校几十场考试。
    """
    rows = db.scalars(select(Exam).where(Exam.is_open.is_(True)).order_by(Exam.id.desc())).all()
    out = []
    for e in rows:
        wanted = [c.strip() for c in (e.target_classes or "").split(",") if c.strip()]
        if not wanted or me.student_class in wanted:
            out.append(e)
    return out


@student_api.get("/exams", response_model=list[StudentExamOut], summary="我能参加的考试")
def student_exams(me: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    exams = _visible_exams(db, me)
    if not exams:
        return []

    done = {
        s.exam_id: s
        for s in db.scalars(
            select(ExamSubmission).where(
                ExamSubmission.exam_id.in_([e.id for e in exams]),
                ExamSubmission.student_id == me.id,
            )
        )
    }

    out = []
    for e in exams:
        sub = done.get(e.id)
        visible = sub is not None and e.show_score
        out.append(
            StudentExamOut(
                id=e.id,
                title=e.title,
                token=e.token,
                total=len(e.paper.items) if e.paper else 0,
                submitted=sub is not None,
                # 老师关掉"交卷后看分数"时连历史分数也不给看，口径保持一致
                score=sub.score if visible else None,
                objective_score=sub.objective_score if visible else None,
                subjective_score=sub.subjective_score if visible else None,
                full_score=(sub.objective_total + sub.subjective_total) if visible else None,
                # 操作题还没批完时列表上标一句，免得学生以为分就这么多了
                pending_manual=bool(sub and sub.subjective_total > 0 and sub.graded_at is None),
                show_score=e.show_score,
                allow_retake=e.allow_retake,
                submitted_at=sub.submitted_at if sub else None,
                created_at=e.created_at,
            )
        )
    return out


def _exam_for(db: Session, me: Student, exam_id: int) -> Exam:
    exam = next((e for e in _visible_exams(db, me) if e.id == exam_id), None)
    if not exam:
        raise HTTPException(status_code=404, detail="这场考试不存在或已经关闭")
    return exam


@student_api.get("/exams/{exam_id}/paper", summary="取卷（不含答案）")
def student_paper(
    exam_id: int, me: Student = Depends(get_current_student), db: Session = Depends(get_db)
):
    exam = _exam_for(db, me, exam_id)

    if not exam.allow_retake:
        dup = db.scalar(
            select(ExamSubmission).where(
                ExamSubmission.exam_id == exam.id, ExamSubmission.student_id == me.id
            )
        )
        if dup:
            raise HTTPException(status_code=409, detail="你已经交过这场考试了，如需重考请找老师")

    items = load_items(db, exam.paper)
    return {
        "title": exam.title,
        "school": exam.paper.school,
        "duration": exam.paper.duration,
        "code": exam.paper.code,
        "total": len(items),
        "full_score": sum(int(it.get("score") or 0) for it in items),
        # 和公开答题页同一个函数，答案在这一步就被剥掉了
        "groups": strip_answers(group_items(items)),
    }


@student_api.post("/exams/{exam_id}/submit", summary="交卷，后端判分")
def student_submit(
    exam_id: int,
    body: dict,
    me: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    exam = _exam_for(db, me, exam_id)
    answers = {str(k): str(v) for k, v in (body.get("answers") or {}).items()}

    if not exam.allow_retake:
        dup = db.scalar(
            select(ExamSubmission).where(
                ExamSubmission.exam_id == exam.id, ExamSubmission.student_id == me.id
            )
        )
        if dup:
            raise HTTPException(status_code=409, detail="你已经交过这场考试了，如需重考请找老师")

    items = load_items(db, exam.paper)
    result = grade(items, answers)

    # 姓名班级从账号来，学生填不了也改不了，成绩不会张冠李戴
    db.add(
        ExamSubmission(
            exam_id=exam.id,
            student_id=me.id,
            student_name=me.name,
            student_class=me.student_class,
            student_no=me.student_no,
            answers_json=json.dumps(answers, ensure_ascii=False),
            detail_json=json.dumps(result["detail"], ensure_ascii=False),
            **submission_scores(result),
        )
    )
    db.commit()

    # 和公开答题页共用同一段"给学生看什么"的逻辑，两处口径不会走样
    return submit_out(exam, result).model_dump()


def _mine_text(item: dict, raw: str) -> str:
    """把学生交上去的东西变成一句人看得懂的话。

    操作题交的是一份终态（文件夹快照、文档段落模型、网页源码），几十 KB 的
    JSON —— 原样摆在回看页上没人看得懂，还白白多传一份。AI 工具题是例外：
    学生交的就是他问出去的那几句话，那恰恰是"我做了什么"。
    """
    text = (raw or "").strip()
    if item.get("type") not in manual_types():
        return text
    if (item.get("sim") or {}).get("kind") == "ai":
        try:
            msgs = ((json.loads(text) or {}).get("state") or {}).get("messages") or []
        except (ValueError, AttributeError):
            msgs = []
        said = [str(m.get("text") or "").strip() for m in msgs if m.get("role") == "user"]
        return "\n".join(x for x in said if x) or "（没有提交对话）"
    return "已在本机完成操作，系统已记录操作结果" if text else "（未作答）"


@student_api.get("/exams/{exam_id}/review", summary="回看自己交的卷")
def student_review(
    exam_id: int, me: Student = Depends(get_current_student), db: Session = Depends(get_db)
):
    """交过卷之后回看自己写了什么。

    **默认只给"我选了什么"，不给对错。** 考试常常分批考（上午一个班、下午
    一个班），先考完的学生若能看到对错，题目当场就传出去了。所以：

        show_answer 关着  ——  只有自己的作答，没有对错、没有每题得分、
                              也没有操作题的检查项（检查项本身就是答案）
        show_answer 开着  ——  每题正确与否、每题得分、正确答案一起给

    总分另走 `show_score`，和考试列表、交卷页一个口径。

    老师评阅完操作题，这里读到的分数当场就变 —— 明细是从这份答卷本身读的，
    不是交卷那一刻的快照。
    """
    exam = _exam_for(db, me, exam_id)
    sub = db.scalar(
        select(ExamSubmission)
        .where(ExamSubmission.exam_id == exam.id, ExamSubmission.student_id == me.id)
        .order_by(ExamSubmission.id.desc())
    )
    if sub is None:
        raise HTTPException(status_code=404, detail="你还没交过这场考试")

    try:
        rows = json.loads(sub.detail_json or "[]") or []
    except ValueError:
        rows = []
    detail = {str(d.get("id")): d for d in rows if isinstance(d, dict)}

    no = 0
    groups = []
    # 和取卷同一个函数：答案和检查点在 strip_answers() 那一步就没了
    for g in strip_answers(group_items(load_items(db, exam.paper))):
        got = []
        for q in g["items"]:
            no += 1
            d = detail.get(str(q["id"])) or {}
            row = {
                "id": q["id"],
                "no": no,
                "type": q["type"],
                "stem": q.get("stem", ""),
                "options": q.get("options") or [],
                "image_url": q.get("image_url") or "",
                "score": int(q.get("score") or 0),
                "mine": _mine_text(q, d.get("mine", "")),
            }
            if exam.show_answer:
                row["ok"] = d.get("ok")
                row["earned"] = d.get("earned")
                row["answer"] = d.get("answer") or ""
                row["checks"] = [
                    {"desc": str(c.get("desc") or ""), "ok": bool(c.get("ok"))}
                    for c in (d.get("checks") or [])
                ]
            got.append(row)
        groups.append({"name": g.get("name") or "", "items": got})

    full = (sub.objective_total or 0) + (sub.subjective_total or 0)
    return {
        "title": exam.title,
        "submitted_at": sub.submitted_at,
        "show_score": exam.show_score,
        "show_answer": exam.show_answer,
        "score": sub.score if exam.show_score else None,
        "full_score": full if exam.show_score else None,
        "pending_manual": bool(sub.subjective_total and sub.graded_at is None),
        "groups": groups,
    }


@student_api.get("/typing/records", summary="我的打字练习记录")
def student_typing_records(
    limit: int = Query(50, ge=1, le=200),
    me: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(TypingRecord)
        .where(TypingRecord.student_id == me.id)
        .order_by(TypingRecord.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "module": r.module,
            "difficulty": r.difficulty,
            "speed": r.speed,
            "accuracy": r.accuracy,
            "duration": r.duration,
            "stars": r.stars,
            "created_at": r.created_at,
        }
        for r in rows
    ]


def _avg_score(db: Session, me: Student, exams: list[Exam]) -> int | None:
    """这个学生所有考试的平均分，折成百分制。

    **为什么折百分制**：卷面总分各场不一样（100 分的期末、50 分的小测），
    把 92 和 46 直接平均出来的数谁也看不懂。折成得分率再平均，才是一句
    "我平时大概考多少"。

    **口径跟着「交卷后看分数」走**：老师关掉那个开关的考试不计入 —— 否则
    学生从平均分里就能倒推出被藏起来的那一场考了多少。

    老师评阅完操作题，`score` 当场就变，所以这个平均分是**刷新即更新**的。
    """
    allowed = {e.id for e in exams if e.show_score}
    if not allowed:
        return None
    rates = []
    for s in db.scalars(
        select(ExamSubmission).where(
            ExamSubmission.student_id == me.id,
            ExamSubmission.exam_id.in_(allowed),
        )
    ):
        full = (s.objective_total or 0) + (s.subjective_total or 0)
        if full > 0:
            rates.append((s.score or 0) / full * 100)
    return round(sum(rates) / len(rates)) if rates else None


@student_api.get("/home", response_model=StudentHomeOut, summary="首页要的汇总数字")
def student_home(me: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    exams = _visible_exams(db, me)
    done = 0
    if exams:
        done = db.scalar(
            select(func.count(func.distinct(ExamSubmission.exam_id))).where(
                ExamSubmission.student_id == me.id,
                ExamSubmission.exam_id.in_([e.id for e in exams]),
            )
        ) or 0

    typing_count = db.scalar(
        select(func.count()).select_from(TypingRecord).where(TypingRecord.student_id == me.id)
    ) or 0
    best = db.scalar(
        select(func.max(TypingRecord.speed)).where(TypingRecord.student_id == me.id)
    ) or 0
    avg_acc = db.scalar(
        select(func.avg(TypingRecord.accuracy)).where(TypingRecord.student_id == me.id)
    ) or 0

    return StudentHomeOut(
        student=StudentOut.model_validate(me),
        exam_total=len(exams),
        exam_done=done,
        exam_avg_score=_avg_score(db, me, exams),
        typing_count=typing_count,
        typing_best_speed=int(best),
        typing_avg_accuracy=round(avg_acc),
    )


# ================================================================ 教师端管理
@admin_api.get("", response_model=list[StudentOut], summary="学生列表")
def list_students(
    class_id: int | None = None,
    student_class: str | None = None,
    keyword: str | None = None,
    is_active: bool | None = None,
    # 一个学校几千人很正常，默认就把全校发下去；界面那边分页显示，
    # 不会因为一次拿太多把表格撑卡。10000 是硬上限，防止有人误传个巨大的值
    # 把整库拉出来撑爆内存。
    limit: int = Query(10000, ge=1, le=10000),
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = _mine(select(Student), _scope(db, me))
    if class_id is not None:
        stmt = stmt.where(Student.class_id == class_id)
    if student_class:
        stmt = stmt.where(Student.student_class == student_class)
    if is_active is not None:
        stmt = stmt.where(Student.is_active.is_(is_active))
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(Student.name.like(like) | Student.student_no.like(like)
                          | Student.pinyin.like(like.lower()))
    stmt = stmt.order_by(Student.student_class, Student.student_no).limit(limit)
    return _out(db.scalars(stmt))


@admin_api.get("/classes", response_model=list[str], summary="出现过的班级，供筛选下拉")
def student_classes(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        _mine(select(Student.student_class), _scope(db, me))
        .where(Student.student_class != "")
        .distinct()
        .order_by(Student.student_class)
    ).all()
    return [r[0] for r in rows]


@admin_api.post("", response_model=StudentOut, summary="新增一个学生账号")
def create_student(
    body: StudentCreate, me: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    no = check_student_no(body.student_no)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="姓名不能为空")

    cls = _own_class(db, _scope(db, me), body.class_id, required=True)
    if db.scalar(select(Student).where(Student.student_no == no)):
        raise HTTPException(status_code=400, detail=f"学号「{no}」已经有账号了")

    pwd = check_student_password(body.password) if body.password else initial_password(no)
    row = Student(
        student_no=no,
        name=name[:64],
        class_id=cls.id if cls else None,
        student_class=cls.display if cls else "",
        gender=norm_gender(body.gender),
        pinyin=pinyin.name_pinyin(name),
        password_hash=hash_password(pwd),
        created_by=me.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return StudentOut.model_validate(row)


@admin_api.post("/batch", summary="粘贴名单批量建账号")
def batch_students(
    body: StudentBatchIn, me: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """和「上传表格」共用同一套解析和入库逻辑（services/roster.py）。

    一行四列：学号、姓名、班级、性别，后两列选填。从 Excel 复制粘贴过来
    自带制表符分隔，直接粘就行；手打的用空格隔开「学号 姓名」两列。
    班级留空的归到弹窗里选的那个班。

    初始密码就是学号，学生登录后自己改。已存在的学号跳过而不是报错 ——
    名单里混进几个已建的很正常，不该因此让整批都导不进去。
    """
    scope = _scope(db, me)
    fallback = _own_class(db, scope, body.class_id, required=False)
    rows = roster.paste_rows(body.text)
    if not rows:
        raise HTTPException(status_code=400, detail="名单是空的，没有可导入的内容")
    return roster.ingest(
        db, rows, me.id, fallback,
        make_password=initial_password, hash_it=hash_password,
        allowed=scope,
    )


@admin_api.patch("/{sid}", response_model=StudentOut, summary="改学生资料或重置密码")
def update_student(
    sid: int,
    body: StudentUpdate,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scope = _scope(db, me)
    row = db.get(Student, sid)
    # 别的班的学生：和不存在一个回法，连"有这个人"都不透露
    if not row or not _in_scope(row, scope):
        raise HTTPException(status_code=404, detail="学生不存在")

    data = body.model_dump(exclude_unset=True)
    if data.pop("password", None):
        row.password_hash = hash_password(check_student_password(body.password))

    # 换班时显示名要跟着换，成绩筛选和导出都用那个字符串
    if "class_id" in data:
        # 老师只能在自己的几个班之间调，调出去就管不着了
        cls = _own_class(db, scope, data.pop("class_id"), required=True)
        if (cls.id if cls else None) != row.class_id:
            row.class_role = ""          # 调走了，原来班里的班干部不跟着走
        row.class_id = cls.id if cls else None
        row.student_class = cls.display if cls else ""

    # 拼音：明确给了就用老师填的（多音字程序猜不准）；给空串或者改了姓名就按姓名重算
    new_name = (data.get("name") or "").strip()
    if "pinyin" in data:
        raw = (data.pop("pinyin") or "").strip()
        if raw:
            got = pinyin.norm_pinyin(raw)
            if not got:
                raise HTTPException(status_code=400, detail="拼音只能是英文字母（ü 写成 v），不带声调和空格")
            row.pinyin = got
        else:
            row.pinyin = pinyin.name_pinyin(new_name or row.name)
    elif new_name and new_name != row.name:
        row.pinyin = pinyin.name_pinyin(new_name)

    if "class_role" in data:
        role = (data.pop("class_role") or "").strip()
        if role not in CLASS_ROLES:
            raise HTTPException(status_code=400, detail="班干部只能是「班长」「组长」或不设")
        if role and row.class_id is None:
            raise HTTPException(status_code=400, detail="这位学生还没分班，先把他分到班里再设班干部")
        if role == "班长":
            # 一个班一位班长：换人时原来那位自动卸任
            for other in db.scalars(select(Student).where(
                    Student.class_id == row.class_id, Student.class_role == "班长",
                    Student.id != row.id)):
                other.class_role = ""
        row.class_role = role

    # 性别走归一：界面上是下拉，但接口也可能被别处调用，写法统一到「男/女/空」
    if "gender" in data:
        row.gender = norm_gender(data.pop("gender"))

    for k, v in data.items():
        setattr(row, k, v.strip()[:64] if isinstance(v, str) else v)

    db.commit()
    db.refresh(row)
    return StudentOut.model_validate(row)


@admin_api.post("/bulk", summary="批量启用／停用／删除／重置密码")
def bulk_students(
    body: StudentBulkIn, me: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """删除是真删，界面上要手工输入「删除」两个字才放行。

    老师只能动自己班的学生：勾选里混进别的班的 id（接口被直接调用时）一律不认。

    删掉学生账号后，他交过的卷子和练过的字都保留（外键置空），
    只是不再挂在账号上 —— 成绩是班级资料，不该跟着账号一起消失。
    """
    ids = list(dict.fromkeys(body.ids))
    if not ids:
        raise HTTPException(status_code=400, detail="没有选中任何学生")

    rows = list(db.scalars(_mine(select(Student).where(Student.id.in_(ids)), _scope(db, me))))
    if not rows:
        raise HTTPException(status_code=404, detail="选中的学生都不存在了，刷新看看")

    if body.action == "enable":
        for r in rows:
            r.is_active = True
    elif body.action == "disable":
        for r in rows:
            r.is_active = False
    elif body.action == "reset_password":
        for r in rows:
            r.password_hash = hash_password(initial_password(r.student_no))
    else:  # delete
        for r in rows:
            db.query(ExamSubmission).filter(ExamSubmission.student_id == r.id).update(
                {ExamSubmission.student_id: None}, synchronize_session=False
            )
            db.query(TypingRecord).filter(TypingRecord.student_id == r.id).update(
                {TypingRecord.student_id: None}, synchronize_session=False
            )
            db.delete(r)

    db.commit()
    return {"action": body.action, "affected": len(rows)}


# ================================================================ 导入导出



@admin_api.get("/template.xlsx", summary="下载学生导入模板")
def student_template(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """三列：学号、姓名、班级。

    班级名必须和「班级」页面里的一模一样，所以模板里直接把现有班级列出来，
    老师照着填就不会错 —— 让人凭记忆敲「七(3)班」还是「七年级3班」，
    十有八九对不上。
    """
    scope = _scope(db, me)
    stmt = select(SchoolClass).where(SchoolClass.is_active.is_(True))
    if scope is not None:
        # 老师的模板只列自己的班 —— 列了别人的班，照抄进去也导不进来
        stmt = stmt.where(SchoolClass.id.in_(list(scope) or [-1]))
    classes = list(db.scalars(
        stmt.order_by(SchoolClass.sort_order, SchoolClass.grade, SchoolClass.name)))
    sample_class = classes[0].display if classes else "七年级1班"

    wb = Workbook()
    ws = wb.active
    ws.title = "学生名单"
    ws.append(["学号", "姓名", "班级", "性别"])
    ws.append(["20260101", "张三", sample_class, "男"])
    ws.append(["20260102", "李四", sample_class, "女"])
    for col, w in zip("ABCD", [18, 14, 18, 8]):
        ws.column_dimensions[col].width = w

    note = wb.create_sheet("填写说明")
    for line in [
        ["把学生名单填在「学生名单」这一页，四列：学号、姓名、班级、性别。"],
        ["第一行的表头请保留，示例的两行可以直接改掉。"],
        ["", ],
        ["★ 班级必须和系统里的名称完全一致，可用的班级见「可用班级」那一页。"],
        ["  班级留空的话，会归到导入时选的那个班；都没有就是「未分班」。"],
        ["", ],
        ["性别填「男」或「女」，选填。留空或写别的都不影响建账号，"],
        ["  只是这一栏空着，以后可以在学生列表里补。"],
        ["", ],
        ["拼音不用填：导入时按姓名自动生成，单独存一列，在学生列表里能看到、能改。"],
        ["学生用姓名拼音登录（如 zhangsan），初始密码 123456，登录后自己改；"],
        ["  登录时先选班级再填拼音；同一个班里拼音重了的同学改填学号。"],
        ["  用学号登录的老客户端照旧：账号填学号，初始密码就是学号。"],
        ["已经存在的学号会自动跳过，不会覆盖原有账号。"],
        ["也可以存成 CSV 再上传，编码用 UTF-8 或 GBK 都行。"],
    ]:
        note.append(line)
    note.column_dimensions["A"].width = 60

    # 把现有班级原样列出来，复制粘贴就不会写错
    sheet = wb.create_sheet("可用班级")
    sheet.append(["班级（照抄到名单的「班级」列）", "年级", "任课老师"])
    for c in classes:
        sheet.append([c.display, c.grade, (c.owner.name or c.owner.username) if c.owner else ""])
    if not classes:
        sheet.append(["还没有建班级，请先到「班级」页面建班", "", ""])
    for col, w in zip("ABC", [30, 12, 14]):
        sheet.column_dimensions[col].width = w

    buf = io.BytesIO()
    wb.save(buf)
    name = quote("学生导入模板.xlsx")
    return Response(
        content=buf.getvalue(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"},
    )


@admin_api.post("/import", summary="从 Excel/CSV 导入学生")
def import_students(
    class_id: int | None = Query(None, description="导进哪个班，留空则不分班"),
    file: UploadFile = File(...),
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """四列：学号、姓名、班级、性别，按这个顺序读。和「粘贴名单」共用同一套
    解析和入库逻辑（services/roster.py），两个入口的规则完全一致。

    **工作簿里每一张表都会读** —— 一个年级一张表、按班分表都很常见。
    模板自带的「填写说明」「可用班级」两页认得出来，会自动跳过。

    **这个函数是 `def` 不是 `async def`，别改回去。**
    每建一个账号都要算一次 bcrypt（约 190 毫秒），1500 人就是近 5 分钟纯 CPU。
    写成 async 的话这 5 分钟全压在事件循环上，整个网站会彻底卡死 —— 真出过。
    写成同步的，FastAPI 会把它丢进线程池，bcrypt 在 C 层会释放 GIL，
    别的请求照常有人服务。
    """
    # 同步读。上面那条注释说了为什么这个端点不能是 async
    raw = file.file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件太大了，超过 5 MB")

    try:
        rows, skipped_sheets = roster.sheet_rows(file.filename or "", raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not rows:
        extra = f"（跳过了这些工作表：{'、'.join(skipped_sheets)}）" if skipped_sheets else ""
        raise HTTPException(
            status_code=400,
            detail=f"没读到任何学生{extra}。"
            "表格要有「学号」「姓名」两列，第一行写表头即可。",
        )

    scope = _scope(db, me)
    fallback = _own_class(db, scope, class_id, required=False)
    result = roster.ingest(
        db, rows, me.id, fallback,
        make_password=initial_password, hash_it=hash_password,
        allowed=scope,
    )
    result["sheets_skipped"] = skipped_sheets
    return result


@admin_api.get("/export.xlsx", summary="导出学生名单")
def export_students(
    class_id: int | None = None,
    keyword: str | None = None,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出的表和导入模板同构（学号、姓名在前两列），改完能直接再导回来。
    老师只导得出自己班的学生。"""
    stmt = _mine(select(Student), _scope(db, me))
    if class_id is not None:
        stmt = stmt.where(Student.class_id == class_id)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(Student.name.like(like) | Student.student_no.like(like)
                          | Student.pinyin.like(like.lower()))
    rows = list(db.scalars(stmt.order_by(Student.student_class, Student.student_no)))

    wb = Workbook()
    ws = wb.active
    ws.title = "学生名单"
    # 前四列和导入模板完全一致，导出的表改完可以直接再导回来
    ws.append(["学号", "姓名", "班级", "性别", "拼音", "班干部", "状态", "创建时间"])
    for s in rows:
        ws.append([
            s.student_no,
            s.name,
            s.student_class or "未分班",
            s.gender,
            s.pinyin,
            s.class_role,
            "正常" if s.is_active else "已停用",
            s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "",
        ])
    for col, w in zip("ABCDEFGH", [16, 12, 16, 8, 16, 8, 10, 18]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)

    cls = db.get(SchoolClass, class_id) if class_id is not None else None
    name = quote(f"学生名单_{cls.display if cls else '全部'}.xlsx")
    return Response(
        content=buf.getvalue(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"},
    )
