"""按卷面结构组卷：六个大题依次抽题，再把每个大题的分摊到题上。

和「按题型自由组卷」的区别：大题**不等于**题型。「互联网原理与创新」里
既有选择题又有操作题，「操作题」大题里三道题的知识范围还是钉死的
（Windows → WPS → 人工智能）。所以一个大题由若干 slot 拼成，
每个 slot 说清楚"从哪些知识范围抽几道什么题型"。

两个容易出错的地方，这里各解决一次：

1. **抢题**。「选择题」大题要 30 道不限范围的选择题，「物联网实践与探索」
   要 3 道物联网选择题。如果按卷面顺序抽，前者会先把物联网的选择题抽走，
   后者就凑不齐。所以**先抽限定了知识范围的 slot，再抽不限范围的**，
   两轮都从同一个"已用过"集合里排除，一道题不会在一张卷子上出现两次。

2. **分数对不上**。分数按难度分摊，但除不尽是常态。用最大余数法保证
   每个大题的分**精确**等于配置值，卷面总分就精确等于各大题之和。
"""

import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Question
from ..siteconfig import PaperSectionConf, site
from .sampler import pick

# 主观题在同一个大题里的分数权重。乘 2 只是让它排在前面，
# 真正保证"操作题分最高"的是后面的 _lift_manual() 修正。
MANUAL_WEIGHT = 2.0


def manual_types() -> set[str]:
    return set(site.exam.manual_types)


def is_long_or_image(q: Question) -> bool:
    """算不算"长题目或带图片的题"。"""
    if q.image_url:
        return True
    return len("".join((q.stem or "").split())) >= site.paper.long_stem_chars


# ---------------------------------------------------------------- 抽题


def _slot_pool(
    db: Session, slot, *, scopes_filter: list[str] | None, require_answer: bool
) -> list[Question]:
    stmt = select(Question).where(
        Question.is_deleted.is_(False), Question.type == slot.type
    )
    wanted = slot.scopes or scopes_filter
    if wanted:
        stmt = stmt.where(Question.scope.in_(wanted))
    pool = list(db.scalars(stmt))

    # 客观题**一律**要求有答案，不看界面上那个勾：没答案的客观题占着分却
    # 永远判不了，学生怎么答都拿不到这几分，卷面总分就成了拿不到的数。
    # 主观题本来就靠人看，没写答案要点也能出。
    if require_answer or slot.type not in manual_types():
        pool = [q for q in pool if (q.answer or "").strip()]
    return pool


def _fill_slot(
    pool: list[Question],
    slot,
    used: set[int],
    scope_order: list[str],
    rnd: random.Random,
    use_pinned: bool,
) -> list[Question]:
    """抽满一个 slot。prefer 只是排序偏好，抽不够时用普通题补齐，不会空着。"""
    avail = [q for q in pool if q.id not in used]
    if slot.prefer != "long_or_image":
        return pick(avail, slot.count, scope_order, rnd, use_pinned=use_pinned)

    first = [q for q in avail if is_long_or_image(q)]
    chosen = pick(first, slot.count, scope_order, rnd, use_pinned=use_pinned)
    if len(chosen) < slot.count:
        taken = {q.id for q in chosen}
        rest = [q for q in avail if q.id not in taken and not is_long_or_image(q)]
        chosen += pick(rest, slot.count - len(chosen), scope_order, rnd, use_pinned=use_pinned)
    return chosen


def pick_sections(
    db: Session,
    sections: list[PaperSectionConf],
    *,
    counts: dict[str, int] | None,
    scope_order: list[str],
    scopes: list[str] | None,
    require_answer: bool,
    use_pinned: bool,
    rnd: random.Random,
) -> tuple[list[dict], list[str]]:
    """按卷面结构抽题，返回 ([{name, score, items:[Question], ...}], 警告)。

    counts 是界面上改过的题量，键是 "大题名/第几个slot"（见 slot_key）；
    没传就用配置里的默认值。
    """
    counts = counts or {}
    warnings: list[str] = []
    used: set[int] = set()
    picked: dict[str, list[Question]] = {}

    jobs = []
    for si, sec in enumerate(sections):
        for li, slot in enumerate(sec.slots):
            want = counts.get(slot_key(sec, li))
            want = slot.count if want is None else max(0, int(want))
            if want:
                jobs.append((si, li, sec, slot, want))

    # 限定了知识范围的先抽 —— 它们的候选池最小，让它们先挑
    jobs.sort(key=lambda j: (0 if j[3].scopes else 1, j[0], j[1]))

    for si, li, sec, slot, want in jobs:
        wanted_slot = slot.model_copy(update={"count": want})
        pool = _slot_pool(db, wanted_slot, scopes_filter=scopes, require_answer=require_answer)
        chosen = _fill_slot(pool, wanted_slot, used, scope_order, rnd, use_pinned)
        used.update(q.id for q in chosen)
        picked[f"{si}/{li}"] = chosen

        if len(chosen) < want:
            where = f"「{sec.name}」" + (f"·{slot.label}" if slot.label else "")
            scope_hint = f"（{'、'.join(slot.scopes)}）" if slot.scopes else ""
            warnings.append(
                f"{where}要 {want} 道{slot.type}{scope_hint}，题库里只凑出 {len(chosen)} 道"
            )

    out = []
    for si, sec in enumerate(sections):
        items: list[Question] = []
        for li in range(len(sec.slots)):
            items += picked.get(f"{si}/{li}", [])
        if not items:
            continue
        out.append({"name": sec.name, "score": sec.score, "conf": sec, "items": items})

    missing = [s.name for s in sections if s.score and s.name not in {g["name"] for g in out}]
    if missing:
        warnings.append(
            "「" + "」「".join(missing) + "」一道题都没抽到，这几个大题的分数没有落处，"
            "卷面总分会少掉它们"
        )
    return out, warnings


def slot_key(sec, li: int) -> str:
    """界面上改题量用的键。用大题名而不是下标，改了 config.yaml 的顺序也对得上。"""
    return f"{sec.name}/{li}"


# ---------------------------------------------------------------- 赋分


def _largest_remainder(weights: list[float], total: int) -> list[int]:
    """按权重把 total 分成整数，和**精确**等于 total。余数大的先拿。"""
    n = len(weights)
    if n == 0 or total <= 0:
        return [0] * n
    s = sum(weights)
    if s <= 0:
        weights = [1.0] * n
        s = float(n)

    exact = [total * w / s for w in weights]
    out = [int(x) for x in exact]
    left = total - sum(out)
    # 余数一样时给权重高的（也就是难度高的），再一样就按原顺序
    order = sorted(range(n), key=lambda i: (-(exact[i] - out[i]), -weights[i], i))
    for i in order[:left]:
        out[i] += 1
    return out


def _lift_manual(scores: list[int], manual: list[bool]) -> list[int]:
    """让每道主观题的分都**严格高于**本大题里任何一道客观题。

    这是用户定的第一原则：同一个大题里操作题的分最高。按难度分摊出来的
    结果不一定满足（难度是 1~5，主观客观可能撞上），所以这里做一次搬运：
    从分最高的客观题上挪 1 分给分最低的主观题，直到满足或挪不动为止。

    挪不动的情形（分太少、客观题都只剩 1 分）就保持原样 —— 宁可分配得
    略不理想，也不能凭空多出分来让大题总分对不上。
    """
    if not any(manual) or all(manual):
        return scores

    scores = list(scores)
    budget = sum(scores) + 1  # 每轮至少搬走 1 分，循环必然结束
    for _ in range(budget):
        mans = [i for i, m in enumerate(manual) if m]
        objs = [i for i, m in enumerate(manual) if not m]
        lo = min(mans, key=lambda i: (scores[i], i))
        hi = max(objs, key=lambda i: (scores[i], -i))
        if scores[lo] > scores[hi]:
            break
        if scores[hi] <= 1:      # 客观题不能扣成 0 分
            break
        scores[hi] -= 1
        scores[lo] += 1
    return scores


def allocate_scores(items: list[dict], total: int, *, by_difficulty: bool = True) -> list[int]:
    """把一个大题的 total 分摊到它的题上，返回每道题的分（整数，和恰好等于 total）。

    - by_difficulty=True：权重取难度（1~5），主观题再乘 MANUAL_WEIGHT；
    - by_difficulty=False：等分，除不尽的零头给难度高的题。

    先给每道题保底 1 分再分剩下的，避免出现"这道题 0 分"。分数不够保底
    （题比分多）时退回纯比例分配，此时确实会有 0 分的题，卷面上会显示出来。
    """
    n = len(items)
    if n == 0:
        return []
    if total <= 0:
        return [0] * n

    mt = manual_types()
    manual = [it.get("type") in mt for it in items]
    weights = [
        (float(it.get("difficulty") or 3) if by_difficulty else 1.0)
        * (MANUAL_WEIGHT if m else 1.0)
        for it, m in zip(items, manual)
    ]

    if total >= n:
        extra = _largest_remainder(weights, total - n)
        scores = [1 + e for e in extra]
    else:
        scores = _largest_remainder(weights, total)

    return _lift_manual(scores, manual)
