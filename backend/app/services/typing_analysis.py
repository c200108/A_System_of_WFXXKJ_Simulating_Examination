"""打字学情分析：统计 + 自动结论（2.12.0）。

    analyze(records, module, scope, roster, today, days)  →  「打字学情分析」页要的整份数据

纯计算，不碰数据库。records 是已经按模块、时间筛好的 TypingRecord 行；
roster 是 {班级名: 在册人数}，用来算参与率。

## 口径

- **一个学生 = 班级 + 姓名**。学生平台上练的挂着账号，免登录页练的只有手填的班级姓名，
  统一按这两样认，同一个人不会被拆成两个。
- **速度只在单个文字模块里比**：中文是字/分、英文是字母/分，混在一起没有意义；
  键盘模块没有速度。所以选了「中文」或「英文」才出速度的图和结论。
- **达标** = 两星及以上（正确率达到该难度的门槛，见 config.yaml 的 typing.star_thresholds）。
- **各班比较**先在每个学生身上求平均、再在学生之间平均 —— 练得多的学生不会把全班的数拽走。
- **进步** = 这段时间里最后 3 次的平均速度（键盘模块用正确率）减最初 3 次的，练满 4 次才算。
"""

from __future__ import annotations

import math
from collections import OrderedDict
from datetime import date, datetime, timedelta

TEXT_MODULES = ("中文", "英文")
DIFFICULTY_ORDER = ["简单", "中等", "困难"]
ACC_BANDS = [(95, 101, "95–100%"), (90, 95, "90–94%"), (80, 90, "80–89%"),
             (70, 80, "70–79%"), (60, 70, "60–69%"), (0, 60, "<60%")]
LOW_ACC = 80


def key_of(r) -> str:
    return f"{r.student_class or ''}|{r.student_name or ''}"


def _avg(values) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def _median(values) -> float | None:
    s = sorted(v for v in values if v is not None)
    if not s:
        return None
    n = len(s)
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _quartiles(values) -> list:
    s = sorted(v for v in values if v is not None)
    if not s:
        return [0, 0, 0, 0, 0]
    half = len(s) // 2
    low, high = s[:half], s[half + len(s) % 2:]
    return [s[0], _median(low or s), _median(s), _median(high or s), s[-1]]


def _pct(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


def _stamp(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""


def speed_bands(speeds: list) -> list:
    """按最快的那个定格子宽度，最多 12 段。"""
    if not speeds:
        return []
    top = max(speeds)
    width = next((w for w in (5, 10, 20, 30, 50, 100) if top / w < 12), 200)
    out = []
    for i in range(max(1, math.ceil((top + 1) / width))):
        lo, hi = i * width, (i + 1) * width
        out.append({"label": f"{lo}–{hi}", "count": sum(1 for s in speeds if lo <= s < hi)})
    return out


def _students(records: list, speedy: bool) -> "OrderedDict[str, dict]":
    groups: "OrderedDict[str, list]" = OrderedDict()
    for r in sorted(records, key=lambda x: (x.created_at or datetime.min, x.id or 0)):
        groups.setdefault(key_of(r), []).append(r)
    out: "OrderedDict[str, dict]" = OrderedDict()
    for k, rs in groups.items():
        metric = [x.speed if speedy else x.accuracy for x in rs]
        out[k] = {
            "key": k, "name": rs[0].student_name, "class": rs[0].student_class or "未填班级",
            "count": len(rs),
            "best_speed": max(x.speed for x in rs) if speedy else None,
            "avg_speed": _avg(x.speed for x in rs) if speedy else None,
            "avg_accuracy": _avg(x.accuracy for x in rs),
            "reach_rate": _pct(sum(1 for x in rs if x.stars >= 2), len(rs)),
            "progress": (round(sum(metric[-3:]) / 3 - sum(metric[:3]) / 3, 1)
                         if len(rs) >= 4 else None),
            "minutes": round(sum(x.duration for x in rs) / 60, 1),
            "last_at": _stamp(rs[-1].created_at),
            "records": rs,
        }
    return out


def _trend(records: list, speedy: bool, today: date | None, days: int) -> dict:
    """按天汇总（跨度超过 62 天按周）；没人练的日子也列出来，线才不会骗人。"""
    dated = [r for r in records if r.created_at]
    if not dated:
        return {"unit": "day", "points": []}
    first = min(r.created_at.date() for r in dated)
    last = max(r.created_at.date() for r in dated)
    if days and today:
        first, last = min(first, today - timedelta(days=days - 1)), max(last, today)
    unit = "day" if (last - first).days < 62 else "week"

    def bucket(d: date) -> date:
        return d if unit == "day" else d - timedelta(days=d.weekday())

    groups: "OrderedDict[date, list]" = OrderedDict()
    d, step = bucket(first), timedelta(days=1 if unit == "day" else 7)
    while d <= last:
        groups[d] = []
        d += step
    for r in dated:
        groups.setdefault(bucket(r.created_at.date()), []).append(r)
    return {"unit": unit, "points": [{
        "date": d.isoformat(),
        "label": d.strftime("%m-%d") + ("" if unit == "day" else " 起"),
        "count": len(rs),
        "students": len({key_of(x) for x in rs}),
        "avg_speed": _avg(x.speed for x in rs) if speedy else None,
        "avg_accuracy": _avg(x.accuracy for x in rs),
    } for d, rs in sorted(groups.items())]}


def analyze(records: list, module: str = "", scope: dict | None = None,
            roster: dict | None = None, today: date | None = None, days: int = 0) -> dict:
    speedy = module in TEXT_MODULES
    scope = scope or {"kind": "all"}
    roster = roster or {}
    n = len(records)
    studs = _students(records, speedy)
    speeds = [r.speed for r in records] if speedy else []
    accs = [r.accuracy for r in records]

    summary = {
        "count": n,
        "students": len(studs),
        "per_student": round(n / len(studs), 1) if studs else None,
        "avg_speed": _avg(speeds) if speedy else None,
        "median_speed": _median(speeds) if speedy else None,
        "max_speed": max(speeds) if speeds else None,
        "avg_accuracy": _avg(accs),
        "median_accuracy": _median(accs),
        "avg_duration": round(sum(r.duration for r in records) / n) if n else None,
        "minutes": round(sum(r.duration for r in records) / 60, 1),
        "reach_rate": _pct(sum(1 for r in records if r.stars >= 2), n),
        "three_star_rate": _pct(sum(1 for r in records if r.stars >= 3), n),
        "once_only": sum(1 for s in studs.values() if s["count"] == 1),
    }

    diffs: "OrderedDict[str, list]" = OrderedDict((d, []) for d in DIFFICULTY_ORDER)
    for r in records:
        diffs.setdefault(r.difficulty or "未注明", []).append(r)
    difficulties = [{
        "name": name, "count": len(rs), "share": _pct(len(rs), n),
        "avg_speed": _avg(x.speed for x in rs) if speedy else None,
        "avg_accuracy": _avg(x.accuracy for x in rs),
        "reach_rate": _pct(sum(1 for x in rs if x.stars >= 2), len(rs)),
    } for name, rs in diffs.items() if rs]

    mods: "OrderedDict[str, list]" = OrderedDict()
    for r in records:
        mods.setdefault(r.module, []).append(r)
    by_module = [{
        "name": name, "count": len(rs), "students": len({key_of(x) for x in rs}),
        "avg_speed": _avg(x.speed for x in rs) if name in TEXT_MODULES else None,
        "avg_accuracy": _avg(x.accuracy for x in rs),
    } for name, rs in mods.items()]

    per_class: "OrderedDict[str, list]" = OrderedDict()
    for s in sorted(studs.values(), key=lambda x: x["class"]):
        per_class.setdefault(s["class"], []).append(s)
    classes = []
    for name, ss in per_class.items():
        rs = [x for s in ss for x in s["records"]]
        size = roster.get(name)
        classes.append({
            "name": name, "students": len(ss), "roster": size,
            "participation": _pct(len(ss), size) if size else None,
            "count": len(rs), "per_student": round(len(rs) / len(ss), 1),
            "avg_speed": _avg(s["avg_speed"] for s in ss) if speedy else None,
            "avg_accuracy": _avg(s["avg_accuracy"] for s in ss),
            "reach_rate": _pct(sum(1 for x in rs if x.stars >= 2), len(rs)),
            "box": _quartiles([s["avg_speed"] for s in ss]) if speedy else None,
        })

    ordered = sorted(studs.values(), key=lambda s: (
        -((s["best_speed"] if speedy else s["avg_accuracy"]) or 0), -(s["avg_accuracy"] or 0), s["name"]))
    ranking = [{**{k: v for k, v in s.items() if k != "records"}, "rank": i}
               for i, s in enumerate(ordered, 1)]

    compare = []
    if scope.get("kind") == "students":
        for s in studs.values():
            compare.append({**{k: v for k, v in s.items() if k != "records"}, "points": [{
                "at": _stamp(x.created_at), "speed": x.speed if speedy else None,
                "accuracy": x.accuracy, "difficulty": x.difficulty, "stars": x.stars,
            } for x in s["records"]]})

    result = {
        "module": module, "speedy": speedy, "scope": scope, "summary": summary,
        "accuracy_bands": [{"label": lab, "count": sum(1 for a in accs if lo <= a < hi)}
                           for lo, hi, lab in ACC_BANDS],
        "speed_bands": speed_bands(speeds),
        "stars": [{"label": "★" * k if k else "无星", "count": sum(1 for r in records if r.stars == k)}
                  for k in range(4)],
        "difficulties": difficulties,
        "by_module": by_module,
        "trend": _trend(records, speedy, today, days),
        "classes": classes,
        "ranking": ranking,
        "compare": compare,
    }
    result["conclusions"] = conclusions(result, records)
    return result


def conclusions(r: dict, records: list) -> list:
    """把数据翻成几句老师能直接拿去讲的话。"""
    s = r["summary"]
    if not s["count"]:
        return ["这个范围里还没有打字练习记录，学生练习后这里会自动出结论。"]
    speedy = r["speedy"]
    unit = "字/分" if r["module"] == "中文" else "字母/分" if r["module"] == "英文" else ""
    kind = r["scope"].get("kind")
    who = {"classes": "所选班级", "students": "所选学生"}.get(kind, "全体学生")
    group = kind != "students"
    out = []

    head = f"{who}共 {s['students']} 人练习 {s['count']} 次（人均 {s['per_student']} 次，累计 {s['minutes']} 分钟）"
    if speedy:
        head += f"，平均速度 {s['avg_speed']} {unit}（中位数 {s['median_speed']}，最快 {s['max_speed']}）"
    out.append(head + f"，平均正确率 {s['avg_accuracy']}%。")
    if not speedy and not r["module"]:
        parts = [f"{m['name']} {m['count']} 次" + (f"、平均 {m['avg_speed']}" if m["avg_speed"] is not None else "")
                 for m in r["by_module"]]
        out.append("各模块：" + "；".join(parts) + "。速度要分模块看，请在上方选「中文」或「英文」。")

    if group and s["count"] >= 3:
        level = ("整体掌握得不错" if s["reach_rate"] >= 80 else
                 "多数练习达到了要求" if s["reach_rate"] >= 60 else "达标率偏低，建议放慢速度、先练准")
        out.append(f"达标（两星及以上）占 {s['reach_rate']}%，三星占 {s['three_star_rate']}% —— {level}。")

    if speedy:
        low = [x for x in records if x.accuracy < LOW_ACC]
        ok = [x for x in records if x.accuracy >= LOW_ACC]
        if len(low) >= 5 and len(ok) >= 5:
            a, b = _avg(x.speed for x in low), _avg(x.speed for x in ok)
            if a and b and a > b * 1.1:
                out.append(f"正确率低于 {LOW_ACC}% 的 {len(low)} 次练习平均速度 {a}，反而比其余的（{b}）快 —— "
                           "有学生在抢速度、牺牲准确，讲评时强调「先准后快」。")

    pts = [p for p in r["trend"]["points"] if p["count"]]
    metric = "avg_speed" if speedy else "avg_accuracy"
    if len(pts) >= 4:
        half = len(pts) // 2
        a, b = _avg(p[metric] for p in pts[:half]), _avg(p[metric] for p in pts[half:])
        if a is not None and b is not None:
            what, u = ("平均速度", f" {unit}") if speedy else ("平均正确率", "%")
            d = round(b - a, 1)
            trend = f"提高了 {d}{u}" if d > 0.5 else f"下降了 {-d}{u}" if d < -0.5 else "基本持平"
            out.append(f"走势：后半段{what}比前半段{trend}。")

    classes = [c for c in r["classes"] if c["students"]]
    if group and len(classes) >= 2:
        key = "avg_speed" if speedy else "avg_accuracy"
        best = max(classes, key=lambda c: c[key] or 0)
        worst = min(classes, key=lambda c: c[key] or 0)
        u = f" {unit}" if speedy else "%"
        out.append(f"班级之间：{best['name']} 最好（{best[key]}{u}），{worst['name']} 最弱（{worst[key]}{u}）。")
    joined = [c for c in classes if c["participation"] is not None]
    if group and joined:
        least = min(joined, key=lambda c: c["participation"])
        if least["participation"] < 100:
            out.append(f"参与率最低的是 {least['name']}：名单 {least['roster']} 人，练过的 {least['students']} 人"
                       f"（{least['participation']}%），还有 {least['roster'] - least['students']} 人没练过。")
    if group and s["students"] >= 5 and s["once_only"]:
        out.append(f"只练过一次的学生有 {s['once_only']} 人（{_pct(s['once_only'], s['students'])}%），"
                   "打字靠反复练，可以督促他们多练几次。")

    easy = next((d for d in r["difficulties"] if d["name"] == "简单"), None)
    if group and easy and easy["share"] and easy["share"] >= 70 and (easy["reach_rate"] or 0) >= 80:
        out.append(f"{easy['share']}% 的练习是简单难度，且达标率 {easy['reach_rate']}%，可以引导达标的学生挑战中等难度。")

    moved = [x for x in r["ranking"] if x["progress"] is not None]
    if group and moved:
        up = sorted([x for x in moved if x["progress"] > 0], key=lambda x: -x["progress"])[:3]
        u = f" {unit}" if speedy else "%"
        if up:
            out.append("进步最明显：" + "、".join(f"{x['name']}（{x['class']}，+{x['progress']}{u}）" for x in up) + "。")
        down = [x for x in moved if x["progress"] < -5]
        if down:
            out.append(f"有 {len(down)} 人最近几次比最初明显退步，名单里按「进步」排序可以看到是谁。")

    for c in r["compare"][:8]:
        bit = f"最快 {c['best_speed']}、平均 {c['avg_speed']}，" if speedy else ""
        prog = "" if c["progress"] is None else f"，最近比最初 {'+' if c['progress'] >= 0 else ''}{c['progress']}"
        out.append(f"{c['name']}（{c['class']}）：练了 {c['count']} 次，{bit}正确率 {c['avg_accuracy']}%{prog}。")
    return out
