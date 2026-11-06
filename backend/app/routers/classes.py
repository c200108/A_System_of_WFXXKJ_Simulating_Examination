"""班级管理。

班级原来只是一串手打的文字，"七(3)班"和"七3班"是两个班，老师和学生各打各的
就对不上。改成一张表之后，两边都从下拉里选同一个 id。

班级归属决定了**谁能给谁发考试**：
- 老师只能给自己名下的班发考试；
- 管理员发的考试全体学生都收得到。

增删改班级只有管理员能做 —— 班级是全校的组织结构，不该让任课老师随手改。
老师能看列表（发考试要选班），也能看出哪些班是自己的。
"""

import os
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import ClassLog, SchoolClass, Student, StudentPoint, User, now_local
from ..services import recycle, seating
from ..schemas import (
    ClassBatchIn,
    ClassBulkIn,
    ClassBulkOwnerIn,
    ClassIn,
    ClassLogIn,
    ClassLogOut,
    ClassOut,
    ClassUpdate,
    PointIn,
    PointOut,
    SeatPlanIn,
    SeatSheetIn,
)

router = APIRouter(prefix="/api/classes", tags=["班级"])


def _out(row: SchoolClass, student_count: int = 0) -> ClassOut:
    return ClassOut(
        id=row.id,
        grade=row.grade,
        name=row.name,
        display=row.display,
        owner_id=row.owner_id,
        owner_name=(row.owner.name or row.owner.username) if row.owner else "",
        is_active=row.is_active,
        student_count=student_count,
        seat_kind=seat_kind(row.seat_file),
        seat_name=row.seat_name or "",
        seat_url=f"/uploads/seats/{row.seat_file}" if row.seat_file else "",
        has_seat_sheet=bool(row.seat_sheet),
    )


# ================================================================ 上机座次表
SEAT_IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
SEAT_SHEET = {".xls", ".xlsx"}


def seat_kind(name: str) -> str:
    ext = os.path.splitext(name or "")[1].lower()
    return "image" if ext in SEAT_IMAGE else "sheet" if ext in SEAT_SHEET else ""


def _seat_dir() -> str:
    path = os.path.join(settings.upload_dir, "seats")
    os.makedirs(path, exist_ok=True)
    return path


def _can_seat(row: SchoolClass, me: User) -> None:
    """座次表是班里的事：班主任（名下的老师）和管理员能传、能删。"""
    if me.role != "admin" and row.owner_id != me.id:
        raise HTTPException(status_code=403, detail=f"「{row.display}」不是你带的班，不能改它的座次表")



def owned_class_ids(db: Session, user: User) -> set[int] | None:
    """这位老师管得着哪些班。管理员返回 None，表示不设限。"""
    if user.role == "admin":
        return None
    return {
        c.id
        for c in db.scalars(select(SchoolClass).where(SchoolClass.owner_id == user.id))
    }


@router.get("", response_model=list[ClassOut], summary="班级列表")
def list_classes(
    mine: bool = Query(False, description="只看自己名下的班"),
    include_inactive: bool = Query(False),
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(SchoolClass)
    if not include_inactive:
        stmt = stmt.where(SchoolClass.is_active.is_(True))
    if mine and me.role != "admin":
        stmt = stmt.where(SchoolClass.owner_id == me.id)
    elif mine:
        # 管理员点"只看我的"就看自己名下的，不是看全部
        stmt = stmt.where(SchoolClass.owner_id == me.id)

    rows = db.scalars(
        stmt.order_by(SchoolClass.sort_order, SchoolClass.grade, SchoolClass.name)
    ).all()

    counts = dict(
        db.execute(
            select(Student.class_id, func.count()).group_by(Student.class_id)
        ).all()
    )
    return [_out(r, counts.get(r.id, 0)) for r in rows]


@router.post("", response_model=ClassOut, summary="新建班级（管理员）")
def create_class(
    body: ClassIn, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    grade = (body.grade or "").strip()
    name = (body.name or "").strip()
    if not grade:
        raise HTTPException(status_code=400, detail="年级不能为空")
    if not name:
        raise HTTPException(status_code=400, detail="班级名不能为空")

    if db.scalar(
        select(SchoolClass).where(SchoolClass.grade == grade, SchoolClass.name == name)
    ):
        raise HTTPException(status_code=400, detail=f"「{grade}{name}」已经存在了")

    row = SchoolClass(
        grade=grade[:16],
        name=name[:32],
        owner_id=body.owner_id,
        sort_order=body.sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/batch", summary="按年级批量建班（管理员）")
def batch_classes(
    body: ClassBatchIn, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    """比如七年级 1~12 班，一次建完，不用点十二回。"""
    grade = (body.grade or "").strip()
    if not grade:
        raise HTTPException(status_code=400, detail="年级不能为空")
    if body.start > body.end:
        raise HTTPException(status_code=400, detail="起始班号不能大于结束班号")
    if body.end - body.start >= 60:
        raise HTTPException(status_code=400, detail="一次最多建 60 个班")

    existing = {
        c.name
        for c in db.scalars(select(SchoolClass).where(SchoolClass.grade == grade))
    }
    added, skipped = 0, 0
    for i in range(body.start, body.end + 1):
        name = f"{i}{body.suffix}"
        if name in existing:
            skipped += 1
            continue
        db.add(SchoolClass(grade=grade[:16], name=name[:32], sort_order=i))
        added += 1
    db.commit()
    return {"added": added, "skipped": skipped}


@router.patch("/{cid}", response_model=ClassOut, summary="改班级（管理员）")
def update_class(
    cid: int,
    body: ClassUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.get(SchoolClass, cid)
    if not row:
        raise HTTPException(status_code=404, detail="班级不存在")

    data = body.model_dump(exclude_unset=True)

    if "owner_id" in data and data["owner_id"] is not None:
        owner = db.get(User, data["owner_id"])
        if not owner:
            raise HTTPException(status_code=404, detail="指定的教师不存在")
        if not owner.is_active:
            raise HTTPException(status_code=400, detail="不能把班分给已停用的账号")

    for k, v in data.items():
        setattr(row, k, v.strip()[:32] if isinstance(v, str) else v)

    db.commit()
    db.refresh(row)

    # 班级改了名，挂在这个班下的学生的显示名要跟着改，
    # 否则学生页和成绩筛选里还是旧名字
    if "grade" in data or "name" in data:
        db.query(Student).filter(Student.class_id == row.id).update(
            {Student.student_class: row.display}, synchronize_session=False
        )
        db.commit()

    return _out(row)


@router.delete("/{cid}", summary="删除班级（管理员）")
def delete_class(
    cid: int,
    force: bool = Query(False, description="班里还有学生时也删"),
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """班里还有人时默认不让删 —— 多半是点错了。

    真要删，学生不会跟着没，只是变成"未分班"，得重新分配。
    """
    row = db.get(SchoolClass, cid)
    if not row:
        raise HTTPException(status_code=404, detail="班级不存在")

    n = db.scalar(
        select(func.count()).select_from(Student).where(Student.class_id == cid)
    ) or 0
    if n and not force:
        raise HTTPException(
            status_code=409,
            detail=f"「{row.display}」里还有 {n} 名学生。"
            "先把他们转到别的班，或者确认后强制删除（学生会变成未分班）。",
        )

    recycle.trash(db, me, "class", f"班级「{row.display}」", SchoolClass, [row.id],
                  detail=f"{n} 名学生变成未分班" if n else "")
    db.query(Student).filter(Student.class_id == cid).update(
        {Student.class_id: None}, synchronize_session=False
    )
    db.delete(row)
    db.commit()
    return {"ok": True, "detached": n}


@router.get("/grades", response_model=list[str], summary="出现过的年级，供下拉用")
def list_grades(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(SchoolClass.grade).distinct().order_by(SchoolClass.grade)
    ).all()
    return [r[0] for r in rows]


@router.post("/bulk", summary="批量删除班级（管理员）")
def bulk_classes(
    body: ClassBulkIn,
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """一次删掉勾选的班。

    和单个删除同一条规矩：**班里还有学生时默认不删**，会把哪几个班有多少人
    报回去让人确认。学期初批量建了十几个班、建错一批想清掉，一个个点太慢。

    确认之后（force=True）学生不会跟着没，只是变成"未分班"，得重新分配 ——
    这一点和单个删除完全一致，不因为是批量就变得更狠。
    """
    ids = [i for i in dict.fromkeys(body.ids) if i]
    if not ids:
        raise HTTPException(status_code=400, detail="没有选中任何班级")

    rows = list(db.scalars(select(SchoolClass).where(SchoolClass.id.in_(ids))))
    if not rows:
        raise HTTPException(status_code=404, detail="选中的班级都不存在了，刷新看看")

    # 一次查清每个班有多少人，别在循环里逐个 count
    counts = dict(
        db.execute(
            select(Student.class_id, func.count())
            .where(Student.class_id.in_([c.id for c in rows]))
            .group_by(Student.class_id)
        ).all()
    )
    occupied = [(c, counts.get(c.id, 0)) for c in rows if counts.get(c.id)]

    if occupied and not body.force:
        detail = "、".join(f"{c.display}（{n} 人）" for c, n in occupied[:6])
        more = f" 等 {len(occupied)} 个班" if len(occupied) > 6 else ""
        raise HTTPException(
            status_code=409,
            detail=f"{detail}{more}里还有学生。"
            "先把他们转到别的班，或者确认后强制删除（这些学生会变成未分班）。",
        )

    detached = sum(n for _, n in occupied)
    recycle.trash(db, me, "class", f"{len(rows)} 个班级", SchoolClass, [c.id for c in rows],
                  detail=recycle.names(rows, "display"))
    db.query(Student).filter(Student.class_id.in_([c.id for c in rows])).update(
        {Student.class_id: None}, synchronize_session=False
    )
    for c in rows:
        db.delete(c)
    db.commit()
    return {"ok": True, "deleted": len(rows), "detached": detached}


@router.post("/bulk-owner", summary="批量分配班主任（管理员）")
def bulk_owner(
    body: ClassBulkOwnerIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """把勾中的班一次分给同一位老师，owner_id 留空就是批量取消分配。

    开学时一位老师带一个年级六个班是常事，一个个下拉选六遍纯属浪费时间。
    停用的账号不能接班 —— 接了也发不出考试，不如当场拦住。
    """
    ids = [i for i in dict.fromkeys(body.ids) if i]
    if not ids:
        raise HTTPException(status_code=400, detail="没有选中任何班级")

    if body.owner_id is not None:
        owner = db.get(User, body.owner_id)
        if not owner:
            raise HTTPException(status_code=404, detail="指定的教师不存在")
        if not owner.is_active:
            raise HTTPException(status_code=400, detail="不能把班分给已停用的账号")

    rows = list(db.scalars(select(SchoolClass).where(SchoolClass.id.in_(ids))))
    if not rows:
        raise HTTPException(status_code=404, detail="选中的班级都不存在了，刷新看看")

    for c in rows:
        c.owner_id = body.owner_id
    db.commit()
    return {"ok": True, "updated": len(rows)}


@router.post("/{cid}/seat", response_model=ClassOut, summary="上传本班上机座次表（图片或 Excel）")
async def upload_seat(cid: int, file: UploadFile = File(...),
                      me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SchoolClass, cid)
    if not row:
        raise HTTPException(status_code=404, detail="班级不存在")
    _can_seat(row, me)
    original = os.path.basename(file.filename or "")
    ext = os.path.splitext(original)[1].lower()
    if ext not in SEAT_IMAGE | SEAT_SHEET:
        raise HTTPException(status_code=400,
                            detail="座次表只支持图片（png/jpg/gif/webp/bmp）或表格（xls/xlsx）")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件是空的")
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"文件不能超过 {settings.max_upload_mb} MB")

    name = f"{uuid.uuid4().hex}{ext}"          # 磁盘上用随机名：别的班猜不到地址
    with open(os.path.join(_seat_dir(), name), "wb") as f:
        f.write(content)
    old = row.seat_file
    row.seat_file, row.seat_name = name, original[:128] or f"座次表{ext}"
    db.commit()
    if old:
        try:
            os.remove(os.path.join(_seat_dir(), os.path.basename(old)))
        except OSError:
            pass
    db.refresh(row)
    return _out(row)


@router.delete("/{cid}/seat", response_model=ClassOut, summary="删掉本班的座次表")
def delete_seat(cid: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(SchoolClass, cid)
    if not row:
        raise HTTPException(status_code=404, detail="班级不存在")
    _can_seat(row, me)
    old = row.seat_file
    row.seat_file, row.seat_name = "", ""
    db.commit()
    if old:
        try:
            os.remove(os.path.join(_seat_dir(), os.path.basename(old)))
        except OSError:
            pass
    db.refresh(row)
    return _out(row)


@router.get("/{cid}/seat/file", summary="下载座次表（按上传时的原名）")
def download_seat(cid: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """图片可以直接用 seat_url 在新页面打开；表格走这里，下载下来还是老师上传时的名字。"""
    row = db.get(SchoolClass, cid)
    if not row or not row.seat_file:
        raise HTTPException(status_code=404, detail="这个班还没有上传座次表")
    path = os.path.join(_seat_dir(), os.path.basename(row.seat_file))
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="座次表文件找不到了，请重新上传")
    name = row.seat_name or f"{row.display}座次表{os.path.splitext(path)[1]}"
    return FileResponse(path, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})


# ================================================================ 在线座次（2.20.0）
SEAT_SHEET_MAX = 2 * 1024 * 1024     # 一个班的座次表 JSON 最大 2 MB，正常一张表几十 KB


def _class_or_404(db: Session, cid: int) -> SchoolClass:
    row = db.get(SchoolClass, cid)
    if not row:
        raise HTTPException(status_code=404, detail="班级不存在")
    return row


@router.get("/{cid}/seat-sheet", summary="取本班的在线座次")
def get_seat_sheet(cid: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """表格谁都能看（发考试的老师也想知道谁坐哪）；编辑、排座位、看学困生只给
    本班老师和管理员。学生名单（含学困生标记）只在 can_edit 时给。"""
    import json

    row = _class_or_404(db, cid)
    can_edit = me.role == "admin" or row.owner_id == me.id
    out = {"class_id": row.id, "display": row.display, "can_edit": can_edit,
           "sheet": json.loads(row.seat_sheet) if row.seat_sheet else None,
           "students": []}
    if can_edit:
        rows = db.scalars(select(Student).where(Student.class_id == row.id,
                                                Student.is_active.is_(True))
                          .order_by(Student.student_no))
        out["students"] = [{"id": s.id, "student_no": s.student_no, "name": s.name,
                            "gender": s.gender or "", "struggling": bool(s.struggling),
                            "class_role": s.class_role or ""}
                           for s in rows]
    return out


@router.put("/{cid}/seat-sheet", response_model=ClassOut, summary="保存本班的在线座次")
def save_seat_sheet(cid: int, body: SeatSheetIn, me: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    import json

    row = _class_or_404(db, cid)
    _can_seat(row, me)
    raw = json.dumps(body.sheet, ensure_ascii=False)
    if len(raw.encode("utf-8")) > SEAT_SHEET_MAX:
        raise HTTPException(status_code=413, detail="座次表太大了（超过 2 MB），删掉一些空行空列再存")
    row.seat_sheet = raw
    db.commit()
    db.refresh(row)
    n = db.scalar(select(func.count()).select_from(Student).where(Student.class_id == row.id)) or 0
    return _out(row, n)


@router.delete("/{cid}/seat-sheet", response_model=ClassOut, summary="清掉本班的在线座次")
def delete_seat_sheet(cid: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _class_or_404(db, cid)
    _can_seat(row, me)
    row.seat_sheet = None
    db.commit()
    db.refresh(row)
    return _out(row)


@router.post("/{cid}/seat-plan", summary="一键导入本班学生：按区域和选项排座位")
def seat_plan(cid: int, body: SeatPlanIn, me: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """只算不存：返回「哪个格子放谁」，前端填进表格、老师看过再点保存。"""
    row = _class_or_404(db, cid)
    _can_seat(row, me)
    rows = db.scalars(select(Student).where(Student.class_id == row.id,
                                            Student.is_active.is_(True)))
    people = [{"id": s.id, "student_no": s.student_no, "name": s.name,
               "gender": s.gender or "", "struggling": bool(s.struggling)} for s in rows]
    if not people:
        raise HTTPException(status_code=400, detail="这个班还没有学生，先去「学生管理」导入名单")
    try:
        return seating.plan(people, body.ranges, zone=body.zone,
                            alternate=body.alternate_gender,
                            struggling_zone=body.struggling_zone, shuffle=body.shuffle,
                            seed=body.seed, content=body.content, skip=body.skip)
    except seating.RangeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


# ================================================================ 课堂情况日志
# 在线座次右边那一栏：每次上机记一条（请假缺勤、设备问题……）。
# 看：和座次表一样谁都能看（任课老师想知道上节课机房出了什么事）；写、改、删：本班老师和管理员。
LOG_LIMIT = 500   # 一个班最多返回最近 500 条，一学期上机一般几十次


def _log_or_404(db: Session, cid: int, lid: int) -> ClassLog:
    log = db.get(ClassLog, lid)
    if not log or log.class_id != cid:
        raise HTTPException(status_code=404, detail="这条日志不存在（可能已经被删了）")
    return log


@router.get("/{cid}/logs", response_model=list[ClassLogOut], summary="本班的课堂情况日志")
def list_logs(cid: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _class_or_404(db, cid)
    return db.scalars(select(ClassLog).where(ClassLog.class_id == cid)
                      .order_by(ClassLog.lesson_date.desc(), ClassLog.id.desc())
                      .limit(LOG_LIMIT)).all()


@router.post("/{cid}/logs", response_model=ClassLogOut, summary="新建一条课堂情况日志")
def create_log(cid: int, body: ClassLogIn, me: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    row = _class_or_404(db, cid)
    _can_seat(row, me)
    if not body.title.strip() and not body.content.strip():
        raise HTTPException(status_code=400, detail="标题和内容至少写一样")
    now = now_local()
    log = ClassLog(class_id=cid, lesson_date=body.lesson_date, title=body.title.strip(),
                   content=body.content, author_id=me.id,
                   author_name=(me.name or me.username or "")[:64],
                   created_at=now, updated_at=now)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.put("/{cid}/logs/{lid}", response_model=ClassLogOut, summary="修改一条课堂情况日志")
def update_log(cid: int, lid: int, body: ClassLogIn, me: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    row = _class_or_404(db, cid)
    _can_seat(row, me)
    log = _log_or_404(db, cid, lid)
    if not body.title.strip() and not body.content.strip():
        raise HTTPException(status_code=400, detail="标题和内容至少写一样")
    log.lesson_date = body.lesson_date
    log.title = body.title.strip()
    log.content = body.content
    log.updated_at = now_local()
    db.commit()
    db.refresh(log)
    return log


@router.delete("/{cid}/logs/{lid}", summary="删掉一条课堂情况日志")
def delete_log(cid: int, lid: int, me: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    row = _class_or_404(db, cid)
    _can_seat(row, me)
    db.delete(_log_or_404(db, cid, lid))
    db.commit()
    return {"ok": True}


# ================================================================ 课堂加减分
# 在线座次里右键学生加分 / 减分。一笔一行：看得到什么时候、为什么，点错了撤销那一笔。
# 只给本班老师和管理员（和排座位一样）；别的老师打开座次表看不到分数。
POINT_RECENT = 200


@router.get("/{cid}/points", summary="本班学生的课堂得分：总分 + 最近的记录")
def list_points(cid: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = _class_or_404(db, cid)
    _can_seat(row, me)
    totals = dict(db.execute(select(StudentPoint.student_id, func.sum(StudentPoint.delta))
                             .where(StudentPoint.class_id == cid)
                             .group_by(StudentPoint.student_id)).all())
    recent = db.scalars(select(StudentPoint).where(StudentPoint.class_id == cid)
                        .order_by(StudentPoint.id.desc()).limit(POINT_RECENT)).all()
    return {"totals": {str(k): int(v or 0) for k, v in totals.items()},
            "recent": [PointOut.model_validate(p).model_dump(mode="json") for p in recent]}


@router.post("/{cid}/points", summary="给本班一位学生加分 / 减分")
def add_point(cid: int, body: PointIn, me: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    row = _class_or_404(db, cid)
    _can_seat(row, me)
    if body.delta == 0:
        raise HTTPException(status_code=400, detail="加减分不能是 0")
    stu = db.get(Student, body.student_id)
    if not stu or stu.class_id != cid:
        raise HTTPException(status_code=400, detail="这位学生不在这个班里")
    p = StudentPoint(class_id=cid, student_id=stu.id, delta=body.delta, reason=body.reason.strip(),
                     author_name=(me.name or me.username or "")[:64], created_at=now_local())
    db.add(p)
    db.commit()
    db.refresh(p)
    total = db.scalar(select(func.sum(StudentPoint.delta)).where(
        StudentPoint.class_id == cid, StudentPoint.student_id == stu.id)) or 0
    return {"total": int(total), "entry": PointOut.model_validate(p).model_dump(mode="json")}


@router.delete("/{cid}/points/{pid}", summary="撤销一笔加减分")
def undo_point(cid: int, pid: int, me: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    row = _class_or_404(db, cid)
    _can_seat(row, me)
    p = db.get(StudentPoint, pid)
    if not p or p.class_id != cid:
        raise HTTPException(status_code=404, detail="这笔记录不存在（可能已经撤销了）")
    sid = p.student_id
    db.delete(p)
    db.commit()
    total = db.scalar(select(func.sum(StudentPoint.delta)).where(
        StudentPoint.class_id == cid, StudentPoint.student_id == sid)) or 0
    return {"ok": True, "student_id": sid, "total": int(total)}
