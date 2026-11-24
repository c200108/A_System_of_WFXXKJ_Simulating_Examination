"""课堂签到 + 在线座次附加工作表（2.24.0）。规则见 services/checkin.py。

老师（要登录，发起 / 结束 / 改表只给本班老师和管理员，看谁都能看）：
    POST   /api/classes/{cid}/checkins              发起签到 {minutes: 1~10}
    GET    /api/classes/{cid}/checkins/current      最近一次签到的进度（网页每 2 秒问一次，结束就不问了）
    POST   /api/classes/{cid}/checkins/{id}/stop    提前结束
    GET    /api/classes/{cid}/seat-tabs             附加工作表清单（sheet1 是 classes.seat_sheet，不在这里）
    GET/PUT/DELETE /api/classes/{cid}/seat-tabs/{tid}

    DELETE /api/classes/{cid}/checkins/{id}/entries/{eid}   撤销一条签到（2.26.0）

认座设置（2.26.0，全校一份；看谁都能看，改只给管理员）：
    GET    /api/checkin-seat/rule               现在的认座规则、绑座模式还剩多久
    PUT    /api/checkin-seat/rule               {mode, offset}
    GET    /api/checkin-seat/preview            按某个规则算「哪台电脑 → 哪个座号」 ?mode&offset&class_id
    POST   /api/checkin-seat/bind-mode          开 / 关绑座模式 {minutes: 0~60}
    GET    /api/checkin-seat/bindings           绑过座号的电脑
    DELETE /api/checkin-seat/bindings/{device}  删一条（device = all 全删）

学生桌面端（学生令牌）：
    GET    /api/student/checkin     有没有签到（顺便记一次在线心跳）?host=电脑名&lan_ip=内网IP（4.16.0 起带）
    POST   /api/student/checkin     签到 {checkin_id, seat, host, lan_ip}
    POST   /api/student/seat-bind   绑座模式里给这台电脑选座号 {seat, host, lan_ip}
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..database import get_db
from ..deps import get_current_student, get_current_user, require_admin
from ..models import Checkin, SchoolClass, SeatBinding, SeatTab, Student, User
from ..services import checkin as ck
from ..services import throttle
from .classes import SEAT_SHEET_MAX, _can_seat, _class_or_404


router = APIRouter(prefix="/api/classes", tags=["课堂签到"])
seat_router = APIRouter(prefix="/api/checkin-seat", tags=["课堂签到"])
student_router = APIRouter(prefix="/api/student", tags=["学生平台"])


class CheckinIn(BaseModel):
    minutes: int = Field(ge=1, le=10)


class CheckinSignIn(BaseModel):
    checkin_id: int
    seat: str = Field(max_length=16)
    host: str = Field(default="", max_length=128)
    lan_ip: str = Field(default="", max_length=64)


class SeatRuleIn(BaseModel):
    mode: str = Field(max_length=16)
    offset: int = Field(default=0, ge=0, le=65535)


class BindModeIn(BaseModel):
    minutes: int = Field(ge=0, le=60)


class SeatBindIn(BaseModel):
    seat: str = Field(max_length=16)
    host: str = Field(default="", max_length=128)
    lan_ip: str = Field(default="", max_length=64)


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


@router.delete("/{cid}/checkins/{kid}/entries/{eid}", summary="撤销一条签到")
def revoke_entry(cid: int, kid: int, eid: int, me: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    cls = _class_or_404(db, cid)
    _can_seat(cls, me)
    row = db.get(Checkin, kid)
    if not row or row.class_id != cid:
        raise HTTPException(status_code=404, detail="没有这次签到")
    ck.revoke(db, row, eid)
    return ck.teacher_view(db, cls, row)


# ---------------------------------------------------------------- 认座设置
def _rule_out(db: Session) -> dict:
    until = ck.bind_until(db)
    return {**ck.rule(db), "modes": ck.MODES,
            "bind_remaining": max(0, int((until - clock.now()).total_seconds())) if until else 0}


@seat_router.get("/rule", summary="认座规则")
def get_rule(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _rule_out(db)


@seat_router.put("/rule", summary="改认座规则（管理员）")
def put_rule(body: SeatRuleIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    ck.set_rule(db, body.mode, body.offset)
    return _rule_out(db)


@seat_router.get("/preview", summary="按规则预览哪台电脑对哪个座号")
def rule_preview(mode: str = "", offset: int = -1, class_id: int = 0,
                 _: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = ck.rule(db)
    if mode in ck.MODES:
        r["mode"] = mode
    if 0 <= offset <= 65535:
        r["offset"] = offset
    cls = db.get(SchoolClass, class_id) if class_id else None
    labels = [x["seat"] for x in ck.seats(ck.sheet1(cls) if cls else ck.default_sheet())]
    return {**ck.preview(db, r, labels), "mode": r["mode"], "offset": r["offset"],
            "sheet": cls.display if cls else "学校默认座次表"}


@seat_router.post("/bind-mode", summary="开 / 关绑座模式（管理员）")
def bind_mode(body: BindModeIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    ck.set_bind_mode(db, body.minutes)
    return _rule_out(db)


@seat_router.get("/bindings", summary="绑过座号的电脑")
def list_bindings(_: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return ck.bindings(db)


@seat_router.delete("/bindings/{device}", summary="删绑座（管理员；all = 全删）")
def delete_binding(device: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    q = select(SeatBinding) if device == "all" else select(SeatBinding).where(SeatBinding.device == device)
    for b in db.scalars(q):
        db.delete(b)
    db.commit()
    return {"ok": True}


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
def my_checkin(request: Request, host: str = "", lan_ip: str = "",
               me: Student = Depends(get_current_student), db: Session = Depends(get_db)):
    host, lan_ip = ck.clean_host(host), ck.clean_ip(lan_ip)
    ck.heartbeat(db, me, _device(request), _ip(request), host, lan_ip)
    db.commit()                       # 心跳先落库：下面自动签到签不上回滚时不连它一起丢
    out = ck.student_view(db, me, _device(request), _ip(request), host, lan_ip)
    db.commit()
    return out


@student_router.post("/checkin", summary="签到：选座号")
def do_checkin(body: CheckinSignIn, request: Request, me: Student = Depends(get_current_student),
               db: Session = Depends(get_db)):
    host, lan_ip = ck.clean_host(body.host), ck.clean_ip(body.lan_ip)
    ck.heartbeat(db, me, _device(request), _ip(request), host, lan_ip)     # 签到本身也算在线
    return ck.sign(db, me, body.checkin_id, body.seat, _device(request), _ip(request), host, lan_ip)


@student_router.post("/seat-bind", summary="绑座模式：给这台电脑选座号")
def do_bind(body: SeatBindIn, request: Request, me: Student = Depends(get_current_student),
            db: Session = Depends(get_db)):
    return ck.bind(db, me, body.seat, _device(request), ck.clean_host(body.host), ck.clean_ip(body.lan_ip))
