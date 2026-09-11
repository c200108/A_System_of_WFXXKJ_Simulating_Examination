"""需求反馈 + 更新日志。

反馈：学生和老师都能提，**不需要登录**；提交后公开展示在反馈区。
      老师登录后能在评论下回复、点赞；**下架和删除只有管理员能做** ——
      这两个动作会让内容从公开区消失，权限收在一个人手里，出了事查得清。
更新日志：公开可看，按 Keep a Changelog 规范组织 —— 一个版本一组，
      组内按 Added / Changed / Fixed 等变动类型再分。
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import (
    get_current_user,
    get_optional_user,
    require_admin,
    require_delete_permission,
)
from ..models import ChangelogEntry, Feedback, FeedbackLike, FeedbackReply, User
from ..schemas import (
    ChangelogEntryIn,
    ChangelogEntryOut,
    ChangelogVersionOut,
    FeedbackIn,
    FeedbackOut,
    FeedbackReplyIn,
    FeedbackReplyOut,
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


def _out(row: Feedback, me: User | None) -> FeedbackOut:
    """一条反馈的公开视图。contact 不在 FeedbackOut 里，构造不出来也就漏不出去。"""
    return FeedbackOut(
        id=row.id,
        author=row.author,
        category=row.category,
        content=row.content,
        replies=[FeedbackReplyOut.model_validate(r) for r in row.replies],
        like_count=len(row.likes),
        liked_by_me=bool(me) and any(lk.user_id == me.id for lk in row.likes),
        created_at=row.created_at,
    )


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
        return _out(dup, None)

    row = Feedback(
        author=author[:64],
        contact=body.contact.strip()[:64],
        category=body.category,
        content=content,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row, None)


@router.get("/feedback", response_model=list[FeedbackOut], summary="反馈列表（公开）")
def list_feedback(
    category: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    me: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """公开接口只返回没被下架的。联系方式不在响应模型里，不会外泄。

    带令牌访问时会顺带标出哪几条是自己点过赞的（liked_by_me）；不带令牌照常返回。
    """
    stmt = select(Feedback).where(Feedback.is_public.is_(True))
    if category:
        stmt = stmt.where(Feedback.category == category)
    rows = db.scalars(stmt.order_by(Feedback.created_at.desc()).limit(limit)).all()
    return [_out(r, me) for r in rows]


@router.get("/feedback/all", summary="全部反馈，含已下架和联系方式（管理员）")
def list_feedback_all(
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """联系方式和已下架的内容只给管理员看，普通老师用公开列表就够了。"""
    rows = db.scalars(select(Feedback).order_by(Feedback.created_at.desc()).limit(500)).all()
    return [
        {**_out(r, me).model_dump(), "contact": r.contact, "is_public": r.is_public}
        for r in rows
    ]


@router.post("/feedback/{fid}/reply", response_model=FeedbackOut, summary="在反馈下回复（教师）")
def reply_feedback(
    fid: int,
    body: FeedbackReplyIn,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """每位老师各回各的，互相不覆盖；回复公开显示，署老师的名字。"""
    row = db.get(Feedback, fid)
    if not row:
        raise HTTPException(status_code=404, detail="反馈不存在")
    content = body.reply.strip()
    if not content:
        raise HTTPException(status_code=400, detail="回复内容不能为空")

    db.add(
        FeedbackReply(
            feedback_id=row.id,
            user_id=me.id,
            author=(me.name or me.username)[:64],
            is_admin=me.role == "admin",
            content=content,
        )
    )
    db.commit()
    db.refresh(row)
    return _out(row, me)


@router.delete("/feedback/replies/{rid}", summary="撤回一条回复（本人或管理员）")
def delete_reply(
    rid: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    row = db.get(FeedbackReply, rid)
    if not row:
        raise HTTPException(status_code=404, detail="回复不存在")
    if me.role != "admin" and row.user_id != me.id:
        raise HTTPException(status_code=403, detail="只能撤回自己的回复")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/feedback/{fid}/like", response_model=FeedbackOut, summary="点赞/取消点赞（教师）")
def toggle_like(
    fid: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """再点一次就是取消。一人一条，唯一约束保证点不重。"""
    row = db.get(Feedback, fid)
    if not row:
        raise HTTPException(status_code=404, detail="反馈不存在")

    existing = db.scalar(
        select(FeedbackLike).where(
            FeedbackLike.feedback_id == fid, FeedbackLike.user_id == me.id
        )
    )
    if existing:
        db.delete(existing)
    else:
        db.add(FeedbackLike(feedback_id=fid, user_id=me.id))
    db.commit()
    db.refresh(row)
    return _out(row, me)


@router.patch("/feedback/{fid}/visibility", response_model=FeedbackOut, summary="上架/下架（管理员）")
def toggle_feedback(
    fid: int,
    is_public: bool,
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    row = db.get(Feedback, fid)
    if not row:
        raise HTTPException(status_code=404, detail="反馈不存在")
    row.is_public = is_public
    db.commit()
    db.refresh(row)
    return _out(row, me)


@router.delete("/feedback/{fid}", summary="删除反馈（管理员）")
def delete_feedback(
    fid: int, _: User = Depends(require_admin), db: Session = Depends(get_db)
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


@router.delete("/changelog/{eid}", summary="删除一条日志（需要删除权）")
def delete_entry(
    eid: int, _: User = Depends(require_delete_permission), db: Session = Depends(get_db)
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
