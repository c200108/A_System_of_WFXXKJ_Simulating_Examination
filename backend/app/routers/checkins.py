"""课堂签到 + 在线座次附加工作表（2.24.0）。规则见 services/checkin.py。

老师（要登录，发起 / 结束 / 改表只给本班老师和管理员，看谁都能看）：
    POST   /api/classes/{cid}/checkins              发起签到 {minutes: 1~10}
    GET    /api/classes/{cid}/checkins/current      最近一次签到的进度（网页每 2 秒问一次，结束就不问了）
    POST   /api/classes/{cid}/checkins/{id}/stop    提前结束
    GET    /api/classes/{cid}/seat-tabs             附加工作表清单（sheet1 是 classes.seat_sheet，不在这里）
    GET/PUT/DELETE /api/classes/{cid}/seat-tabs/{tid}

学生桌面端（学生令牌）：
    GET    /api/student/checkin     有没有签到（顺便记一次在线心跳）
    POST   /api/student/checkin     签到 {checkin_id, seat}
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..database import get_db
from ..deps import get_current_student, get_current_user
from ..models import Checkin, SchoolClass, SeatTab, Student, User
from ..services import checkin as ck
from ..services import throttle
from .classes import SEAT_SHEET_MAX, _can_seat, _class_or_404


router = APIRouter(prefix="/api/classes", tags=["课堂签到"])
student_router = APIRouter(prefix="/api/student", tags=["学生平台"])


class CheckinIn(BaseModel):
    minutes: int = Field(ge=1, le=10)


class CheckinSignIn(BaseModel):
    checkin_id: int
    seat: str = Field(max_length=16)


class SeatTabIn(BaseModel):
    sheet: dict


def _ip(request: Request) -> str:
    return throttle.ip_of(request)[3:]


def _device(request: Request) -> str:
    who = throttle.device_of(request)
    return who if who.startswith("d:") else ""


# ---------------------------------------------------------------- 老师
@router.post("/{cid}/checkins", summary="发起签到")
def start_checkin(cid: int, body: CheckinIn, me: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    cls = _class_or_404(db, cid)
    _can_seat(cls, me)
    row = ck.start(db, cls, body.minutes, me.name or me.username)
    return ck.teacher_view(db, cls, row)


@router.get("/{cid}/checkins/current", summary="最近一次签到的进度")
def current_checkin(cid: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cls = _class_or_404(db, cid)
    row = db.scalar(select(Checkin).where(Checkin.class_id == cid).order_by(Checkin.id.desc()).limit(1))
    return {"checkin": ck.teacher_view(db, cls, row) if row else None}


@router.post("/{cid}/checkins/{kid}/stop", summary="提前结束签到")
def stop_checkin(cid: int, kid: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cls = _class_or_404(db, cid)
    _can_seat(cls, me)
    row = db.get(Checkin, kid)
    if not row or row.class_id != cid:
        raise HTTPException(status_code=404, detail="没有这次签到")
    now = clock.now()
    if row.ends_at > now:
        row.ends_at = now
        db.commit()
    return ck.teacher_view(db, cls, row)


def _tab_or_404(db: Session, cid: int, tid: int) -> SeatTab:
    tab = db.get(SeatTab, tid)
    if not tab or tab.class_id != cid:
        raise HTTPException(status_code=404, detail="这张工作表不存在（可能被删了）")
    return tab


@router.get("/{cid}/seat-tabs", summary="在线座次的附加工作表")
def list_tabs(cid: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _class_or_404(db, cid)
    rows = db.scalars(select(SeatTab).where(SeatTab.class_id == cid).order_by(SeatTab.id))
    return [{"id": t.id, "name": t.name, "created_at": t.created_at} for t in rows]


@router.get("/{cid}/seat-tabs/{tid}", summary="取一张附加工作表")
def get_tab(cid: int, tid: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cls = _class_or_404(db, cid)
    tab = _tab_or_404(db, cid, tid)
    return {"id": tab.id, "name": tab.name, "sheet": json.loads(tab.sheet),
            "can_edit": me.role == "admin" or cls.owner_id == me.id}


@router.put("/{cid}/seat-tabs/{tid}", summary="保存一张附加工作表")
def save_tab(cid: int, tid: int, body: SeatTabIn, me: User = Depends(get_current_user),
             db: Session = Depends(get_db)):
    cls = _class_or_404(db, cid)
    _can_seat(cls, me)
    tab = _tab_or_404(db, cid, tid)
    raw = json.dumps(body.sheet, ensure_ascii=False)
    if len(raw.encode("utf-8")) > SEAT_SHEET_MAX:
        raise HTTPException(status_code=413, detail="座次表太大了（超过 2 MB）")
    tab.sheet = raw
    db.commit()
    return {"ok": True}


@router.delete("/{cid}/seat-tabs/{tid}", summary="删一张附加工作表")
def delete_tab(cid: int, tid: int, me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    cls = _class_or_404(db, cid)
    _can_seat(cls, me)
    tab = _tab_or_404(db, cid, tid)
    if ck.active(db, cid) and ck.active(db, cid).tab_id == tab.id:
        raise HTTPException(status_code=409, detail="签到还在进行，这张表正在用，结束签到后再删")
    db.delete(tab)
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- 学生桌面端
@student_router.get("/checkin", summary="有没有签到（学生端每几秒问一次，顺便记在线）")
def my_checkin(request: Request, me: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    ck.heartbeat(db, me, _device(request), _ip(request))
    out = ck.student_view(db, me)
    db.commit()
    return out


@student_router.post("/checkin", summary="签到：选座号")
def do_checkin(body: CheckinSignIn, request: Request, me: Student = Depends(get_current_student),
               db: Session = Depends(get_db)):
    ck.heartbeat(db, me, _device(request), _ip(request))     # 签到本身也算在线
    return ck.sign(db, me, body.checkin_id, body.seat, _device(request), _ip(request))
