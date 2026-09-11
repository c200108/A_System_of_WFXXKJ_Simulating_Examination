"""班级管理。

班级原来只是一串手打的文字，"七(3)班"和"七3班"是两个班，老师和学生各打各的
就对不上。改成一张表之后，两边都从下拉里选同一个 id。

班级归属决定了**谁能给谁发考试**：
- 老师只能给自己名下的班发考试；
- 管理员发的考试全体学生都收得到。

增删改班级只有管理员能做 —— 班级是全校的组织结构，不该让任课老师随手改。
老师能看列表（发考试要选班），也能看出哪些班是自己的。
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import SchoolClass, Student, User
from ..schemas import ClassBatchIn, ClassIn, ClassOut, ClassUpdate

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
    )


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
    _: User = Depends(require_admin),
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
