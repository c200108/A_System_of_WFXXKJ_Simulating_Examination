# -*- coding: utf-8 -*-
"""exe 里的「地址槽」：网站导出 exe 时把本网站的地址写进去，文件名不用改（学生端 4.15.0）。

PyInstaller 单文件 exe 里的 Python 代码是压缩过的，没法在里面找个字符串直接改。但 exe 的
**版本信息资源**（文件属性里那一栏）是原样存的 UTF-16 文本，打包时在「备注」里留一段固定长度的
占位：`WFXXKJ-SERVER=` 后面跟 120 个 `~`。网站导出时把占位换成地址（不够长的补 `~`，总长度不变），
exe 别的字节一个不动；程序启动时读自己这个 exe 文件，找到这段就知道连哪儿。

服务端 backend/app/services/client_exe.py 有一份一样的读写（后端镜像里没有 desktop/），
两边的标记、长度、填充字符必须一致，测试守着。
"""

from __future__ import annotations

import re

MARK = "WFXXKJ" + "-SERVER="     # 拆开写：源码里别出现整段标记（虽然代码是压缩的，稳妥点）
FILL = "~"
SIZE = 120                      # 地址最长多少个字符
ENC = "utf-16-le"

# 地址：可带 http:// 或 https://，主机名 / IPv4 / [IPv6]，可带端口，不带路径
_ADDR = re.compile(r"^(https?://)?(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]+)(:\d{1,5})?/?$")


def placeholder() -> str:
    """打包时写进版本信息「备注」的那一段。"""
    return MARK + FILL * SIZE


def valid(addr: str) -> bool:
    addr = str(addr or "").strip()
    return 0 < len(addr) <= SIZE and FILL not in addr and bool(_ADDR.match(addr))


def find(data: bytes) -> list[int]:
    """标记出现在哪些位置（字节偏移）。"""
    needle = MARK.encode(ENC)
    out, at = [], data.find(needle)
    while at >= 0:
        out.append(at)
        at = data.find(needle, at + 1)
    return out


def read(data: bytes) -> str | None:
    """读出写进去的地址。没有槽返回 None；有槽没写（还是占位）返回空串。"""
    hits = find(data)
    if len(hits) != 1:
        return None
    start = hits[0] + len(MARK.encode(ENC))
    raw = data[start:start + SIZE * 2]
    if len(raw) < SIZE * 2:
        return None
    try:
        text = raw.decode(ENC)
    except UnicodeDecodeError:
        return None
    addr = text.rstrip(FILL)
    return addr if not addr or valid(addr) else None


def write(data: bytes, addr: str) -> bytes:
    """把地址写进槽里，返回新的 exe 字节。没有槽、地址不对抛 ValueError。"""
    addr = str(addr or "").strip().rstrip("/")
    if not valid(addr):
        raise ValueError(f"地址「{addr}」不对：只能是域名或 IP，可带端口和 http:// / https://")
    hits = find(data)
    if len(hits) != 1:
        raise ValueError("这个 exe 里没有地址槽（4.15.0 以前打的），只能用改文件名的办法")
    start = hits[0] + len(MARK.encode(ENC))
    body = (addr + FILL * (SIZE - len(addr))).encode(ENC)
    return data[:start] + body + data[start + len(body):]


def read_file(path) -> str | None:
    """读一个 exe 文件里的地址。读不了返回 None。"""
    try:
        with open(path, "rb") as fh:
            return read(fh.read())
    except OSError:
        return None
