"""考试：取卷（去答案）与后端判分。

安全上的关键约定：
    给学生的接口一律走 exam_questions(..., with_answer=False)，
    答案只在 grade() 里读，永远不进响应体。

判分分两段（2.4.0 起）：

    客观题  选择题、判断题这些机器判得了的 —— 交卷当场算分；
    主观题  操作题这些要人看的 —— 先记 0 分，老师在成绩页逐题给分后补上。

所以一份答卷的总分 = 客观题得分 + 主观题得分，老师阅卷后 score 会变。
学生交完卷立刻看到的是客观题那一段，界面上会写明"操作题待老师评阅"。

**老卷子（2.4.0 之前组的）没有每题分值**，这里会自动退回原来的算法：
按客观题正确率折成百分制。历史成绩因此一分不变。判断依据是
has_scores()：卷面上有没有任何一道题带分值。
"""

import json
import secrets
from datetime import datetime

from sqlalchemy.orm import Session

from ..models import Exam, Paper, PaperItem, Question
from ..siteconfig import site
from . import sim
from .paper import right_letter


def _json(raw, fallback):
    """读一段存在库里的 JSON。坏了就当默认值 —— 一道题的仿真数据格式不对，
    不该让整场考试交不上卷。"""
    try:
        got = json.loads(raw or "")
    except (ValueError, TypeError):
        return fallback
    return got if isinstance(got, type(fallback)) else fallback


def new_token() -> str:
    """学生链接里的口令，够随机以防被猜到。"""
    return secrets.token_urlsafe(site.exam.token_length)


def manual_types() -> set[str]:
    """要老师人工评阅的题型，见 config.yaml 的 exam.manual_types。"""
    return set(site.exam.manual_types)


def is_manual(item: dict) -> bool:
    return item.get("type") in manual_types()


def has_scores(items: list[dict]) -> bool:
    """这份卷子有没有设每题分值。没有就是 2.4.0 之前的老卷子。"""
    return any(int(it.get("score") or 0) for it in items)


def _item_from_row(item: PaperItem, q: Question) -> dict:
    """把试卷里的一题还原成完整结构（含打乱后的选项与答案）。"""
    snap = json.loads(item.snapshot_json) if item.snapshot_json else {}
    out = {
        "id": q.id,
        "code": q.code,
        "type": q.type,
        "stem": q.stem,
        "answer": snap.get("answer", q.answer) or "",
        "scope": q.scope,
        "source": q.source,
        "image_url": q.image_url,
        "difficulty": q.difficulty,
        "section": item.section or q.type,   # 老卷子没存大题，按题型归
        "score": item.score or 0,
        "options": snap.get("options")
        or [{"label": o.label, "content": o.content} for o in q.options],
    }
    if q.sim_task is not None:
        # sim  —— 学生要拿到的：打开时看到什么
        # sim_checks —— **等同于答案**，只在服务端读，由 strip_answers() 摘掉
        out["sim"] = sim.sim_for_student({
            "id": q.sim_task.id, "kind": q.sim_task.kind, "title": q.sim_task.title,
            "env": _json(q.sim_task.env_json, {}),
        })
        out["sim_checks"] = _json(q.sim_task.checks_json, [])
    return out


def load_items(db: Session, paper: Paper) -> list[dict]:
    """按卷面顺序取出全部题目（含答案，仅供服务端使用）。"""
    out = []
    for it in paper.items:
        q = db.get(Question, it.question_id)
        if q:
            out.append(_item_from_row(it, q))
    return out


def group_items(items: list[dict]) -> list[dict]:
    """按大题分组。大题不等于题型 —— 「物联网实践与探索」里两种题型都有。"""
    groups: list[dict] = []
    for it in items:
        name = it.get("section") or it["type"]
        g = next((g for g in groups if g["name"] == name), None)
        if not g:
            g = {"name": name, "type": name, "score": 0, "items": []}
            groups.append(g)
        g["items"].append(it)
        g["score"] += int(it.get("score") or 0)
    return groups


def strip_answers(groups: list[dict]) -> list[dict]:
    """去掉答案再发给学生。多留一道关卡，避免以后改代码时不小心漏出去。

    每题的分值是留着的 —— 卷面上本来就印着"本题 2 分"，那不是答案线索。
    """
    return [
        {
            "name": g.get("name") or g["type"],
            "type": g["type"],
            "score": g.get("score", 0),
            "items": [
                # sim_checks 是仿真题的答案，和 answer 一样绝不能发给学生
            {
                k: v for k, v in it.items()
                if k not in ("answer", "source", "difficulty", "sim_checks")
            }
                for it in g["items"]
            ],
        }
        for g in groups
    ]


def scorable(item: dict) -> bool:
    """能不能机器判分。操作题靠人看；原卷没给答案的题不计分，
    否则不作答会被判成答对。"""
    return not is_manual(item) and bool((item.get("answer") or "").strip())


def grade(items: list[dict], answers: dict) -> dict:
    """后端判分。answers 的键是题目 id（字符串或数字都认）。

    返回里 score 是**当前**总分：主观题还没批，所以等于客观题得分。
    老师批完走 apply_manual() 重算。
    """
    scored = has_scores(items)
    detail = []
    auto_manual: dict[str, int] = {}     # 仿真题自动判出来的分，预填给老师
    auto_sub = 0
    right = 0
    objective = 0
    obj_score = 0
    obj_total = 0
    sub_total = 0

    for it in items:
        mine = answers.get(str(it["id"]), answers.get(it["id"], ""))
        mine = "" if mine is None else str(mine).strip()
        pts = int(it.get("score") or 0)

        if not scorable(it):
            manual = is_manual(it)
            if manual:
                sub_total += pts
            entry = {
                "id": it["id"],
                "type": it["type"],
                "scored": False,
                "manual": manual,
                "score": pts,
                "earned": 0,
                "mine": mine,
                "answer": it.get("answer") or "",
                "reason": "待老师评阅" if manual else "原卷未给答案，不计分",
            }
            # 挂了仿真任务的操作题：按检查点当场判分。判出来的分只是**预填**，
            # 老师在成绩页照样能改（apply_manual 覆盖它）。
            if manual and it.get("sim_checks"):
                ran = sim.run_checks(
                    (it.get("sim") or {}).get("kind"),
                    it["sim_checks"],
                    sim.load_state(mine),
                )
                earned = scale_sim(ran, pts)
                auto_manual[str(it["id"])] = earned
                auto_sub += earned
                entry.update(
                    earned=earned,
                    auto=True,
                    reason="仿真题自动判分，老师可复核",
                    checks=ran["results"],
                    check_passed=sum(1 for r in ran["results"] if r["ok"]),
                    check_total=len(ran["results"]),
                )
            detail.append(entry)
            continue

        objective += 1
        obj_total += pts
        correct = right_letter(it)
        ok = mine == correct
        if ok:
            right += 1
            obj_score += pts
        detail.append(
            {
                "id": it["id"],
                "type": it["type"],
                "scored": True,
                "manual": False,
                "score": pts,
                "earned": pts if ok else 0,
                "ok": ok,
                "mine": mine,
                "answer": correct,
            }
        )

    if not scored:
        # 老卷子：没设分值，照旧按客观题正确率折百分制
        obj_score = round(right / objective * 100) if objective else 0
        obj_total = 100 if objective else 0
        sub_total = 0
        auto_manual, auto_sub = {}, 0

    return {
        "right_count": right,
        "objective_count": objective,
        "objective_score": obj_score,
        "objective_total": obj_total,
        "subjective_score": auto_sub,
        "subjective_total": sub_total,
        # 仿真题已经判了，总分把那部分算进去；剩下的等老师批完再补
        "score": obj_score + auto_sub,
        "full_score": obj_total + sub_total,
        "pending_manual": sum(1 for d in detail if d.get("manual") and not d.get("auto")),
        "auto_manual": auto_manual,
        "detail": detail,
    }


def scale_sim(ran: dict, pts: int) -> int:
    """把检查点的得分折算成这道题在卷面上的分值。

    检查点的总分是出题时定的（比如四小问各 2 分），而卷面分值是组卷时按难度
    分摊出来的（这道题可能只占 7 分）—— 两者对不上是常态，必须按比例折算，
    否则会出现"一道 7 分的题判出 8 分"。
    """
    full = int(ran.get("full") or 0)
    if not full or pts <= 0:
        return 0
    got = int(round(pts * int(ran.get("score") or 0) / full))
    return max(0, min(pts, got))


def submission_scores(result: dict) -> dict:
    """交卷时要落库的分数字段。两个交卷入口（学生端、凭链接）共用这一份，
    省得一处加了字段另一处忘了加。"""
    fields = {
        "right_count": result["right_count"],
        "objective_count": result["objective_count"],
        "score": result["score"],
        "objective_score": result["objective_score"],
        "objective_total": result["objective_total"],
        "subjective_score": result["subjective_score"],
        "subjective_total": result["subjective_total"],
        # 仿真题判出来的分预填进去，老师在成绩页能改
        "manual_json": json.dumps(result.get("auto_manual") or {}, ensure_ascii=False),
    }
    # 主观题全是仿真题、已经当场判完的，就别再出现在老师的"待批"里了。
    # graded_by 留空表示不是人批的，成绩页上会标「自动判分」。
    if result["subjective_total"] > 0 and result["pending_manual"] == 0:
        fields["graded_at"] = datetime.now()
    return fields


def apply_manual(detail: list[dict], manual_scores: dict) -> dict:
    """把老师给的主观题分数填进明细，重算主观分。

    manual_scores 的键是题目 id，值是得分；超出该题满分的按满分算，
    负数按 0 算 —— 老师手滑打多一位不该让总分冒出卷面。
    返回 {detail, subjective_score, graded_count, pending}。
    """
    got = 0
    graded = 0
    pending = 0

    for d in detail:
        if not d.get("manual"):
            continue
        full = int(d.get("score") or 0)
        raw = manual_scores.get(str(d["id"]), manual_scores.get(d["id"]))
        if raw is None or raw == "":
            d["earned"] = 0
            d["graded"] = False
            pending += 1
            continue
        try:
            value = int(round(float(raw)))
        except (TypeError, ValueError):
            value = 0
        value = max(0, min(full, value))
        d["earned"] = value
        d["graded"] = True
        got += value
        graded += 1

    return {
        "detail": detail,
        "subjective_score": got,
        "graded_count": graded,
        "pending": pending,
    }


def question_stats(exam: Exam, items: list[dict]) -> list[dict]:
    """每题的作答情况，老师用来看哪道题错得多。"""
    by_id = {it["id"]: it for it in items}
    counters: dict[int, dict] = {
        it["id"]: {"right": 0, "wrong": 0, "blank": 0} for it in items
    }

    for sub in exam.submissions:
        for d in json.loads(sub.detail_json or "[]"):
            c = counters.get(d["id"])
            if c is None or not d.get("scored"):
                continue
            if not d.get("mine"):
                c["blank"] += 1
            elif d.get("ok"):
                c["right"] += 1
            else:
                c["wrong"] += 1

    out = []
    for qid, c in counters.items():
        it = by_id[qid]
        answered = c["right"] + c["wrong"] + c["blank"]
        out.append(
            {
                "id": qid,
                "type": it["type"],
                "scope": it["scope"],
                "section": it.get("section") or it["type"],
                "score": int(it.get("score") or 0),
                "difficulty": it.get("difficulty") or 3,
                "stem": it["stem"][:60],
                "answer": it.get("answer") or "",
                "right": c["right"],
                "wrong": c["wrong"],
                "blank": c["blank"],
                "accuracy": round(c["right"] / answered * 100) if answered else 0,
                "scorable": scorable(it),
            }
        )
    return out
