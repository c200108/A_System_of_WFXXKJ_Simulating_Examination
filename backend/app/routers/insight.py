"""学生学情（2.16.0）：一个学生的考试、排名、打字、第三方教学网页数据汇总在一页。

教师端学生名单「学情」一列点进来。看得到谁的学情和学生名单一样按班隔离：
老师只看自己班的学生，管理员看全校。

各块数据的口径：
- 考试：老师看得到的考试（自己发的 + 管理员发的，同考试页），同一场考了几次取最新一次；
  排名按这场考试里每个学生的最新一份答卷算，分「全部参考」和「本班」两个名次；
- 打字：这个学生账号下的成绩，以及没登录、手填了同班同名的成绩；
- 第三方网页（API 数据）：对上了这个学生的记录，**只算看的人自己的 API**（管理员看全部）——
  各老师的 API 数据不互通，学情里也一样；同伴对他的互评（被评人是他）单列。
"""

from __future__ import annotations

import json
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import DataApi, DataRecord, DataRecordItem, Exam, ExamSubmission, Student, TypingRecord, User
from ..services import dataapi as svc
from .exams import _visible as visible_exams
from .students import _in_scope, _scope

router = APIRouter(prefix="/api/students", tags=["学生学情"])


def _full(s: ExamSubmission) -> int:
    return (s.objective_total or 0) + (s.subjective_total or 0)


def _rate(s: ExamSubmission) -> float | None:
    f = _full(s)
    return round((s.score or 0) / f * 100, 1) if f > 0 else None


def _key(s: ExamSubmission) -> str:
    return f"id:{s.student_id}" if s.student_id else f"no:{s.student_no}" if s.student_no else \
        f"nm:{s.student_class}/{s.student_name}"


def _latest(subs) -> dict[str, ExamSubmission]:
    out: dict[str, ExamSubmission] = {}
    for s in sorted(subs, key=lambda x: (x.submitted_at, x.id)):
        out[_key(s)] = s
    return out


def _rank(score: int, scores: list[int]) -> int:
    return 1 + sum(1 for x in scores if x > score)


def _exams(db: Session, me: User, stu: Student) -> dict:
    mine = or_(ExamSubmission.student_id == stu.id,
               and_(ExamSubmission.student_id.is_(None), ExamSubmission.student_no == stu.student_no,
                    ExamSubmission.student_no != ""))
    exam_ids = set(db.scalars(select(ExamSubmission.exam_id).where(mine)))
    if not exam_ids:
        return {"items": [], "count": 0, "avg_rate": None, "class_rank": None, "class_size": None}
    exams = db.scalars(visible_exams(select(Exam).where(Exam.id.in_(exam_ids)), me, db)).all()
    items = []
    for e in exams:
        latest = _latest(e.submissions)
        me_sub = next((s for k, s in latest.items()
                       if s.student_id == stu.id or (not s.student_id and s.student_no == stu.student_no)), None)
        if not me_sub:
            continue
        all_scores = [s.score or 0 for s in latest.values()]
        cls_subs = [s for s in latest.values() if s.student_class == me_sub.student_class]
        cls_scores = [s.score or 0 for s in cls_subs]
        items.append({
            "exam_id": e.id, "title": e.title, "submitted_at": me_sub.submitted_at,
            "score": me_sub.score or 0, "full": _full(me_sub), "rate": _rate(me_sub),
            "right_count": me_sub.right_count, "objective_count": me_sub.objective_count,
            "pending": me_sub.subjective_total > 0 and me_sub.graded_at is None,
            "rank": _rank(me_sub.score or 0, all_scores), "takers": len(all_scores),
            "class_rank": _rank(me_sub.score or 0, cls_scores), "class_takers": len(cls_scores),
            "avg": round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
            "class_avg": round(sum(cls_scores) / len(cls_scores), 1) if cls_scores else None,
            "attempts": sum(1 for s in e.submissions
                            if s.student_id == stu.id or (not s.student_id and s.student_no == stu.student_no)),
        })
    items.sort(key=lambda x: x["submitted_at"] or 0)
    rates = [i["rate"] for i in items if i["rate"] is not None]
    avg_rate = round(sum(rates) / len(rates), 1) if rates else None

    # 班内综合名次：同班同学在这几场里的平均得分率
    class_rank = class_size = None
    if avg_rate is not None and stu.student_class:
        per: dict[str, list] = defaultdict(list)
        for e in exams:
            for s in _latest(e.submissions).values():
                if s.student_class == stu.student_class and _rate(s) is not None:
                    per[_key(s)].append(_rate(s))
        avgs = {k: sum(v) / len(v) for k, v in per.items() if v}
        mine_avg = avgs.get(f"id:{stu.id}") or avgs.get(f"no:{stu.student_no}") or avg_rate
        class_size = len(avgs)
        class_rank = 1 + sum(1 for v in avgs.values() if v > mine_avg + 1e-9)
    return {"items": items, "count": len(items), "avg_rate": avg_rate,
            "class_rank": class_rank, "class_size": class_size}


def _typing(db: Session, stu: Student) -> dict:
    rows = db.scalars(select(TypingRecord).where(or_(
        TypingRecord.student_id == stu.id,
        and_(TypingRecord.student_id.is_(None), TypingRecord.student_name == stu.name,
             TypingRecord.student_class == stu.student_class, TypingRecord.student_class != ""),
    )).order_by(TypingRecord.created_at)).all()
    by_mod: dict[str, list] = defaultdict(list)
    for r in rows:
        by_mod[r.module].append(r)
    modules = [{
        "module": m, "count": len(v), "best_speed": max(x.speed for x in v),
        "avg_speed": round(sum(x.speed for x in v) / len(v)), "avg_accuracy": round(sum(x.accuracy for x in v) / len(v)),
        "minutes": round(sum(x.duration for x in v) / 60),
    } for m, v in by_mod.items()]
    return {
        "count": len(rows),
        "best_speed": max((r.speed for r in rows), default=0),
        "avg_accuracy": round(sum(r.accuracy for r in rows) / len(rows)) if rows else None,
        "minutes": round(sum(r.duration for r in rows) / 60),
        "modules": modules,
        "recent": [{"at": r.created_at, "module": r.module, "difficulty": r.difficulty, "speed": r.speed,
                    "accuracy": r.accuracy, "duration": r.duration, "stars": r.stars}
                   for r in rows[-100:][::-1]],
        "trend": [{"at": r.created_at, "module": r.module, "speed": r.speed, "accuracy": r.accuracy}
                  for r in rows[-200:]],
    }


def _web(db: Session, me: User, stu: Student) -> dict:
    apis = db.scalars(select(DataApi) if me.role == "admin"
                      else select(DataApi).where(DataApi.owner_id == me.id)).all()
    by_id = {a.id: a for a in apis}
    if not by_id:
        return {"count": 0, "apis": [], "recent": [], "dimensions": [], "peer_received": []}
    recs = db.scalars(select(DataRecord).where(
        DataRecord.api_id.in_(list(by_id)), DataRecord.student_id == stu.id, DataRecord.flag == "normal",
    ).order_by(DataRecord.received_at)).all()
    # 同伴给他的互评
    peer = db.scalars(select(DataRecord).where(
        DataRecord.api_id.in_(list(by_id)), DataRecord.type == "peer_eval", DataRecord.flag == "normal",
        or_(and_(DataRecord.target_no == stu.student_no, DataRecord.target_no != ""),
            and_(DataRecord.target_no == "", DataRecord.target_name == stu.name,
                 or_(DataRecord.class_name == stu.student_class, DataRecord.class_name == ""))),
    ).order_by(DataRecord.received_at)).all()

    groups: dict[int, list] = defaultdict(list)
    for r in recs:
        groups[r.api_id].append(r)
    api_out = []
    for aid, rs in groups.items():
        sc = [r.score / r.max_score * 100 for r in rs if r.score is not None and r.max_score]
        api_out.append({
            "api_id": aid, "name": by_id[aid].name, "template": by_id[aid].template,
            "count": len(rs), "last_at": rs[-1].received_at,
            "avg_rate": round(sum(sc) / len(sc), 1) if sc else None,
            "pages": sorted({r.page for r in rs if r.page}),
            "activities": sorted({r.activity_name or r.activity_id for r in rs if r.activity_name or r.activity_id}),
        })
    api_out.sort(key=lambda x: x["last_at"], reverse=True)

    # 评价维度：自评、同伴给他的评价，各自平均（有满分的折成百分）
    ids_self = [r.id for r in recs if r.type == "self_eval"]
    ids_peer = [r.id for r in peer]
    dims: dict[str, dict] = {}
    for kind, ids in (("self", ids_self), ("peer", ids_peer)):
        if not ids:
            continue
        for it in db.scalars(select(DataRecordItem).where(DataRecordItem.record_id.in_(ids),
                                                          DataRecordItem.kind == "rating")):
            if it.score is None:
                continue
            v = it.score / it.max_score * 100 if it.max_score else it.score
            dims.setdefault(it.item, {"self": [], "peer": []})[kind].append(v)
    avg = lambda xs: round(sum(xs) / len(xs), 1) if xs else None  # noqa: E731
    dimensions = [{"item": k, "self": avg(v["self"]), "peer": avg(v["peer"])} for k, v in dims.items()]

    def row(r: DataRecord) -> dict:
        try:
            payload = json.loads(r.payload or "{}")
        except ValueError:
            payload = {}
        if isinstance(payload, dict):
            payload.pop("_token", None)
        return {"id": r.id, "api_id": r.api_id, "api_name": by_id[r.api_id].name, "type": r.type,
                "type_name": svc.TYPE_NAMES.get(r.type, r.type),
                "activity": r.activity_name or r.activity_id, "page": r.page, "score": r.score,
                "max_score": r.max_score, "comment": r.comment, "at": r.received_at,
                "target": r.target_name or r.target_no, "student": r.student_name or r.student_no,
                "payload": payload}

    return {
        "count": len(recs),
        "apis": api_out,
        "recent": [row(r) for r in recs[-100:][::-1]],
        "dimensions": dimensions,
        "peer_received": [row(r) for r in peer[-50:][::-1]],
    }


@router.get("/{sid}/insight", summary="学生学情：考试、排名、打字、第三方网页数据")
def insight(sid: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    stu = db.get(Student, sid)
    if not stu or not _in_scope(stu, _scope(db, me)):
        raise HTTPException(status_code=404, detail="学生不存在")
    return {
        "student": {"id": stu.id, "student_no": stu.student_no, "name": stu.name,
                    "student_class": stu.student_class, "gender": stu.gender, "class_role": stu.class_role,
                    "is_active": stu.is_active},
        "exams": _exams(db, me, stu),
        "typing": _typing(db, stu),
        "web": _web(db, me, stu),
    }
