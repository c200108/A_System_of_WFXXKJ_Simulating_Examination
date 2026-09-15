"""把数据库里的数据导成一份「跟版本无关」的文件夹。

    python -m tools.export_data /输出目录

产物：每张表一个 `表名.jsonl`（一行一条记录），外加一份 `meta.json` 记着
导出时间、迁移版本、每张表有哪些列和多少行。

## 为什么不用 mysqldump

mysqldump 导出的 SQL 里带着 `DROP TABLE` + `CREATE TABLE`，还原时会把目标库的
表结构**倒退**成导出那天的样子，再指望 alembic 升回来。这有两个坑：

1. 倒退之后 `alembic_version` 也跟着退回旧版。如果新版本期间**新增过表**，
   那些表在目标库里已经存在，而 alembic 认为还没建，升级时会撞上
   "table already exists" 直接失败；
2. 表结构由导出文件决定，等于让一份旧备份去覆盖新系统的结构 —— 方向反了。

改成只导数据之后，**表结构永远以目标库为准**（全新 clone 部署出来就是最新的），
导入时按列名对齐：

- 新版本加的列 → 导出文件里没有 → 用列的默认值，老数据照样进得去（向上兼容）
- 新版本删掉的列 → 导出文件里有 → 导入时跳过并明确报出来，不会整批失败
- 新版本加的表 → 导出文件里没有 → 保持空表

## 不导口令

老版本会把 `.env` 里的口令导进 `env.secrets`，还原时按到新机器上。这是错的：
MySQL 的口令存在数据卷里、只在第一次建库时采用，新部署的卷用的是它自己那套
口令，硬按旧口令上去只会导致连不上（这个坑今天踩了一整天）。

所以这里**只导非机密的部署设置**（端口、对外地址、镜像源）到 `settings.env`，
口令一律不导 —— 新机器沿用它自己生成的那套即可。
"""

import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import inspect, select

from app.database import SessionLocal, engine
from app.models import Base

# 这张表不导：它记的是"目标库的表结构升到第几版了"，属于目标库自己的状态。
# 导过去会让目标库以为自己退回了旧版本，正是上面说的那个坑。
SKIP_TABLES = {"alembic_version"}


def encode(value):
    """把一个字段值变成能写进 JSON 的东西。"""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def alembic_version(conn) -> str:
    try:
        row = conn.exec_driver_sql("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else ""
    except Exception:
        return ""


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "/data-export"
    tables_dir = os.path.join(out_dir, "tables")
    os.makedirs(tables_dir, exist_ok=True)

    insp = inspect(engine)
    present = set(insp.get_table_names())

    db = SessionLocal()
    try:
        meta_tables = {}
        total_rows = 0

        for table in Base.metadata.sorted_tables:
            if table.name in SKIP_TABLES:
                continue
            if table.name not in present:
                # 模型里有、库里还没有（迁移没跑全），跳过并记下来
                meta_tables[table.name] = {"列": [], "行数": 0, "备注": "库里没有这张表"}
                continue

            cols = [c.name for c in table.columns]
            path = os.path.join(tables_dir, f"{table.name}.jsonl")
            n = 0
            with open(path, "w", encoding="utf-8") as f:
                # 逐行写，不一次性读进内存 —— 成绩表以后可能上万行
                for row in db.execute(select(table)).mappings():
                    f.write(
                        json.dumps(
                            {k: encode(v) for k, v in row.items()},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    n += 1
            meta_tables[table.name] = {"列": cols, "行数": n}
            total_rows += n
            print(f"  {table.name:<20} {n:>7} 行")

        with engine.connect() as conn:
            version = alembic_version(conn)

        meta = {
            "说明": (
                "本目录由 tools/export_data.py 生成，只含数据、不含表结构、不含口令。"
                "导入时表结构以目标库为准，按列名对齐 —— 所以老备份能导进新版本系统。"
            ),
            "导出时间": datetime.now().isoformat(sep=" ", timespec="seconds"),
            "来源主机": os.environ.get("HOSTNAME", ""),
            "迁移版本": version,
            "表数量": len(meta_tables),
            "总行数": total_rows,
            "表": meta_tables,
        }
        with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=1)

        print(f"\n[导出] {len(meta_tables)} 张表，共 {total_rows} 行 → {tables_dir}")
        print(f"[导出] 迁移版本 {version or '（读不到）'}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
