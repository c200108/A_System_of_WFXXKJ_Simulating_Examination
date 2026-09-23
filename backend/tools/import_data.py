"""把 export_data.py 导出的那份数据，灌进**本机现有**的数据库。

    python -m tools.import_data /data-export            # 试算，不写库
    python -m tools.import_data /data-export --write    # 真的导

服务器（data-import.sh，MySQL）和机房版（工具/数据搬家.py，SQLite）导入都走这里。
两边的备份格式一样，所以**服务器的备份能导进机房版，机房版的也能导进服务器**。

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

这是"还原"不是"合并"：目标表里原有的行会被删掉，换成备份里的。试算时会**逐表
报出本机有、备份里没有的行数** —— 那些行导完就没了（导入脚本事先存的回滚点里有）。

## 写之前先体检：SQLite 装得下的，MySQL 不一定装得下

机房版是 SQLite，服务器是 MySQL，同一份数据两边的规矩不一样：

| | SQLite | MySQL |
|---|---|---|
| VARCHAR(64) 存 70 个字 | 照存 | 拒绝（1406 Data too long） |
| TEXT 存 70 KB | 照存 | 拒绝（TEXT 只有 64 KB，0014 起已全改 LONGTEXT） |
| 唯一键 "Abc" 和 "abc " | 两行 | 撞车（utf8mb4_unicode_ci 不分大小写、不管结尾空格） |

撞上哪一条，MySQL 都会让整个事务回滚 —— 一行都进不去，报错还只说第一条。所以
**写库之前逐行体检**，有问题就把每一处（哪张表、哪一行、哪一列、超了多少）列出来，
一个字都不写。去导出的那一边改好再导，而不是在这边偷偷截断 —— 截断就是丢数据。

时间列解析不出来的也算体检不过：原来是悄悄变成空的。

## 时间

MySQL 的 DATETIME 只到秒，还是四舍五入的（23:59:59.6 会进到第二天）。
导进 MySQL 时把秒以下直接截掉。

## 配图

表导完之后还原 uploads（见 tools/uploads_archive.py）：备份里有的写进去，
本机有、备份里没有的一个不删。

## 外键

整个过程关掉外键检查再打开，所以表的先后顺序不影响结果 —— 不然
exam_submissions 先于 exams 导入就会失败。
"""

import json
import os
import sys
import unicodedata
from datetime import datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, inspect, select

from app.config import settings
from app.database import engine
from app.models import Base
from tools import uploads_archive

# app_meta 记的是这台机器自己的状态（时钟校正挪到了哪），不能被别处的备份盖掉
SKIP_TABLES = {"alembic_version", "app_meta"}
SHOW = 20          # 每类问题最多列多少条，其余只报个数


def parse_dt(value):
    """JSON 里的时间字符串 → datetime（本地时间、不带时区）。解析不出来返回 None。"""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:                               # 带时区的（+08:00）换成本机本地时间
        got = datetime.fromisoformat(text)
    except ValueError:
        return None
    return got.astimezone().replace(tzinfo=None) if got.tzinfo else got


def coerce(column, value, is_mysql=False):
    """按目标列的类型把 JSON 里的值转回去。

    JSON 只有字符串/数字/布尔/null，而库里有 DateTime、Date、Boolean。
    不转的话 SQLite 会原样存字符串，以后按时间排序就乱了。
    """
    if value is None:
        return None
    t = column.type
    if isinstance(t, DateTime):
        dt = parse_dt(value)
        if dt is not None and is_mysql:
            dt = dt.replace(microsecond=0)       # MySQL 会四舍五入，不如先截掉
        return dt
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


# ---------------------------------------------------------------- 体检
def capacity(coltype):
    """目标库这一列最多装多少：("字", n) / ("字节", n)；没有实际上限返回 None。只看 MySQL。"""
    name = type(coltype).__name__.upper()
    if name in ("VARCHAR", "CHAR", "NVARCHAR", "NCHAR") and getattr(coltype, "length", None):
        return "字", coltype.length
    return {"TINYTEXT": ("字节", 255), "TEXT": ("字节", 65535),
            "MEDIUMTEXT": ("字节", 16777215)}.get(name)


def fold(value):
    """utf8mb4_unicode_ci 眼里的"同一个值"：不分大小写、不分全角半角、不管结尾空格。"""
    return unicodedata.normalize("NFKC", str(value)).casefold().rstrip(" ")


def unique_keys(insp, table_name):
    """目标库这张表上的唯一约束（含主键），每个是一组列名。"""
    keys = []
    pk = insp.get_pk_constraint(table_name).get("constrained_columns") or []
    if pk:
        keys.append(("主键", tuple(pk)))
    for u in insp.get_unique_constraints(table_name):
        keys.append((u.get("name") or "唯一键", tuple(u["column_names"])))
    for ix in insp.get_indexes(table_name):
        if ix.get("unique"):
            keys.append((ix.get("name") or "唯一索引", tuple(ix["column_names"])))
    seen, out = set(), []
    for name, cols in keys:
        if cols not in seen:
            seen.add(cols)
            out.append((name, cols))
    return out


def inspect_table(table, path, use, insp, is_mysql, target_ids):
    """逐行过一遍备份里的这张表。返回 (行数, 问题列表, 本机会被清掉的行数)。"""
    problems = []
    db_types = {c["name"]: c["type"] for c in insp.get_columns(table.name)}
    caps = {c: capacity(db_types[c]) for c in use if c in db_types} if is_mysql else {}
    time_cols = [c for c in use if isinstance(table.columns[c].type, (DateTime, Date))]
    keys = [(name, cols) for name, cols in unique_keys(insp, table.name)
            if all(c in use for c in cols)]
    seen = {cols: {} for _name, cols in keys}      # 折算后的键值 → 第一次出现时的 id
    ids = set()
    n = 0
    for row in read_rows(path):
        n += 1
        rid = row.get("id", f"第{n}行")
        ids.add(row.get("id"))
        for c in time_cols:
            v = row.get(c)
            if isinstance(v, str) and v.strip() and parse_dt(v) is None:
                problems.append(f"{table.name}.{c}（id={rid}）时间看不懂：{v!r}")
        for c, cap in caps.items():
            v = row.get(c)
            if not isinstance(v, str) or cap is None:
                continue
            unit, limit = cap
            got = len(v) if unit == "字" else len(v.encode("utf-8"))
            if got > limit:
                problems.append(f"{table.name}.{c}（id={rid}）{got} {unit}，超过服务器上限 {limit} {unit}")
        for name, cols in keys:
            vals = [row.get(c) for c in cols]
            if any(v is None for v in vals):
                continue                          # 唯一键里 NULL 不算撞
            k = tuple(fold(v) if is_mysql and isinstance(v, str) else v for v in vals)
            if k not in seen[cols]:
                seen[cols][k] = rid
            else:
                first = seen[cols][k]
                shown = "、".join(f"{c}={row.get(c)!r}" for c in cols)
                why = "（MySQL 不分大小写、不管结尾空格）" if is_mysql else ""
                problems.append(f"{table.name} 的 id={first} 和 id={rid} 撞了{name}：{shown}{why}")
    gone = len(target_ids - ids) if target_ids is not None else 0
    return n, problems, gone


def main() -> int:
    src = next((a for a in sys.argv[1:] if not a.startswith("--")), "/data-export")
    write = "--write" in sys.argv
    tables_dir = os.path.join(src, "tables")

    if not os.path.isdir(tables_dir):
        raise SystemExit(f"[导入] {tables_dir} 不存在，这个目录不像是 export_data.py 导出的")

    meta = {}
    meta_path = os.path.join(src, "meta.json")
    if os.path.isfile(meta_path):
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        print(f"[导入] 备份来自 {meta.get('导出时间', '?')}"
              f"（{meta.get('来源数据库') or '?'}），迁移版本 {meta.get('迁移版本') or '?'}，"
              f"{meta.get('表数量', '?')} 张表 / {meta.get('总行数', '?')} 行")

    is_mysql = engine.dialect.name == "mysql"
    insp = inspect(engine)
    present = set(insp.get_table_names())
    by_name = {t.name: t for t in Base.metadata.sorted_tables}
    # 库里**实际**有哪些列。不能只看模型 —— 迁移没跑全的时候两者会不一样，
    # 那时候按模型去插会撞上 "Unknown column"，报错还指不到病根。
    db_cols = {name: {c["name"] for c in insp.get_columns(name)} for name in present}

    plans = []
    notes: list = []
    problems: list = []
    gone: dict = {}

    with engine.connect() as conn:
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
            target_ids = None
            if "id" in db_cols.get(table_name, set()):
                target_ids = {r[0] for r in conn.execute(select(table.c.id))}
            if first is None:
                plans.append((table, path, [], [], 0))
                if target_ids:
                    gone[table_name] = len(target_ids)
                continue

            # 三方取交集：模型认得、库里真有、备份里带着，三者都满足才导
            have = set(table.columns.keys()) & db_cols.get(table_name, set())
            backup_cols = list(first.keys())
            use = [c for c in backup_cols if c in have]
            dropped = [c for c in backup_cols if c not in have]
            added = [c for c in have if c not in backup_cols]

            missing = set(table.columns.keys()) - db_cols.get(table_name, set())
            if missing:
                notes.append(
                    f"「{table_name}」库里缺这些列：{'、'.join(sorted(missing))}"
                    " —— 迁移没跑全？先 alembic upgrade head 再导"
                )
            if dropped:
                notes.append(f"「{table_name}」备份里的这些列本系统已删除，不导入：{'、'.join(dropped)}")
            if added:
                notes.append(f"「{table_name}」本系统新增的列备份里没有，用默认值：{'、'.join(added)}")

            n, bad, lost = inspect_table(table, path, use, insp, is_mysql, target_ids)
            problems += bad
            if lost:
                gone[table_name] = lost
            plans.append((table, path, use, dropped, n))

    print("\n[导入] 打算这样导：")
    total = 0
    for table, _path, use, _dropped, n in plans:
        print(f"  {table.name:<20} {n:>7} 行   {len(use)} 列")
        total += n
    print(f"  合计 {total} 行")

    if notes:
        print("\n[导入] 版本差异（不影响继续，但请过目）：")
        for line in notes:
            print(f"  · {line}")

    if gone:
        print("\n[导入] 本机有、备份里没有的行 —— **导入后会被清掉**（回滚点里有）：")
        for name, lost in sorted(gone.items()):
            print(f"  · {name:<20} {lost:>6} 行")
        print("  这是「还原」：导完本机就和备份一模一样。上面这些行要留着的话，"
              "先在本机导出一份，别直接导。")

    archive = uploads_archive.find(src)
    if archive:
        got = uploads_archive.plan(archive, settings.upload_dir)
        print(f"\n[导入] 配图（{os.path.basename(archive)}）：新增 {got['新增']}、"
              f"内容相同 {got['相同']}、覆盖 {got['覆盖']}；本机另有 {got['保留']} 个"
              "备份里没有的文件，一个不删")
    else:
        print("\n[导入] 备份里没有配图包（uploads.tar.gz / uploads.zip），配图不动")

    if problems:
        target = "服务器（MySQL）" if is_mysql else "本机"
        print(f"\n[导入] **体检没过：{len(problems)} 处数据{target}装不下或有冲突**，一个字都没写：")
        for line in problems[:SHOW]:
            print(f"  × {line}")
        if len(problems) > SHOW:
            print(f"  …… 还有 {len(problems) - SHOW} 处")
        print("  去导出的那一边把这些改好（改短、改掉重复的），重新导出再导。"
              "这边不替你截断 —— 截断就是丢数据。")
        return 2

    if not write:
        print("\n[导入] 试算而已，没有写库。确认没问题就加 --write 再跑一次。")
        return 0

    done: dict = {}

    with engine.begin() as conn:
        # 关外键：不然 exam_submissions 先于 exams 导入就会失败。
        # 放在同一个事务里，出错整体回滚，不会留下删了一半的库。
        if is_mysql:
            conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
        else:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")

        for table, path, use, _dropped, _n in plans:
            conn.execute(table.delete())
            if not use:
                done[table.name] = 0
                continue

            cols = [table.columns[c] for c in use]
            batch = []
            written = 0
            for row in read_rows(path):
                batch.append({c.name: coerce(c, row.get(c.name), is_mysql) for c in cols})
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
    for table, _path, _use, _dropped, n in plans:
        got = done.get(table.name, 0)
        mark = "=" if got == n else "≠"
        if got != n:
            bad += 1
        print(f"  {table.name:<20} {got:>7} {mark} {n}")

    if archive:
        wrote = uploads_archive.unpack(archive, settings.upload_dir)
        print(f"\n[导入] 配图已还原：写入 {wrote} 个文件（内容相同的跳过），本机原有的一个没删")

    if bad:
        print(f"\n[导入] 有 {bad} 张表行数对不上，别直接投入使用，先查清楚。")
        return 1
    print(f"\n[导入] 全部对得上，共 {sum(done.values())} 行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
