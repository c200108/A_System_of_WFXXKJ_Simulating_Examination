"""打字训练。

学生端（/api/typing/config、/api/typing/records POST）**不需要登录**——
和考试的 /api/take 一样，学生只填班级姓名。
教师端（成绩、统计、导出、删除）需要登录。

评分放在后端做：前端只上报"敲了多少、对了多少、用了多久"这三个原始量，
速度、正确率、星级都由服务端算。这样改评分标准不用重新构建前端，
学生也没法直接伪造一个满分成绩上来（虽然仍能伪造原始量，
但校内工具没必要做到防作弊那一步）。
"""

import io
import math
import re
from datetime import date, datetime, time, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from openpyxl import Workbook
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .. import clock
from ..database import get_db
from ..deps import get_current_user, get_optional_student, require_delete_permission
from ..models import SchoolClass, Student, TypingRecord, TypingText, TypingTheme, User
from ..schemas import (
    IdsIn,
    TypingRecordPage,
    TypingConfigOut,
    TypingTextBulkIn,
    TypingTextIn,
    TypingTextOut,
    TypingTextUpdate,
    TypingThemeIn,
    TypingThemeOut,
    TypingThemeUpdate,
    TypingRecordIn,
    TypingRecordOut,
    TypingResultOut,
    TypingStatsOut,
)
from ..services import recycle, throttle, typing_analysis
from ..services.typing_texts import (
    add_texts,
    build_passage,
    default_theme_id,
    ensure_default_theme,
    parse_txt,
    text_hash,
)
from ..siteconfig import site

router = APIRouter(prefix="/api/typing", tags=["打字训练"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MODULES = ("键盘", "英文", "中文")


def _enabled() -> None:
    if not site.typing.enabled:
        raise HTTPException(status_code=404, detail="打字训练未启用")


def _stars(accuracy: int, speed: int, difficulty: str) -> int:
    """与原页面同一套规则：正确率达标给两星，再高一档且速度够快给三星。"""
    conf = site.typing
    base = getattr(conf.star_thresholds, difficulty, 80)
    if accuracy >= base + 12 and (difficulty == "简单" or speed >= conf.three_star_min_speed):
        return 3
    if accuracy >= base:
        return 2
    if accuracy >= base - 15:
        return 1
    return 0


# ---------------------------------------------------------------- 学生端（公开）
@router.get("/config", response_model=TypingConfigOut, summary="取练习配置与文本（公开）")
def get_config():
    _enabled()
    c = site.typing
    return TypingConfigOut(
        school=site.school.name,
        difficulties=c.difficulties,
        time_limits=c.time_limits,
        default_difficulty=c.default_difficulty,
        default_limit=c.default_limit,
        min_done_ratio=c.min_done_ratio,
        submit_interval_sec=c.submit_interval_sec,
        passage_per_minute=c.passage_per_minute,
    )


def _norm_class(name: str) -> str:
    """班级名比对前统一一下：去空格、全角括号换半角 —— 「七（3）班」和「七(3)班」是同一个班。"""
    return re.sub(r"\s+", "", name or "").replace("（", "(").replace("）", ")")


def _on_roster(db: Session, student_class: str, student_name: str) -> Student | None:
    """免登录页手填的班级 + 姓名，在学生名单里找这个人。找不到返回 None。

    班级两样都认：学生记录上存的班级名，和他所在班级的当前名字（班级改过名也对得上）。
    """
    name = (student_name or "").strip()
    want = _norm_class(student_class)
    if not name or not want:
        return None
    for st in db.scalars(select(Student).where(Student.name == name, Student.is_active.is_(True))):
        names = {_norm_class(st.student_class)}
        if st.class_id:
            cls = db.get(SchoolClass, st.class_id)
            if cls:
                names.add(_norm_class(cls.display))
        if want in names:
            return st
    return None


def _roster_tip(student_class: str, student_name: str) -> str:
    return (f"学生名单里没有「{student_class.strip()} {student_name.strip()}」："
            "请按老师给的名单选班级、填姓名（姓名不要带空格）；确实不在名单里的请找老师添加")


def _not_done(body: TypingRecordIn) -> str:
    """中文英文没打完「一半」（min_done_ratio）就不收，返回原因；够了返回空串。

    **限时练习过了一半时间也算够**：拼出来的文本有 7～9 段，英文简单难度一篇就四五百个字母，
    1 分钟限时的练习谁也敲不完一半，只认字数的话限时练习就永远交不上了。
    exe 不限时（time_limit=0），只认字数。键盘模块不管这一条。
    """
    ratio = site.typing.min_done_ratio
    if body.module == "键盘" or ratio <= 0:
        return ""
    if body.target_chars <= 0:
        return "学生端版本太旧，交不了成绩：网页刷新一下页面，exe 请老师换成新版"
    need = math.ceil(body.target_chars * ratio)
    if body.typed_chars >= need:
        return ""
    limit = body.time_limit if body.time_limit in site.typing.time_limits else 0
    if limit and body.duration >= limit * 60 * ratio:
        return ""
    pct = round(ratio * 100)
    tip = f"要打完 {pct}% 才能交成绩：这段 {body.target_chars} 字，你敲了 {body.typed_chars} 字，至少要 {need} 字"
    if limit:
        tip += f"（或者练满 {math.ceil(limit * ratio * 10) / 10:g} 分钟）"
    return tip


@router.get("/passage", summary="按难度随机取一篇练习文本（公开）")
def get_passage(
    request: Request,
    mode: str = Query(..., pattern="^(english|chinese)$"),
    difficulty: str = Query(...),
    db: Session = Depends(get_db),
):
    """文本来自数据库，老师可在「打字」页增删改或上传 txt 批量导入。

    同一台电脑每分钟最多取 passage_per_minute 次 —— 不限的话有人一直点「换一段」挑短的。
    """
    _enabled()
    who = throttle.device_of(request)
    n = site.typing.passage_per_minute
    throttle.check(db, "passage", who, n, 60, f"换文本太频繁了，同一台电脑每分钟最多换 {n} 次")
    text = build_passage(db, mode, difficulty)
    if not text:
        raise HTTPException(
            status_code=404,
            detail=f"启用的主题里，「{difficulty}」难度下还没有{'英文' if mode == 'english' else '中文'}文本，"
            "请老师在「题库 → 练习文本」添加文本或启用主题",
        )
    throttle.hit(db, "passage", who)
    db.commit()
    return {"text": text}


@router.get("/roster-classes", response_model=list[str], summary="名单里的班级，供免登录页下拉（公开）")
def roster_classes(db: Session = Depends(get_db)):
    """免登录打字页的班级下拉：只有班级名，不带任何学生信息。"""
    _enabled()
    names = {c.display for c in db.scalars(select(SchoolClass).where(SchoolClass.is_active.is_(True)))}
    names |= {r[0] for r in db.execute(
        select(Student.student_class).where(Student.is_active.is_(True)).distinct()) if r[0]}
    return sorted(names)


@router.get("/check-student", summary="手填的班级姓名在不在名单里（公开）")
def check_student(
    request: Request,
    student_class: str = Query("", max_length=64),
    student_name: str = Query("", max_length=64),
    db: Session = Depends(get_db),
):
    """免登录页点「开始」前先问一声，别等练完了才告诉学生交不上。只回对不对，不回任何学生信息。"""
    _enabled()
    if not site.typing.require_roster:
        return {"ok": True}
    # 一分钟最多问 30 次：防的是拿名字一个个去试
    throttle.check(db, "roster", throttle.device_of(request), 30, 60, "查询太频繁了")
    throttle.hit(db, "roster", throttle.device_of(request))
    db.commit()
    ok = _on_roster(db, student_class, student_name) is not None
    return {"ok": ok, "tip": "" if ok else _roster_tip(student_class, student_name)}


@router.post("/records", response_model=TypingResultOut, summary="学生交成绩（公开）")
def submit_record(
    body: TypingRecordIn,
    request: Request,
    me: Student | None = Depends(get_optional_student),
    db: Session = Depends(get_db),
):
    _enabled()
    # **认领到账号上。** 首页那三个数字（练习次数、最快速度、平均正确率）只统计
    # 挂了账号的记录，没挂上的话成绩照样入库、老师也看得见，但学生自己的首页
    # 永远是 0 —— 桌面端就踩过这个（交卷那条路 4.4.0 修过，打字这条漏了）。
    #
    # 令牌优先；没令牌或者令牌过期了，就按学号认领。学号是全校唯一的，
    # 认得准；认不上（校外的公开页面、学号写错）就照旧留空，不挡着交成绩。
    if not me and body.student_no.strip():
        me = db.scalar(select(Student).where(
            Student.student_no == body.student_no.strip(), Student.is_active.is_(True)))

    # 免登录页手填的：班级 + 姓名必须在学生名单里（config.yaml 的 typing.require_roster）。
    # 对上了就挂到那个学生账号上 —— 他自己的首页也能看到这次练习
    if (not me and site.typing.require_roster
            and body.student_class.strip() and body.student_name.strip()):
        me = _on_roster(db, body.student_class, body.student_name)
        if not me:
            raise HTTPException(status_code=400, detail=_roster_tip(body.student_class, body.student_name))

    # 带着账号来的，班级姓名一律以账号为准，前端填什么都不算数，
    # 免得改个输入框就把成绩记到别人头上。公开页面来的还是手填。
    if me:
        body.student_name, body.student_class = me.name, me.student_class
    if not body.student_name.strip() or not body.student_class.strip():
        raise HTTPException(status_code=400, detail="请填写班级和姓名")
    if body.module not in MODULES:
        raise HTTPException(status_code=400, detail=f"模块只能是 {'/'.join(MODULES)}")
    why = _not_done(body)
    if why:
        raise HTTPException(status_code=400, detail=why)
    # 放在最后判：前面几条不过的根本没交上，不该占这一分钟的名额
    who = throttle.device_of(request)
    gap = site.typing.submit_interval_sec
    throttle.check(db, "submit", who, 1, gap,
                   f"交得太快了，同一台电脑每 {gap} 秒只能交一次成绩" if gap != 60
                   else "交得太快了，同一台电脑每分钟只能交一次成绩")

    typed = max(0, body.typed_chars)
    correct = max(0, min(body.correct_chars, typed))
    secs = max(1, round(body.duration))

    accuracy = round(correct / typed * 100) if typed else 0
    # 键盘模块统计的是按键次数，算"字/分"没有意义，统一记 0
    speed = 0 if body.module == "键盘" else round(correct / (secs / 60))
    stars = _stars(accuracy, speed, body.difficulty)

    rec = TypingRecord(
        student_id=me.id if me else None,
        student_name=body.student_name.strip()[:64],
        student_class=body.student_class.strip()[:64],
        module=body.module,
        difficulty=body.difficulty,
        speed=speed,
        accuracy=accuracy,
        duration=secs,
        typed_chars=typed,
        stars=stars,
    )
    db.add(rec)
    throttle.hit(db, "submit", who)
    db.commit()

    return TypingResultOut(
        module=body.module, speed=speed, accuracy=accuracy,
        duration=secs, stars=stars, difficulty=body.difficulty,
    )


# ---------------------------------------------------------------- 教师端（要登录）
class RecordFilter:
    """成绩页的筛选条件。分页查询、导出、按条件删除用的是同一份，删掉的正是看到的。"""

    def __init__(
        self,
        student_class: str = "",
        module: str = "",
        difficulty: str = "",
        keyword: str = Query("", max_length=64),
        date_from: date | None = None,
        date_to: date | None = None,
    ):
        self.student_class, self.module, self.difficulty = student_class, module, difficulty
        self.keyword = keyword.strip()
        self.date_from, self.date_to = date_from, date_to

    def apply(self, stmt):
        if self.student_class:
            stmt = stmt.where(TypingRecord.student_class == self.student_class)
        if self.module:
            stmt = stmt.where(TypingRecord.module == self.module)
        if self.difficulty:
            stmt = stmt.where(TypingRecord.difficulty == self.difficulty)
        if self.keyword:
            stmt = stmt.where(TypingRecord.student_name.like(f"%{self.keyword}%"))
        if self.date_from:
            stmt = stmt.where(TypingRecord.created_at >= datetime.combine(self.date_from, time.min))
        if self.date_to:
            stmt = stmt.where(TypingRecord.created_at < datetime.combine(self.date_to + timedelta(days=1), time.min))
        return stmt

    @property
    def empty(self) -> bool:
        return not any((self.student_class, self.module, self.difficulty, self.keyword,
                        self.date_from, self.date_to))


SORTS = {
    "speed": TypingRecord.speed, "accuracy": TypingRecord.accuracy, "duration": TypingRecord.duration,
    "stars": TypingRecord.stars, "time": TypingRecord.created_at, "name": TypingRecord.student_name,
    "class": TypingRecord.student_class,
}


@router.get("/records/search", response_model=TypingRecordPage, summary="成绩：筛选 + 排序 + 分页")
def search_records(
    f: RecordFilter = Depends(),
    sort: str = Query("time", pattern="^(" + "|".join(SORTS) + ")$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    total = db.scalar(f.apply(select(func.count()).select_from(TypingRecord))) or 0
    col = SORTS[sort]
    stmt = f.apply(select(TypingRecord)).order_by(
        col.desc() if order == "desc" else col.asc(), TypingRecord.id.desc())
    items = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).all()
    return TypingRecordPage(total=total, items=list(items))


@router.post("/records/delete", summary="批量删除勾选的成绩（需要删除权）")
def delete_records(
    body: IdsIn,
    me: User = Depends(require_delete_permission),
    db: Session = Depends(get_db),
):
    ids = list(dict.fromkeys(body.ids))
    if not ids:
        raise HTTPException(status_code=400, detail="没有勾选任何成绩")
    _trash_records(db, me, ids)
    n = recycle.delete_ids(db, TypingRecord, ids)
    db.commit()
    return {"deleted": n}


def _trash_records(db: Session, me: User, ids: list[int], f: "RecordFilter | None" = None) -> None:
    """打字成绩进回收站。标题里写上是哪个班、什么条件，回收站里一眼认得出。"""
    where = []
    if f is not None:
        where = [x for x in (f.student_class, f.module, f.difficulty,
                             f.keyword and f"姓名含「{f.keyword}」") if x]
        if f.date_from or f.date_to:
            where.append(f"{f.date_from or '…'} 至 {f.date_to or '…'}")
    first = db.get(TypingRecord, ids[0]) if len(ids) == 1 else None
    title = (f"{first.student_name}（{first.student_class}）的 {first.module} 打字成绩"
             if first else f"{len(ids)} 条打字成绩")
    recycle.trash(db, me, "typing_record", title, TypingRecord, ids,
                  detail="筛选：" + "，".join(where) if where else "")


@router.get("/analysis", summary="打字学情分析（可视化页用）")
def analysis(
    module: str = Query("", pattern="^(|中文|英文|键盘)$"),
    days: int = Query(30, ge=0, le=3650),
    classes: list[str] = Query([]),
    students: list[str] = Query([]),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """module：只看一个模块（速度只在中文 / 英文里比）；days：最近几天，0 = 全部；
    classes：只看这几个班；students：几个学生对比（「班级|姓名」）。都不给就是全体。"""
    stmt = select(TypingRecord)
    if module:
        stmt = stmt.where(TypingRecord.module == module)
    today = clock.today()
    if days:
        stmt = stmt.where(TypingRecord.created_at >= datetime.combine(today - timedelta(days=days - 1), time.min))
    everyone = list(db.scalars(stmt))

    want_students = {s for s in students if s.strip()}
    want_classes = {c.strip() for c in classes if c.strip()}
    if want_students:
        rows, scope = [r for r in everyone if typing_analysis.key_of(r) in want_students], {"kind": "students"}
    elif want_classes:
        rows = [r for r in everyone if (r.student_class or "未填班级") in want_classes]
        scope = {"kind": "classes", "classes": sorted(want_classes)}
    else:
        rows, scope = everyone, {"kind": "all"}

    roster = dict(db.execute(
        select(Student.student_class, func.count()).where(Student.is_active.is_(True))
        .group_by(Student.student_class)).all())
    result = typing_analysis.analyze(rows, module, scope, roster, today, days)

    by_key: dict = {}
    for r in everyone:
        k = typing_analysis.key_of(r)
        o = by_key.setdefault(k, {"key": k, "name": r.student_name,
                                  "class": r.student_class or "未填班级", "count": 0})
        o["count"] += 1
    result["options"] = {
        "classes": sorted({r.student_class or "未填班级" for r in everyone}),
        "students": sorted(by_key.values(), key=lambda o: (o["class"], o["name"])),
    }
    result["days"] = days
    result["updated_at"] = clock.now().isoformat(sep=" ", timespec="seconds")
    return result


@router.get("/records", response_model=list[TypingRecordOut], summary="成绩列表")
def list_records(
    student_class: str | None = None,
    module: str | None = None,
    keyword: str | None = None,
    order: str = Query("speed", pattern="^(speed|accuracy|time)$"),
    limit: int = Query(200, ge=1, le=2000),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(TypingRecord)
    if student_class:
        stmt = stmt.where(TypingRecord.student_class == student_class)
    if module:
        stmt = stmt.where(TypingRecord.module == module)
    if keyword:
        stmt = stmt.where(TypingRecord.student_name.like(f"%{keyword}%"))

    if order == "accuracy":
        stmt = stmt.order_by(TypingRecord.accuracy.desc(), TypingRecord.speed.desc())
    elif order == "time":
        stmt = stmt.order_by(TypingRecord.created_at.desc())
    else:
        stmt = stmt.order_by(TypingRecord.speed.desc(), TypingRecord.accuracy.desc())

    return list(db.scalars(stmt.limit(limit)))


@router.get("/stats", response_model=TypingStatsOut, summary="学情统计")
def stats(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(TypingRecord)) or 0
    if not total:
        return TypingStatsOut(total=0)

    avg_acc = db.scalar(select(func.avg(TypingRecord.accuracy))) or 0
    avg_dur = db.scalar(select(func.avg(TypingRecord.duration))) or 0
    # 键盘模块速度恒为 0，算平均速度时要排除，否则会把均值拉低
    avg_spd = db.scalar(
        select(func.avg(TypingRecord.speed)).where(TypingRecord.speed > 0)
    ) or 0

    students = db.scalar(
        select(func.count()).select_from(
            select(TypingRecord.student_class, TypingRecord.student_name)
            .distinct()
            .subquery()
        )
    ) or 0

    by_module = dict(
        db.execute(
            select(TypingRecord.module, func.count()).group_by(TypingRecord.module)
        ).all()
    )

    # 正确率分布，和原页面一样分四档
    buckets = {"≥90": 0, "80-89": 0, "70-79": 0, "<70": 0}
    for (acc,) in db.execute(select(TypingRecord.accuracy)).all():
        key = "≥90" if acc >= 90 else "80-89" if acc >= 80 else "70-79" if acc >= 70 else "<70"
        buckets[key] += 1

    by_class = [
        {
            "student_class": row[0],
            "count": row[1],
            "avg_accuracy": round(row[2] or 0),
            "avg_speed": round(row[3] or 0),
        }
        for row in db.execute(
            select(
                TypingRecord.student_class,
                func.count(),
                func.avg(TypingRecord.accuracy),
                func.avg(TypingRecord.speed),
            )
            .group_by(TypingRecord.student_class)
            .order_by(func.avg(TypingRecord.accuracy).desc())
        ).all()
    ]

    return TypingStatsOut(
        total=total,
        students=students,
        avg_accuracy=round(avg_acc),
        avg_speed=round(avg_spd),
        avg_duration=round(avg_dur),
        by_module=by_module,
        accuracy_buckets=buckets,
        by_class=by_class,
    )


@router.get("/classes", response_model=list[str], summary="出现过的班级，供筛选下拉")
def classes(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(TypingRecord.student_class).distinct().order_by(TypingRecord.student_class)
    ).all()
    return [r[0] for r in rows]


@router.get("/export.xlsx", summary="导出成绩 Excel")
def export_xlsx(
    f: RecordFilter = Depends(),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """导出的是成绩页上**当前筛选**出来的那些（没筛就是全部）。"""
    rows = db.scalars(f.apply(select(TypingRecord)).order_by(TypingRecord.created_at.desc())).all()

    wb = Workbook()
    ws = wb.active
    ws.title = "打字成绩"
    ws.append(["姓名", "班级", "模块", "难度", "速度(字/分)", "正确率%", "用时(秒)", "敲字数", "星级", "时间"])
    for r in rows:
        ws.append([
            r.student_name, r.student_class, r.module, r.difficulty,
            r.speed or "", r.accuracy, r.duration, r.typed_chars, r.stars,
            r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
        ])
    for col, w in zip("ABCDEFGHIJ", [12, 14, 8, 8, 12, 9, 10, 9, 7, 20]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    name = quote("打字训练成绩.xlsx")
    return Response(
        content=buf.getvalue(),
        media_type=XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"},
    )


@router.delete("/records/{record_id}", summary="删除一条成绩（需要删除权）")
def delete_record(
    record_id: int,
    me: User = Depends(require_delete_permission),
    db: Session = Depends(get_db),
):
    rec = db.get(TypingRecord, record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="记录不存在")
    _trash_records(db, me, [rec.id])
    db.delete(rec)
    db.commit()
    return {"ok": True}


@router.delete("/records", summary="按筛选条件删除成绩，不带条件就是清空（需要删除权）")
def clear_records(
    f: RecordFilter = Depends(),
    me: User = Depends(require_delete_permission),
    db: Session = Depends(get_db),
):
    """条件和成绩页的筛选一样 —— 页面上「删除筛选出的 N 条」删掉的正是看到的那 N 条。

    **先把 id 查出来再按 id 删。** 原来写的是一条
    `DELETE FROM typing_records WHERE id IN (SELECT id FROM typing_records WHERE …)`，
    SQLite 认、MySQL 不认（错误 1093：不能在子查询里读正在删的表），
    于是正式服务器上一点「删除筛选出的全部」就 500，管理员和老师都一样。
    """
    ids = list(db.scalars(f.apply(select(TypingRecord.id))))
    if ids:
        _trash_records(db, me, ids, f)
    n = recycle.delete_ids(db, TypingRecord, ids)
    db.commit()
    return {"ok": True, "deleted": n}


# ---------------------------------------------------------------- 文本库管理（要登录）
@router.get("/texts", response_model=list[TypingTextOut], summary="文本列表")
def list_texts(
    mode: str | None = None,
    difficulty: str | None = None,
    keyword: str | None = None,
    theme_id: int | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(TypingText)
    if theme_id:
        stmt = stmt.where(_in_theme(db, theme_id))
    if mode:
        stmt = stmt.where(TypingText.mode == mode)
    if difficulty:
        stmt = stmt.where(TypingText.difficulty == difficulty)
    if keyword:
        stmt = stmt.where(TypingText.content.like(f"%{keyword}%"))
    return list(db.scalars(stmt.order_by(TypingText.id.desc()).limit(500)))


@router.get("/texts/stats", summary="每种模式各难度有多少段")
def text_stats(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(TypingText.mode, TypingText.difficulty, func.count())
        .where(TypingText.is_active.is_(True))
        .group_by(TypingText.mode, TypingText.difficulty)
    ).all()
    out: dict[str, dict[str, int]] = {"english": {}, "chinese": {}}
    for mode, diff, n in rows:
        out.setdefault(mode, {})[diff] = n
    return out


@router.post("/texts", response_model=TypingTextOut, summary="新增一段文本")
def create_text(
    body: TypingTextIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content = body.content.strip()
    if len(content) < 5:
        raise HTTPException(status_code=400, detail="文本太短，至少 5 个字符")

    h = text_hash(content)
    if db.scalar(select(TypingText).where(TypingText.content_hash == h)):
        raise HTTPException(status_code=409, detail="这段文本已经在库里了")

    row = TypingText(
        mode=body.mode,
        difficulty=body.difficulty,
        content=content,
        content_hash=h,
        source="自定义",
        created_by=user.id,
        theme_id=_theme_or_default(db, body.theme_id),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/texts/{text_id}", response_model=TypingTextOut, summary="改一段文本")
def update_text(
    text_id: int,
    body: TypingTextUpdate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(TypingText, text_id)
    if not row:
        raise HTTPException(status_code=404, detail="文本不存在")

    data = body.model_dump(exclude_unset=True)
    if "content" in data:
        content = data["content"].strip()
        if len(content) < 5:
            raise HTTPException(status_code=400, detail="文本太短，至少 5 个字符")
        h = text_hash(content)
        other = db.scalar(
            select(TypingText).where(TypingText.content_hash == h, TypingText.id != text_id)
        )
        if other:
            raise HTTPException(status_code=409, detail="改成的内容和库里另一段重复了")
        row.content = content
        row.content_hash = h
        data.pop("content")
    if "theme_id" in data:
        data["theme_id"] = _theme_or_default(db, data["theme_id"])

    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/texts/{text_id}", summary="删一段文本")
def delete_text(
    text_id: int, me: User = Depends(require_delete_permission), db: Session = Depends(get_db)
):
    row = db.get(TypingText, text_id)
    if not row:
        raise HTTPException(status_code=404, detail="文本不存在")
    recycle.trash(db, me, "typing_text", f"练习文本：{(row.content or '')[:40]}", TypingText, [row.id])
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/texts/bulk", summary="批量操作选中的文本（删除／启用／停用）")
def bulk_texts(
    body: TypingTextBulkIn,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """界面上勾一批再一次性处理，省得一条条点。

    action=delete 删除，enable/disable 改启用状态。
    id 是前端勾出来的，不存在的直接忽略，不报错 —— 多半是别人已经删了。
    """
    ids = list(dict.fromkeys(body.ids))  # 去重且保持顺序
    if not ids:
        raise HTTPException(status_code=400, detail="没有选中任何文本")
    if len(ids) > 2000:
        raise HTTPException(status_code=400, detail="一次最多处理 2000 段")

    # 启停谁都能做，删除要权限 —— 在这里判而不是挂依赖，
    # 因为同一个接口三种动作，权限要求不一样
    if body.action == "delete" and me.role != "admin" and not me.can_delete:
        raise HTTPException(
            status_code=403,
            detail="你还没有删除权限。练习文本是全校共用的，"
            "需要请管理员在「账号」页面给你开通「删除权」后再操作。",
        )

    if body.action == "theme":
        tid = _theme_or_default(db, body.theme_id)
    rows = db.scalars(select(TypingText).where(TypingText.id.in_(ids))).all()
    if body.action == "theme":
        for r in rows:
            r.theme_id = tid
    elif body.action == "delete":
        if rows:
            recycle.trash(db, me, "typing_text", f"{len(rows)} 段练习文本", TypingText,
                          [r.id for r in rows], detail=(rows[0].content or "")[:40])
        for r in rows:
            db.delete(r)
    else:
        want = body.action == "enable"
        for r in rows:
            r.is_active = want
    db.commit()
    return {"action": body.action, "affected": len(rows), "requested": len(ids)}


@router.post("/texts/import", summary="上传 txt 批量导入")
async def import_texts(
    mode: str = Query(..., pattern="^(english|chinese)$"),
    difficulty: str = Query(...),
    split: str = Query("line", pattern="^(line|blank)$"),
    theme_id: int | None = Query(None, description="归到哪个主题，不给就是「信息生活」"),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """split=line 一行一段（默认）；split=blank 空行分段。重复的自动跳过。"""
    if not (file.filename or "").lower().endswith(".txt"):
        raise HTTPException(status_code=400, detail="只支持 .txt 文件")

    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件不能超过 2 MB")

    try:
        chunks = parse_txt(raw, split)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not chunks:
        raise HTTPException(status_code=400, detail="这个文件里没读到内容")

    tid = _theme_or_default(db, theme_id)
    res = add_texts(db, mode, difficulty, chunks, source="导入", created_by=user.id, theme_id=tid)
    res["total"] = len(chunks)
    return res


# ---------------------------------------------------------------- 主题（2.15.0，要登录）
def _theme_or_default(db: Session, theme_id: int | None) -> int:
    """给了主题就核对一下它在不在，没给就归内置的「信息生活」。"""
    if theme_id:
        if not db.get(TypingTheme, theme_id):
            raise HTTPException(status_code=400, detail="这个主题不存在（可能刚被删了），刷新一下再选")
        return theme_id
    return default_theme_id(db) or ensure_default_theme(db)


def _in_theme(db: Session, theme_id: int):
    """属于这个主题的文本。theme_id 为空的文本算内置主题的。"""
    if theme_id == default_theme_id(db):
        return (TypingText.theme_id == theme_id) | TypingText.theme_id.is_(None)
    return TypingText.theme_id == theme_id


def _theme_out(db: Session, row: TypingTheme) -> TypingThemeOut:
    default = default_theme_id(db)
    stmt = (select(TypingText.mode, TypingText.difficulty, func.count())
            .where(TypingText.is_active.is_(True), _in_theme(db, row.id))
            .group_by(TypingText.mode, TypingText.difficulty))
    counts: dict = {}
    total = 0
    for mode, diff, n in db.execute(stmt).all():
        counts.setdefault(mode, {})[diff] = n
        total += n
    out = TypingThemeOut.model_validate(row)
    out.counts, out.total = counts, total
    out.is_builtin = row.is_builtin or row.id == default
    return out


def _keep_one_enabled(db: Session) -> None:
    if not db.scalar(select(TypingTheme.id).where(TypingTheme.is_enabled.is_(True)).limit(1)):
        raise HTTPException(status_code=400,
                            detail="至少要保留一个启用的主题，不然学生取不到练习文本")


@router.get("/themes", response_model=list[TypingThemeOut], summary="主题列表（带各难度文本数）")
def list_themes(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ensure_default_theme(db)
    rows = db.scalars(select(TypingTheme).order_by(TypingTheme.sort_order, TypingTheme.id))
    return [_theme_out(db, r) for r in rows]


@router.post("/themes", response_model=TypingThemeOut, summary="新增主题")
def create_theme(body: TypingThemeIn, _: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="主题名不能为空")
    if db.scalar(select(TypingTheme.id).where(TypingTheme.name == name)):
        raise HTTPException(status_code=409, detail=f"已经有「{name}」这个主题了")
    last = db.scalar(select(func.max(TypingTheme.sort_order))) or 0
    row = TypingTheme(name=name, is_enabled=True, sort_order=last + 1, is_builtin=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _theme_out(db, row)


@router.put("/themes/{theme_id}", response_model=TypingThemeOut, summary="改主题：名称、启用、排序")
def update_theme(theme_id: int, body: TypingThemeUpdate, _: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    row = db.get(TypingTheme, theme_id)
    if not row:
        raise HTTPException(status_code=404, detail="主题不存在")
    data = body.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        name = data["name"].strip()
        if not name:
            raise HTTPException(status_code=400, detail="主题名不能为空")
        if db.scalar(select(TypingTheme.id).where(TypingTheme.name == name, TypingTheme.id != theme_id)):
            raise HTTPException(status_code=409, detail=f"已经有「{name}」这个主题了")
        row.name = name
    if data.get("is_enabled") is not None:
        row.is_enabled = data["is_enabled"]
    if data.get("sort_order") is not None:
        row.sort_order = data["sort_order"]
    db.flush()
    _keep_one_enabled(db)
    db.commit()
    db.refresh(row)
    return _theme_out(db, row)


@router.delete("/themes/{theme_id}", summary="删除主题（文本归回「信息生活」；需要删除权）")
def delete_theme(theme_id: int, me: User = Depends(require_delete_permission),
                 db: Session = Depends(get_db)):
    """主题删了，它下面的文本**不删**，归回内置的「信息生活」（停用的照样停用）。
    进回收站：还原主题时，这些文本会接回原来的主题。"""
    row = db.get(TypingTheme, theme_id)
    if not row:
        raise HTTPException(status_code=404, detail="主题不存在")
    default = default_theme_id(db)
    if row.is_builtin or row.id == default:
        raise HTTPException(status_code=400, detail="内置主题「信息生活」不能删除")
    moved = db.scalar(select(func.count()).select_from(TypingText).where(TypingText.theme_id == row.id))
    recycle.trash(db, me, "typing_theme", f"打字主题：{row.name}", TypingTheme, [row.id],
                  detail=f"{moved} 段文本归回「信息生活」")
    # 置空 = 算内置主题；不直接改成内置主题的 id，回收站还原时才接得回去（只接还是空的那些）
    db.execute(update(TypingText).where(TypingText.theme_id == row.id).values(theme_id=None))
    db.delete(row)
    db.flush()
    if not db.scalar(select(TypingTheme.id).where(TypingTheme.is_enabled.is_(True)).limit(1)) and default:
        db.get(TypingTheme, default).is_enabled = True     # 删的是唯一启用的那个：把内置的打开
    db.commit()
    return {"ok": True, "moved": moved}