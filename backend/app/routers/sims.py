"""仿真操作题的题面与判分规则（教师端）。

一个仿真任务 = 初始环境 + 检查点。题库里的操作题挂上它之后，学生就能在
网页里把操作做完，服务端按检查点判分（见 services/sim.py）。

**检查点等同于答案**：这里所有带检查点的接口都要求登录教师身份，
学生端一律走 exam 那条路，由 sim.sim_for_student() 把检查点摘掉。

出题怎么省事：老师在仿真器里把题做一遍，按「以当前状态为答案」，前端把
初始环境和终态发到 /propose，这里算出差异、生成检查点草稿，老师改改措辞和
分值就能存。指望一线老师手写断言 JSON 是不现实的。
"""

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import Question, SimTask, User
from ..schemas import SimProposeIn, SimTaskIn, SimTaskOut, SimTaskUpdate, SimTryIn
from ..services import sim

router = APIRouter(prefix="/api/sims", tags=["仿真操作题"])


def _load(raw: str, fallback):
    try:
        got = json.loads(raw or "")
    except (ValueError, TypeError):
        return fallback
    return got if isinstance(got, type(fallback)) else fallback


def _out(row: SimTask, count: int = 0) -> SimTaskOut:
    return SimTaskOut(
        id=row.id,
        kind=row.kind,
        title=row.title,
        env=_load(row.env_json, {}),
        checks=_load(row.checks_json, []),
        question_count=count,
        created_at=row.created_at,
    )


def _get(db: Session, sid: int) -> SimTask:
    row = db.get(SimTask, sid)
    if not row:
        raise HTTPException(status_code=404, detail="这个仿真任务不存在")
    return row


@router.get("", response_model=list[SimTaskOut], summary="仿真任务列表")
def list_sims(
    kind: str | None = Query(None, pattern="^(win|wps|html)$"),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(SimTask)
    if kind:
        stmt = stmt.where(SimTask.kind == kind)
    rows = list(db.scalars(stmt.order_by(SimTask.id.desc())))
    used = dict(
        db.execute(
            select(Question.sim_task_id, func.count())
            .where(Question.sim_task_id.isnot(None), Question.is_deleted.is_(False))
            .group_by(Question.sim_task_id)
        ).all()
    )
    return [_out(r, used.get(r.id, 0)) for r in rows]


@router.get("/blank", summary="某种题型的空白环境")
def blank(kind: str = Query(pattern="^(win|wps|html)$"), _: User = Depends(get_current_user)):
    """新建时给个能直接上手的起点，不用从空 JSON 开始编。"""
    return {"kind": kind, "env": sim.blank_env(kind)}


@router.get("/{sid}", response_model=SimTaskOut, summary="仿真任务详情（含检查点）")
def get_sim(sid: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _out(_get(db, sid))


@router.post("", response_model=SimTaskOut, summary="新建仿真任务")
def create_sim(body: SimTaskIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    row = SimTask(
        kind=body.kind,
        title=(body.title or "").strip()[:128],
        env_json=json.dumps(body.env or sim.blank_env(body.kind), ensure_ascii=False),
        checks_json=json.dumps(body.checks, ensure_ascii=False),
        created_by=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.patch("/{sid}", response_model=SimTaskOut, summary="改仿真任务")
def update_sim(sid: int, body: SimTaskUpdate, _: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    row = _get(db, sid)
    data = body.model_dump(exclude_unset=True)
    if "title" in data:
        row.title = (data["title"] or "").strip()[:128]
    if "env" in data and data["env"] is not None:
        row.env_json = json.dumps(data["env"], ensure_ascii=False)
    if "checks" in data and data["checks"] is not None:
        row.checks_json = json.dumps(data["checks"], ensure_ascii=False)
    db.commit()
    db.refresh(row)
    return _out(row)


@router.delete("/{sid}", summary="删除仿真任务")
def delete_sim(sid: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """挂着这个任务的题目不会跟着删，只是退回「老师人工评阅」。

    已经考完的答卷也不受影响 —— 那些分早就算进成绩里了。
    """
    row = _get(db, sid)
    n = db.query(Question).filter(Question.sim_task_id == sid).update(
        {Question.sim_task_id: None}, synchronize_session=False
    )
    db.delete(row)
    db.commit()
    return {"ok": True, "detached": n}


@router.post("/propose", summary="拿初始环境和终态的差异生成检查点草稿")
def propose(body: SimProposeIn, _: User = Depends(get_current_user)):
    checks = sim.propose(body.kind, body.env, body.state)
    return {"checks": checks, "count": len(checks)}


@router.post("/{sid}/try", summary="试判：拿一份终态跑一遍检查点")
def try_run(sid: int, body: SimTryIn, _: User = Depends(get_current_user),
            db: Session = Depends(get_db)):
    """老师存题之前自己验一遍：按答案做一遍应该满分，什么都不做应该 0 分。

    检查点写错了（比如路径少写一层）在这里就能看出来，
    不用等考完了才发现全班这道题都是 0 分。
    """
    row = _get(db, sid)
    checks = body.checks if body.checks is not None else _load(row.checks_json, [])
    return sim.run_checks(row.kind, checks, body.state or {})
