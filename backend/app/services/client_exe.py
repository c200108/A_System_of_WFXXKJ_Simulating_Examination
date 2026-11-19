"""从本网站导出学生端 exe，自动带上本网站的地址（服务端 2.23.2 / 学生端 4.15.0）。

原来「下载学生客户端」是浏览器直接从 GitHub 下附件，那些 exe 打包时烤的是开发者自己服务器的地址
—— 别的学校部署了也连到那儿去，还把那个地址公开了。现在 exe 由本网站转一手，导出时带上本网站地址，
两种办法：

1. **改文件名**：`exam-client-4.15.0-win32-runtime@exam.xxx.cn_8080.exe`。学生端一直认文件名里
   `@` 后面的地址（client/shell.py 的 server_from_name），老版 exe 也认。缺点是网管一改名就没了。
2. **写进 exe**：文件名不变，地址写进 exe 里预留的「地址槽」（版本信息的备注，UTF-16 原样存）。
   4.15.0 起打的 exe 才有槽；读写规则和 desktop/client/slot.py 一模一样，测试守着两边一致。

exe 从哪来：
- 机房版：项目根目录的「发布」文件夹（随项目一起拷进机房，不联网）；
- 联网版：GitHub 最新正式版（Latest）的附件，下过的存在 data/client-cache/<版本>/ 下，下次直接用。
  服务器连不上 GitHub 时可以把 exe 放进 CLIENT_EXE_DIR（默认 ./data/client-exe）当本地来源。
"""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

from ..config import settings

REPO = "c200108/A_System_of_WFXXKJ_Simulating_Examination"
LAN_PREFIX = "exam-client-lan-"
BACKEND_DIR = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------- 地址槽（和 desktop/client/slot.py 一致）
MARK = "WFXXKJ" + "-SERVER="
FILL = "~"
SIZE = 120
ENC = "utf-16-le"
_ADDR = re.compile(r"^(https?://)?(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.-]+)(:\d{1,5})?/?$")


def valid_addr(addr: str) -> bool:
    addr = str(addr or "").strip()
    return 0 < len(addr) <= SIZE and FILL not in addr and bool(_ADDR.match(addr))


def slot_hits(data: bytes) -> int:
    return data.count(MARK.encode(ENC))


def read_slot(data: bytes) -> str | None:
    needle = MARK.encode(ENC)
    if data.count(needle) != 1:
        return None
    start = data.find(needle) + len(needle)
    try:
        return data[start:start + SIZE * 2].decode(ENC).rstrip(FILL)
    except UnicodeDecodeError:
        return None


def write_slot(data: bytes, addr: str) -> bytes:
    addr = str(addr or "").strip().rstrip("/")
    if not valid_addr(addr):
        raise ValueError(f"地址「{addr}」不对：只能是域名或 IP，可带端口和 http:// / https://")
    needle = MARK.encode(ENC)
    if data.count(needle) != 1:
        raise ValueError("这个 exe 里没有地址槽（学生端 4.15.0 以前打的），请用「改文件名」的方式导出")
    start = data.find(needle) + len(needle)
    body = (addr + FILL * (SIZE - len(addr))).encode(ENC)
    return data[:start] + body + data[start + len(body):]


def host_for_name(addr: str) -> str:
    """写进文件名的那段：去掉 http(s)://，端口前的冒号换成下划线（冒号在文件名里非法）。
    学生端看到域名会自己先试 https 再退回 http，看到 IP 直接用 http。"""
    host = re.sub(r"^https?://", "", str(addr or "").strip(), flags=re.I).rstrip("/")
    return host.replace(":", "_")


def renamed(name: str, addr: str) -> str:
    stem = name[:-4] if name.lower().endswith(".exe") else name
    stem = stem.split("@", 1)[0]
    return f"{stem}@{host_for_name(addr)}.exe"


# ---------------------------------------------------------------- exe 从哪来
def _local_dirs() -> list[Path]:
    dirs = []
    if settings.client_exe_dir:
        dirs.append(Path(settings.client_exe_dir))
    dirs.append(BACKEND_DIR.parent / "发布")          # 机房版：随项目拷进来的那几个 exe
    return [d for d in dirs if d.is_dir() and any(d.glob("*.exe"))]


def _label(name: str) -> str:
    n = name.lower()
    bits = "32 位" if "32" in n else "64 位" if "64" in n else ""
    parts = ["姓名登录版" if ("name-login" in n or "姓名登录" in name) else "学号登录版", bits]
    if "runtime" in n or "内置运行库" in name:
        parts.append("内置运行库" + ("（Win7 学生机发这个）" if bits == "32 位" else ""))
    return " · ".join(p for p in parts if p)


def _github_latest(timeout: int = 15) -> dict:
    req = urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                                 headers={"Accept": "application/vnd.github+json",
                                          "User-Agent": "exam-server"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def catalog() -> dict:
    """能导出哪些 exe：{source, version, items: [{name, size, label}], error}。"""
    for d in _local_dirs():
        items = [{"name": p.name, "size": p.stat().st_size, "label": _label(p.name)}
                 for p in sorted(d.glob("*.exe"))]
        return {"source": "local", "version": "", "items": items, "error": ""}
    try:
        rel = _github_latest()
    except Exception as exc:                                # noqa: BLE001
        return {"source": "github", "version": "", "items": [],
                "error": f"服务器连不上 GitHub（{exc.__class__.__name__}）。可以在自己电脑上从发布页下载 exe，"
                         f"放进服务器的 {settings.client_exe_dir or './data/client-exe'} 文件夹再来导出"}
    items = [{"name": a["name"], "size": a.get("size", 0), "label": _label(a["name"])}
             for a in rel.get("assets") or []
             if str(a.get("name", "")).lower().endswith(".exe")
             and not str(a["name"]).startswith(LAN_PREFIX)]
    return {"source": "github", "version": str(rel.get("tag_name") or "").lstrip("vV"),
            "items": items, "error": ""}


def fetch(name: str) -> bytes:
    """取一个 exe 的原始字节。本地有就用本地的，没有就从 GitHub 最新版下（带缓存）。"""
    if "/" in name or "\\" in name or not name.lower().endswith(".exe"):
        raise FileNotFoundError(name)
    for d in _local_dirs():
        f = d / name
        if f.is_file():
            return f.read_bytes()
        raise FileNotFoundError(name)
    rel = _github_latest()
    tag = str(rel.get("tag_name") or "latest")
    asset = next((a for a in rel.get("assets") or [] if a.get("name") == name), None)
    if not asset or name.startswith(LAN_PREFIX):
        raise FileNotFoundError(name)
    cache = Path(settings.client_cache_dir) / re.sub(r"[^\w.-]", "_", tag)
    f = cache / name
    if f.is_file() and f.stat().st_size == asset.get("size", -1):
        return f.read_bytes()
    req = urllib.request.Request(asset["browser_download_url"], headers={"User-Agent": "exam-server"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = resp.read()
    cache.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".part")
    tmp.write_bytes(data)
    tmp.replace(f)
    return data
