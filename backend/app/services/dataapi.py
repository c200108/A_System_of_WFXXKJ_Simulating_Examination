"""教师端「API」板块的核心：把第三方送来的各种样子的数据认成一条条记录，以及统计。

## 收什么样的数据（尽量都接住）

推荐的「标准信封」见 docs/API数据接入规范.md：student / type / activity / target / score /
answers / ratings / comment / data / client_id / submitted_at，**每一项都可以不填**。

不按信封来也收：整条原样存进 payload，再按常见别名去认学生学号姓名班级、得分、评语
（学号叫 student_no、sno、xh、学号 都行），认不出的字段原样显示在数据表单里。

## 学生对不对得上

学号对上平台名单里的学生，或者「班级 + 姓名」唯一对上，就记 student_id —— 这条数据
会汇总进那个学生的「学情」。对不上的只在 API 的数据表单里显示，不影响任何东西。
"""

from __future__ import annotations

import json
import math
import re
import secrets
import string
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any, Iterable
from urllib.parse import urlsplit

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from .. import clock
from ..models import DataApi, DataRecord, DataRecordItem, SchoolClass, Student

TEMPLATES = {
    "answer": "答题回收",
    "self_eval": "自我评价",
    "peer_eval": "同伴互评",
    "survey": "问卷调查",
    "custom": "自定义",
}
TYPE_NAMES = {
    "answer": "答题",
    "self_eval": "自评",
    "peer_eval": "互评",
    "survey": "问卷",
    "event": "操作记录",
    "data": "数据",
}
# 模板 → 没写 type 时默认算什么类型
DEFAULT_TYPE = {"answer": "answer", "self_eval": "self_eval", "peer_eval": "peer_eval",
                "survey": "survey", "custom": "data"}

MAX_RECORDS = 50_000          # 每个 API 最多存这么多条
MAX_ITEM_BYTES = 256 * 1024   # 单条
MAX_BODY_BYTES = 2 * 1024 * 1024
MAX_BATCH = 500
MAX_SUB_ITEMS = 300           # 一条里最多拆这么多道题／评价维度

_ALNUM = string.ascii_letters + string.digits


def new_key() -> str:
    return "".join(secrets.choice(_ALNUM) for _ in range(12))


def new_token() -> str:
    return "".join(secrets.choice(_ALNUM) for _ in range(32))


# ---------------------------------------------------------------- 认字段
ALIASES = {
    "student_no": ("student_no", "studentNo", "studentno", "student_id", "studentId", "sno", "xh",
                   "stu_no", "stuNo", "学号", "学生学号"),
    "student_name": ("student_name", "studentName", "name", "xm", "stu_name", "姓名", "学生姓名", "学生"),
    "class_name": ("class_name", "className", "class", "clazz", "bj", "student_class", "班级"),
    "score": ("score", "total_score", "totalScore", "得分", "分数", "总分", "成绩"),
    "max_score": ("max_score", "maxScore", "full_score", "fullScore", "total", "满分"),
    "comment": ("comment", "comments", "remark", "feedback", "评语", "评价", "留言", "反思", "感想"),
    "type": ("type", "kind", "record_type", "类型"),
    "client_id": ("client_id", "clientId", "record_id", "recordId", "uuid"),
    "submitted_at": ("submitted_at", "submittedAt", "submit_time", "time", "timestamp", "提交时间"),
    "page": ("page", "page_url", "pageUrl", "url", "来源网页"),
    "activity_id": ("activity_id", "activityId", "task_id", "taskId", "lesson_id", "任务编号"),
    "activity_name": ("activity_name", "activityName", "task", "task_name", "lesson", "活动", "任务",
                      "课题", "课程"),
}
_STUDENT_KEYS = {"no": "student_no", "name": "student_name", "class": "class_name"}


def _first(d: dict, names: Iterable[str]):
    for n in names:
        if n in d and d[n] not in (None, ""):
            return d[n]
    return None


def _s(v, n: int) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        v = json.dumps(v, ensure_ascii=False)
    return str(v).strip()[:n]


def _num(v) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    try:
        f = float(str(v).strip().rstrip("分%"))
        return f if math.isfinite(f) else None
    except ValueError:
        return None


def _bool(v) -> bool | None:
    if isinstance(v, bool):
        return v
    if v is None or v == "":
        return None
    t = str(v).strip().lower()
    if t in ("1", "true", "yes", "y", "对", "正确", "是", "√", "✓", "right"):
        return True
    if t in ("0", "false", "no", "n", "错", "错误", "否", "×", "✗", "wrong"):
        return False
    return None


def _time(v) -> datetime | None:
    if v in (None, ""):
        return None
    try:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            ts = v / 1000 if v > 1e11 else v          # 毫秒或秒
            return datetime.fromtimestamp(ts).replace(microsecond=0)
        t = datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
        if t.tzinfo is not None:
            t = t.astimezone().replace(tzinfo=None)
        return t.replace(microsecond=0)
    except (ValueError, OverflowError, OSError):
        return None


def page_of(url: str) -> str:
    """来源网页：去掉 ? 和 # 后面的，同一个网页不同参数算一个。"""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        p = urlsplit(url)
    except ValueError:
        return url[:255]
    if p.scheme in ("http", "https") and p.netloc:
        return f"{p.scheme}://{p.netloc}{p.path}"[:255]
    return url.split("?")[0].split("#")[0][:255]


def _person(raw, prefix: str) -> dict:
    """student / target 可以是 {"no","name","class"}，也可以只是一个名字字符串。"""
    out = {"no": "", "name": "", "class": ""}
    if isinstance(raw, dict):
        out["no"] = _s(_first(raw, ("no", "id", "student_no", "sno", "xh", "学号")), 64)
        out["name"] = _s(_first(raw, ("name", "student_name", "xm", "姓名")), 64)
        out["class"] = _s(_first(raw, ("class", "class_name", "className", "bj", "班级")), 64)
    elif raw not in (None, ""):
        out["name"] = _s(raw, 64)
    return out


def _items(raw, kind: str) -> list[dict]:
    """answers / ratings：列表 [{q, answer, correct, score, max, time_ms}]，或者 {题号: 答案}。"""
    out = []
    if isinstance(raw, dict):
        raw = [{"item": k, ("score" if kind == "rating" else "answer"): v} for k, v in raw.items()]
    if not isinstance(raw, list):
        return out
    for i, it in enumerate(raw[:MAX_SUB_ITEMS]):
        if not isinstance(it, dict):
            it = {"answer": it} if kind == "answer" else {"score": it}
        name = _first(it, ("q", "item", "id", "qid", "question", "no", "dimension", "name", "题号", "维度"))
        out.append({
            "item": _s(name if name is not None else i + 1, 64),
            "answer": _s(_first(it, ("answer", "value", "choice", "response", "作答", "答案")), 255),
            "correct": _bool(_first(it, ("correct", "is_correct", "isCorrect", "right", "对错"))),
            "score": _num(_first(it, ("score", "point", "points", "得分", "分"))),
            "max_score": _num(_first(it, ("max", "max_score", "maxScore", "full", "满分"))),
            "time_ms": _int(_first(it, ("time_ms", "timeMs", "duration_ms", "用时"))),
        })
    return out


def _int(v) -> int | None:
    f = _num(v)
    return int(f) if f is not None and abs(f) < 2**31 else None


def normalize(raw: Any, api: DataApi, referer: str = "") -> dict:
    """一条原始数据 → 要落库的字段。raw 不是对象的（数字、字符串）包成 {"value": raw}。"""
    if not isinstance(raw, dict):
        raw = {"value": raw}
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    look = {**data, **raw}                      # 顶层优先，再看 data 里

    student = _person(raw.get("student"), "student")
    for k, col in _STUDENT_KEYS.items():
        if not student[k]:
            student[k] = _s(_first(look, ALIASES[col]), 64)
    if isinstance(look.get("student_name"), dict) or student["name"].startswith("{"):
        student["name"] = ""
    target = _person(_first(raw, ("target", "peer", "reviewee", "被评人", "评价对象")), "target")

    act = raw.get("activity")
    if isinstance(act, dict):
        act_id = _s(_first(act, ("id", "code")), 64)
        act_name = _s(_first(act, ("name", "title")), 128)
    else:
        act_id = _s(_first(look, ALIASES["activity_id"]), 64)
        act_name = _s(act if act not in (None, "") else _first(look, ALIASES["activity_name"]), 128)

    typ = _s(_first(raw, ALIASES["type"]), 32) or DEFAULT_TYPE.get(api.template, "data")
    answers = _items(_first(raw, ("answers", "questions", "items", "作答")), "answer")
    ratings = _items(_first(raw, ("ratings", "scores", "dimensions", "评分", "评价维度")), "rating")

    score = _num(_first(look, ALIASES["score"]))
    max_score = _num(_first(look, ALIASES["max_score"]))
    if score is None and answers and any(a["score"] is not None for a in answers):
        score = sum(a["score"] or 0 for a in answers)
        if max_score is None and all(a["max_score"] is not None for a in answers):
            max_score = sum(a["max_score"] for a in answers)

    page_url = _s(_first(look, ALIASES["page"]), 1000) or referer
    cid = _s(_first(raw, ALIASES["client_id"]), 64) or None
    return {
        "client_id": cid,
        "type": typ,
        "activity_id": act_id,
        "activity_name": act_name,
        "page": page_of(page_url),
        "student_no": student["no"],
        "student_name": student["name"],
        "class_name": student["class"],
        "target_no": target["no"],
        "target_name": target["name"],
        "score": score,
        "max_score": max_score,
        "comment": _s(_first(look, ALIASES["comment"]), 5000),
        "submitted_at": _time(_first(look, ALIASES["submitted_at"])),
        "_answers": answers,
        "_ratings": ratings,
    }


# ---------------------------------------------------------------- 对学生
def match_student(db: Session, no: str, name: str, cls: str) -> Student | None:
    if no:
        row = db.scalar(select(Student).where(Student.student_no == no))
        if row:
            return row
    if name and cls:
        rows = db.scalars(select(Student).where(Student.name == name, Student.student_class == cls)).all()
        if len(rows) == 1:
            return rows[0]
    return None


# ---------------------------------------------------------------- 入库
class Rejected(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        super().__init__(message)
        self.status, self.code, self.message, self.headers = status, code, message, headers or {}


def accepting(api: DataApi) -> None:
    if api.status != "active":
        raise Rejected(423, "PAUSED", "这个 API 已暂停接收")
    now = clock.now()
    if api.accept_from and now < api.accept_from:
        raise Rejected(423, "OUT_OF_WINDOW", f"还没到接收时间（{api.accept_from:%Y-%m-%d %H:%M} 开始）")
    if api.accept_until and now > api.accept_until:
        raise Rejected(423, "OUT_OF_WINDOW", f"已过接收截止时间（{api.accept_until:%Y-%m-%d %H:%M}）")


def store(db: Session, api: DataApi, items: list, meta: dict) -> list[dict]:
    """把一批数据存进去，返回每条的结果（顺序和传进来的一致）。不提交。"""
    results = []
    room = MAX_RECORDS - (api.record_count or 0)
    now = clock.now()
    for raw in items:
        size = len(json.dumps(raw, ensure_ascii=False).encode("utf-8"))
        if size > MAX_ITEM_BYTES:
            results.append({"ok": False, "code": "PAYLOAD_TOO_LARGE",
                            "message": f"单条不能超过 {MAX_ITEM_BYTES // 1024} KB"})
            continue
        if raw in (None, "", {}, []):
            results.append({"ok": False, "code": "EMPTY", "message": "内容是空的"})
            continue
        f = normalize(raw, api, meta.get("referer", ""))
        if f["client_id"]:
            old = db.scalar(select(DataRecord.id).where(DataRecord.api_id == api.id,
                                                       DataRecord.client_id == f["client_id"]))
            if old:
                results.append({"ok": True, "id": old, "duplicate": True})
                continue
        if room <= 0:
            results.append({"ok": False, "code": "QUOTA_FULL",
                            "message": f"这个 API 已存满 {MAX_RECORDS} 条，请老师清理后再提交"})
            continue
        stu = match_student(db, f["student_no"], f["student_name"], f["class_name"])
        answers, ratings = f.pop("_answers"), f.pop("_ratings")
        if stu:
            f["student_no"] = f["student_no"] or stu.student_no
            f["student_name"] = f["student_name"] or stu.name
            f["class_name"] = f["class_name"] or stu.student_class
        payload = raw if isinstance(raw, dict) else {"value": raw}
        rec = DataRecord(api_id=api.id, student_id=stu.id if stu else None,
                         payload=json.dumps(payload, ensure_ascii=False), received_at=now,
                         source_ip=meta.get("ip", "")[:64], device_id=meta.get("device", "")[:80],
                         origin=meta.get("origin", "")[:255], user_agent=meta.get("ua", "")[:255], **f)
        if api.dedupe == "latest" and (rec.student_no or rec.student_name):
            _supersede(db, api, rec)
        db.add(rec)
        db.flush()
        for kind, rows in (("answer", answers), ("rating", ratings)):
            for it in rows:
                db.add(DataRecordItem(record_id=rec.id, api_id=api.id, kind=kind, **it))
        room -= 1
        api.record_count = (api.record_count or 0) + 1
        results.append({"ok": True, "id": rec.id, "duplicate": False, "student_matched": stu is not None})
    if any(r.get("ok") and not r.get("duplicate") for r in results):
        api.last_received_at = now
    return results


def _supersede(db: Session, api: DataApi, rec: DataRecord) -> None:
    """只算最新一条：同一学生、同一活动、同一类型、同一被评人的旧记录标成被替代。"""
    who = (DataRecord.student_no == rec.student_no) if rec.student_no else (
        (DataRecord.student_name == rec.student_name) & (DataRecord.class_name == rec.class_name))
    db.execute(update(DataRecord).where(
        DataRecord.api_id == api.id, who, DataRecord.type == rec.type,
        DataRecord.activity_id == rec.activity_id, DataRecord.activity_name == rec.activity_name,
        DataRecord.target_no == rec.target_no, DataRecord.target_name == rec.target_name,
        DataRecord.superseded.is_(False),
    ).values(superseded=True))


def recount(db: Session, api: DataApi) -> None:
    api.record_count = db.scalar(select(func.count()).select_from(DataRecord)
                                 .where(DataRecord.api_id == api.id)) or 0


def resupersede(db: Session, api: DataApi) -> None:
    """改了「重复提交怎么算」之后，把被替代标记全部重算一遍。"""
    db.execute(update(DataRecord).where(DataRecord.api_id == api.id).values(superseded=False))
    if api.dedupe != "latest":
        return
    seen = set()
    rows = db.execute(
        select(DataRecord.id, DataRecord.student_no, DataRecord.student_name, DataRecord.class_name,
               DataRecord.type, DataRecord.activity_id, DataRecord.activity_name,
               DataRecord.target_no, DataRecord.target_name)
        .where(DataRecord.api_id == api.id).order_by(DataRecord.received_at.desc(), DataRecord.id.desc())
    ).all()
    old = []
    for r in rows:
        if not (r.student_no or r.student_name):
            continue
        k = (r.student_no or f"{r.class_name}/{r.student_name}", r.type, r.activity_id, r.activity_name,
             r.target_no, r.target_name)
        if k in seen:
            old.append(r.id)
        seen.add(k)
    for i in range(0, len(old), 500):
        db.execute(update(DataRecord).where(DataRecord.id.in_(old[i:i + 500])).values(superseded=True))


# ---------------------------------------------------------------- 字段（数据表单的动态列）
def flat(payload: dict, prefix: str = "", depth: int = 0, out: dict | None = None) -> dict:
    """payload 摊平成 {路径: 值}，最多两层；列表、更深的对象整块显示成 JSON。"""
    out = {} if out is None else out
    for k, v in payload.items():
        path = f"{prefix}{k}"
        if k in ("_token", "student", "answers", "ratings", "activity", "target") and not prefix:
            continue
        if isinstance(v, dict) and depth < 1:
            flat(v, path + ".", depth + 1, out)
        else:
            out[path] = v
    return out


# ---------------------------------------------------------------- 统计（数据大图）
def class_ids_of(api: DataApi) -> list[int]:
    return [int(x) for x in (api.class_ids or "").split(",") if x.strip().isdigit()]


def _ppl(r) -> str:
    return r.student_no or (f"{r.class_name}/{r.student_name}" if r.student_name else "")


def stats(db: Session, api: DataApi, *, type_: str = "", activity: str = "", page: str = "",
          class_name: str = "", since: datetime | None = None) -> dict:
    """数据大图要的数。只算 flag=normal、没被替代的记录。"""
    q = select(DataRecord).where(DataRecord.api_id == api.id, DataRecord.flag == "normal",
                                 DataRecord.superseded.is_(False))
    if type_:
        q = q.where(DataRecord.type == type_)
    if activity:
        q = q.where((DataRecord.activity_id == activity) | (DataRecord.activity_name == activity))
    if page:
        q = q.where(DataRecord.page == page)
    if class_name:
        q = q.where(DataRecord.class_name == class_name)
    if since:
        q = q.where(DataRecord.received_at >= since)
    recs = db.scalars(q.order_by(DataRecord.received_at)).all()
    ids = [r.id for r in recs]

    people = {_ppl(r) for r in recs if _ppl(r)}
    scored = [r for r in recs if r.score is not None]
    rates = [r.score / r.max_score * 100 for r in scored if r.max_score]
    now = clock.now()

    # 应交人数：关联班级里的在籍学生
    expected = None
    roster_names: dict[str, str] = {}
    cids = class_ids_of(api)
    if cids:
        studs = db.scalars(select(Student).where(Student.class_id.in_(cids), Student.is_active.is_(True))).all()
        expected = len(studs)
        roster_names = {s.student_no: s.name for s in studs}
    submitted_roster = len({r.student_no for r in recs if r.student_no in roster_names}) if cids else None
    missing = sorted((no, nm) for no, nm in roster_names.items()
                     if no not in {r.student_no for r in recs})[:200] if cids else []

    # 提交时间线：按分钟（跨度超过 3 小时按小时，超过 3 天按天）
    timeline = []
    if recs:
        span = recs[-1].received_at - recs[0].received_at
        fmt = "%m-%d" if span > timedelta(days=3) else ("%m-%d %H:00" if span > timedelta(hours=3) else "%H:%M")
        c = Counter(r.received_at.strftime(fmt) for r in recs)
        timeline = [{"t": k, "n": v} for k, v in c.items()]

    # 成绩分布：按得分率 10 段
    dist = [0] * 10
    for x in rates:
        dist[min(9, max(0, int(x // 10)))] += 1
    if not rates and scored:
        lo, hi = min(r.score for r in scored), max(r.score for r in scored)
        step = (hi - lo) / 10 or 1
        dist = [0] * 10
        for r in scored:
            dist[min(9, int((r.score - lo) / step))] += 1
        dist_labels = [f"{lo + i * step:g}~{lo + (i + 1) * step:g}" for i in range(10)]
    else:
        dist_labels = [f"{i * 10}~{i * 10 + 10}%" for i in range(10)]

    # 逐题、逐维度
    items = db.scalars(select(DataRecordItem).where(DataRecordItem.record_id.in_(ids))).all() if ids else []
    by_id = {r.id: r for r in recs}
    q_stat: dict[str, dict] = {}
    rate_self: dict[str, list] = defaultdict(list)
    rate_peer: dict[str, list] = defaultdict(list)
    rate_all: dict[str, list] = defaultdict(list)
    for it in items:
        rec = by_id.get(it.record_id)
        if it.kind == "answer":
            s = q_stat.setdefault(it.item, {"q": it.item, "n": 0, "right": 0, "judged": 0,
                                            "choices": Counter(), "wrong": [], "time": []})
            s["n"] += 1
            if it.correct is not None:
                s["judged"] += 1
                s["right"] += 1 if it.correct else 0
                if not it.correct and rec and len(s["wrong"]) < 50:
                    s["wrong"].append(rec.student_name or rec.student_no)
            if it.answer:
                s["choices"][it.answer[:40]] += 1
            if it.time_ms:
                s["time"].append(it.time_ms)
        else:
            v = it.score
            if v is None:
                continue
            pct = v / it.max_score * 100 if it.max_score else None
            val = pct if pct is not None else v
            (rate_peer if rec and rec.type == "peer_eval" else rate_self if rec and rec.type == "self_eval"
             else rate_all)[it.item].append(val)
    questions = []
    for s in q_stat.values():
        questions.append({
            "q": s["q"], "n": s["n"],
            "rate": round(s["right"] / s["judged"] * 100, 1) if s["judged"] else None,
            "choices": s["choices"].most_common(8),
            "wrong": s["wrong"],
            "avg_time_ms": round(sum(s["time"]) / len(s["time"])) if s["time"] else None,
        })
    questions.sort(key=lambda x: _natural(x["q"]))
    dims = sorted(set(rate_self) | set(rate_peer) | set(rate_all), key=_natural)
    avg = lambda xs: round(sum(xs) / len(xs), 2) if xs else None  # noqa: E731
    radar = [{"item": d, "self": avg(rate_self.get(d, [])), "peer": avg(rate_peer.get(d, [])),
              "other": avg(rate_all.get(d, []))} for d in dims][:30]

    # 互评矩阵：评价人 × 被评人 的平均分
    matrix = defaultdict(list)
    for r in recs:
        if r.type == "peer_eval" and (r.target_name or r.target_no):
            v = r.score
            if v is None:
                vals = [it.score for it in items if it.record_id == r.id and it.kind == "rating" and it.score is not None]
                v = sum(vals) / len(vals) if vals else None
            if v is not None:
                matrix[(r.student_name or r.student_no, r.target_name or r.target_no)].append(v)
    raters = sorted({k[0] for k in matrix})[:60]
    targets = sorted({k[1] for k in matrix})[:60]
    peer_matrix = {"raters": raters, "targets": targets,
                   "cells": [[raters.index(a), targets.index(b), round(sum(v) / len(v), 2)]
                             for (a, b), v in matrix.items() if a in raters and b in targets]}

    # 班级对比
    by_cls: dict[str, list] = defaultdict(list)
    for r in recs:
        by_cls[r.class_name or "未填班级"].append(r)
    classes = [{"class": k, "records": len(v), "people": len({_ppl(x) for x in v if _ppl(x)}),
                "avg": avg([x.score for x in v if x.score is not None]),
                "avg_rate": avg([x.score / x.max_score * 100 for x in v if x.score is not None and x.max_score])}
               for k, v in sorted(by_cls.items())]

    # 评语关键词：中文按 2~4 字的片段、英文按单词，去掉常见虚词
    words = Counter()
    for r in recs:
        for w in _keywords(r.comment):
            words[w] += 1

    types = Counter(r.type for r in recs)
    pages = Counter(r.page or "（未注明来源网页）" for r in recs)
    acts = Counter(r.activity_name or r.activity_id for r in recs if r.activity_name or r.activity_id)
    latest = [{"id": r.id, "student": r.student_name or r.student_no or "匿名", "class": r.class_name,
               "type": r.type, "score": r.score, "max_score": r.max_score,
               "at": r.received_at.isoformat(), "matched": r.student_id is not None}
              for r in recs[-20:][::-1]]
    return {
        "records": len(recs),
        "people": len(people),
        "matched_people": len({r.student_id for r in recs if r.student_id}),
        "expected": expected,
        "submitted_roster": submitted_roster,
        "missing": [{"no": a, "name": b} for a, b in missing],
        "avg_score": avg([r.score for r in scored]),
        "avg_rate": avg(rates),
        "max_score": max((r.score for r in scored), default=None),
        "min_score": min((r.score for r in scored), default=None),
        "last5min": sum(1 for r in recs if r.received_at >= now - timedelta(minutes=5)),
        "timeline": timeline,
        "distribution": {"labels": dist_labels, "values": dist},
        "questions": questions,
        "radar": radar,
        "peer_matrix": peer_matrix,
        "classes": classes,
        "keywords": words.most_common(30),
        "types": [{"type": k, "name": TYPE_NAMES.get(k, k), "n": v} for k, v in types.most_common()],
        "pages": [{"page": k, "n": v} for k, v in pages.most_common(50)],
        "activities": [{"activity": k, "n": v} for k, v in acts.most_common(50)],
        "latest": latest,
    }


def summary(db: Session, api: DataApi, activity: str = "") -> dict:
    """给第三方网页显示用的汇总：不含任何学生个人信息。"""
    s = stats(db, api, activity=activity)
    return {
        "records": s["records"], "people": s["people"], "avg_score": s["avg_score"],
        "avg_rate": s["avg_rate"], "max_score": s["max_score"], "min_score": s["min_score"],
        "questions": [{"q": q["q"], "n": q["n"], "rate": q["rate"]} for q in s["questions"]],
        "dimensions": s["radar"],
        "distribution": s["distribution"],
    }


_STOP = set("的了是我在和就都也很有这那他她它们你吗呢吧啊着过还又与及而但并对把被让从给向")
_NAT = re.compile(r"(\d+)")


def _natural(s: str):
    return [int(p) if p.isdigit() else p for p in _NAT.split(str(s))]


def _keywords(text: str) -> list[str]:
    if not text:
        return []
    out = []
    for w in re.findall(r"[A-Za-z]{3,}", text):
        out.append(w.lower())
    for seg in re.findall(r"[一-鿿]+", text):
        seg = "".join(ch for ch in seg if ch not in _STOP)
        for i in range(len(seg) - 1):
            out.append(seg[i:i + 2])
    return out
