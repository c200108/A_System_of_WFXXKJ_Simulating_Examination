# -*- coding: utf-8 -*-
"""真实文件夹的快照 —— 客户端拍，服务器判。

**结构和网页版仿真器交上来的完全一致**，所以判分器
（`backend/app/services/sim.py`）一个字都不用改 —— 它不知道、也不需要知道
这份状态是浏览器里点出来的还是从真机上拍的：

    {"fs": {"win02/会徽/冬梦.txt": {"type":"file","content":"…","readonly":true}},
     "recycle": {…}, "meta": {…}}

路径**相对考试根目录**：考场机器上考试文件夹可能在 C:\\EXAM，也可能在别处，
题目不该跟着变。
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# 只有这些扩展名才把内容读进快照。二进制读进来会把包撑大，
# 而判分要比对内容的本来也只有文本文件。
TEXT_EXT = {".txt", ".log", ".csv", ".md", ".html", ".htm", ".css", ".js",
            ".bat", ".ini", ".xml", ".py", ".json"}
MAX_TEXT = 64 * 1024
MAX_HASH = 32 * 1024 * 1024
MARK = ".exam-root"          # 铺考场时留的记号，没有它就不敢删


def norm(path) -> str:
    """统一成正斜杠、去掉结尾斜杠，和判分器的 norm_path 一个规矩。"""
    s = str(path).strip().replace("\\", "/")
    s = re.sub(r"/{2,}", "/", s).rstrip("/")
    if re.match(r"^[a-zA-Z]:", s):
        s = s[0].upper() + s[1:]
    return s


def rel_of(path: Path, root: Path) -> str:
    try:
        return norm(path.relative_to(root))
    except ValueError:
        return norm(path)


def read_text(path: Path) -> str | None:
    """把文本文件读成 str。

    记事本存出来的编码有三种：ANSI（中文机器上是 GBK，XP/Win7 的默认）、
    UTF-8（可能带 BOM）、Unicode（UTF-16LE 带 BOM），三种都得认。

    顺序不能乱，第 0 期在这里栽过一次：「一起向未来」的 GBK 是 10 个字节，
    拿 utf-16 去解**不会报错**，会安静地解出一串乱码汉字，判分于是说
    "内容里没有这几个字"。所以 utf-16 只在真有 BOM 时才用。
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if not raw:
        return ""
    if raw[:3] == b"\xef\xbb\xbf":
        return raw.decode("utf-8-sig", "replace")
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", "replace")
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def md5_of(path: Path, size: int) -> str:
    if size > MAX_HASH:
        return ""
    h = hashlib.md5()
    try:
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def win_attrs(p: Path) -> dict:
    """只读 / 隐藏。判分器认这两个键。"""
    out: dict = {}
    try:
        st = p.stat()
    except OSError:
        return out
    if os.name == "nt":
        attrs = getattr(st, "st_file_attributes", 0)
        if attrs & 0x1:
            out["readonly"] = True
        if attrs & 0x2:
            out["hidden"] = True
    elif not os.access(p, os.W_OK):
        out["readonly"] = True
    return out


def file_node(p: Path) -> dict:
    node: dict = {"type": "file"}
    try:
        st = p.stat()
        node["size"] = st.st_size
        node["mtime"] = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return node
    node.update(win_attrs(p))
    if p.suffix.lower() in TEXT_EXT and st.st_size <= MAX_TEXT:
        text = read_text(p)
        if text is not None:
            node["content"] = text
    node["md5"] = md5_of(p, st.st_size)
    return node


def snapshot(root: str | Path) -> dict:
    """遍历考试文件夹，拍一份快照。"""
    root = Path(root)
    started = time.perf_counter()
    fs: dict[str, dict] = {}
    if root.exists():
        for dirpath, dirnames, filenames in os.walk(root):
            here = Path(dirpath)
            for name in dirnames:
                p = here / name
                fs[rel_of(p, root)] = {"type": "dir", **win_attrs(p)}
            for name in filenames:
                if name == MARK:
                    continue
                p = here / name
                fs[rel_of(p, root)] = file_node(p)
    return {
        "fs": fs,
        "recycle": recycle_bin(root),
        "meta": {
            "root": norm(root),
            "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "count": len(fs),
            "seconds": round(time.perf_counter() - started, 3),
            "host": os.environ.get("COMPUTERNAME", ""),
        },
    }


# ================================================================ 回收站
def recycle_bin(root: Path) -> dict:
    """回收站里属于本次考试的东西。

    Vista 及以后：X:\\$Recycle.Bin\\<SID>\\$I******，头部记着原路径。
    **XP 的 C:\\RECYCLER\\<SID>\\INFO2 是另一种格式，没做** —— "删掉了"用
    missing（文件不在了）判就够，in_recycle 只在"要求放进回收站而不是彻底
    删除"时才用得上。
    """
    out: dict[str, dict] = {}
    if os.name != "nt":
        return out
    drive = str(root)[:2] if re.match(r"^[a-zA-Z]:", str(root)) else "C:"
    base = Path(drive + "\\$Recycle.Bin")
    if not base.exists():
        return out
    want = norm(root) + "/"
    for sid in _safe_iterdir(base):
        for item in _safe_iterdir(sid):
            if not item.name.startswith("$I"):
                continue
            info = _read_recycle_info(item)
            if info and norm(info["path"]).startswith(want):
                out[norm(info["path"])[len(want):]] = {
                    "type": "file", "size": info["size"], "deleted_at": info["at"],
                }
    return out


def _safe_iterdir(p: Path):
    try:
        return list(p.iterdir())
    except OSError:
        return []


def _read_recycle_info(path: Path):
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if len(raw) < 28:
        return None
    ver, size, filetime = struct.unpack("<qqq", raw[:24])
    if ver == 1:
        blob = raw[24:24 + 520]
    elif ver == 2:
        (n,) = struct.unpack("<i", raw[24:28])
        blob = raw[28:28 + n * 2]
    else:
        return None
    name = blob.decode("utf-16-le", "ignore").split("\x00", 1)[0]
    at = ""
    if filetime > 0:
        try:
            at = datetime.fromtimestamp(
                filetime / 10_000_000 - 11644473600, timezone.utc
            ).strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            at = ""
    return {"path": name, "size": size, "at": at}


# ================================================================ 铺考场
def rmtree_force(path: Path) -> None:
    """删整棵目录，遇到只读文件先去掉只读再删。

    实测踩到的：题目要求"把文件设为只读"，学生照做了，下一场考试重新
    布置考场时 rmtree 直接 PermissionError [WinError 5]。考场机器上这一步
    必须自愈，不能让监考老师去手工删文件夹。
    """
    def retry(func, target, _exc):
        try:
            os.chmod(target, 0o666)
            func(target)
        except OSError:
            pass

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=retry)
    else:
        shutil.rmtree(path, onerror=lambda f, t, e: retry(f, t, e))


def clear_root(root: Path, force: bool = False) -> None:
    """清空考试文件夹。**会删东西，所以有两道闸。**

    目标必须是至少两层的路径（挡住 C:\\ 这种），而且里面得有上次留下的记号
    文件，否则要 force 才肯动。考场机器上误删老师自己的文件夹，一次都不能发生。
    """
    root = Path(root)
    if len(root.resolve().parts) < 2:
        raise RuntimeError(f"拒绝操作：{root} 看起来是盘符根目录")
    if not root.exists():
        return
    if not (root / MARK).exists() and not force:
        raise RuntimeError(
            f"{root} 已经存在，而且不是考试程序建的（没有 {MARK} 记号文件）。\n"
            "确认里面没有要紧东西再重试。"
        )
    rmtree_force(root)
    if root.exists():
        raise RuntimeError(f"清不干净 {root}，可能有文件被别的程序占着")


def mark_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / MARK).write_text("考试程序建的考试文件夹，考完可以整个删掉\n", encoding="utf-8")
