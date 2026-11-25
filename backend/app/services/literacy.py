"""人工智能通识教育测评题（2.27.0）：七、八年级各一套，跟着代码走。

## 题目从哪来

literacy_bank.json 是学校发的两份 Word 汇总（《2026年下半年人工智能通识教育测评·七/八年级试题》）
整理出来的：单选、多选、判断、填空，答案照原卷。文档后半截「补充题目（来源 examcoo，答案由 AI
推断、待核对）」也收了，来源记成「测评题（补充，答案待核对）」，老师在题库里按来源一筛就能挑出来核对。

服务器每次启动（app.seed）按题干查重补一遍：库里已有（包括删进回收站的）就跳过 —— 老师删掉的
不会再冒出来，改过的也不动。

## 和别的题怎么隔开

两个知识范围「人工智能通识教育测评题（七年级）」「（八年级）」：

- **不进六大题**：卷面结构的每一组都不会从这两个范围里抽（blueprint.slot_pool）；
- **只能按题型组卷**，而且一张卷只能选其中**一个**：和其他十类互斥，七、八年级之间也互斥；
- 选了它：操作题固定 0 道；选择题 + 判断题合计 40 道（选择题占多数，界面上每次随机一个比例）；
  填空题默认 0、可以改。
- 平常（没选它）按题型组卷、六大题都**看不到**这两个范围的题。
"""

from __future__ import annotations

import json
from pathlib import Path

SCOPE_G7 = "人工智能通识教育测评题（七年级）"
SCOPE_G8 = "人工智能通识教育测评题（八年级）"
EXAM_SCOPES = (SCOPE_G7, SCOPE_G8)
SOURCE = "测评题"
SOURCE_UNVERIFIED = "测评题（补充，答案待核对）"

# 选了测评题时，选择题 + 判断题一共几道
OBJECTIVE_TOTAL = 40

_BANK = Path(__file__).with_name("literacy_bank.json")


def is_exam_scope(name: str | None) -> bool:
    return (name or "") in EXAM_SCOPES


def bank() -> list[dict]:
    return json.loads(_BANK.read_text(encoding="utf-8"))


def ensure_scopes(db) -> int:
    """两个知识范围不在字典表里就加上（排在十类后面）。老师停用过的不动。返回新加几个。"""
    from sqlalchemy import func, select

    from ..constants import DICT_SCOPE
    from ..models import DictItem

    have = set(db.scalars(select(DictItem.name).where(DictItem.category == DICT_SCOPE)))
    top = db.scalar(select(func.max(DictItem.sort_order)).where(DictItem.category == DICT_SCOPE)) or 0
    added = 0
    for i, name in enumerate(EXAM_SCOPES, 1):
        if name not in have:
            db.add(DictItem(category=DICT_SCOPE, name=name, sort_order=top + 100 + i, is_active=True))
            added += 1
    return added


def seed_literacy(db) -> int:
    """库里没有的测评题补进去，返回新增几道。调用方负责 commit。"""
    from sqlalchemy import select

    from ..models import Option, Question
    from ..siteconfig import site
    from .difficulty import estimate
    from .importer import stem_hash

    have = set(db.scalars(select(Question.stem_hash)).all())
    added = []
    for item in bank():
        h = stem_hash(item["stem"])
        if h in have:
            continue
        q = Question(
            type=item["type"], stem=item["stem"], stem_hash=h, answer=item["answer"],
            scope=item["scope"], source=SOURCE if item.get("verified") else SOURCE_UNVERIFIED,
            difficulty=estimate(item["type"], item["stem"], item["scope"], len(item["options"])),
        )
        opts = item["options"]
        if item["type"] == "判断题":
            # 判断题在答题界面上是「A 正确 / B 错误」两个选项，和导入、手工新增的判断题一样
            opts = [{"label": a, "content": b} for a, b in site.import_.judge_options]
        for i, o in enumerate(opts):
            q.options.append(Option(label=o["label"], content=o["content"], sort_order=i))
        db.add(q)
        have.add(h)
        added.append(q)
    if added:
        db.flush()
        for q in added:
            q.code = f"T{q.id:04d}"
    return len(added)


def split_scopes(scopes: list[str] | None) -> tuple[list[str], str | None]:
    """组卷时选的知识范围 → (普通范围, 测评范围)。

    混选（测评 + 别的、七年级 + 八年级）抛 ValueError，说人话。
    """
    scopes = [s for s in (scopes or []) if s]
    exam = [s for s in scopes if is_exam_scope(s)]
    if not exam:
        return scopes, None
    if len(exam) > 1:
        raise ValueError("七年级、八年级的测评题不能放在同一张卷子里，只能选一个年级")
    if len(scopes) > 1:
        raise ValueError("人工智能通识教育测评题和其他知识范围互斥，选了它就不能再选别的范围")
    return [], exam[0]
