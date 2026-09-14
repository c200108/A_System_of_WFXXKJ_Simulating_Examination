"""给题库里没标过难度的题重新估一遍难度。

什么时候用：2.4.0/2.4.1 部署的全新实例，题库是从 legacy/ 那份原卷灌进去的，
而当时灌库的脚本忘了给难度，于是 331 道题全是默认值 3 —— 组卷时"按难度分摊
分值"就等于没生效，每道题分数都一样。2.4.4 修好了灌库脚本，但已经建好的库
还得跑一次这个把值补上。

    docker compose exec backend python -m tools.fix_difficulty          # 看看会改什么，不落库
    docker compose exec backend python -m tools.fix_difficulty --write  # 真的改

**默认只动难度还是 3 的题**（3 是没标过时的默认值）。老师手工调成 1/2/4/5 的
不碰 —— 人工判断优先于自动估算。确实想整库重估就加 --all，但那会覆盖掉手工
标注，想清楚再用。
"""

import argparse
import sys

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Question
from app.services.difficulty import estimate

DEFAULT_LEVEL = 3   # 没标过难度时的取值，见 models.Question.difficulty


def main() -> int:
    ap = argparse.ArgumentParser(description="重估题库难度")
    ap.add_argument("--write", action="store_true", help="真的写库；不加只看结果")
    ap.add_argument(
        "--all",
        action="store_true",
        help="整库重估，包括老师手工标过的（会覆盖人工判断，慎用）",
    )
    args = ap.parse_args()

    db = SessionLocal()
    try:
        rows = list(db.scalars(select(Question).where(Question.is_deleted.is_(False))))
        if not rows:
            print("[难度] 题库是空的，没什么可估的")
            return 0

        targets = rows if args.all else [q for q in rows if q.difficulty == DEFAULT_LEVEL]
        print(f"[难度] 题库共 {len(rows)} 道，这次处理 {len(targets)} 道"
              + ("（整库重估）" if args.all else f"（只动难度还是 {DEFAULT_LEVEL} 的）"))

        changed = 0
        spread: dict[int, int] = {}
        for q in rows:
            level = q.difficulty
            if q in targets:
                level = estimate(q.type, q.stem, q.scope, len(q.options))
                if level != q.difficulty:
                    changed += 1
                    if args.write:
                        q.difficulty = level
            spread[level] = spread.get(level, 0) + 1

        print("[难度] 估完之后的分布：")
        for lv in sorted(spread):
            print(f"        {lv} 级 {spread[lv]:5d} 道")

        if not args.write:
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
