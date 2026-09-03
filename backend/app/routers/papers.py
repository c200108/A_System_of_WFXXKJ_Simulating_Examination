import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..constants import DICT_TYPE
from ..database import get_db
from ..deps import get_current_user
from ..models import Paper, PaperItem, Question, User
from ..schemas import PaperGenerateIn, PaperGenerateOut, PaperOut
from ..services.export import questions_to_xlsx, student_html
from ..services.paper import build_paper
from ..services.sampler import allocate
from .dicts import active_names, scope_order

router = APIRouter(prefix="/api/papers", tags=["组卷"])

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _safe_name(name: str) -> str:
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "")
    return name.strip() or "试卷"


def _attachment(filename: str) -> dict:
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}


def _persist(db: Session, paper: dict, user: User) -> int:
    row = Paper(
        title=paper["title"],
        school=paper["school"],
        duration=paper["duration"],
        code=paper["code"],
        config_json=json.dumps({"seed": paper["seed"]}, ensure_ascii=False),
        created_by=user.id,
    )
    order = 0
    for group in paper["groups"]:
        for it in group["items"]:
            row.items.append(
                PaperItem(
                    question_id=it["id"],
                    order_no=order,
                    # 打乱后的样子存快照，重新打开和当初印出去的一致
                    snapshot_json=json.dumps(
                        {"answer": it["answer"], "options": it["options"]}, ensure_ascii=False
                    ),
                )
            )
            order += 1
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.id


@router.post("/generate", response_model=PaperGenerateOut, summary="均衡抽题组卷")
def generate(
    body: PaperGenerateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = scope_order(db)
    picked_order = [k for k in order if not body.scopes or k in body.scopes]

    paper = build_paper(
        db,
        counts=body.counts,
        type_order=active_names(db, DICT_TYPE),
        scope_order=picked_order,
        scopes=body.scopes,
        require_answer=body.require_answer,
        use_pinned=body.use_pinned,
        shuffle_opts=body.shuffle_options,
        seed=body.seed,
        title=body.title,
        school=body.school,
        duration=body.duration,
    )
    if not paper["total"]:
        raise HTTPException(status_code=400, detail="按当前条件抽不到题目，请调大题量或放宽知识范围")

    # tally 要把所有知识范围都列出来，前端好画分布条
    paper["tally"] = {k: paper["tally"].get(k, 0) for k in order}
    paper["paper_id"] = _persist(db, paper, user) if body.save else None
    return paper


@router.post("/preview-plan", summary="只算名额分布，不真的抽题")
def preview_plan(
    body: PaperGenerateIn,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = scope_order(db)
    picked_order = [k for k in order if not body.scopes or k in body.scopes]
    tally = {k: 0 for k in order}
    total = 0
    shortfall: list[str] = []

    for qtype, want in body.counts.items():
        if want <= 0:
            continue
        stmt = select(Question).where(
            Question.is_deleted.is_(False), Question.type == qtype
        )
        if body.scopes:
            stmt = stmt.where(Question.scope.in_(body.scopes))
        pool = list(db.scalars(stmt))
        if body.require_answer:
            pool = [q for q in pool if (q.answer or "").strip()]
        if want > len(pool):
            shortfall.append(f"{qtype}最多 {len(pool)} 题")
        for k, cnt in allocate(pool, want, picked_order).items():
            tally[k] = tally.get(k, 0) + cnt
            total += cnt

    return {"total": total, "tally": tally, "shortfall": shortfall}


@router.post("/export/xlsx", summary="把当前这份卷子导成 Excel")
def export_paper_xlsx(body: PaperGenerateOut, _: User = Depends(get_current_user)):
    rows = [it.model_dump() for g in body.groups for it in g.items]
    data = questions_to_xlsx(rows, "试卷")
    return Response(
        content=data, media_type=XLSX_MIME, headers=_attachment(_safe_name(body.title) + ".xlsx")
    )


@router.post("/export/student-html", summary="导出学生答题网页（单文件，可直接分发）")
def export_student_html(body: PaperGenerateOut, _: User = Depends(get_current_user)):
    html = student_html(body.model_dump())
    return Response(
        content=html.encode("utf-8"),
        media_type="text/html; charset=utf-8",
        headers=_attachment(_safe_name(body.title) + "_学生答题.html"),
    )


@router.get("", response_model=list[PaperOut], summary="历史试卷")
def list_papers(
    limit: int = 50, _: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    rows = db.scalars(select(Paper).order_by(Paper.id.desc()).limit(limit)).all()
    out = []
    for p in rows:
        item = PaperOut.model_validate(p)
        item.question_count = len(p.items)
        out.append(item)
    return out


@router.get("/{paper_id}", response_model=PaperGenerateOut, summary="打开历史试卷")
def get_paper(paper_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在")

    groups: list[dict] = []
    tally: dict[str, int] = {k: 0 for k in scope_order(db)}
    total = 0

    for it in paper.items:
        q = db.get(Question, it.question_id)
        if not q:
            continue  # 题目后来被物理删除了，跳过
        snap = json.loads(it.snapshot_json) if it.snapshot_json else {}
        item = {
            "id": q.id,
            "code": q.code,
            "type": q.type,
            "stem": q.stem,
            "answer": snap.get("answer", q.answer),
            "scope": q.scope,
            "source": q.source,
            "image_url": q.image_url,
            "options": snap.get("options")
            or [{"label": o.label, "content": o.content} for o in q.options],
        }
        group = next((g for g in groups if g["type"] == q.type), None)
        if not group:
            group = {"type": q.type, "items": []}
            groups.append(group)
        group["items"].append(item)
        tally[q.scope] = tally.get(q.scope, 0) + 1
        total += 1

    return {
        "paper_id": paper.id,
        "title": paper.title,
        "school": paper.school,
        "duration": paper.duration,
        "code": paper.code,
        "seed": json.loads(paper.config_json or "{}").get("seed", ""),
        "total": total,
        "tally": tally,
        "warnings": [],
        "groups": groups,
        "questions": [it for g in groups for it in g["items"]],
    }


@router.delete("/{paper_id}", summary="删除试卷")
def delete_paper(paper_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在")
    db.delete(paper)
    db.commit()
    return {"ok": True}
