"""服务器（MySQL）和机房版（SQLite）互相导数据：导得过去、一样不少。

两边导出导入走的是同一段代码（tools/export_data.py、import_data.py），所以这里
在 SQLite 上把整条路走一遍。MySQL 那一侧的差异（VARCHAR 超长、TEXT 64 KB、
大小写不敏感的唯一键）靠 import_data 的体检拦住，体检本身的判断在下面单测。

真 MySQL 上的整库往返（机房版 4914 行 + 106 张图 → MySQL → 再导回 SQLite，逐列比对
一致）做过一遍，记在 docs/更新日志/2.9.0.md。
"""

import io
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from tools import uploads_archive  # noqa: E402


def _run(url, upload, *args):
    env = dict(os.environ, DATABASE_URL=url, UPLOAD_DIR=str(upload),
               PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return subprocess.run([sys.executable, *args], cwd=BACKEND, env=env,
                          capture_output=True, text=True, encoding="utf-8")


def _db(tmp_path, name):
    url = "sqlite:///" + (tmp_path / name).as_posix()
    got = _run(url, tmp_path / "unused", "-m", "alembic", "upgrade", "head")
    assert got.returncode == 0, got.stdout + got.stderr
    return url


def _rows(url, sql):
    from sqlalchemy import text
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return conn.execute(text(sql)).fetchall()
    finally:
        engine.dispose()


# ================================================================ 配图包
def test_配图打包再还原_本机原有的一个不删(tmp_path):
    src, dst = tmp_path / "源", tmp_path / "目标"
    (src / "images").mkdir(parents=True)
    (src / "images" / "题目图.png").write_bytes(b"png-1")
    (src / "imports").mkdir()
    (src / "imports" / "题库.xlsx").write_bytes(b"xlsx")
    (dst / "images").mkdir(parents=True)
    (dst / "images" / "目标上原有的.png").write_bytes(b"keep")
    (dst / "images" / "题目图.png").write_bytes(b"old")

    pack = tmp_path / "uploads.tar.gz"
    assert uploads_archive.pack(str(src), str(pack)) == (2, 9)
    names = tarfile.open(pack).getnames()
    assert "uploads/images/题目图.png" in names, "要和服务器 tar czf -C data uploads 的布局一样"

    assert uploads_archive.plan(str(pack), str(dst)) == {"新增": 1, "相同": 0, "覆盖": 1, "保留": 1}
    assert uploads_archive.unpack(str(pack), str(dst)) == 2
    assert (dst / "images" / "题目图.png").read_bytes() == b"png-1"
    assert (dst / "imports" / "题库.xlsx").read_bytes() == b"xlsx"
    assert (dst / "images" / "目标上原有的.png").read_bytes() == b"keep", "本机原有的不能删"
    assert uploads_archive.unpack(str(pack), str(dst)) == 0, "内容相同的跳过"


@pytest.mark.parametrize("prefix", ["", "uploads/"])
def test_老版本机房版的zip也认(tmp_path, prefix):
    """老机房版自己打的是 uploads.zip，成员名不带 uploads/ 前缀。"""
    z = tmp_path / "uploads.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr(prefix + "images/老图.jpg", b"jpg")
    assert uploads_archive.find(str(tmp_path)) == str(z)
    dst = tmp_path / "目标"
    uploads_archive.unpack(str(z), str(dst))
    assert (dst / "images" / "老图.jpg").read_bytes() == b"jpg"


def test_包里的危险路径一律跳过(tmp_path):
    pack = tmp_path / "uploads.tar.gz"
    with tarfile.open(pack, "w:gz") as tar:
        for name in ("uploads/../../逃出去.txt", "/etc/绝对路径.txt", "uploads/C:/盘符.txt",
                     "uploads/images/正常.png"):
            data = b"x"
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    dst = tmp_path / "目标"
    uploads_archive.unpack(str(pack), str(dst))
    got = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert got == ["uploads.tar.gz", "目标/images/正常.png"], got


# ================================================================ 整库往返
def test_导出再导入_表和配图一样不少(tmp_path):
    """一台机器导出、另一台导入：行、列、配图都在；目标上原有的配图不删；
    目标上有、备份里没有的行，试算时要明明白白报出来"会被清掉"。"""
    a = _db(tmp_path, "甲.db")
    b = _db(tmp_path, "乙.db")
    up_a, up_b = tmp_path / "甲uploads", tmp_path / "乙uploads"
    (up_a / "images").mkdir(parents=True)
    (up_a / "images" / "q1.png").write_bytes(b"q1")
    (up_b / "images").mkdir(parents=True)
    (up_b / "images" / "乙自己的.png").write_bytes(b"b")

    from sqlalchemy import text
    for url, rows in ((a, [(1, "七年级", "1班"), (2, "七年级", "2班")]), (b, [(9, "九年级", "9班")])):
        engine = create_engine(url)
        with engine.begin() as conn:
            for rid, grade, name in rows:
                conn.execute(text("INSERT INTO classes (id, grade, name, is_active, created_at) "
                                  "VALUES (:i, :g, :n, 1, '2026-09-23 08:10:00')"),
                             {"i": rid, "g": grade, "n": name})
        engine.dispose()

    out = tmp_path / "导出"
    got = _run(a, up_a, "-m", "tools.export_data", str(out))
    assert got.returncode == 0, got.stdout + got.stderr
    meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
    assert meta["配图"]["文件数"] == 1 and (out / "uploads.tar.gz").is_file()

    dry = _run(b, up_b, "-m", "tools.import_data", str(out))
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert "会被清掉" in dry.stdout and "classes" in dry.stdout, "乙那个 9 班导完就没了，得说"
    assert not (up_b / "images" / "q1.png").exists(), "试算不能动文件"

    got = _run(b, up_b, "-m", "tools.import_data", str(out), "--write")
    assert got.returncode == 0, got.stdout + got.stderr
    assert _rows(b, "SELECT id, name, created_at FROM classes ORDER BY id") == [
        (1, "1班", "2026-09-23 08:10:00.000000"), (2, "2班", "2026-09-23 08:10:00.000000")]
    assert (up_b / "images" / "q1.png").read_bytes() == b"q1", "配图要跟着过来"
    assert (up_b / "images" / "乙自己的.png").exists(), "目标上原有的配图不删"


def test_体检不过就一个字都不写(tmp_path):
    """时间看不懂、主键重复：原来一个悄悄变成空，一个让整批回滚还只报第一条。"""
    a = _db(tmp_path, "甲.db")
    b = _db(tmp_path, "乙.db")
    out = tmp_path / "导出"
    assert _run(a, tmp_path / "u", "-m", "tools.export_data", str(out)).returncode == 0
    (out / "tables" / "classes.jsonl").write_text(
        json.dumps({"id": 1, "grade": "七年级", "name": "1班", "owner_id": None,
                    "is_active": True, "created_at": "昨天下午"}, ensure_ascii=False) + "\n"
        + json.dumps({"id": 1, "grade": "七年级", "name": "2班", "owner_id": None,
                      "is_active": True, "created_at": "2026-09-23 08:00:00"}, ensure_ascii=False)
        + "\n", encoding="utf-8")
    before = _rows(b, "SELECT COUNT(*) FROM users")[0][0]

    got = _run(b, tmp_path / "u", "-m", "tools.import_data", str(out), "--write")
    assert got.returncode == 2, got.stdout + got.stderr
    assert "昨天下午" in got.stdout and "撞了主键" in got.stdout
    assert "一个字都没写" in got.stdout
    assert _rows(b, "SELECT COUNT(*) FROM users")[0][0] == before, "别的表也不能动"


# ================================================================ MySQL 的规矩
def test_按服务器上的列类型算容量():
    from sqlalchemy.dialects import mysql
    from tools.import_data import capacity
    assert capacity(mysql.VARCHAR(32)) == ("字", 32)
    assert capacity(mysql.TEXT()) == ("字节", 65535)
    assert capacity(mysql.MEDIUMTEXT()) == ("字节", 16777215)
    assert capacity(mysql.LONGTEXT()) is None
    assert capacity(mysql.INTEGER()) is None


def test_MySQL眼里的同一个值():
    """utf8mb4_unicode_ci：不分大小写、不分全角半角、不管结尾空格。"""
    from tools.import_data import fold
    assert fold("Admin") == fold("admin ") == fold("ＡＤＭＩＮ")
    assert fold("admin") != fold(" admin"), "开头的空格是算数的"


def test_时间截到秒_MySQL不会把午夜前的四舍五入到第二天():
    from sqlalchemy import Column, DateTime
    from tools.import_data import coerce
    col = Column("t", DateTime)
    assert coerce(col, "2026-09-23 23:59:59.700000", is_mysql=True) == datetime(2026, 9, 23, 23, 59, 59)
    assert coerce(col, "2026-09-23T08:00:00+08:00").tzinfo is None
    assert coerce(col, "看不懂") is None


# ================================================================ 时间
def test_建记录的时间是本地时间精确到秒_不是UTC(tmp_path):
    """SQLite 的 CURRENT_TIMESTAMP 是 UTC，MySQL 的 NOW() 是北京时间 —— 以前机房版
    建的每一行都比服务器早 8 小时。现在时间由程序给。"""
    from app.models import Base, SchoolClass

    engine = create_engine("sqlite:///" + (tmp_path / "t.db").as_posix())
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        row = SchoolClass(grade="七年级", name="1班")
        db.add(row)
        db.commit()
        got = db.scalar(select(SchoolClass.created_at))
    engine.dispose()
    assert got.microsecond == 0
    assert abs((got - datetime.now()).total_seconds()) < 120, (
        f"建记录的时间 {got} 和本地时间 {datetime.now()} 对不上 —— 是不是又成了 UTC？")
