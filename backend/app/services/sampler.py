"""均衡抽题：与原 HTML 的 allocate / pick 完全一致的名额轮流分配算法。

思路：每一轮把名额给「已分配最少 → 池子最大 → 知识范围顺序靠前」的那一类，
某个范围题目不够时名额自动让给其他范围。
"""

import random

from ..models import Question


def allocate(pool: list[Question], n: int, scope_order: list[str]) -> dict[str, int]:
    """把 n 个名额在各知识范围之间轮流分配，返回 {知识范围: 名额}。"""
    by_scope: dict[str, list[Question]] = {}
    for q in pool:
        by_scope.setdefault(q.scope, []).append(q)

    keys = [k for k in scope_order if by_scope.get(k)]
    # 数据库里可能出现字典表之外的历史数据，兜底放到末尾
    keys += [k for k in by_scope if k not in scope_order]

    quota = {k: 0 for k in keys}
    left = min(n, len(pool))
    while left > 0:
        avail = [k for k in keys if quota[k] < len(by_scope[k])]
        if not avail:
            break
        avail.sort(
            key=lambda k: (
                quota[k],
                -len(by_scope[k]),
                scope_order.index(k) if k in scope_order else len(scope_order),
            )
        )
        quota[avail[0]] += 1
        left -= 1
    return quota


def pick(
    pool: list[Question],
    n: int,
    scope_order: list[str],
    rnd: random.Random,
    use_pinned: bool = True,
) -> list[Question]:
    if n <= 0 or not pool:
        return []

    forced: list[Question] = []
    if use_pinned:
        forced = [q for q in pool if q.is_pinned][:n]
    forced_ids = {q.id for q in forced}
    rest = [q for q in pool if q.id not in forced_ids]

    by_scope: dict[str, list[Question]] = {}
    for q in rest:
        by_scope.setdefault(q.scope, []).append(q)

    quota = allocate(rest, n - len(forced), scope_order)
    out = list(forced)
    for k, cnt in quota.items():
        if cnt:
            bucket = by_scope[k][:]
            rnd.shuffle(bucket)
            out.extend(bucket[:cnt])

    rnd.shuffle(out)
    return out
