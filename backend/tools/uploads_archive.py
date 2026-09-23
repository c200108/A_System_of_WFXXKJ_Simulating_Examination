"""题目配图、反馈图片、导入的 Excel 原件（uploads 目录）的打包与还原。

export_data.py 导出时调 pack()，import_data.py 导入时调 plan() / unpack()。
服务器（data-export.sh / data-import.sh）和机房版（工具/数据搬家.py）走的是
同一段代码，所以两边导出来的东西长一个样，谁导给谁都认得。

## 为什么要收到这里来

原来服务器那边用宿主机的 `tar` 打成 uploads.tar.gz，机房版自己用 zipfile 打成
uploads.zip，**各自只认自己那种**：服务器的备份导进机房版，报一句「备份里没有
uploads.zip，配图没还原」；机房版的备份导进服务器，干脆一声不吭 —— 表导进去了，
带图的题目一张图都没有。

## 格式

写：一律 `uploads.tar.gz`，成员名 `uploads/<相对路径>`（和服务器原来 `tar czf -C data
uploads` 打出来的一样，老脚本也解得开）。

读：`uploads.tar.gz` 和 `uploads.zip` 都认，成员名带不带 `uploads/` 前缀都认 ——
老版本机房版打的 zip 就不带。

## 还原是"合并"，不是"替换"

备份里有的文件写进去（内容不同就覆盖），**本机有、备份里没有的文件一个不删**。
文件名是上传时生成的，两台机器上同名的几乎一定是同一张图；多留几张没被引用的图
不碍事，删掉一张还被引用的图就是丢数据。
"""

import hashlib
import io
import os
import shutil
import tarfile
import zipfile

NAMES = ("uploads.tar.gz", "uploads.zip")


def find(folder):
    """备份文件夹里的配图包。没有就返回 None。"""
    for name in NAMES:
        path = os.path.join(folder, name)
        if os.path.isfile(path):
            return path
    return None


def pack(src_dir, out_file):
    """把 src_dir 整个打成 tar.gz。返回 (文件数, 字节数)。src_dir 不存在就打个空包。"""
    n = size = 0
    with tarfile.open(out_file, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        if os.path.isdir(src_dir):
            for root, dirs, files in os.walk(src_dir):
                dirs.sort()
                for name in sorted(files):
                    path = os.path.join(root, name)
                    rel = os.path.relpath(path, src_dir).replace(os.sep, "/")
                    tar.add(path, arcname="uploads/" + rel, recursive=False)
                    n += 1
                    size += os.path.getsize(path)
    return n, size


def _safe_rel(name):
    """把包里的成员名变成安全的相对路径；不安全（绝对路径、..、盘符）返回 ""。"""
    rel = name.replace("\\", "/")
    if rel.startswith("/"):
        return ""
    if rel.startswith("uploads/"):
        rel = rel[len("uploads/"):]
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." or ":" in p for p in parts):
        return ""
    return "/".join(parts)


def members(archive):
    """逐个给出包里的文件：(相对路径, 内容 bytes)。目录、链接、不安全的名字跳过。"""
    if archive.endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                rel = _safe_rel(info.filename)
                if rel:
                    yield rel, z.read(info)
        return
    with tarfile.open(archive, "r:*") as tar:
        for m in tar:
            if not m.isfile():
                continue
            rel = _safe_rel(m.name)
            if rel:
                yield rel, tar.extractfile(m).read()


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _file_digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def plan(archive, dest_dir):
    """试算：包里的文件放进 dest_dir 会怎样。返回 {"新增": n, "相同": n, "覆盖": n, "保留": n}。

    「保留」是本机有、包里没有的文件 —— 还原时一个不删。
    """
    got = {"新增": 0, "相同": 0, "覆盖": 0, "保留": 0}
    seen = set()
    for rel, data in members(archive):
        seen.add(rel)
        target = os.path.join(dest_dir, *rel.split("/"))
        if not os.path.isfile(target):
            got["新增"] += 1
        elif _file_digest(target) == _digest(data):
            got["相同"] += 1
        else:
            got["覆盖"] += 1
    if os.path.isdir(dest_dir):
        for root, _dirs, files in os.walk(dest_dir):
            for name in files:
                rel = os.path.relpath(os.path.join(root, name), dest_dir).replace(os.sep, "/")
                if rel not in seen:
                    got["保留"] += 1
    return got


def unpack(archive, dest_dir):
    """把包里的文件写进 dest_dir（合并：同名覆盖，别的不动）。返回写了几个文件。

    先写临时文件再改名，写到一半断电也不会留下半张图。
    """
    n = 0
    for rel, data in members(archive):
        target = os.path.join(dest_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.isfile(target) and _file_digest(target) == _digest(data):
            continue
        tmp = target + ".导入中"
        with open(tmp, "wb") as f:
            shutil.copyfileobj(io.BytesIO(data), f)
        os.replace(tmp, target)
        n += 1
    return n
