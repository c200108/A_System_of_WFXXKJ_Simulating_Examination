"""把整个数据库从一个地方搬到另一个地方（SQLite ↔ MySQL ↔ PostgreSQL 都行）。

典型用法——本机 SQLite 搬进 MySQL：

    cd backend
    .venv\\Scripts\\python.exe -m tools.migrate_db ^
        --from "sqlite:///./data/app.db" ^
        --to   "mysql+pymysql://exam:密码@127.0.0.1:3306/exam?charset=utf8mb4"

不写 --from 就用 backend/.env 里当前的 DATABASE_URL 作为源。

做了什么：
1. 在目标库按 models.py 建好全部表，并把 alembic 版本号标到最新
   （这样以后 alembic upgrade head 不会又从头跑一遍）；
2. 按外键依赖顺序逐表复制，**主键原样保留**——不然试卷里记的题目 id 就对不上了；
3. 复制完逐表核对行数，对不上就报错。

注意：题目配图是磁盘文件，不在数据库里。换机器时记得把
backend/data/uploads/ 整个目录一起拷过去。
"""

import argparse
import os
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, func, insert, inspect, select

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 复制时一次塞多少行，太大容易撞上 MySQL 的 max_allowed_packet
BATCH = 500


def _head_revision() -> str | None:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def _stamp(engine, revision: str) -> None:
    """把 alembic 版本号写进目标库，等价于 alembic stamp head。"""
    from sqlalchemy import Column, MetaData, String, Table

    md = MetaData()
    version = Table("alembic_version", md, Column("version_num", String(32), primary_key=True))
    md.create_all(engine)
    with engine.begin() as conn:
        conn.execute(version.delete())
        conn.execute(version.insert().values(version_num=revision))


def main() -> None:
    ap = argparse.ArgumentParser(description="把数据库整体搬到另一个数据库")
    ap.add_argument("--from", dest="src", default=None, help="源库地址，默认读 .env 的 DATABASE_URL")
    ap.add_argument("--to", dest="dst", required=True, help="目标库地址")
    ap.add_argument(
        "--overwrite", action="store_true", help="目标库已有数据时先清空（默认拒绝，防止误覆盖）"
    )
    args = ap.parse_args()

    sys.path.insert(0, BACKEND_DIR)
    from app.models import Base  # noqa: E402  必须在 sys.path 设好之后导入

    src_url = args.src
    if not src_url:
        from app.config import settings  # noqa: E402

        src_url = settings.database_url
        print(f"未指定 --from，使用 .env 里的地址：{src_url}")

    if src_url == args.dst:
        raise SystemExit("源和目标是同一个库，没什么可搬的。")

    src = create_engine(src_url)
    dst = create_engine(args.dst)

    # ---- 连通性先确认，别搬到一半才发现连不上 ----
    for name, engine in (("源", src), ("目标", dst)):
        try:
            with engine.connect():
                pass
        except Exception as exc:
            raise SystemExit(f"{name}库连不上：{exc}")

    print(f"源   : {src.url.render_as_string(hide_password=True)}")
    print(f"目标 : {dst.url.render_as_string(hide_password=True)}")

    # ---- 目标库建表 ----
    Base.metadata.create_all(dst)
    print("目标库表结构已就绪")

    # sorted_tables 已经按外键依赖排好序，父表在前
    tables = list(Base.metadata.sorted_tables)

    # ---- 目标库非空时的保护 ----
    existing = {}
    with dst.connect() as conn:
        for t in tables:
            if inspect(dst).has_table(t.name):
                n = conn.execute(select(func.count()).select_from(t)).scalar() or 0
                if n:
                    existing[t.name] = n
    if existing:
        detail = "、".join(f"{k} {v} 行" for k, v in existing.items())
        if not args.overwrite:
            raise SystemExit(
                f"目标库里已经有数据（{detail}）。\n"
                f"确认要覆盖就加 --overwrite，否则请换一个空库。"
            )
        print(f"目标库已有数据（{detail}），按 --overwrite 清空")
        with dst.begin() as conn:
            for t in reversed(tables):  # 子表先删，避免踩外键
                conn.execute(t.delete())

    # ---- 逐表复制，主键原样保留 ----
    print("\n开始复制：")
    copied = {}
    for t in tables:
        if not inspect(src).has_table(t.name):
            print(f"  {t.name:20} 源库里没有这张表，跳过")
            continue

        with src.connect() as sconn:
            rows = [dict(r) for r in sconn.execute(select(t)).mappings()]

        if rows:
            with dst.begin() as dconn:
                for i in range(0, len(rows), BATCH):
                    dconn.execute(insert(t), rows[i : i + BATCH])
        copied[t.name] = len(rows)
        print(f"  {t.name:20} {len(rows):6d} 行")

    # ---- 核对 ----
    print("\n核对行数：")
    bad = []
    with dst.connect() as conn:
        for name, n in copied.items():
            t = Base.metadata.tables[name]
            got = conn.execute(select(func.count()).select_from(t)).scalar() or 0
            flag = "OK" if got == n else "不一致"
            if got != n:
                bad.append((name, n, got))
            print(f"  {name:20} 源 {n:6d}  目标 {got:6d}  {flag}")

    if bad:
        raise SystemExit("\n有表行数对不上，请检查：" + str(bad))

    head = _head_revision()
    if head:
        _stamp(dst, head)
        print(f"\nalembic 版本号已标记为 {head}")

    print("\n迁移完成。别忘了：")
    print("  1. 把 backend/.env 里的 DATABASE_URL 改成目标库地址")
    print("  2. 换机器的话，把 backend/data/uploads/ 整个目录也拷过去（题目配图在里面）")


if __name__ == "__main__":
    main()
