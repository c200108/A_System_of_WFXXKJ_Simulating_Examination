"""给题库里没评过难度的题估一遍难度。

三种用法：

    python -m tools.fix_difficulty --auto     容器每次启动自动跑这个（见 entrypoint.sh）
    python -m tools.fix_difficulty            人工试算，看看会改什么，不写库
    python -m tools.fix_difficulty --write    人工执行，只动难度还是 3 的题

--auto 和另外两个的区别在**动手的条件**上，这一点是这个文件的关键：

    --auto 只在「全库难度是同一个值」时才动手。

为什么要这么严：老师完全可能特意把某道题标成 3。如果每次启动都把"难度是 3"的
题重估一遍，人工判断就会被自动覆盖掉 —— 这种 bug 很隐蔽，老师会以为自己没改成功。
而"全库 331 道题一个难度"不可能是人标出来的，只可能是灌库时压根没评过，
这时候重估是纯收益。正常题库必然有区分度，--auto 会原样跳过。

真出过这个问题：2.4.4 之前 tools/migrate_from_html.py 建题时漏传 difficulty，
全吃了模型默认值 3，组卷"按难度分摊分值"等于没生效。灌库脚本已经修好，
但从老库还原回来的数据仍是全 3，所以留着 --auto 兜底。
"""

import argparse
import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Question
from app.services.difficulty import estimate

DEFAULT_LEVEL = 3   # 没评过难度时的取值，见 models.Question.difficulty


def uniform_level(levels) -> int | None:
    """全库是不是同一个难度？是就返回那个值，否则返回 None。

    单独拎出来是为了能直接测 —— 这是 --auto 动不动手的唯一依据。
    """
    distinct = set(levels)
    return distinct.pop() if len(distinct) == 1 else None


def alive(db: Session) -> list[Question]:
    return list(db.scalars(select(Question).where(Question.is_deleted.is_(False))))


def backfill(db: Session, rows: list[Question]) -> int:
    """把 rows 的难度重估一遍，返回改动了几道。调用方负责 commit。"""
    changed = 0
    for q in rows:
        level = estimate(q.type, q.stem, q.scope, len(q.options))
        if level != q.difficulty:
            q.difficulty = level
            changed += 1
    return changed


def spread_of(rows: list[Question]) -> dict[int, int]:
    out: dict[int, int] = {}
    for q in rows:
        out[q.difficulty] = out.get(q.difficulty, 0) + 1
    return dict(sorted(out.items()))


def run_auto(db: Session) -> int:
    """容器启动时跑的那一支。不满足条件就原样返回，绝不啰嗦、绝不报错。"""
    rows = alive(db)
    if len(rows) < 2:
        return 0

    level = uniform_level(q.difficulty for q in rows)
    if level is None:
        return 0  # 题库已有区分度，说明评过了，不碰

    changed = backfill(db, rows)
    db.commit()
    print(f"[难度] 题库 {len(rows)} 道题难度全是 {level}，看着是没评过，已自动评好 {changed} 道")
    print(f"[难度] 现在的分布：{spread_of(rows)}")
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description="重估题库难度")
    ap.add_argument(
        "--auto",
        action="store_true",
        help="容器启动时用：只在全库难度是同一个值（= 从没评过）时才动手",
    )
    ap.add_argument("--write", action="store_true", help="真的写库；不加只看结果")
    ap.add_argument(
        "--all",
        action="store_true",
        help="整库重估，包括老师手工标过的（会覆盖人工判断，慎用）",
    )
    args = ap.parse_args()

    db = SessionLocal()
    try:
        if args.auto:
            run_auto(db)
            return 0

        rows = alive(db)
        if not rows:
            print("[难度] 题库是空的，没什么可估的")
            return 0

        targets = rows if args.all else [q for q in rows if q.difficulty == DEFAULT_LEVEL]
        print(f"[难度] 题库共 {len(rows)} 道，这次处理 {len(targets)} 道"
              + ("（整库重估）" if args.all else f"（只动难度还是 {DEFAULT_LEVEL} 的）"))

        before = {q.id: q.difficulty for q in rows}
        changed = backfill(db, targets)

        print("[难度] 估完之后的分布：")
        for lv, n in spread_of(rows).items():
            print(f"        {lv} 级 {n:5d} 道")

        if not args.write:
            db.rollback()  # 试算而已，把内存里改过的还原掉
            for q in rows:
                q.difficulty = before[q.id]
            print(f"\n[难度] 试算而已，没有写库。有 {changed} 道题的难度会变。")
            print("       确认没问题就加 --write 再跑一次。")
            return 0

        db.commit()
        print(f"\n[难度] 已更新 {changed} 道题。老师看着不对，随时在题库页面改。")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
