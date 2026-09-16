"""学生平台的接口，以及教师端的学生账号管理。

分成两半，鉴权完全不同：
- `/api/student/*` 给学生用，认 `get_current_student`（学生令牌）；
- `/api/students/*` 给老师用，认 `get_current_user`（教师令牌）。

学生令牌过不了教师接口，教师令牌也过不了学生接口 —— 令牌里带了身份类型，
两边各认各的（见 security.TOKEN_TEACHER / TOKEN_STUDENT）。

学生这边一律看不到答案：取卷仍然走 take.py 那套 strip_answers()，
判分也还是在服务端做。这个文件不 import 任何会吐答案的东西。
"""

import io
import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from openpyxl import Workbook
from sqlalchemy import func, select
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
from ..routers.take import _submit_out as submit_out
from ..services.exam import submission_scores
from ..services import roster
from ..services.exam import grade, group_items, load_items, strip_answers
# 名单解析和入库都在 services/roster.py，上传表格和粘贴名单共用那一套。
# 这里只保留单个增改用得到的几个小工具。
from ..services.roster import STUDENT_NO_RE, norm_gender

student_api = APIRouter(prefix="/api/student", tags=["学生平台"])
admin_api = APIRouter(prefix="/api/students", tags=["学生账号管理"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PASSWORD_MIN = 6


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


def initial_password(student_no: str) -> str:
    """初始密码。学号够长就直接用学号，太短则补足到 6 位，保证能通过校验。"""
    return student_no if len(student_no) >= PASSWORD_MIN else (student_no + "123456")[:6]


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
    return StudentTokenOut(
        access_token=create_access_token(row.id, "student", typ=TOKEN_STUDENT),
        student=StudentOut.model_validate(row),
    )


@student_api.get("/me", response_model=StudentOut, summary="当前登录的学生")
def student_me(me: Student = Depends(get_current_student)):
    return me


@student_api.post("/password", summary="学生改自己的密码")
def student_change_password(
    body: StudentPasswordChange,
    me: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
):
    """学号和姓名不给改 —— 那是学校给的身份，改了老师就对不上人了。"""
    if not verify_password(body.old_password, me.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    pwd = check_student_password(body.new_password)
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
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Student)
    if class_id is not None:
        stmt = stmt.where(Student.class_id == class_id)
    if student_class:
        stmt = stmt.where(Student.student_class == student_class)
    if is_active is not None:
        stmt = stmt.where(Student.is_active.is_(is_active))
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(Student.name.like(like) | Student.student_no.like(like))
    stmt = stmt.order_by(Student.student_class, Student.student_no).limit(limit)
    return list(db.scalars(stmt))


@admin_api.get("/classes", response_model=list[str], summary="出现过的班级，供筛选下拉")
def student_classes(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Student.student_class)
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

    if db.scalar(select(Student).where(Student.student_no == no)):
        raise HTTPException(status_code=400, detail=f"学号「{no}」已经有账号了")

    cls = resolve_class(db, body.class_id)
    pwd = check_student_password(body.password) if body.password else initial_password(no)
    row = Student(
        student_no=no,
        name=name[:64],
        class_id=cls.id if cls else None,
        student_class=cls.display if cls else "",
        gender=norm_gender(body.gender),
        password_hash=hash_password(pwd),
        created_by=me.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


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
    fallback = resolve_class(db, body.class_id)
    rows = roster.paste_rows(body.text)
    if not rows:
        raise HTTPException(status_code=400, detail="名单是空的，没有可导入的内容")
    return roster.ingest(
        db, rows, me.id, fallback,
        make_password=initial_password, hash_it=hash_password,
    )


@admin_api.patch("/{sid}", response_model=StudentOut, summary="改学生资料或重置密码")
def update_student(
    sid: int,
    body: StudentUpdate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(Student, sid)
    if not row:
        raise HTTPException(status_code=404, detail="学生不存在")

    data = body.model_dump(exclude_unset=True)
    if data.pop("password", None):
        row.password_hash = hash_password(check_student_password(body.password))

    # 换班时显示名要跟着换，成绩筛选和导出都用那个字符串
    if "class_id" in data:
        cls = resolve_class(db, data.pop("class_id"))
        row.class_id = cls.id if cls else None
        row.student_class = cls.display if cls else ""

    # 性别走归一：界面上是下拉，但接口也可能被别处调用，写法统一到「男/女/空」
    if "gender" in data:
        row.gender = norm_gender(data.pop("gender"))

    for k, v in data.items():
        setattr(row, k, v.strip()[:64] if isinstance(v, str) else v)

    db.commit()
    db.refresh(row)
    return row


@admin_api.post("/bulk", summary="批量启用／停用／删除／重置密码")
def bulk_students(
    body: StudentBulkIn, _: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """删除是真删，界面上要手工输入「删除」两个字才放行。

    删掉学生账号后，他交过的卷子和练过的字都保留（外键置空），
    只是不再挂在账号上 —— 成绩是班级资料，不该跟着账号一起消失。
    """
    ids = list(dict.fromkeys(body.ids))
    if not ids:
        raise HTTPException(status_code=400, detail="没有选中任何学生")

    rows = list(db.scalars(select(Student).where(Student.id.in_(ids))))
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
def student_template(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """三列：学号、姓名、班级。

    班级名必须和「班级」页面里的一模一样，所以模板里直接把现有班级列出来，
    老师照着填就不会错 —— 让人凭记忆敲「七(3)班」还是「七年级3班」，
    十有八九对不上。
    """
    classes = list(
        db.scalars(
            select(SchoolClass)
            .where(SchoolClass.is_active.is_(True))
            .order_by(SchoolClass.sort_order, SchoolClass.grade, SchoolClass.name)
        )
    )
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
        ["初始密码就是学号，学生登录后自己改。"],
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

    fallback = resolve_class(db, class_id)
    result = roster.ingest(
        db, rows, me.id, fallback,
        make_password=initial_password, hash_it=hash_password,
    )
    result["sheets_skipped"] = skipped_sheets
    return result


@admin_api.get("/export.xlsx", summary="导出学生名单")
def export_students(
    class_id: int | None = None,
    keyword: str | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出的表和导入模板同构（学号、姓名在前两列），改完能直接再导回来。"""
    stmt = select(Student)
    if class_id is not None:
        stmt = stmt.where(Student.class_id == class_id)
    if keyword:
        like = f"%{keyword.strip()}%"
        stmt = stmt.where(Student.name.like(like) | Student.student_no.like(like))
    rows = list(db.scalars(stmt.order_by(Student.student_class, Student.student_no)))

    wb = Workbook()
    ws = wb.active
    ws.title = "学生名单"
    # 前四列和导入模板完全一致，导出的表改完可以直接再导回来
    ws.append(["学号", "姓名", "班级", "性别", "状态", "创建时间"])
    for s in rows:
        ws.append([
            s.student_no,
            s.name,
            s.student_class or "未分班",
            s.gender,
            "正常" if s.is_active else "已停用",
            s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "",
        ])
    for col, w in zip("ABCDEF", [16, 12, 16, 8, 10, 18]):
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
