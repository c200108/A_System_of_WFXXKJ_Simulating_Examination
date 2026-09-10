"""需求反馈 + 更新日志。

反馈：学生和老师都能提，**不需要登录**；提交后公开展示在反馈区。
      公开意味着可能出现不当内容，所以管理端能下架（不物理删除，留痕可查）。
更新日志：公开可看，按 Keep a Changelog 规范组织 —— 一个版本一组，
      组内按 Added / Changed / Fixed 等变动类型再分。
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import ChangelogEntry, Feedback, User
from ..schemas import (
    ChangelogEntryIn,
    ChangelogEntryOut,
    ChangelogVersionOut,
    FeedbackIn,
    FeedbackOut,
    FeedbackReplyIn,
)

router = APIRouter(prefix="/api", tags=["反馈与日志"])

CATEGORIES = ("建议", "问题", "表扬", "其他")
CHANGE_TYPES = ("Added", "Changed", "Deprecated", "Removed", "Fixed", "Security")

# 变动类型的中文说明，前端直接用，不用各写一份
CHANGE_TYPE_LABELS = {
    "Added": "新增",
    "Changed": "变更",
    "Deprecated": "弃用",
    "Removed": "移除",
    "Fixed": "修复",
    "Security": "安全",
}


# ================================================================ 需求反馈
@router.post("/feedback", response_model=FeedbackOut, summary="提交反馈（公开）")
def create_feedback(body: FeedbackIn, db: Session = Depends(get_db)):
    author = body.author.strip()
    content = body.content.strip()
    if not author:
        raise HTTPException(status_code=400, detail="请填写您的称呼")
    if len(content) < 5:
        raise HTTPException(status_code=400, detail="说得再具体一点吧，至少 5 个字")
    if body.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"类型只能是 {'/'.join(CATEGORIES)}")

    # 同一个人重复提交完全一样的内容，多半是手抖点了两次
    dup = db.scalar(
        select(Feedback).where(Feedback.author == author, Feedback.content == content)
    )
    if dup:
        return dup

    row = Feedback(
        author=author[:64],
        contact=body.contact.strip()[:64],
        category=body.category,
        content=content,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/feedback", response_model=list[FeedbackOut], summary="反馈列表（公开）")
def list_feedback(
    category: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """公开接口只返回没被下架的。联系方式不在响应模型里，不会外泄。"""
    stmt = select(Feedback).where(Feedback.is_public.is_(True))
    if category:
        stmt = stmt.where(Feedback.category == category)
    return list(db.scalars(stmt.order_by(Feedback.created_at.desc()).limit(limit)))


@router.get("/feedback/all", summary="全部反馈，含已下架和联系方式（教师）")
def list_feedback_all(
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(Feedback).order_by(Feedback.created_at.desc()).limit(500)).all()
    return [
        {
            "id": r.id,
            "author": r.author,
            "contact": r.contact,
            "category": r.category,
            "content": r.content,
            "is_public": r.is_public,
            "reply": r.reply,
            "replied_at": r.replied_at,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("/feedback/{fid}/reply", response_model=FeedbackOut, summary="答复反馈（教师）")
def reply_feedback(
    fid: int,
    body: FeedbackReplyIn,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(Feedback, fid)
    if not row:
        raise HTTPException(status_code=404, detail="反馈不存在")
    row.reply = body.reply.strip()
    row.replied_at = datetime.now() if row.reply else None
    db.commit()
    db.refresh(row)
    return row


@router.patch("/feedback/{fid}/visibility", response_model=FeedbackOut, summary="上架/下架（教师）")
def toggle_feedback(
    fid: int,
    is_public: bool,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.get(Feedback, fid)
    if not row:
        raise HTTPException(status_code=404, detail="反馈不存在")
    row.is_public = is_public
    db.commit()
    db.refresh(row)
    return row


@router.delete("/feedback/{fid}", summary="删除反馈（教师）")
def delete_feedback(
    fid: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    row = db.get(Feedback, fid)
    if not row:
        raise HTTPException(status_code=404, detail="反馈不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


# ================================================================ 更新日志
@router.get("/changelog", response_model=list[ChangelogVersionOut], summary="更新日志（公开）")
def get_changelog(db: Session = Depends(get_db)):
    """按 Keep a Changelog 组织：新版本在前，同版本内按变动类型分组。"""
    rows = db.scalars(
        select(ChangelogEntry).order_by(
            ChangelogEntry.released_on.desc(),
            ChangelogEntry.version.desc(),
            ChangelogEntry.sort_order,
            ChangelogEntry.id,
        )
    ).all()

    versions: list[ChangelogVersionOut] = []
    index: dict[str, ChangelogVersionOut] = {}

    for r in rows:
        v = index.get(r.version)
        if v is None:
            v = ChangelogVersionOut(
                version=r.version, released_on=r.released_on, groups=[]
            )
            index[r.version] = v
            versions.append(v)

        group = next((g for g in v.groups if g["type"] == r.change_type), None)
        if group is None:
            group = {
                "type": r.change_type,
                "label": CHANGE_TYPE_LABELS.get(r.change_type, r.change_type),
                "items": [],
            }
            v.groups.append(group)
        group["items"].append({"id": r.id, "content": r.content})

    # 组内顺序固定成规范里的排列，读起来更整齐
    order = {t: i for i, t in enumerate(CHANGE_TYPES)}
    for v in versions:
        v.groups.sort(key=lambda g: order.get(g["type"], 99))

    return versions


@router.get("/changelog/types", summary="变动类型清单（公开）")
def changelog_types():
    return [{"value": t, "label": CHANGE_TYPE_LABELS[t]} for t in CHANGE_TYPES]


@router.post("/changelog", response_model=ChangelogEntryOut, summary="新增一条日志（教师）")
def create_entry(
    body: ChangelogEntryIn,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if body.change_type not in CHANGE_TYPES:
        raise HTTPException(
            status_code=400, detail=f"变动类型只能是 {'/'.join(CHANGE_TYPES)}"
        )
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="内容不能为空")

    row = ChangelogEntry(
        version=body.version.strip(),
        released_on=body.released_on or date.today(),
        change_type=body.change_type,
        content=content,
        sort_order=body.sort_order,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/changelog/{eid}", summary="删除一条日志（教师）")
def delete_entry(
    eid: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    row = db.get(ChangelogEntry, eid)
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/changelog/latest", summary="最新版本号（公开，页脚显示用）")
def latest_version(db: Session = Depends(get_db)):
    row = db.execute(
        select(ChangelogEntry.version, ChangelogEntry.released_on)
        .order_by(ChangelogEntry.released_on.desc(), ChangelogEntry.id.desc())
        .limit(1)
    ).first()
    if not row:
        return {"version": "", "released_on": None}
    return {"version": row[0], "released_on": row[1]}
