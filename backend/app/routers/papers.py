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
from ..services.blueprint import slot_key
from ..services.export import questions_to_xlsx, student_html
from ..services.paper import build_by_sections, build_paper
from ..services.sampler import allocate
from ..siteconfig import site
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
        config_json=json.dumps(
            {
                "seed": paper["seed"],
                "by_sections": paper.get("by_sections", False),
                "full_score": paper.get("full_score", 0),
                # 大题的顺序也存一份：config.yaml 以后改了顺序，
                # 重新打开这份历史试卷仍然按当初的顺序排
                "sections": [g.get("name") or g["type"] for g in paper["groups"]],
            },
            ensure_ascii=False,
        ),
        created_by=user.id,
    )
    order = 0
    for group in paper["groups"]:
        for it in group["items"]:
            row.items.append(
                PaperItem(
                    question_id=it["id"],
                    order_no=order,
                    section=it.get("section") or group.get("name") or group["type"],
                    score=int(it.get("score") or 0),
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


def _sections_for(body: PaperGenerateIn):
    """把界面上改过的大题分值套到配置的卷面结构上。题量不在这儿，走 section_counts。"""
    out = []
    for sec in site.paper.sections:
        score = body.section_scores.get(sec.name)
        out.append(sec if score is None else sec.model_copy(update={"score": max(0, int(score))}))
    return out


@router.post("/generate", response_model=PaperGenerateOut, summary="均衡抽题组卷")
def generate(
    body: PaperGenerateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = scope_order(db)
    picked_order = [k for k in order if not body.scopes or k in body.scopes]

    common = dict(
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
    if body.by_sections:
        paper = build_by_sections(
            db, sections=_sections_for(body), counts=body.section_counts, **common
        )
    else:
        paper = build_paper(
            db, counts=body.counts, type_order=active_names(db, DICT_TYPE), **common
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
    if body.by_sections:
        return _preview_sections(body, db)

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

    return {"total": total, "tally": tally, "shortfall": shortfall, "full_score": 0}


def _preview_sections(body: PaperGenerateIn, db: Session) -> dict:
    """按卷面结构预览：每个大题要几道、题库够不够、总分多少。

    只查数量不抽题，所以改一个数字就能立刻看到"够不够"，不用等组完卷。
    """
    order = scope_order(db)
    picked_order = [k for k in order if not body.scopes or k in body.scopes]
    tally = {k: 0 for k in order}
    shortfall: list[str] = []
    sections = []
    total = 0

    for sec in _sections_for(body):
        want_sum = 0
        have_sum = 0
        for li, slot in enumerate(sec.slots):
            want = body.section_counts.get(slot_key(sec, li))
            want = slot.count if want is None else max(0, int(want))
            if not want:
                continue
            stmt = select(Question).where(
                Question.is_deleted.is_(False), Question.type == slot.type
            )
            wanted = slot.scopes or body.scopes
            if wanted:
                stmt = stmt.where(Question.scope.in_(wanted))
            pool = list(db.scalars(stmt))
            if body.require_answer or slot.type not in site.exam.manual_types:
                pool = [q for q in pool if (q.answer or "").strip()]

            have = min(want, len(pool))
            want_sum += want
            have_sum += have
            if have < want:
                where = f"「{sec.name}」" + (f"·{slot.label}" if slot.label else "")
                shortfall.append(f"{where}要 {want} 道，只有 {len(pool)} 道可选")
            # 走和真正抽题同一个名额分配函数。不能直接数 pool 的前 have 条 ——
            # 那是按 id 排的，不限范围的大题会显示成「全是 Python 编程基础」，
            # 而实际抽题是在各范围之间轮流分名额的，两边对不上。
            for k, cnt in allocate(pool, have, picked_order).items():
                tally[k] = tally.get(k, 0) + cnt

        sections.append(
            {"name": sec.name, "score": sec.score, "want": want_sum, "have": have_sum}
        )
        total += have_sum

    return {
        "total": total,
        "tally": tally,
        "shortfall": shortfall,
        "sections": sections,
        "full_score": sum(s["score"] for s in sections),
    }


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

    conf = json.loads(paper.config_json or "{}")
    groups: list[dict] = []
    tally: dict[str, int] = {k: 0 for k in scope_order(db)}
    total = 0

    for it in paper.items:
        q = db.get(Question, it.question_id)
        if not q:
            continue  # 题目后来被物理删除了，跳过
        snap = json.loads(it.snapshot_json) if it.snapshot_json else {}
        name = it.section or q.type  # 老卷子没存大题，按题型归
        item = {
            "id": q.id,
            "code": q.code,
            "type": q.type,
            "stem": q.stem,
            "answer": snap.get("answer", q.answer),
            "scope": q.scope,
            "source": q.source,
            "image_url": q.image_url,
            "difficulty": q.difficulty,
            "section": name,
            "score": it.score or 0,
            "options": snap.get("options")
            or [{"label": o.label, "content": o.content} for o in q.options],
        }
        group = next((g for g in groups if g["name"] == name), None)
        if not group:
            group = {"name": name, "type": name, "score": 0, "items": []}
            groups.append(group)
        group["items"].append(item)
        group["score"] += item["score"]
        tally[q.scope] = tally.get(q.scope, 0) + 1
        total += 1

    return {
        "paper_id": paper.id,
        "title": paper.title,
        "school": paper.school,
        "duration": paper.duration,
        "code": paper.code,
        "seed": conf.get("seed", ""),
        "total": total,
        "full_score": sum(g["score"] for g in groups),
        "by_sections": bool(conf.get("by_sections")),
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
