"""把当前库里的题目难度导出成对照表，存进 legacy/题目难度.json。

    python -m tools.dump_difficulty

这张表跟着代码走进 Git，部署时由灌库脚本和启动检查读它 —— 于是**新服务器上的
难度和你本地一模一样**，不依赖"重新估一遍碰巧得出同样结果"。

为什么值得单独存一份而不是每次现估：估算规则以后可能调整，老师也会手工微调
某些题的难度。存成数据之后，这些判断就固定下来了，换台机器部署不会变样。

改了难度想同步到服务器，就在本地题库页面改完，重跑一次这个命令，提交进 Git。

用题干哈希当键，不用题目 id —— id 是每个库各自的自增值，换台机器就对不上；
题干哈希（去掉所有空白后取 sha256）在哪儿算都一样，和题库查重用的是同一个值。
"""

import json
import os
import sys
from datetime import date

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Question

OUT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "legacy",
    "题目难度.json",
)


def main() -> int:
    db = SessionLocal()
    try:
        rows = list(
            db.scalars(
                select(Question)
                .where(Question.is_deleted.is_(False))
                .order_by(Question.id)
            )
        )
        if not rows:
            print("[难度表] 库里没有题，不生成 —— 免得把已有的表覆盖成空的")
            return 1

        spread: dict[int, int] = {}
        items = []
        for q in rows:
            spread[q.difficulty] = spread.get(q.difficulty, 0) + 1
            items.append(
                {
                    "hash": q.stem_hash,
                    "code": q.code or "",
                    "难度": q.difficulty,
                    # 只为了让这个文件能读、能在 diff 里认出改的是哪道题，
                    # 程序不使用这一项
                    "题干": (q.stem or "").strip().replace("\n", " ")[:28],
                }
            )

        data = {
            "说明": (
                "题目难度对照表。部署时按题干哈希查这张表给题目赋难度，"
                "查不到的才按题型和题干估算。改难度请在题库页面改，"
                "然后重跑 python -m tools.dump_difficulty 更新本文件。"
            ),
            "生成日期": date.today().isoformat(),
            "题目数": len(items),
            "难度分布": {str(k): spread[k] for k in sorted(spread)},
            "题目": items,
        }

        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
        with open(OUT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)

        print(f"[难度表] 已导出 {len(items)} 道题 → {OUT_PATH}")
        print(f"[难度表] 分布：{data['难度分布']}")
        print("[难度表] 记得把这个文件一起提交进 Git，部署时才用得上。")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
