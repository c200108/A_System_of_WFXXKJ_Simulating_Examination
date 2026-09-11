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
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from openpyxl import Workbook
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, get_optional_student
from ..models import Student, TypingRecord, TypingText, User
from ..schemas import (
    TypingConfigOut,
    TypingTextBulkIn,
    TypingTextIn,
    TypingTextOut,
    TypingTextUpdate,
    TypingRecordIn,
    TypingRecordOut,
    TypingResultOut,
    TypingStatsOut,
)
from ..services.typing_texts import add_texts, build_passage, parse_txt, text_hash
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
    db: Session = Depends(get_db),
):
    """文本来自数据库，老师可在「打字」页增删改或上传 txt 批量导入。"""
    _enabled()
    text = build_passage(db, mode, difficulty)
    if not text:
        raise HTTPException(
            status_code=404,
            detail=f"「{difficulty}」难度下还没有{'英文' if mode == 'english' else '中文'}文本，请老师先在打字页添加",
        )
    return {"text": text}


@router.post("/records", response_model=TypingResultOut, summary="学生交成绩（公开）")
def submit_record(
    body: TypingRecordIn,
    me: Student | None = Depends(get_optional_student),
    db: Session = Depends(get_db),
):
    _enabled()
    # 学生平台上带着令牌来的，班级姓名一律以账号为准，前端填什么都不算数，
    # 免得改个输入框就把成绩记到别人头上。公开页面来的还是手填。
    if me:
        body.student_name, body.student_class = me.name, me.student_class
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


# ---------------------------------------------------------------- 文本库管理（要登录）
@router.get("/texts", response_model=list[TypingTextOut], summary="文本列表")
def list_texts(
    mode: str | None = None,
    difficulty: str | None = None,
    keyword: str | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(TypingText)
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

    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/texts/{text_id}", summary="删一段文本")
def delete_text(
    text_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    row = db.get(TypingText, text_id)
    if not row:
        raise HTTPException(status_code=404, detail="文本不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/texts/bulk", summary="批量操作选中的文本（删除／启用／停用）")
def bulk_texts(
    body: TypingTextBulkIn,
    _: User = Depends(get_current_user),
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

    rows = db.scalars(select(TypingText).where(TypingText.id.in_(ids))).all()
    if body.action == "delete":
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

    res = add_texts(db, mode, difficulty, chunks, source="导入", created_by=user.id)
    res["total"] = len(chunks)
    return res
