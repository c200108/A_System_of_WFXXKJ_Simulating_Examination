"""一场考试的成绩分析：各维度的统计 + 自动写出来的结论。

    analyze(items, subs, pass_score, scope)  →  给「成绩分析」页的一整份数据

纯计算，不碰数据库：items 是 load_items() 出来的卷面，subs 是答卷行。
这样每个数、每句结论都能在测试里对着算。

## 口径

- **得分率** = 得分 / 满分。卷面总分不一定是 100（老师能改大题分值），所以比较、
  划线一律按得分率；显示时再换回分数。
- 老卷子（2.4.0 之前，没有每题分值）按客观题正确率折百分制，满分 100，每题得分率
  就是答对率。
- 操作题还没评完的，按**当前**得分算（检查点部分通过的是按比例预填的分），另外
  单独报"还有几份待评阅"—— 评完之后页面自动刷新，数跟着变。
- 及格线取 config.yaml 的 exam.pass_score；优秀 ≥ 85%，低分 < 40%。
- 区分度：按总分排，取前 27% 和后 27% 两组，这道题两组得分率之差（-1～1）。
  高分组答得好、低分组答不好，说明这题能把会的和不会的分开；差不多甚至倒过来，
  多半是题目有歧义或者答案有问题。
"""

from __future__ import annotations

import json
import math
from collections import OrderedDict

EXCELLENT = 85        # 优秀线（得分率 %）
LOW = 40              # 低分线（得分率 %）


def _pct(x: float) -> float:
    return round(x * 100, 1)


def _median(values: list) -> float:
    s = sorted(values)
    n = len(s)
    if not n:
        return 0.0
    return float(s[n // 2]) if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def _quartiles(values: list) -> tuple:
    s = sorted(values)
    if not s:
        return (0, 0, 0, 0, 0)
    half = len(s) // 2
    low, high = s[:half], s[half + (len(s) % 2):]
    return (s[0], _median(low or s), _median(s), _median(high or s), s[-1])


def _std(values: list) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


def _stats(scores: list, full: float, pass_score: int) -> dict:
    n = len(scores)
    if not n:
        return {"count": 0, "avg": None, "avg_rate": None, "median": None, "max": None,
                "min": None, "std": None, "pass_rate": None, "excellent_rate": None,
                "low_rate": None, "full_marks": 0}
    rates = [s / full * 100 if full else 0 for s in scores]
    avg = sum(scores) / n
    return {
        "count": n,
        "avg": round(avg, 1),
        "avg_rate": round(avg / full * 100, 1) if full else 0,
        "median": round(_median(scores), 1),
        "max": max(scores),
        "min": min(scores),
        "std": round(_std(scores), 1),
        "pass_rate": _pct(sum(1 for r in rates if r >= pass_score) / n),
        "excellent_rate": _pct(sum(1 for r in rates if r >= EXCELLENT) / n),
        "low_rate": _pct(sum(1 for r in rates if r < LOW) / n),
        "full_marks": sum(1 for s in scores if full and s >= full),
    }


def _earned_by_question(detail: list, scored: bool) -> dict:
    """{题目 id: (得分, 这题满分, 有没有作答)}。老卷子没分值，答对记 1 分、满分 1。"""
    out = {}
    for d in detail:
        if scored:
            out[d["id"]] = (int(d.get("earned") or 0), int(d.get("score") or 0), bool(d.get("mine")))
        elif d.get("scored"):
            out[d["id"]] = (1 if d.get("ok") else 0, 1, bool(d.get("mine")))
    return out


def _group_rates(items: list, earned: dict, key: str) -> "OrderedDict[str, dict]":
    """按大题 / 知识范围 / 题型汇总：满分、平均得分、得分率。"""
    out: "OrderedDict[str, dict]" = OrderedDict()
    for it in items:
        name = it.get(key) or it.get("type") or "其他"
        g = out.setdefault(name, {"name": name, "full": 0, "got": 0.0, "questions": 0})
        g["questions"] += 1
    for it in items:
        name = it.get(key) or it.get("type") or "其他"
        g = out[name]
        pts = [e.get(it["id"]) for e in earned.values()]
        pts = [p for p in pts if p]
        full = pts[0][1] if pts else int(it.get("score") or 0)
        g["full"] += full
        g["got"] += (sum(p[0] for p in pts) / len(pts)) if pts else 0
    for g in out.values():
        g["avg"] = round(g["got"], 1)
        g["rate"] = round(g["got"] / g["full"] * 100, 1) if g["full"] else None
        del g["got"]
    return out


def analyze(items: list, subs: list, pass_score: int, scope: dict | None = None,
            all_subs: list | None = None, scored: bool = True) -> dict:
    """subs 是要分析的那一批（全部 / 某几个班 / 选中的几个学生），all_subs 是全场
    （算名次用）。scope 原样放回去，页面上用来显示"现在看的是谁"。"""
    all_subs = all_subs if all_subs is not None else subs
    full = sum(int(it.get("score") or 0) for it in items) if scored else 100
    # 每份答卷的明细只解析一次：带考场快照的答卷一份就上百 KB，按题循环里反复
    # json.loads 的话，60 份 × 60 道题就是三千多次，页面每 20 秒还要刷新一回
    details = {s.id: json.loads(s.detail_json or "[]") for s in subs}
    by_q = {sid: {d.get("id"): d for d in dl} for sid, dl in details.items()}
    scores = [s.score for s in subs]
    summary = _stats(scores, full, pass_score)
    summary["full"] = full
    # 老卷子（没设分值）操作题不计分，谈不上"待复核"
    summary["pending"] = sum(
        1 for s in subs
        if (s.subjective_total or 0) > 0
        and any(d.get("manual") and not d.get("graded") for d in details[s.id])
    )

    # ---------------- 分数段：按满分切十段
    bands = []
    for i in range(10):
        lo, hi = full * i / 10, full * (i + 1) / 10
        n = sum(1 for s in scores if (lo <= s < hi) or (i == 9 and s >= hi))
        bands.append({"from": round(lo), "to": round(hi), "label": f"{round(lo)}–{round(hi)}", "count": n})

    # ---------------- 班级
    by_class = OrderedDict()
    for s in sorted(subs, key=lambda x: x.student_class or ""):
        by_class.setdefault(s.student_class or "未填班级", []).append(s.score)
    classes = []
    for name, sc in by_class.items():
        st = _stats(sc, full, pass_score)
        st["name"] = name
        st["box"] = _quartiles(sc)
        classes.append(st)

    # ---------------- 每题 / 大题 / 知识范围 / 题型
    earned = {s.id: _earned_by_question(details[s.id], scored) for s in subs}
    ordered = sorted(subs, key=lambda x: -x.score)
    k = max(1, round(len(ordered) * 0.27)) if ordered else 0
    high = [s.id for s in ordered[:k]]
    low = [s.id for s in ordered[-k:]] if k else []

    def rate_of(qid, ids):
        pts = [earned[i].get(qid) for i in ids]
        pts = [p for p in pts if p and p[1]]
        return sum(p[0] / p[1] for p in pts) / len(pts) if pts else None

    questions = []
    for no, it in enumerate(items, 1):
        pts = [e.get(it["id"]) for e in earned.values()]
        pts = [p for p in pts if p]
        per_full = pts[0][1] if pts else int(it.get("score") or 0)
        avg = sum(p[0] for p in pts) / len(pts) if pts else 0
        rate = avg / per_full * 100 if per_full else None
        hi, lo = rate_of(it["id"], high), rate_of(it["id"], low)
        disc = round(hi - lo, 2) if hi is not None and lo is not None and len(ordered) >= 4 else None
        questions.append({
            "no": no, "id": it["id"], "type": it["type"], "section": it.get("section") or it["type"],
            "scope": it.get("scope") or "", "stem": (it.get("stem") or "")[:80],
            "score": per_full, "avg": round(avg, 2), "rate": round(rate, 1) if rate is not None else None,
            "blank": sum(1 for p in pts if not p[2]), "answered": len(pts),
            "discrimination": disc,
        })

    # ---------------- 操作题：每个检查点的通过率
    operations = []
    by_id = {q["id"]: q for q in questions}
    for it in items:
        tally: "OrderedDict[str, list]" = OrderedDict()
        for s in subs:
            d = by_q[s.id].get(it["id"])
            if d and d.get("checks"):
                for c in d["checks"]:
                    t = tally.setdefault(str(c.get("desc") or ""), [0, 0])
                    t[0] += 1 if c.get("ok") else 0
                    t[1] += 1
        if tally:
            q = by_id[it["id"]]
            operations.append({
                "no": q["no"], "id": it["id"], "stem": q["stem"], "rate": q["rate"],
                # passed / total：通过人数、作答人数，分题排名里要写「30 人里 12 人过」
                "checks": [{"desc": desc, "pass_rate": _pct(ok / n) if n else 0,
                            "passed": ok, "total": n}
                           for desc, (ok, n) in tally.items()],
            })

    # ---------------- 名次（在全场里排）
    board = sorted(all_subs, key=lambda x: (-x.score, x.student_no or ""))
    rank_of, last, last_rank = {}, None, 0
    for i, s in enumerate(board, 1):
        if s.score != last:
            last, last_rank = s.score, i
        rank_of[s.id] = last_rank
    ranking = [{
        "sub_id": s.id, "rank": rank_of.get(s.id), "name": s.student_name, "class": s.student_class,
        "no": s.student_no, "score": s.score, "rate": round(s.score / full * 100, 1) if full else 0,
        "objective": s.objective_score, "subjective": s.subjective_score,
    } for s in sorted(subs, key=lambda x: (rank_of.get(x.id, 0), x.student_no or ""))]

    # ---------------- 学生之间比
    compare = []
    if scope and scope.get("kind") == "students":
        for s in subs:
            mine = {s.id: earned[s.id]}
            compare.append({
                "sub_id": s.id, "name": s.student_name, "class": s.student_class,
                "score": s.score, "rate": round(s.score / full * 100, 1) if full else 0,
                "rank": rank_of.get(s.id), "of": len(board),
                "by_scope": [{"name": g["name"], "rate": g["rate"]}
                             for g in _group_rates(items, mine, "scope").values()],
                "by_section": [{"name": g["name"], "rate": g["rate"]}
                               for g in _group_rates(items, mine, "section").values()],
            })

    result = {
        "scope": scope or {"kind": "all"},
        "summary": summary,
        "bands": bands,
        "classes": classes,
        "sections": list(_group_rates(items, earned, "section").values()),
        "scopes": list(_group_rates(items, earned, "scope").values()),
        "types": list(_group_rates(items, earned, "type").values()),
        "questions": questions,
        "operations": operations,
        "ranking": ranking,
        "compare": compare,
    }
    result["conclusions"] = conclusions(result, pass_score)
    return result


def conclusions(r: dict, pass_score: int) -> list:
    """把数据翻成几句老师能直接拿去讲评的话。"""
    s = r["summary"]
    out = []
    if not s["count"]:
        return ["还没有人交卷，交卷之后这里会自动出结论。"]
    full = s["full"]
    kind = (r.get("scope") or {}).get("kind")
    who = {"all": "全体参考学生", "classes": "所选班级", "students": "所选学生"}.get(kind, "全体参考学生")
    # 几个学生之间比：分布、班级之间这些是"群体"的说法，三五个人谈不上，只留个人的
    group = kind != "students"

    out.append(f"{who}共 {s['count']} 人，平均分 {s['avg']}/{full}（得分率 {s['avg_rate']}%），"
               f"中位数 {s['median']}，最高 {s['max']}、最低 {s['min']}。")

    if group and s["count"] >= 3:
        level = ("整体掌握得不错" if s["pass_rate"] >= 90 else
                 "大部分学生达到了要求" if s["pass_rate"] >= 70 else
                 "及格率偏低，需要重点补一补")
        out.append(f"及格率 {s['pass_rate']}%（及格线 {pass_score}%），优秀率 {s['excellent_rate']}%"
                   f"（≥{EXCELLENT}%），低分率 {s['low_rate']}%（<{LOW}%）—— {level}。")

        top = max(r["bands"], key=lambda b: b["count"])
        gap = s["avg"] - s["median"]
        shape = ("有少数低分拉低了平均分" if gap < -full * 0.03 else
                 "有少数高分拉高了平均分" if gap > full * 0.03 else "分布比较均衡")
        spread = s["std"] / full if full else 0
        spread_word = "分化明显" if spread > 0.2 else "差距适中" if spread > 0.1 else "比较集中"
        out.append(f"分数最集中在 {top['label']} 分这一段（{top['count']} 人），{shape}；"
                   f"标准差 {s['std']}，学生之间{spread_word}。")

    classes = [c for c in r["classes"] if c["count"]]
    if group and len(classes) >= 2:
        best = max(classes, key=lambda c: c["avg"])
        worst = min(classes, key=lambda c: c["avg"])
        diff = round(best["avg"] - worst["avg"], 1)
        tail = "，差距明显，建议对照两个班的错题看看问题出在哪" if full and diff > full * 0.1 else "，各班差距不大"
        out.append(f"班级之间：{best['name']} 平均分最高（{best['avg']}），{worst['name']} 最低"
                   f"（{worst['avg']}），相差 {diff} 分{tail}。")

    scopes = [g for g in r["scopes"] if g["rate"] is not None and g["full"]]
    if len(scopes) >= 2:
        weak = sorted(scopes, key=lambda g: g["rate"])[:2]
        strong = max(scopes, key=lambda g: g["rate"])
        out.append("薄弱的知识范围：" + "、".join(f"{g['name']}（得分率 {g['rate']}%）" for g in weak)
                   + f"；掌握最好的是 {strong['name']}（{strong['rate']}%）。")

    qs = [q for q in r["questions"] if q["rate"] is not None]
    if qs:
        hard = sorted(qs, key=lambda q: q["rate"])[:3]
        out.append("得分率最低的题：" + "、".join(f"第 {q['no']} 题（{q['type']}，{q['rate']}%）" for q in hard)
                   + "，讲评时优先讲。")
        under = [q for q in qs if q["rate"] < 40]
        if len(under) >= 3:
            out.append(f"得分率不到 40% 的题有 {len(under)} 道，占全卷 {round(len(under) / len(qs) * 100)}%。")
    odd = [q for q in r["questions"] if q["discrimination"] is not None and q["discrimination"] < 0.1
           and q["rate"] is not None and 15 < q["rate"] < 95]
    if odd:
        out.append("区分度偏低的题：" + "、".join(f"第 {q['no']} 题（{q['discrimination']}）" for q in odd[:3])
                   + "——高分组和低分组答得差不多，可以检查一下题目有没有歧义、答案对不对。")

    ops = [c for o in r["operations"] for c in o["checks"]]
    if ops:
        worst_check = min(ops, key=lambda c: c["pass_rate"])
        op_rates = [o["rate"] for o in r["operations"] if o["rate"] is not None]
        head = (f"操作题平均得分率 {round(sum(op_rates) / len(op_rates), 1)}%，" if op_rates
                else "操作题（这份卷子没设分值，操作题不计入总分）")
        out.append(f"{head}通过率最低的一步是「{worst_check['desc']}」（{worst_check['pass_rate']}%）。")

    for c in r["compare"][:6]:
        good = [g for g in c["by_scope"] if g["rate"] is not None]
        if good:
            best = max(good, key=lambda g: g["rate"])
            weak = min(good, key=lambda g: g["rate"])
            out.append(f"{c['name']}（{c['class']}）：{c['score']} 分，全场第 {c['rank']}/{c['of']} 名；"
                       f"最强 {best['name']}（{best['rate']}%），最弱 {weak['name']}（{weak['rate']}%）。")
    if len(r["compare"]) == 2:
        a, b = r["compare"]
        diffs = []
        rb = {g["name"]: g["rate"] for g in b["by_scope"]}
        for g in a["by_scope"]:
            if g["rate"] is not None and rb.get(g["name"]) is not None:
                diffs.append((g["rate"] - rb[g["name"]], g["name"]))
        if diffs:
            d, name = max(diffs, key=lambda x: abs(x[0]))
            lead, lag = (a, b) if d > 0 else (b, a)
            out.append(f"两人差距最大在「{name}」：{lead['name']} 比 {lag['name']} 高 {abs(round(d, 1))} 个百分点。")

    if s["pending"]:
        out.append(f"还有 {s['pending']} 份答卷的操作题等老师复核，上面的数字按当前得分算；"
                   "评阅完成后页面会自动刷新。")
    return out
