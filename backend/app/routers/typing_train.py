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
import random
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import TypingRecord, User
from ..schemas import (
    TypingConfigOut,
    TypingRecordIn,
    TypingRecordOut,
    TypingResultOut,
    TypingStatsOut,
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
    )


@router.get("/passage", summary="按难度随机取一篇练习文本（公开）")
def get_passage(
    mode: str = Query(..., pattern="^(english|chinese)$"),
    difficulty: str = Query(...),
):
    """每次随机洗牌拼几段，保证限时练习有足够内容，且两次不会完全一样。"""
    _enabled()
    c = site.typing
    lib = (c.english if mode == "english" else c.chinese).get(difficulty)
    if not lib:
        raise HTTPException(status_code=404, detail=f"「{difficulty}」难度下没有配置{mode}文本")

    pool = list(lib)
    random.shuffle(pool)
    lo, hi = (c.passages_per_round + [7, 9])[:2]
    count = min(len(pool), random.randint(min(lo, hi), max(lo, hi)))
    sep = " " if mode == "english" else ""
    return {"text": sep.join(pool[:count]).rstrip()}


@router.post("/records", response_model=TypingResultOut, summary="学生交成绩（公开）")
def submit_record(body: TypingRecordIn, db: Session = Depends(get_db)):
    _enabled()
    if not body.student_name.strip() or not body.student_class.strip():
        raise HTTPException(status_code=400, detail="请填写班级和姓名")
    if body.module not in MODULES:
        raise HTTPException(status_code=400, detail=f"模块只能是 {'/'.join(MODULES)}")

    typed = max(0, body.typed_chars)
    correct = max(0, min(body.correct_chars, typed))
    secs = max(1, round(body.duration))

    accuracy = round(correct / typed * 100) if typed else 0
    # 键盘模块统计的是按键次数，算"字/分"没有意义，统一记 0
    speed = 0 if body.module == "键盘" else round(correct / (secs / 60))
    stars = _stars(accuracy, speed, body.difficulty)

    rec = TypingRecord(
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
    db.commit()

    return TypingResultOut(
        module=body.module, speed=speed, accuracy=accuracy,
        duration=secs, stars=stars, difficulty=body.difficulty,
    )


# ---------------------------------------------------------------- 教师端（要登录）
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
def export_xlsx(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(TypingRecord).order_by(TypingRecord.created_at.desc())).all()

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


@router.delete("/records/{record_id}", summary="删除一条成绩")
def delete_record(
    record_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    rec = db.get(TypingRecord, record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(rec)
    db.commit()
    return {"ok": True}


@router.delete("/records", summary="清空成绩（可按班级）")
def clear_records(
    student_class: str | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = delete(TypingRecord)
    if student_class:
        stmt = stmt.where(TypingRecord.student_class == student_class)
    n = db.execute(stmt).rowcount
    db.commit()
    return {"ok": True, "deleted": n}
