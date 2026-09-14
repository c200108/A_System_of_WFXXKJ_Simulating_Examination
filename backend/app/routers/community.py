"""需求反馈 + 更新日志。

反馈：学生和老师都能提，**不需要登录**；但**要管理员审核过才出现在公开区**。
      评论区谁都能发，先发后审的话不当内容会有一段时间挂在首页上。
      老师登录后能在已通过的评论下回复、点赞；审核、删除只有管理员能做。
更新日志：公开可看，按 Keep a Changelog 规范组织 —— 一个版本一组，
      组内按 Added / Changed / Fixed 等变动类型再分。
"""

import json
import os
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
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
    FeedbackReviewBulkIn,
    FeedbackReviewIn,
)

router = APIRouter(prefix="/api", tags=["反馈与日志"])

CATEGORIES = ("建议", "问题", "表扬", "其他")
STATUSES = ("pending", "approved", "rejected")

MAX_IMAGES = 3
ALLOWED_IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
# 文件头，用来确认"扩展名是 .png 的东西"确实是张图。
# 只看扩展名的话，改个名字就能往服务器上放任意文件。
# 用 fromhex 而不是带反斜杠的字节字面量：这份源码经过几层工具传递，
# 反斜杠转义被吃掉过好几次，写成十六进制就没有这个隐患。
IMAGE_MAGIC = (
    bytes.fromhex("89504e470d0a1a0a"),  # png
    bytes.fromhex("ffd8ff"),            # jpg
    b"GIF87a",
    b"GIF89a",
    b"RIFF",                            # webp，RIFF 后第 8 字节起还要是 WEBP
)
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


def _images(row: Feedback) -> list[str]:
    """配图存的是 JSON 数组。存过脏值时当没有，不要让整个列表挂掉。"""
    try:
        val = json.loads(row.images or "[]")
        return [str(x) for x in val] if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


def _out(row: Feedback, me: User | None) -> FeedbackOut:
    """一条反馈的公开视图。contact 不在 FeedbackOut 里，构造不出来也就漏不出去。"""
    return FeedbackOut(
        id=row.id,
        author=row.author,
        category=row.category,
        content=row.content,
        images=_images(row),
        status=row.status,
        replies=[FeedbackReplyOut.model_validate(r) for r in row.replies],
        like_count=len(row.likes),
        liked_by_me=bool(me) and any(lk.user_id == me.id for lk in row.likes),
        created_at=row.created_at,
    )


def _check_images(urls: list[str]) -> list[str]:
    """校验配图地址。两种来源：本地上传的 /uploads/... 和 http(s) 外链。

    外链只做格式校验，不去下载 —— 下载外部地址等于让服务器按用户给的
    URL 发请求，是个现成的 SSRF 口子。图片由浏览器去取，服务器不碰。
    """
    out = []
    for raw in urls[:MAX_IMAGES]:
        url = str(raw or "").strip()
        if not url:
            continue
        if url.startswith("/uploads/"):
            out.append(url[:500])
        elif url.startswith(("http://", "https://")):
            out.append(url[:500])
        else:
            raise HTTPException(
                status_code=400,
                detail=f"图片地址「{url[:40]}」不认识，要么是本站上传的，要么是 http/https 开头的网址",
            )
    if len(urls) > MAX_IMAGES:
        raise HTTPException(status_code=400, detail=f"一条反馈最多配 {MAX_IMAGES} 张图")
    return out


# ================================================================ 需求反馈
@router.post("/feedback/images", summary="上传反馈配图（公开）")
async def upload_feedback_image(file: UploadFile = File(...)):
    """反馈不需要登录，所以这个上传口也是公开的。

    三道限制：扩展名白名单、大小上限、**文件头必须真的是图片** ——
    光看扩展名的话，改个名字就能往服务器上放任意文件。
    文件名用随机 uuid，猜不到；加上内容要管理员审过才公开展示。
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE:
        raise HTTPException(status_code=400, detail="只支持 png/jpg/gif/webp")

    content = await file.read()
    limit_mb = min(settings.max_upload_mb, 5)  # 评论配图不需要很大
    if len(content) > limit_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"图片不能超过 {limit_mb} MB")
    if not content:
        raise HTTPException(status_code=400, detail="文件是空的")

    if not content.startswith(IMAGE_MAGIC):
        raise HTTPException(status_code=400, detail="这个文件看起来不是图片，换一张试试")
    if content.startswith(b"RIFF") and content[8:12] != b"WEBP":
        raise HTTPException(status_code=400, detail="这个文件看起来不是图片，换一张试试")

    folder = os.path.join(settings.upload_dir, "feedback")
    os.makedirs(folder, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(folder, name), "wb") as f:
        f.write(content)
    return {"image_url": f"/uploads/feedback/{name}"}


@router.post("/feedback", response_model=FeedbackOut, summary="提交反馈（公开，待审核）")
def create_feedback(body: FeedbackIn, db: Session = Depends(get_db)):
    author = body.author.strip()
    content = body.content.strip()
    if not author:
        raise HTTPException(status_code=400, detail="请填写您的称呼")
    if len(content) < 5:
        raise HTTPException(status_code=400, detail="说得再具体一点吧，至少 5 个字")
    if body.category not in CATEGORIES:
        raise HTTPException(status_code=400, detail=f"类型只能是 {'/'.join(CATEGORIES)}")

    images = _check_images(body.images)

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
        images=json.dumps(images, ensure_ascii=False),
        status="pending",  # 审过才公开
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
    """公开接口**只返回审核通过的**。联系方式不在响应模型里，不会外泄。

    带令牌访问时会顺带标出哪几条是自己点过赞的（liked_by_me）；不带令牌照常返回。
    """
    stmt = select(Feedback).where(Feedback.status == "approved")
    if category:
        stmt = stmt.where(Feedback.category == category)
    rows = db.scalars(stmt.order_by(Feedback.created_at.desc()).limit(limit)).all()
    return [_out(r, me) for r in rows]


@router.get("/feedback/all", summary="全部反馈，含待审核和联系方式（管理员）")
def list_feedback_all(
    status: str | None = Query(None, description="按状态筛，留空看全部"),
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """联系方式和未通过的内容只给管理员看，普通老师用公开列表就够了。"""
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"状态只能是 {'/'.join(STATUSES)}")

    stmt = select(Feedback)
    if status:
        stmt = stmt.where(Feedback.status == status)
    rows = db.scalars(stmt.order_by(Feedback.created_at.desc()).limit(500)).all()
    return [
        {
            **_out(r, me).model_dump(),
            "contact": r.contact,
            "review_note": r.review_note,
            "reviewed_at": r.reviewed_at,
        }
        for r in rows
    ]


@router.get("/feedback/pending-count", summary="待审核条数（教师可见，用来提醒管理员）")
def pending_count(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    n = db.scalar(
        select(func.count()).select_from(Feedback).where(Feedback.status == "pending")
    )
    return {"pending": n or 0}


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
    if row.status != "approved":
        raise HTTPException(status_code=409, detail="这条还没通过审核，等管理员审过再回复")
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
    if row.status != "approved":
        raise HTTPException(status_code=409, detail="这条还没通过审核")

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


@router.patch("/feedback/{fid}/review", response_model=FeedbackOut, summary="审核一条反馈（管理员）")
def review_feedback(
    fid: int,
    body: FeedbackReviewIn,
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """通过 / 拒绝 / 退回待审。拒绝后内容还在库里，只是不进公开区。"""
    row = db.get(Feedback, fid)
    if not row:
        raise HTTPException(status_code=404, detail="反馈不存在")

    row.status = body.status
    row.review_note = body.note.strip()[:255]
    row.reviewed_by = me.id
    row.reviewed_at = datetime.now()
    db.commit()
    db.refresh(row)
    return _out(row, me)


@router.post("/feedback/review-bulk", summary="批量审核（管理员）")
def review_bulk(
    body: FeedbackReviewBulkIn,
    me: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """一次开学能积几十条，一条条点太慢。"""
    ids = list(dict.fromkeys(body.ids))
    if not ids:
        raise HTTPException(status_code=400, detail="没有选中任何反馈")

    rows = list(db.scalars(select(Feedback).where(Feedback.id.in_(ids))))
    now = datetime.now()
    for r in rows:
        r.status = body.status
        r.reviewed_by = me.id
        r.reviewed_at = now
    db.commit()
    return {"status": body.status, "affected": len(rows)}


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
