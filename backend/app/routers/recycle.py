"""数据回收站：删掉的考试、答卷、试卷、题目、学生、班级、打字成绩……先在这里放 7 天。

- 管理员看得到所有人删的；老师只看得到自己删的。
- 还原、彻底删除：删的人自己或者管理员。
- 过了 7 天自动彻底删除（每次打开回收站、每次删东西、服务每小时各清一次）。
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import RecycleItem, User
from ..services import recycle

router = APIRouter(prefix="/api/recycle", tags=["数据回收站"])


class RecycleIdsIn(BaseModel):
    ids: List[int]


def _mine(stmt, user: User):
    return stmt if user.role == "admin" else stmt.where(RecycleItem.deleted_by == user.id)


def _out(item: RecycleItem) -> dict:
    left = item.expires_at - clock.now()
    return {
        "id": item.id,
        "kind": item.kind,
        "kind_name": recycle.KIND_NAMES.get(item.kind, item.kind),
        "title": item.title,
        "detail": item.detail,
        "deleted_by_name": item.deleted_by_name,
        "deleted_at": item.deleted_at,
        "expires_at": item.expires_at,
        "days_left": max(0, left.days + (1 if left.seconds else 0)),
    }


def _pick(db: Session, ids: List[int], user: User) -> List[RecycleItem]:
    rows = list(db.scalars(_mine(select(RecycleItem).where(RecycleItem.id.in_(ids)), user)))
    if not rows:
        raise HTTPException(status_code=404, detail="回收站里没有这几条了（可能已经还原或过期）")
    return rows


@router.get("", summary="回收站列表")
def list_items(kind: str = "", user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    recycle.purge(db)
    stmt = _mine(select(RecycleItem), user)
    if kind:
        stmt = stmt.where(RecycleItem.kind == kind)
    rows = db.scalars(stmt.order_by(RecycleItem.deleted_at.desc(), RecycleItem.id.desc())).all()
    return {"items": [_out(r) for r in rows], "keep_days": recycle.KEEP_DAYS,
            "kinds": recycle.KIND_NAMES}


@router.post("/restore", summary="还原（可批量）")
def restore_items(body: RecycleIdsIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    done, failed = 0, []
    # 先删的后还原：答卷和它的考试都在回收站时，先还原考试（它删得早）
    for item in sorted(_pick(db, body.ids, user), key=lambda r: r.id):
        title = item.title
        try:
            recycle.restore(db, item)
            done += 1
        except recycle.RestoreError as exc:
            failed.append(f"{title}：{exc}")
    return {"restored": done, "failed": failed}


@router.post("/destroy", summary="彻底删除（可批量）")
def destroy_items(body: RecycleIdsIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    rows = _pick(db, body.ids, user)
    for item in rows:
        recycle.destroy(db, item)
    db.commit()
    return {"deleted": len(rows)}


@router.delete("", summary="清空回收站（管理员）")
def clear_all(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(RecycleItem)))
    for item in rows:
        recycle.destroy(db, item)
    db.commit()
    return {"deleted": len(rows)}
