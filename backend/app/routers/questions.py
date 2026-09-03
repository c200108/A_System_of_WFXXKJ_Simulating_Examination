import os
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..constants import DICT_SCOPE, DICT_TYPE
from ..database import get_db
from ..deps import get_current_user
from ..models import Option, Question, User
from ..schemas import QuestionCreate, QuestionOut, QuestionPage, QuestionUpdate, StatsOut
from ..services.export import questions_to_xlsx
from ..services.importer import stem_hash
from .dicts import active_names

router = APIRouter(prefix="/api/questions", tags=["题库"])

ALLOWED_IMAGE = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _filtered(
    keyword: str | None,
    qtype: str | None,
    scope: str | None,
    source: str | None,
    pinned: bool | None,
):
    """题库列表和题库导出用同一套筛选条件，避免两处走样。"""
    stmt = select(Question).where(Question.is_deleted.is_(False))
    if keyword:
        stmt = stmt.where(Question.stem.like(f"%{keyword}%"))
    if qtype:
        stmt = stmt.where(Question.type == qtype)
    if scope:
        stmt = stmt.where(Question.scope == scope)
    if source:
        stmt = stmt.where(Question.source == source)
    if pinned is not None:
        stmt = stmt.where(Question.is_pinned.is_(pinned))
    return stmt


def _validate(db: Session, qtype: str, scope: str) -> None:
    if qtype not in active_names(db, DICT_TYPE):
        raise HTTPException(status_code=400, detail=f"题型「{qtype}」不在配置之内")
    if scope not in active_names(db, DICT_SCOPE):
        raise HTTPException(status_code=400, detail=f"知识范围「{scope}」不在十类之内")


@router.get("", response_model=QuestionPage, summary="题库分页查询")
def list_questions(
    keyword: str | None = None,
    type: str | None = None,
    scope: str | None = None,
    source: str | None = None,
    pinned: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = _filtered(keyword, type, scope, source, pinned)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = db.scalars(
        stmt.order_by(Question.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return QuestionPage(total=total, page=page, page_size=page_size, items=list(items))


@router.get("/stats", response_model=StatsOut, summary="题库概况")
def stats(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    alive = Question.is_deleted.is_(False)
    total = db.scalar(select(func.count()).select_from(Question).where(alive)) or 0
    by_type = dict(
        db.execute(select(Question.type, func.count()).where(alive).group_by(Question.type)).all()
    )
    by_scope = dict(
        db.execute(select(Question.scope, func.count()).where(alive).group_by(Question.scope)).all()
    )
    with_image = (
        db.scalar(
            select(func.count()).select_from(Question).where(alive, Question.image_url.is_not(None))
        )
        or 0
    )
    pinned = (
        db.scalar(
            select(func.count()).select_from(Question).where(alive, Question.is_pinned.is_(True))
        )
        or 0
    )
    sources = [
        s for (s,) in db.execute(select(Question.source).where(alive).distinct()).all() if s
    ]
    return StatsOut(
        total=total,
        by_type=by_type,
        by_scope=by_scope,
        with_image=with_image,
        pinned=pinned,
        sources=sorted(sources),
    )


@router.get("/export.xlsx", summary="导出题库 Excel（可带筛选条件）")
def export_questions(
    keyword: str | None = None,
    type: str | None = None,
    scope: str | None = None,
    source: str | None = None,
    pinned: bool | None = None,
    filename: str = "信息技术题库",
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = list(db.scalars(_filtered(keyword, type, scope, source, pinned).order_by(Question.id)))
    data = questions_to_xlsx(rows, "题库")
    name = quote(f"{filename}.xlsx")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{name}"},
    )


@router.post("/upload-image", summary="上传题目配图，返回可直接引用的 URL")
async def upload_image(file: UploadFile = File(...), _: User = Depends(get_current_user)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_IMAGE:
        raise HTTPException(status_code=400, detail="只支持 png/jpg/gif/webp")
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"图片不能超过 {settings.max_upload_mb} MB")

    images_dir = os.path.join(settings.upload_dir, "images")
    os.makedirs(images_dir, exist_ok=True)
    name = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(images_dir, name), "wb") as f:
        f.write(content)
    # 图片存磁盘，数据库只记路径，不再像原页面那样把 base64 塞进数据里
    return {"image_url": f"/uploads/images/{name}"}


@router.get("/{qid}", response_model=QuestionOut, summary="题目详情")
def get_question(qid: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q or q.is_deleted:
        raise HTTPException(status_code=404, detail="题目不存在")
    return q


@router.post("", response_model=QuestionOut, summary="新增题目")
def create_question(
    body: QuestionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _validate(db, body.type, body.scope)
    h = stem_hash(body.stem)
    dup = db.scalar(select(Question).where(Question.stem_hash == h))
    if dup:
        if dup.is_deleted:
            dup.is_deleted = False  # 曾被软删除，直接恢复而不是报错
            db.commit()
            db.refresh(dup)
            return dup
        raise HTTPException(status_code=409, detail=f"题库里已有相同题干（编号 {dup.id}）")

    q = Question(
        type=body.type,
        stem=body.stem,
        stem_hash=h,
        answer=body.answer,
        scope=body.scope,
        source=body.source,
        image_url=body.image_url,
        is_pinned=body.is_pinned,
        created_by=user.id,
    )
    for i, opt in enumerate(body.options):
        q.options.append(Option(label=opt.label, content=opt.content, sort_order=i))
    db.add(q)
    db.flush()
    q.code = f"C{q.id:04d}"
    db.commit()
    db.refresh(q)
    return q


@router.put("/{qid}", response_model=QuestionOut, summary="修改题目")
def update_question(
    qid: int,
    body: QuestionUpdate,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.get(Question, qid)
    if not q or q.is_deleted:
        raise HTTPException(status_code=404, detail="题目不存在")

    data = body.model_dump(exclude_unset=True)
    options = data.pop("options", None)
    if "type" in data or "scope" in data:
        _validate(db, data.get("type", q.type), data.get("scope", q.scope))
    if "stem" in data and data["stem"] != q.stem:
        h = stem_hash(data["stem"])
        other = db.scalar(select(Question).where(Question.stem_hash == h, Question.id != qid))
        if other:
            raise HTTPException(status_code=409, detail=f"与题目 {other.id} 题干重复")
        q.stem_hash = h
    for k, v in data.items():
        setattr(q, k, v)
    if options is not None:
        q.options.clear()
        db.flush()
        for i, opt in enumerate(options):
            q.options.append(Option(label=opt["label"], content=opt["content"], sort_order=i))
    db.commit()
    db.refresh(q)
    return q


@router.delete("/{qid}", summary="删除题目（软删除，可恢复）")
def delete_question(qid: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    q.is_deleted = True
    db.commit()
    return {"ok": True}


@router.post("/{qid}/restore", summary="恢复被删除的题目")
def restore_question(qid: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.get(Question, qid)
    if not q:
        raise HTTPException(status_code=404, detail="题目不存在")
    q.is_deleted = False
    db.commit()
    return {"ok": True}
