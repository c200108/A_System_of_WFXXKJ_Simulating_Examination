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

## 按机器号自动认座（2.26.0）

学生自己从下拉框选座号，会有人乱选、占掉别人的位置。所以先看「这台电脑是哪个座位」，认得出就不让选：

1. **绑座**（seat_bindings）：老师开「绑座模式」，每台学生机登录后选一次座号，存在服务器上，按设备号认。
   哪种机房都能用，优先级最高；
2. **认座规则**（管理员在网页「认座设置」里选，全校一份，存 app_meta）：
   - host_tail 电脑名最后一段就是座号：`C09-COMPUTE-C14` → C14（联想云教室的机房就这么命名）；
   - host_num  电脑名末尾的数字 − 偏移 = 第几个座位：`PC-023` → 第 23 个；
   - ip_num    内网 IP 末段 − 偏移 = 第几个座位：`10.9.82.105`、偏移 100 → 第 5 个；
   「第几个」按座号排：先字母后数字（A1、A2…A15、B1…），网页上有预览，启用前看清楚哪台对哪个；
   - pick      不认，学生自己选（原来的做法，默认）；
3. 认不出来的电脑照旧从下拉框选。

认出来座号的电脑，学生一登录（或签到时已经登录着）**服务端直接签上**，不弹选择框，学生端只提示一下。
认出来的座号如果已经被一个**自己选的**（pick）同学占了，认出来的这台把它要回来（座号认主人），被挤掉的同学
签到框重新弹出来，再选别的；老师也能在签到详情里撤销任何一条。

电脑名、内网 IP 是学生端（4.16.0 起）自己报的；老学生端不报，就当认不出来，照旧下拉框选。
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
from ..models import AppMeta, Checkin, CheckinEntry, ClientOnline, SchoolClass, SeatBinding, SeatTab, Student

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


def heartbeat(db: Session, student: Student, device: str, ip: str, host: str = "", lan_ip: str = "") -> None:
    now = clock.now()
    row = db.get(ClientOnline, student.id)
    if row is None:
        db.add(ClientOnline(student_id=student.id, last_seen=now, device=device[:80], ip=ip[:64],
                            host=host[:64], lan_ip=lan_ip[:64]))
    else:
        row.last_seen, row.device, row.ip = now, device[:80], ip[:64]
        row.host, row.lan_ip = host[:64], lan_ip[:64]


# ---------------------------------------------------------------- 认座规则 + 绑座（2.26.0）
RULE_KEY = "checkin_seat_rule"
BIND_KEY = "checkin_bind_until"
MODES = {
    "pick": "学生自己从下拉框选座号",
    "host_tail": "电脑名最后一段就是座号（如 C09-COMPUTE-C14 → C14）",
    "host_num": "电脑名末尾的数字 − 偏移 = 第几个座位（如 PC-023 → 第 23 个）",
    "ip_num": "内网 IP 末段 − 偏移 = 第几个座位（如 10.9.82.105、偏移 100 → 第 5 个）",
}
BIND_MINUTES = range(0, 61)
_HOST = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]{0,62}$")
_TAIL_NUM = re.compile(r"(\d+)\D*$")


def clean_host(host: str) -> str:
    host = str(host or "").strip()[:64]
    return host if _HOST.match(host) else ""


def clean_ip(ip: str) -> str:
    ip = str(ip or "").strip()
    try:
        return str(ipaddress.ip_address(ip)) if ipaddress.ip_address(ip).version == 4 else ""
    except ValueError:
        return ""


def _meta(db: Session, key: str) -> str:
    row = db.get(AppMeta, key)
    return row.value if row else ""


def _set_meta(db: Session, key: str, value: str) -> None:
    row = db.get(AppMeta, key)
    if row is None:
        db.add(AppMeta(key=key, value=value))
    else:
        row.value = value


def rule(db: Session) -> dict:
    """{mode, offset}。没设过是 pick（学生自己选）。"""
    try:
        got = json.loads(_meta(db, RULE_KEY) or "{}")
    except ValueError:
        got = {}
    mode = got.get("mode") if got.get("mode") in MODES else "pick"
    try:
        offset = max(0, min(65535, int(got.get("offset") or 0)))
    except (TypeError, ValueError):
        offset = 0
    return {"mode": mode, "offset": offset}


def set_rule(db: Session, mode: str, offset: int) -> dict:
    if mode not in MODES:
        raise HTTPException(status_code=400, detail="没有这种认座方式")
    _set_meta(db, RULE_KEY, json.dumps({"mode": mode, "offset": max(0, min(65535, int(offset or 0)))}))
    db.commit()
    return rule(db)


def bind_until(db: Session) -> datetime | None:
    raw = _meta(db, BIND_KEY)
    try:
        at = datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None
    return at if at and at > clock.now() else None


def set_bind_mode(db: Session, minutes: int) -> datetime | None:
    if minutes not in BIND_MINUTES:
        raise HTTPException(status_code=400, detail="绑座模式只能开 1～60 分钟（0 = 关掉）")
    at = clock.now() + timedelta(minutes=minutes) if minutes else None
    _set_meta(db, BIND_KEY, at.isoformat(timespec="seconds") if at else "")
    db.commit()
    return at


def seat_order(labels) -> list[str]:
    """「第几个座位」的顺序：先字母后数字，A1、A2…A15、B1…（不按表格里摆的位置）。"""
    def key(label: str):
        m = re.match(r"^([A-Z]+)(\d+)$", label)
        return (m.group(1), int(m.group(2))) if m else (label, 0)
    return sorted(set(labels), key=key)


def rule_seat(r: dict, host: str, lan_ip: str, labels: list[str]) -> str:
    """按认座规则算这台电脑的座号；算不出来、或算出来的座号不在这张座次表里，返回空串。"""
    mode, offset = r["mode"], r["offset"]
    if mode == "host_tail" and host:
        tail = re.split(r"[-_. ]+", host.strip())[-1].upper()
        return tail if SEAT.match(tail) and tail in labels else ""
    n = None
    if mode == "host_num" and host:
        m = _TAIL_NUM.search(host)
        n = int(m.group(1)) if m else None
    elif mode == "ip_num" and lan_ip:
        n = int(lan_ip.rsplit(".", 1)[-1])
    if n is None:
        return ""
    order = seat_order(labels)
    i = n - offset
    return order[i - 1] if 1 <= i <= len(order) else ""


def resolve(db: Session, r: dict, device: str, host: str, lan_ip: str, labels: list[str]) -> tuple[str, str]:
    """这台电脑该坐哪：(座号, 怎么认的 bind / auto)；认不出来 ("", "")。绑座优先。"""
    if device.startswith("d:"):
        b = db.get(SeatBinding, device[2:][:80])
        if b and b.seat in labels:
            return b.seat, "bind"
    seat = rule_seat(r, host, lan_ip, labels)
    return (seat, "auto") if seat else ("", "")


def _clear_cell(sheet: dict, seat: str, name: str) -> None:
    spot = next((s for s in seats(sheet) if s["seat"] == seat), None)
    if spot and sheet["data"][spot["y"]][spot["x"]] == name:
        sheet["data"][spot["y"]][spot["x"]] = ""


def _bind_view(db: Session, student: Student, device: str) -> dict | None:
    """绑座模式开着、这台电脑还没绑：给学生端看可选的座号（本班 sheet1 的座号，别的电脑绑了的标出来）。"""
    until = bind_until(db)
    if not until or not device.startswith("d:"):
        return None
    mine = db.get(SeatBinding, device[2:][:80])
    cls = db.get(SchoolClass, student.class_id) if student.class_id else None
    labels = [s["seat"] for s in seats(sheet1(cls) if cls else default_sheet())]
    taken = set(db.scalars(select(SeatBinding.seat).where(SeatBinding.device != device[2:][:80])))
    return {"remaining": max(0, int((until - clock.now()).total_seconds())),
            "mine": mine.seat if mine else "",
            "seats": [{"seat": x, "taken": x in taken} for x in labels]}


def bind(db: Session, student: Student, seat: str, device: str, host: str, lan_ip: str) -> dict:
    seat = str(seat or "").strip().upper()
    if not bind_until(db):
        raise HTTPException(status_code=410, detail="老师已经关了绑座模式")
    if not device.startswith("d:"):
        raise HTTPException(status_code=400, detail="这个学生端太老，报不出设备号，绑不了座号。请换新版学生端")
    if not SEAT.match(seat):
        raise HTTPException(status_code=400, detail="请从下拉框里选座号")
    dev = device[2:][:80]
    other = db.scalar(select(SeatBinding).where(SeatBinding.seat == seat, SeatBinding.device != dev))
    if other:
        raise HTTPException(status_code=409, detail=(
            f"{seat} 已经绑给另一台电脑（{other.host or '没报电脑名'}）了。坐错了请找老师在「认座设置」里删掉那条"))
    row = db.get(SeatBinding, dev)
    if row is None:
        row = SeatBinding(device=dev)
        db.add(row)
    row.seat, row.host, row.lan_ip, row.bound_by, row.at = seat, host[:64], lan_ip[:64], student.name[:64], clock.now()
    db.commit()
    return {"ok": True, "seat": seat}


def bindings(db: Session) -> list[dict]:
    rows = db.scalars(select(SeatBinding).order_by(SeatBinding.seat))
    return [{"device": b.device, "seat": b.seat, "host": b.host, "lan_ip": b.lan_ip,
             "bound_by": b.bound_by, "at": b.at} for b in rows]


def preview(db: Session, r: dict, labels: list[str], minutes: int = 120) -> dict:
    """按某个规则算「哪台电脑 → 哪个座号」：最近 minutes 分钟里登录过学生端的电脑（按设备号去重）。
    同一个座号算到两台电脑上的标出来（规则不合适，或者两台电脑重名）。"""
    since = clock.now() - timedelta(minutes=minutes)
    rows = db.scalars(select(ClientOnline).where(ClientOnline.last_seen >= since)
                      .order_by(ClientOnline.last_seen.desc()))
    names = {}
    seen, out = set(), []
    for o in rows:
        key = o.device or f"ip:{o.ip}"
        if key in seen:
            continue
        seen.add(key)
        seat, how = resolve(db, r, o.device, o.host, o.lan_ip, labels)   # o.device 存的就是 d:xxx
        names.setdefault(o.student_id, None)
        out.append({"host": o.host, "lan_ip": o.lan_ip, "ip": o.ip, "seat": seat, "how": how,
                    "student_id": o.student_id, "last_seen": o.last_seen})
    who = {s.id: s.name for s in db.scalars(select(Student).where(Student.id.in_(list(names) or [0])))}
    count: dict = {}
    for x in out:
        x["student"] = who.get(x.pop("student_id"), "")
        if x["seat"]:
            count[x["seat"]] = count.get(x["seat"], 0) + 1
    for x in out:
        x["clash"] = bool(x["seat"]) and count[x["seat"]] > 1
    out.sort(key=lambda x: (not x["seat"], seat_order([x["seat"]]) if x["seat"] else [], x["host"]))
    return {"machines": out, "seats": len(labels), "matched": sum(1 for x in out if x["seat"]),
            "clash": sorted({x["seat"] for x in out if x["clash"]})}


def _tab_sheet(db: Session, row: Checkin) -> tuple[SeatTab | None, dict]:
    tab = db.get(SeatTab, row.tab_id) if row.tab_id else None
    try:
        return tab, json.loads(tab.sheet) if tab else {}
    except ValueError:
        return tab, {}


def student_view(db: Session, student: Student, device: str = "", ip: str = "",
                 host: str = "", lan_ip: str = "") -> dict:
    """学生端问「有没有签到」：有就带上剩余秒数、可选座号（已被占的标出来）、自己签没签。

    这台电脑认得出座号（绑过座 / 认座规则算得出）就**直接签上**，回的 signed 里 how 是 bind / auto；
    认出来了但签不上（座号被另一台认出来的电脑占了、这台电脑已经给别人签过），auto 里带上座号和原因。
    绑座模式开着、这台电脑还没绑，带上 bind（学生端弹「这台电脑坐哪」）。
    """
    now = clock.now()
    row = active(db, student.class_id, now) if student.class_id else None
    out = {"active": False, "poll": POLL_SECONDS}
    bv = _bind_view(db, student, device)
    if bv and not bv["mine"]:
        out["bind"] = bv
    if not row:
        return out
    _, sheet = _tab_sheet(db, row)
    labels = [s["seat"] for s in seats(sheet)]
    auto = None
    entries = list(db.scalars(select(CheckinEntry).where(CheckinEntry.checkin_id == row.id)))
    if not any(e.student_id == student.id for e in entries):
        seat, how = resolve(db, rule(db), device, host, lan_ip, labels)
        if seat:
            try:
                _place(db, row, student, seat, device, ip, host, how)
            except HTTPException as e:
                db.rollback()
                auto = {"seat": seat, "how": how, "error": e.detail}
            entries = list(db.scalars(select(CheckinEntry).where(CheckinEntry.checkin_id == row.id)))
    mine = next((e for e in entries if e.student_id == student.id), None)
    taken = {e.seat for e in entries}
    cls = db.get(SchoolClass, row.class_id)
    out.update({
        "active": True, "checkin_id": row.id,
        "class": cls.display if cls else "", "started_by": row.started_by,
        "remaining": max(0, int((row.ends_at - now).total_seconds())),
        "signed": {"seat": mine.seat, "how": mine.how} if mine else None,
        "auto": auto,
        "seats": [{"seat": x, "taken": x in taken} for x in labels],
    })
    return out


def sign(db: Session, student: Student, checkin_id: int, seat: str, device: str, ip: str,
         host: str = "", lan_ip: str = "") -> dict:
    seat = str(seat or "").strip().upper()
    now = clock.now()
    row = db.scalar(select(Checkin).where(Checkin.id == checkin_id).with_for_update())
    if not row or row.class_id != student.class_id:
        raise HTTPException(status_code=404, detail="没有这个签到（可能不是你们班的）")
    if row.ends_at <= now:
        raise HTTPException(status_code=410, detail="签到时间已经过了")
    mine = db.scalar(select(CheckinEntry).where(CheckinEntry.checkin_id == row.id,
                                                CheckinEntry.student_id == student.id))
    if mine:
        return {"ok": True, "seat": mine.seat, "already": True, "how": mine.how}
    _, sheet = _tab_sheet(db, row)
    labels = [s["seat"] for s in seats(sheet)]
    # 这台电脑认得出座号，就只能签那个座号（不许借自选去占别人的位置）
    fixed, how = resolve(db, rule(db), device, host, lan_ip, labels)
    if fixed and seat != fixed:
        raise HTTPException(status_code=409, detail=f"这台电脑是 {fixed} 号座位，只能签 {fixed}")
    _place(db, row, student, fixed or seat, device, ip, host, how or "pick")
    db.commit()
    return {"ok": True, "seat": fixed or seat, "already": False, "how": how or "pick"}


def _place(db: Session, row: Checkin, student: Student, seat: str, device: str, ip: str,
           host: str, how: str) -> None:
    """把学生签到 seat 上（不提交）。how 是 auto / bind 的能挤走在这个座号上自己选的（pick）。"""
    now = clock.now()
    entries = list(db.scalars(select(CheckinEntry).where(CheckinEntry.checkin_id == row.id)))
    tab, sheet = _tab_sheet(db, row)
    spot = next((s for s in seats(sheet) if s["seat"] == seat), None)
    if not spot:
        raise HTTPException(status_code=400, detail=f"座号「{seat}」不在座次表里，请从下拉框里选")
    device = (device or "").strip()[:80] or f"ip:{ip}"
    names = {s.id: s.name for s in db.scalars(select(Student).where(
        Student.id.in_([e.student_id for e in entries] or [0])))}
    for e in entries:
        if e.device == device or (_private(ip) and e.ip == ip):
            raise HTTPException(status_code=409, detail=(
                f"这台电脑已经给「{names.get(e.student_id, '另一位同学')}」签过到了，"
                "一台电脑只能签一个人。请在自己的电脑上登录签到"))
    holder = next((e for e in entries if e.seat == seat), None)
    if holder and (how == "pick" or holder.how != "pick"):
        raise HTTPException(status_code=409, detail=(
            f"{seat} 已经有同学签了，请选你自己的座位；坐错了请找老师" if how == "pick" else
            f"{seat} 已经被另一台认出是 {seat} 的电脑签了（{holder.host or '没报电脑名'}），请找老师"))
    if holder:
        # 座号认主人：自己选到这个座号上的那位让出来，签到框会重新弹给他
        _clear_cell(sheet, seat, names.get(holder.student_id, ""))
        db.delete(holder)
        db.flush()
    db.add(CheckinEntry(checkin_id=row.id, student_id=student.id, seat=seat, device=device,
                        ip=ip[:64], at=now, how=how, host=host[:64]))
    if tab is not None:
        sheet["data"][spot["y"]][spot["x"]] = student.name
        tab.sheet = json.dumps(sheet, ensure_ascii=False)
    db.flush()


def revoke(db: Session, row: Checkin, entry_id: int) -> None:
    """老师撤销一条签到：记录删掉、表里那格姓名清掉。签到还没结束的话，那位同学的签到框会重新弹出来。"""
    e = db.get(CheckinEntry, entry_id)
    if not e or e.checkin_id != row.id:
        raise HTTPException(status_code=404, detail="没有这条签到记录")
    tab, sheet = _tab_sheet(db, row)
    st = db.get(Student, e.student_id)
    if tab is not None and st is not None:
        _clear_cell(sheet, e.seat, st.name)
        tab.sheet = json.dumps(sheet, ensure_ascii=False)
    db.delete(e)
    db.commit()


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
        "version": f"{len(entries)}-{entries[-1].id if entries else 0}-{sum(e.id for e in entries)}",
        "total": len(roster), "signed_count": len(entries), "absent": len(roster) - len(signed),
        "signed": [{"id": e.id, "student_id": e.student_id,
                    "name": by_id[e.student_id].name if e.student_id in by_id else "?",
                    "student_no": by_id[e.student_id].student_no if e.student_id in by_id else "",
                    "seat": e.seat, "at": e.at, "how": e.how, "host": e.host} for e in entries],
        "unsigned": [{"student_id": s.id, "name": s.name, "student_no": s.student_no,
                      "online": s.id in online} for s in roster if s.id not in signed],
        "online": [{"student_id": s.id, "name": s.name, "seat": signed[s.id].seat if s.id in signed else ""}
                   for s in roster if s.id in online],
    }
