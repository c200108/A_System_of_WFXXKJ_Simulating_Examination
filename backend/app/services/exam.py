"""考试：取卷（去答案）与后端判分。

安全上的关键约定：
    给学生的接口一律走 exam_questions(..., with_answer=False)，
    答案只在 grade() 里读，永远不进响应体。
"""

import json
import secrets

from sqlalchemy.orm import Session

from ..models import Exam, Paper, PaperItem, Question
from .paper import right_letter


def new_token() -> str:
    """学生链接里的口令，够随机以防被猜到。"""
    return secrets.token_urlsafe(9)


def _item_from_row(item: PaperItem, q: Question) -> dict:
    """把试卷里的一题还原成完整结构（含打乱后的选项与答案）。"""
    snap = json.loads(item.snapshot_json) if item.snapshot_json else {}
    return {
        "id": q.id,
        "code": q.code,
        "type": q.type,
        "stem": q.stem,
        "answer": snap.get("answer", q.answer) or "",
        "scope": q.scope,
        "source": q.source,
        "image_url": q.image_url,
        "options": snap.get("options")
        or [{"label": o.label, "content": o.content} for o in q.options],
    }


def load_items(db: Session, paper: Paper) -> list[dict]:
    """按卷面顺序取出全部题目（含答案，仅供服务端使用）。"""
    out = []
    for it in paper.items:
        q = db.get(Question, it.question_id)
        if q:
            out.append(_item_from_row(it, q))
    return out


def group_items(items: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for it in items:
        g = next((g for g in groups if g["type"] == it["type"]), None)
        if not g:
            g = {"type": it["type"], "items": []}
            groups.append(g)
        g["items"].append(it)
    return groups


def strip_answers(groups: list[dict]) -> list[dict]:
    """去掉答案再发给学生。多留一道关卡，避免以后改代码时不小心漏出去。"""
    return [
        {
            "type": g["type"],
            "items": [
                {k: v for k, v in it.items() if k not in ("answer", "source")}
                for it in g["items"]
            ],
        }
        for g in groups
    ]


def scorable(item: dict) -> bool:
    """操作题靠人工看；原卷没给答案的题不计分，否则不作答会被判成答对。"""
    return item["type"] != "操作题" and bool((item.get("answer") or "").strip())


def grade(items: list[dict], answers: dict) -> dict:
    """后端判分。answers 的键是题目 id（字符串或数字都认）。"""
    detail = []
    right = 0
    objective = 0

    for it in items:
        mine = answers.get(str(it["id"]), answers.get(it["id"], ""))
        mine = "" if mine is None else str(mine).strip()

        if not scorable(it):
            detail.append(
                {
                    "id": it["id"],
                    "type": it["type"],
                    "scored": False,
                    "mine": mine,
                    "answer": it.get("answer") or "",
                    "reason": "操作题需人工评阅" if it["type"] == "操作题" else "原卷未给答案，不计分",
                }
            )
            continue

        objective += 1
        correct = right_letter(it)
        ok = mine == correct
        if ok:
            right += 1
        detail.append(
            {
                "id": it["id"],
                "type": it["type"],
                "scored": True,
                "ok": ok,
                "mine": mine,
                "answer": correct,
            }
        )

    return {
        "right_count": right,
        "objective_count": objective,
        "score": round(right / objective * 100) if objective else 0,
        "detail": detail,
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
