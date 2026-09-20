"""读题库里的操作题，按题干造仿真环境和检查点。

    python backend/tools/stem_to_sim.py                 只看不写（默认）
    python backend/tools/stem_to_sim.py --apply         写进库，给题目挂上
    python backend/tools/stem_to_sim.py --id 289 297    只处理这几道
    python backend/tools/stem_to_sim.py --force         连已经配过的也重做

## 它解决什么

题库里的操作题绝大多数只有题干，没有仿真环境、没有检查点 —— 判分引擎再全也
判不了。手工一道道点，是几天的活。这些题干又是中考的标准写法，格式统一到可以
直接解析（规则在 `app/services/stem.py`）。

## 造出来的是草稿

**跑完一定要去网页后台过一眼。** 认不出来的句子会列在「待办」里，老师在网页
仿真器里补上；AI 工具题不用管，它的检查点是判分时按题干现算的。

所以默认只打印不写库，要写得显式加 `--apply` —— 往题库写东西这件事，不该是
手一滑就发生的。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select                                   # noqa: E402

from app.database import SessionLocal                           # noqa: E402
from app.models import Question, SimTask                        # noqa: E402
from app.services import stem as stem_parser                    # noqa: E402

# 仿真环境里的路径要带上盘符前缀，和老师在网页仿真器里点出来的写法一致
ROOT = "C:/EXAM"


def absolute(env: dict, checks: list) -> None:
    """把相对路径统一加上 C:/EXAM 前缀。

    检查点和环境**必须一起改**，漏一边就全判 0 分 —— 而且报错是"找不到文件"，
    最难查的那种。
    """
    fs = env.get("fs")
    if isinstance(fs, dict):
        env["fs"] = {f"{ROOT}/{k}": v for k, v in fs.items()}
    for c in checks:
        a = c.get("assert") or {}
        if "path" in a:
            a["path"] = f"{ROOT}/{a['path']}"


def main() -> int:
    ap = argparse.ArgumentParser(description="按题干给操作题造仿真环境和检查点")
    ap.add_argument("--apply", action="store_true", help="真写进库（默认只打印）")
    ap.add_argument("--id", nargs="*", type=int, default=None, help="只处理这几道题")
    ap.add_argument("--force", action="store_true", help="连已经配过仿真的也重做")
    args = ap.parse_args()

    db = SessionLocal()
    stmt = select(Question).where(Question.type == "操作题",
                                  Question.is_deleted.is_(False))
    if args.id:
        stmt = stmt.where(Question.id.in_(args.id))
    rows = db.scalars(stmt.order_by(Question.id)).all()

    made = skipped = unknown = 0
    todos: list[tuple[int, list[str]]] = []
    for q in rows:
        if q.sim_task_id and not args.force:
            skipped += 1
            continue
        got = stem_parser.parse(q.stem or "", q.scope or "")
        if not got:
            unknown += 1
            print(f"  #{q.id} [{q.scope}] 看不出是哪类操作题，留给老师")
            continue
        if got["kind"] != "ai" and not got["checks"]:
            unknown += 1
            print(f"  #{q.id} [{q.scope}] 认出是 {got['kind']} 题，但一条检查点都没造出来")
            continue

        absolute(got["env"], got["checks"])
        total = sum(c["score"] for c in got["checks"])
        print(f"  #{q.id} [{q.scope}] → {got['kind']}，"
              f"{len(got['checks'])} 个检查点 / {total} 分"
              + (f"，{len(got['todo'])} 条待办" if got["todo"] else ""))
        if got["todo"]:
            todos.append((q.id, got["todo"]))

        if args.apply:
            task = SimTask(kind=got["kind"],
                           title=(q.stem or "")[:120],
                           env_json=json.dumps(got["env"], ensure_ascii=False),
                           checks_json=json.dumps(got["checks"], ensure_ascii=False),
                           created_by=q.created_by)
            db.add(task)
            db.flush()
            q.sim_task_id = task.id
        made += 1

    if args.apply:
        db.commit()

    print(f"\n造好 {made} 道，跳过 {skipped} 道（已经配过），"
          f"{unknown} 道认不出来")
    if todos:
        print("\n这些题有认不出来的句子，请在网页后台补检查点：")
        for qid, items in todos:
            print(f"  #{qid}")
            for one in items:
                print(f"      · {one[:70]}")
    if not args.apply:
        print("\n以上只是预览。确认没问题后加 --apply 才会写进库。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
