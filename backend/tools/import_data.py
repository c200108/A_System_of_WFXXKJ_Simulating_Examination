"""把 export_data.py 导出的那份数据，灌进**本机现有**的数据库。

    python -m tools.import_data /data-export            # 试算，不写库
    python -m tools.import_data /data-export --write    # 真的导

## 核心约定：表结构以目标库为准

目标库是全新 clone 部署出来的，跑完 `alembic upgrade head` 就是最新结构。
导入**只管往里填数据**，一个字段都不改结构。按列名对齐：

| 情况 | 怎么处理 |
|---|---|
| 两边都有的列 | 照搬 |
| 新版本加的列（导出文件里没有） | 不写，让它取列的默认值 —— **向上兼容靠的就是这条** |
| 新版本删掉的列（导出文件里有） | 跳过这一列，并在结果里明确报出来 |
| 新版本加的表（导出文件里没有） | 保持空表 |
| 新版本删掉的表（导出文件里有） | 整表跳过，并报出来 |

所以一份旧备份导进新版本系统不会失败，也不会悄悄丢东西 —— 丢了什么一定会说。

## 导入前会清空同名表

这是"还原"不是"合并"：目标表里原有的行会被删掉，换成备份里的。
新部署出来的库里本来就只有初始化数据（管理员账号、字典、原卷题库），
清掉正是我们要的。

## 外键

整个过程关掉外键检查再打开，所以表的先后顺序不影响结果 —— 不然
exam_submissions 先于 exams 导入就会失败。
"""

import json
import os
import sys
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, inspect

from app.database import engine
from app.models import Base

SKIP_TABLES = {"alembic_version"}


def parse_dt(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def coerce(column, value):
    """按目标列的类型把 JSON 里的值转回去。

    JSON 只有字符串/数字/布尔/null，而库里有 DateTime、Date、Boolean。
    不转的话 SQLite 会原样存字符串，以后按时间排序就乱了。
    """
    if value is None:
        return None
    t = column.type
    if isinstance(t, DateTime):
        return parse_dt(value)
    if isinstance(t, Date):
        dt = parse_dt(value)
        return dt.date() if dt else None
    if isinstance(t, Boolean):
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "t", "yes")
        return bool(value)
    if isinstance(t, Integer):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return value


def read_rows(path: str):
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError as exc:
                raise SystemExit(
                    f"[导入] {os.path.basename(path)} 第 {lineno} 行不是合法 JSON：{exc}\n"
                    f"        这份备份可能损坏了，别继续导。"
                )


def main() -> int:
    src = sys.argv[1] if len(sys.argv) > 1 else "/data-export"
    write = "--write" in sys.argv
    tables_dir = os.path.join(src, "tables")

    if not os.path.isdir(tables_dir):
        raise SystemExit(f"[导入] {tables_dir} 不存在，这个目录不像是 export_data.py 导出的")

    meta = {}
    meta_path = os.path.join(src, "meta.json")
    if os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        print(f"[导入] 备份来自 {meta.get('导出时间', '?')}，"
              f"迁移版本 {meta.get('迁移版本') or '?'}，"
              f"{meta.get('表数量', '?')} 张表 / {meta.get('总行数', '?')} 行")

    insp = inspect(engine)
    present = set(insp.get_table_names())
    by_name = {t.name: t for t in Base.metadata.sorted_tables}
    # 库里**实际**有哪些列。不能只看模型 —— 迁移没跑全的时候两者会不一样，
    # 那时候按模型去插会撞上 "Unknown column"，报错还指不到病根。
    db_cols = {name: {c["name"] for c in insp.get_columns(name)} for name in present}

    plans = []
    notes: list[str] = []

    for name in sorted(os.listdir(tables_dir)):
        if not name.endswith(".jsonl"):
            continue
        table_name = name[: -len(".jsonl")]
        if table_name in SKIP_TABLES:
            continue

        table = by_name.get(table_name)
        if table is None or table_name not in present:
            notes.append(f"备份里的「{table_name}」表本系统已经没有了，整表跳过")
            continue

        path = os.path.join(tables_dir, name)
        first = next(read_rows(path), None)
        if first is None:
            plans.append((table, path, [], [], 0))
            continue

        # 三方取交集：模型认得、库里真有、备份里带着，三者都满足才导
        have = set(table.columns.keys()) & db_cols.get(table_name, set())
        backup_cols = list(first.keys())
        use = [c for c in backup_cols if c in have]
        gone = [c for c in backup_cols if c not in have]
        added = [c for c in have if c not in backup_cols]

        missing = set(table.columns.keys()) - db_cols.get(table_name, set())
        if missing:
            notes.append(
                f"「{table_name}」库里缺这些列：{'、'.join(sorted(missing))}"
                " —— 迁移没跑全？先 alembic upgrade head 再导"
            )

        if gone:
            notes.append(f"「{table_name}」备份里的这些列本系统已删除，不导入：{'、'.join(gone)}")
        if added:
            notes.append(f"「{table_name}」本系统新增的列备份里没有，用默认值：{'、'.join(added)}")

        n = sum(1 for _ in read_rows(path))
        plans.append((table, path, use, gone, n))

    print("\n[导入] 打算这样导：")
    total = 0
    for table, _path, use, _gone, n in plans:
        print(f"  {table.name:<20} {n:>7} 行   {len(use)} 列")
        total += n
    print(f"  合计 {total} 行")

    if notes:
        print("\n[导入] 版本差异（不影响继续，但请过目）：")
        for line in notes:
            print(f"  · {line}")

    if not write:
        print("\n[导入] 试算而已，没有写库。确认没问题就加 --write 再跑一次。")
        return 0

    is_mysql = engine.dialect.name == "mysql"
    done: dict[str, int] = {}

    with engine.begin() as conn:
        # 关外键：不然 exam_submissions 先于 exams 导入就会失败。
        # 放在同一个事务里，出错整体回滚，不会留下删了一半的库。
        if is_mysql:
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
        else:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")

        for table, path, use, _gone, _n in plans:
            conn.execute(table.delete())
            if not use:
                done[table.name] = 0
                continue

            cols = [table.columns[c] for c in use]
            batch = []
            written = 0
            for row in read_rows(path):
                batch.append({c.name: coerce(c, row.get(c.name)) for c in cols})
                if len(batch) >= 500:
                    conn.execute(table.insert(), batch)
                    written += len(batch)
                    batch = []
            if batch:
                conn.execute(table.insert(), batch)
                written += len(batch)
            done[table.name] = written

        if is_mysql:
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
        else:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")

    print("\n[导入] 逐表核对（左：导入了多少  右：备份里有多少）")
    bad = 0
    for table, _path, _use, _gone, n in plans:
        got = done.get(table.name, 0)
        mark = "=" if got == n else "≠"
        if got != n:
            bad += 1
        print(f"  {table.name:<20} {got:>7} {mark} {n}")

    if bad:
        print(f"\n[导入] 有 {bad} 张表行数对不上，别直接投入使用，先查清楚。")
        return 1
    print(f"\n[导入] 全部对得上，共 {sum(done.values())} 行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
