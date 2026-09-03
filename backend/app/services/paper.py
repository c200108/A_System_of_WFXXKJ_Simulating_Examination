"""组卷：抽题 → 打乱选项（答案跟着走）→ 按题型分大题 → 生成卷号。

打乱逻辑与原 HTML 的 makePaper() 一致：选项内容重排，标签仍按 A/B/C/D 顺序，
正确答案换成它落到的新标签。只对有 A~D 单选答案的选择题生效。
"""

import hashlib
import random
import time

from sqlalchemy.orm import Session

from ..models import Question
from ..siteconfig import site
from .sampler import pick

# 大题序号从配置读，改 config.yaml 的 paper.section_numerals 即可
CN_NUM = site.paper.section_numerals


def _seed_int(seed: str) -> int:
    return int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:8], 16)


def shuffle_options(
    options: list[tuple[str, str]], answer: str, rnd: random.Random
) -> tuple[list[tuple[str, str]], str]:
    """返回 (重排后的选项, 跟着变的答案)。不满足条件时原样返回。"""
    ans = (answer or "").strip().upper()
    if len(options) < 2 or len(ans) != 1 or ans not in "ABCD":
        return options, answer

    labels = [o[0] for o in options]
    if ans not in labels:
        return options, answer

    right_idx = labels.index(ans)
    order = list(range(len(options)))
    rnd.shuffle(order)

    new_options = [(labels[new_i], options[src_i][1]) for new_i, src_i in enumerate(order)]
    new_pos = order.index(right_idx)
    return new_options, labels[new_pos]


def build_paper(
    db: Session,
    *,
    counts: dict[str, int],
    type_order: list[str],
    scope_order: list[str],
    scopes: list[str] | None,
    require_answer: bool,
    use_pinned: bool,
    shuffle_opts: bool,
    seed: str | None,
    title: str,
    school: str,
    duration: str,
) -> dict:
    """抽题并排版成一份完整的卷子。返回可以直接给前端渲染的结构。"""
    from sqlalchemy import select

    seed_str = seed or f"{time.time()}-{random.random()}"
    rnd = random.Random(_seed_int(seed_str))

    groups: list[dict] = []
    warnings: list[str] = []

    # 按题型的固定顺序出大题，和原页面一致
    for qtype in type_order:
        want = int(counts.get(qtype, 0) or 0)
        if want <= 0:
            continue

        stmt = select(Question).where(
            Question.is_deleted.is_(False), Question.type == qtype
        )
        if scopes:
            stmt = stmt.where(Question.scope.in_(scopes))
        pool = list(db.scalars(stmt))
        if require_answer:
            pool = [q for q in pool if (q.answer or "").strip()]

        if want > len(pool):
            warnings.append(f"{qtype}最多 {len(pool)} 题，已按可用上限收窄")

        chosen = pick(pool, want, scope_order, rnd, use_pinned=use_pinned)
        if not chosen:
            continue

        items = []
        for q in chosen:
            opts = [(o.label, o.content) for o in q.options]
            ans = q.answer or ""
            if shuffle_opts and qtype == "选择题":
                opts, ans = shuffle_options(opts, ans, rnd)
            items.append(
                {
                    "id": q.id,
                    "code": q.code,
                    "type": q.type,
                    "stem": q.stem,
                    "answer": ans,
                    "scope": q.scope,
                    "source": q.source,
                    "image_url": q.image_url,
                    "options": [{"label": lb, "content": ct} for lb, ct in opts],
                }
            )
        groups.append({"type": qtype, "items": items})

    flat = [it for g in groups for it in g["items"]]
    tally: dict[str, int] = {k: 0 for k in scope_order}
    for it in flat:
        tally[it["scope"]] = tally.get(it["scope"], 0) + 1

    return {
        "title": title or "信息技术测试卷",
        "school": school,
        "duration": duration,
        "code": site.paper.code_prefix + str(_seed_int(seed_str) % 100000).zfill(5),
        "seed": seed_str,
        "total": len(flat),
        "tally": tally,
        "warnings": warnings,
        "groups": groups,
        "questions": flat,
    }


def right_letter(item: dict) -> str:
    """判断题的「正确/错误」在答题界面上对应 A / B。"""
    a = (item.get("answer") or "").strip()
    if item.get("type") == "判断题":
        return "A" if a == "正确" else "B" if a == "错误" else a
    return a
