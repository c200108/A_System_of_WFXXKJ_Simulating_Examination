"""课堂签到（2.24.0）。

老师在班级详情里「发起签到」（1～10 分钟）→ 自动建一张附加工作表（表名是发起时间，结构照搬 sheet1、
姓名格清空）→ 本班登录着的学生桌面端每几秒问一次 /api/student/checkin，问到就弹框锁住，
学生从下拉框选座号签到 → 姓名立刻填进那张表的座位上，老师网页每 2 秒刷新一次看到。

## 座号是什么

在线座次 sheet1 里写着座号的格子：一到三个字母加一到三位数字，如 `A1`、`B12`、`C3`（学校默认空表就是
这么排的：座号一格，紧挨着右边一格写姓名）。签到时姓名填进座号**右边那一格**。标成「设备故障」的
座位（sheet.broken 里有那个姓名格）不给选。sheet1 里一个座号都没有的班不能发起签到。

## 同一台电脑只能给一个人签

学生端带的设备号（exe 按网卡和机器名算的 X-Device-Id）一次签到只能用一次；机房版（学生机直连，
看到的是学生机自己的内网 IP）同一个内网 IP 也只能签一次。线上服务器前面有 nginx、整个机房一个出口 IP，
那时只认设备号。
"""

from __future__ import annotations

import copy
import ipaddress
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import clock
from ..models import Checkin, CheckinEntry, ClientOnline, SchoolClass, SeatTab, Student

MINUTES = range(1, 11)
ONLINE_SECONDS = 20          # 最近这么多秒内有心跳的算「已登录」
POLL_SECONDS = 5             # 学生端多久问一次
SEAT = re.compile(r"^[A-Za-z]{1,3}[0-9]{1,3}$")
DEFAULT = Path(__file__).resolve().parents[1] / "assets" / "seat-default.json"


def default_sheet() -> dict:
    return json.loads(DEFAULT.read_text(encoding="utf-8"))


def sheet1(cls: SchoolClass) -> dict:
    """班级的主座次表（没存过就是学校默认空表）。"""
    if cls.seat_sheet:
        try:
            got = json.loads(cls.seat_sheet)
            if isinstance(got, dict) and isinstance(got.get("data"), list):
                return got
        except ValueError:
            pass
    return default_sheet()


def _cell(x: int, y: int) -> str:
    out, n = "", x + 1
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return f"{out}{y + 1}"


def seats(sheet: dict) -> list[dict]:
    """表里的座位：[{seat: 'A1', x, y}]，x/y 是**姓名格**（座号右边那格）的坐标。按表格先行后列。"""
    data = sheet.get("data") or []
    broken = sheet.get("broken") or {}
    out, seen = [], set()
    for y, row in enumerate(data):
        if not isinstance(row, list):
            continue
        for x, v in enumerate(row):
            label = str(v if v is not None else "").strip().upper()
            if not SEAT.match(label) or label in seen or x + 1 >= len(row):
                continue
            if _cell(x + 1, y) in broken:
                continue
            seen.add(label)
            out.append({"seat": label, "x": x + 1, "y": y})
    return out


def blank_copy(sheet: dict) -> dict:
    """照搬结构，把座位上的姓名格清空（签到时一个一个填）。"""
    out = copy.deepcopy(sheet)
    for s in seats(out):
        out["data"][s["y"]][s["x"]] = ""
    return out


def active(db: Session, class_id: int, now: datetime | None = None) -> Checkin | None:
    now = now or clock.now()
    return db.scalar(select(Checkin).where(Checkin.class_id == class_id, Checkin.ends_at > now)
                     .order_by(Checkin.id.desc()).limit(1))


def start(db: Session, cls: SchoolClass, minutes: int, who: str) -> Checkin:
    if minutes not in MINUTES:
        raise HTTPException(status_code=400, detail="签到时长只能是 1～10 分钟")
    now = clock.now()
    if active(db, cls.id, now):
        raise HTTPException(status_code=409, detail="这个班已经有一个签到在进行中，等它结束或先点「结束签到」")
    base = sheet1(cls)
    if not seats(base):
        raise HTTPException(status_code=400, detail="在线座次 sheet1 里没有座号（如 A1、B3 这样的格子），学生没法选座位")
    name = now.strftime("%Y%m%d/%H:%M")
    taken = set(db.scalars(select(SeatTab.name).where(SeatTab.class_id == cls.id)))
    if name in taken:
        n = 2
        while f"{name}-{n}" in taken:
            n += 1
        name = f"{name}-{n}"
    tab = SeatTab(class_id=cls.id, name=name, sheet=json.dumps(blank_copy(base), ensure_ascii=False),
                  created_at=now)
    db.add(tab)
    db.flush()
    row = Checkin(class_id=cls.id, tab_id=tab.id, started_by=who[:64], started_at=now,
                  ends_at=now + timedelta(minutes=minutes))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _private(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # 只认学校内网那三段（机房版学生机直连时看到的就是它们）；回环、文档用的地址段都不算
    lan = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    return a.version == 4 and any(a in ipaddress.ip_network(n) for n in lan)


def heartbeat(db: Session, student: Student, device: str, ip: str) -> None:
    now = clock.now()
    row = db.get(ClientOnline, student.id)
    if row is None:
        db.add(ClientOnline(student_id=student.id, last_seen=now, device=device[:80], ip=ip[:64]))
    else:
        row.last_seen, row.device, row.ip = now, device[:80], ip[:64]


def _tab_sheet(db: Session, row: Checkin) -> tuple[SeatTab | None, dict]:
    tab = db.get(SeatTab, row.tab_id) if row.tab_id else None
    try:
        return tab, json.loads(tab.sheet) if tab else {}
    except ValueError:
        return tab, {}


def student_view(db: Session, student: Student) -> dict:
    """学生端问「有没有签到」：有就带上剩余秒数、可选座号（已被占的标出来）、自己签没签。"""
    now = clock.now()
    row = active(db, student.class_id, now) if student.class_id else None
    if not row:
        return {"active": False, "poll": POLL_SECONDS}
    entries = list(db.scalars(select(CheckinEntry).where(CheckinEntry.checkin_id == row.id)))
    mine = next((e for e in entries if e.student_id == student.id), None)
    taken = {e.seat for e in entries}
    _, sheet = _tab_sheet(db, row)
    cls = db.get(SchoolClass, row.class_id)
    return {
        "active": True, "poll": POLL_SECONDS, "checkin_id": row.id,
        "class": cls.display if cls else "", "started_by": row.started_by,
        "remaining": max(0, int((row.ends_at - now).total_seconds())),
        "signed": {"seat": mine.seat} if mine else None,
        "seats": [{"seat": s["seat"], "taken": s["seat"] in taken} for s in seats(sheet)],
    }


def sign(db: Session, student: Student, checkin_id: int, seat: str, device: str, ip: str) -> dict:
    seat = str(seat or "").strip().upper()
    now = clock.now()
    row = db.scalar(select(Checkin).where(Checkin.id == checkin_id).with_for_update())
    if not row or row.class_id != student.class_id:
        raise HTTPException(status_code=404, detail="没有这个签到（可能不是你们班的）")
    if row.ends_at <= now:
        raise HTTPException(status_code=410, detail="签到时间已经过了")
    entries = list(db.scalars(select(CheckinEntry).where(CheckinEntry.checkin_id == row.id)))
    mine = next((e for e in entries if e.student_id == student.id), None)
    if mine:
        return {"ok": True, "seat": mine.seat, "already": True}
    tab, sheet = _tab_sheet(db, row)
    spot = next((s for s in seats(sheet) if s["seat"] == seat), None)
    if not spot:
        raise HTTPException(status_code=400, detail=f"座号「{seat}」不在座次表里，请从下拉框里选")
    if any(e.seat == seat for e in entries):
        raise HTTPException(status_code=409, detail=f"{seat} 已经有同学签了，请选你自己的座位；坐错了请找老师")
    device = (device or "").strip()[:80] or f"ip:{ip}"
    names = {s.id: s.name for s in db.scalars(select(Student).where(
        Student.id.in_([e.student_id for e in entries] or [0])))}
    for e in entries:
        if e.device == device or (_private(ip) and e.ip == ip):
            raise HTTPException(status_code=409, detail=(
                f"这台电脑已经给「{names.get(e.student_id, '另一位同学')}」签过到了，"
                "一台电脑只能签一个人。请在自己的电脑上登录签到"))
    db.add(CheckinEntry(checkin_id=row.id, student_id=student.id, seat=seat, device=device,
                        ip=ip[:64], at=now))
    if tab is not None:
        sheet["data"][spot["y"]][spot["x"]] = student.name
        tab.sheet = json.dumps(sheet, ensure_ascii=False)
    db.commit()
    return {"ok": True, "seat": seat, "already": False}


def teacher_view(db: Session, cls: SchoolClass, row: Checkin) -> dict:
    """老师看的：应到、已签（姓名—座号）、未签名单、缺勤人数、已登录的学生（含没签的）。"""
    now = clock.now()
    roster = list(db.scalars(select(Student).where(Student.class_id == cls.id, Student.is_active.is_(True))
                             .order_by(Student.student_no)))
    entries = list(db.scalars(select(CheckinEntry).where(CheckinEntry.checkin_id == row.id)
                              .order_by(CheckinEntry.id)))
    by_id = {s.id: s for s in roster}
    signed = {e.student_id: e for e in entries}
    online = {o.student_id for o in db.scalars(select(ClientOnline).where(
        ClientOnline.student_id.in_(list(by_id) or [0]),
        ClientOnline.last_seen >= now - timedelta(seconds=ONLINE_SECONDS)))}
    tab = db.get(SeatTab, row.tab_id) if row.tab_id else None
    return {
        "id": row.id, "tab_id": row.tab_id, "tab_name": tab.name if tab else "",
        "started_by": row.started_by, "started_at": row.started_at, "ends_at": row.ends_at,
        "active": row.ends_at > now, "remaining": max(0, int((row.ends_at - now).total_seconds())),
        "version": f"{len(entries)}-{entries[-1].id if entries else 0}",
        "total": len(roster), "signed_count": len(entries), "absent": len(roster) - len(signed),
        "signed": [{"student_id": e.student_id, "name": by_id[e.student_id].name if e.student_id in by_id else "?",
                    "student_no": by_id[e.student_id].student_no if e.student_id in by_id else "",
                    "seat": e.seat, "at": e.at} for e in entries],
        "unsigned": [{"student_id": s.id, "name": s.name, "student_no": s.student_no,
                      "online": s.id in online} for s in roster if s.id not in signed],
        "online": [{"student_id": s.id, "name": s.name, "seat": signed[s.id].seat if s.id in signed else ""}
                   for s in roster if s.id in online],
    }
