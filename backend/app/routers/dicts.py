from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import DICT_SCOPE, DICT_TYPE
from ..database import get_db
from ..deps import get_current_user, require_admin
from ..models import DictItem, User
from ..schemas import DictItemIn, DictItemOut

router = APIRouter(prefix="/api/dicts", tags=["字典配置"])


def active_names(db: Session, category: str) -> list[str]:
    rows = db.scalars(
        select(DictItem)
        .where(DictItem.category == category, DictItem.is_active.is_(True))
        .order_by(DictItem.sort_order, DictItem.id)
    )
    return [r.name for r in rows]


def scope_order(db: Session) -> list[str]:
    """抽题算法要用的知识范围固定顺序。"""
    return active_names(db, DICT_SCOPE)


@router.get("", response_model=list[DictItemOut], summary="取知识范围/题型清单")
def list_dicts(
    category: str | None = None,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(DictItem).where(DictItem.is_active.is_(True))
    if category:
        stmt = stmt.where(DictItem.category == category)
    return list(db.scalars(stmt.order_by(DictItem.category, DictItem.sort_order, DictItem.id)))


@router.post("", response_model=DictItemOut, summary="新增枚举项（管理员）")
def create_dict(
    body: DictItemIn, _: User = Depends(require_admin), db: Session = Depends(get_db)
):
    if body.category not in (DICT_SCOPE, DICT_TYPE):
        raise HTTPException(status_code=400, detail="category 只能是 scope 或 qtype")
    exists = db.scalar(
        select(DictItem).where(DictItem.category == body.category, DictItem.name == body.name)
    )
    if exists:
        exists.is_active = True
        exists.sort_order = body.sort_order
        db.commit()
        db.refresh(exists)
        return exists
    item = DictItem(category=body.category, name=body.name, sort_order=body.sort_order)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/{item_id}", summary="停用枚举项（管理员）")
def disable_dict(item_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    item = db.get(DictItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="不存在")
    item.is_active = False
    db.commit()
    return {"ok": True}
