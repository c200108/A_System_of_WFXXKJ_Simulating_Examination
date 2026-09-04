"""迁移脚本本身的测试。

为什么要单独一个文件：其余测试用 `Base.metadata.create_all()` 直接照 models.py 建表，
**根本不经过 alembic**。所以「测试全绿」并不代表迁移能跑——真出过一次：
0002 给 Text 列写了 server_default，SQLite 接受、MySQL 报 1101 拒绝，
Docker 部署一启动就卡在迁移失败的重启循环里，而测试一片绿。

这里从空库跑一遍完整的 upgrade head，再和 models.py 的表结构比对。
默认用临时 SQLite；指定 MIGRATION_TEST_DATABASE_URL 时在真实 MySQL 上跑，
方言差异才藏不住：

    set MIGRATION_TEST_DATABASE_URL=mysql+pymysql://root:密码@127.0.0.1:3306/mig_test?charset=utf8mb4
    pytest tests/test_migrations.py

注意那个库里的表每次都会被清空，绝不要指向正式库。
"""

import os
import pathlib
import sys

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

BACKEND_DIR = pathlib.Path(__file__).resolve().parent.parent

EXPECTED_TABLES = {
    "users",
    "dict_items",
    "questions",
    "options",
    "papers",
    "paper_items",
    "exams",
    "exam_submissions",
    "import_logs",
}


def _alembic_config(url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    # 直接把目标库写进 alembic 配置。不能靠改环境变量：app.config 的 settings
    # 带 lru_cache，conftest 一导入就固定成临时 SQLite 了，之后再改环境变量没用，
    # 迁移会打到那个已经建好表的库上。env.py 会优先采用这里给的地址。
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


@pytest.fixture
def blank_db(tmp_path):
    """一个全新的空库。"""
    url = os.environ.get("MIGRATION_TEST_DATABASE_URL")
    if not url:
        return "sqlite:///" + (tmp_path / "mig.db").as_posix()

    # 指向 MySQL 时先清空，否则上一轮留下的表会让 upgrade 直接撞车
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            names = inspect(conn).get_table_names()
            if names:
                conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=0")
                for t in names:
                    conn.exec_driver_sql(f"DROP TABLE IF EXISTS `{t}`")
                conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS=1")
    finally:
        engine.dispose()
    return url


def test_upgrade_head_from_scratch(blank_db):
    """空库一路升到最新版本，中途不许报错。"""
    command.upgrade(_alembic_config(blank_db), "head")

    tables = _tables(blank_db)
    missing = (EXPECTED_TABLES | {"alembic_version"}) - tables
    assert not missing, f"迁移后缺少这些表：{missing}"


def test_migrated_schema_matches_models(blank_db):
    """迁移建出来的表结构，要和 models.py 直接建的一致。

    两者一旦跑偏，就会出现「新装的实例好好的、老实例升级后出问题」这类难查的故障。
    """
    command.upgrade(_alembic_config(blank_db), "head")

    engine = create_engine(blank_db)
    try:
        insp = inspect(engine)
        migrated = {
            t: {c["name"] for c in insp.get_columns(t)}
            for t in insp.get_table_names()
            if t != "alembic_version"
        }
    finally:
        engine.dispose()

    sys.path.insert(0, str(BACKEND_DIR))
    from app.models import Base

    for table in Base.metadata.sorted_tables:
        assert table.name in migrated, f"迁移没有建出 {table.name} 表"
        model_cols = {c.name for c in table.columns}
        diff = model_cols ^ migrated[table.name]
        assert not diff, (
            f"{table.name} 表的列对不上，models.py 与迁移脚本相差 {diff}。"
            f"改了 models.py 就要补一个迁移。"
        )


def test_downgrade_runs(blank_db):
    """降级路径也要能走通，否则升级出问题时没法回退。"""
    cfg = _alembic_config(blank_db)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")

    left = _tables(blank_db) - {"alembic_version"}
    assert not left, f"降级后还残留这些表：{left}"
