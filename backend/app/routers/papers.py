import io
import json
import zipfile
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..constants import DICT_TYPE
from ..database import get_db
from ..deps import get_current_user
from ..models import Exam, Paper, PaperItem, Question, User
from ..schemas import IdsIn, PaperExportIn, PaperGenerateIn, PaperGenerateOut, PaperOut
from ..services import recycle
from ..services.blueprint import slot_hint, slot_key, slot_pool
from ..services.export import questions_to_xlsx, student_html
from ..services.literacy import OBJECTIVE_TOTAL, split_scopes
from ..services.paper import build_by_sections, build_paper, even_scores, num, show, type_pool
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
                # 选择判断题乱序：学生取卷时各自打乱（services/exam.wants_shuffle）
                "shuffle": bool(paper.get("shuffle")),
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
                    # 按题型的卷子不存分值（可能带小数，列是整数），取题时当场平均分（even_scores）
                    score=int(it.get("score") or 0) if paper.get("by_sections") else 0,
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


def _check_literacy(body: PaperGenerateIn) -> str | None:
    """人工智能通识教育测评题的规矩（2.27.0），组卷和预览都先过一遍。返回选中的测评范围。

    - 和其他知识范围互斥，七、八年级之间也互斥；
    - 只能按题型组卷（六大题里根本没有它）；
    - 操作题固定 0 道；选择题 + 判断题合计 40 道，选择题多于判断题；填空题随意。
    """
    try:
        _, exam = split_scopes(body.scopes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if not exam:
        return None
    if body.by_sections:
        raise HTTPException(status_code=400, detail="人工智能通识教育测评题只能「按题型」组卷，六大题里没有它")
    counts = {k: max(0, int(v or 0)) for k, v in body.counts.items()}
    counts["操作题"] = 0
    pick_n, judge_n = counts.get("选择题", 0), counts.get("判断题", 0)
    if pick_n + judge_n != OBJECTIVE_TOTAL:
        raise HTTPException(
            status_code=400,
            detail=f"测评题的选择题和判断题一共要 {OBJECTIVE_TOTAL} 道（现在 {pick_n} + {judge_n}）",
        )
    if pick_n <= judge_n:
        raise HTTPException(status_code=400, detail="测评题的选择题要占大多数（比判断题多）")
    body.counts = counts
    return exam


@router.post("/generate", response_model=PaperGenerateOut, summary="均衡抽题组卷")
def generate(
    body: PaperGenerateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _check_literacy(body)
    order = scope_order(db)
    picked_order = [k for k in order if not body.scopes or k in body.scopes]

    common = dict(
        scope_order=picked_order,
        scopes=body.scopes,
        require_answer=body.require_answer,
        use_pinned=body.use_pinned,
        shuffle=body.wants_shuffle(),
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
    _check_literacy(body)
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
        pool = type_pool(db, qtype, body.scopes, body.require_answer)
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
            # **和真正抽题用同一个函数。** 自己再写一遍筛选条件的话，多一个
            # 筛选维度（比如"只要拖拽题"）就会漏掉一处：预览说够，组卷说不够。
            pool = slot_pool(db, slot, scopes_filter=body.scopes,
                             require_answer=body.require_answer)

            have = min(want, len(pool))
            want_sum += want
            have_sum += have
            if have < want:
                where = f"「{sec.name}」·{slot_hint(slot)}"
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
    rows = db.scalars(select(Paper).where(Paper.is_hidden.is_(False))
                      .order_by(Paper.id.desc()).limit(limit)).all()
    exams = dict(db.execute(
        select(Exam.paper_id, func.count()).where(Exam.paper_id.in_([p.id for p in rows]))
        .group_by(Exam.paper_id)
    ).all()) if rows else {}
    out = []
    for p in rows:
        item = PaperOut.model_validate(p)
        item.question_count = len(p.items)
        item.exam_count = exams.get(p.id, 0)
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

    # 按题型的卷子：和考试里一样当场每题平均分（2.28.0 补分，2.29.0 起每题一样）
    flat = [it for g in groups for it in g["items"]]
    even_scores(flat, force=conf.get("by_sections") is False)
    full = show(sum(num(it["score"]) for it in flat))
    for g in groups:
        g["score"] = show(sum(num(it["score"]) for it in g["items"]))
        for it in g["items"]:
            it["score"] = show(it["score"])

    return {
        "paper_id": paper.id,
        "title": paper.title,
        "school": paper.school,
        "duration": paper.duration,
        "code": paper.code,
        "seed": conf.get("seed", ""),
        "total": total,
        "full_score": full,
        "by_sections": bool(conf.get("by_sections")),
        "shuffle": bool(conf.get("shuffle")),
        "tally": tally,
        "warnings": [],
        "groups": groups,
        "questions": [it for g in groups for it in g["items"]],
    }


def _trash_paper(db: Session, user: User, paper: Paper) -> int:
    """删一份存档卷（2.28.0 起**不再连带删考试**）。

    还有考试在用这份卷：只把卷子从「历史试卷」里藏起来（is_hidden），考试照常能考、能看成绩、
    能看样卷 —— 两边解除绑定；没有考试在用：照旧真删，进回收站。
    返回「保留下来的考试场数」（藏起来的那种）。不提交 —— 单个删和批量删都在调用方一次提交。"""
    exams = db.scalars(select(Exam).where(Exam.paper_id == paper.id)).all()
    if exams:
        paper.is_hidden = True
        return len(exams)
    recycle.trash(db, user, "paper", f"试卷「{paper.title}」", Paper, [paper.id], detail=paper.code or "")
    db.delete(paper)
    return 0


@router.delete("/{paper_id}", summary="删除试卷")
def delete_paper(paper_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    paper = db.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在")
    kept = _trash_paper(db, user, paper)
    db.commit()
    return {"ok": True, "kept_exams": kept}


@router.post("/bulk-delete", summary="批量删除勾选的历史试卷（进回收站）")
def bulk_delete_papers(body: IdsIn, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """和单个删一样的规矩（登录的老师都能删，连带考试和答卷一起进回收站），
    每份卷各占回收站一条，能一份一份还原。整批一个事务：要么全删，要么一份不动。
    已经不在的（别人刚删了）记进 failed，不算错。"""
    ids = list(dict.fromkeys(body.ids))
    if not ids:
        raise HTTPException(status_code=400, detail="没有选中任何试卷")
    found = {p.id: p for p in db.scalars(select(Paper).where(Paper.id.in_(ids)))}
    deleted, exams, failed = [], 0, []
    for pid in ids:
        paper = found.get(pid)
        if paper is None:
            failed.append({"id": pid, "reason": "试卷不存在（可能已经被删了）"})
            continue
        exams += _trash_paper(db, user, paper)
        deleted.append(pid)
    db.commit()
    return {"deleted": deleted, "exams": exams, "failed": failed}


@router.post("/bulk-export", summary="批量导出勾选的历史试卷（打成一个 zip）")
def bulk_export_papers(body: PaperExportIn, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    """每份卷照单个导出的办法生成 Excel / 学生答题网页，打进一个 zip。
    文件名前面带序号和卷号，同名的卷子不会互相覆盖。找不到的卷子写进 zip 里的「说明.txt」。"""
    ids = list(dict.fromkeys(body.ids))
    if not ids:
        raise HTTPException(status_code=400, detail="没有选中任何试卷")
    buf = io.BytesIO()
    missing, done = [], 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, pid in enumerate(ids, 1):
            if db.get(Paper, pid) is None:
                missing.append(pid)
                continue
            paper = PaperGenerateOut(**get_paper(pid, user, db))
            stem = f"{i:02d}_{_safe_name(paper.title)}" + (f"_{paper.code}" if paper.code else "")
            if body.fmt in ("xlsx", "both"):
                rows = [it.model_dump() for g in paper.groups for it in g.items]
                zf.writestr(stem + ".xlsx", questions_to_xlsx(rows, "试卷"))
            if body.fmt in ("html", "both"):
                zf.writestr(stem + "_学生答题.html", student_html(paper.model_dump()).encode("utf-8"))
            done += 1
        if missing:
            zf.writestr("说明.txt", "下面这些试卷没找到（可能已经被删了），没有导出：\n"
                        + "\n".join(f"  id {m}" for m in missing) + "\n")
    if not done:
        raise HTTPException(status_code=404, detail="选中的试卷都不存在了")
    return Response(content=buf.getvalue(), media_type="application/zip",
                    headers=_attachment(f"历史试卷_{done}份.zip"))