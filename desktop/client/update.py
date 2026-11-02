# -*- coding: utf-8 -*-
r"""检查更新：登录页那个「检查更新」按钮背后的事。

## 只在学生（老师）点按钮时联网

**考试中绝不自己去查、也绝不弹窗。** 按钮只在登录页，点一次查一次；两次之间
至少隔 60 秒（`Throttle`），一个机房几十台一起狂点也不至于把更新源打挂 ——
GitHub 的接口对同一个出口 IP 一小时只给 60 次。

## 更新源：打包时烤进去

`build.py --update-url ...` 烤进 `_build.UPDATE_URL`（几个地址用空格隔开，按顺序试），
和教师端地址一个烤法。**默认只有一个：联网版公开仓库的 GitHub Releases** —— 查版本走 GitHub
的接口，exe 从 GitHub 下，上百台机器一起升级也不占学校服务器的带宽。

点一次「检查更新」**整次 5 秒封顶**（`check_within`），拿不到就提示「无法获取更新」，不重试。
下载另算（每读一块最多等 30 秒）。

联网版、机房版的 exe **发在同一个 Release 里**：机房版的附件名带 `exam-client-lan-` 前缀，
联网版不带。烤进去的渠道（`_build.CHANNEL`）决定认哪一组 —— 机房版绝不会下到联网版的 exe。
（附件名用英文：GitHub 会把附件名里的中文换掉，中文说明放在附件的 label 里。）

给了好几个更新源时（比如以后加上自建源当备用）：前面的查不通换后面的；下载失败、
前面那个源缺这个变体，也去后面的源找同一版本。

· **自建源**（预留，默认不用；以后换成自己服务器的域名或 IP）：一个 JSON，格式见
  desktop/README.md「检查更新」一节。可以只写 `moved_to` 指向新清单（换服务器用）：

      {"version": "4.12.0", "notes": "这一版改了什么",
       "assets": {"win32-runtime": {"url": "exam-client-4.12.0-win32-runtime.exe",
                                    "size": 8866572, "sha256": "…"},
                  "win64-runtime": "http://192.168.1.8:8080/client/x64.exe"}}

  url 可以写相对路径，相对于这个 JSON 的地址。size / sha256 可省，给了就校验。

· **GitHub Releases**（仓库得是公开的）：`https://api.github.com/repos/<owner>/<repo>/releases`
  （也可以只写 `<owner>/<repo>`）。从列表里挑 tag 是 v<数字> 的最新正式发布（教师端 APP 的 teacher-v… 不算），
  版本号取 tag_name，说明取 body，下载地址按
  附件名里的变体后缀认（`exam-client-4.12.0-win32-runtime.exe` → `win32-runtime`）。

## 升级：原地换掉自己，文件名不变

1. 新 exe 下载到**同一个文件夹**的 `<原文件名>.download`，校验大小（和 sha256）
   以及开头的 `MZ`；
2. 正在运行的 exe **可以改名但不能覆盖** —— 所以把自己改名成 `<原文件名>.old`，
   再把下载好的改成原来的名字，启动它，自己退出；
3. 新版启动时顺手删掉那个 `.old`（`cleanup_old`）。

为什么不用"等进程退出再替换"的 bat：bat 要按代码页写中文路径，Win7 上
`chcp 65001` 跑批处理又有毛病；改名这一步在进程还活着的时候就能做完，不用等、不用猜。

**换完还是那一个单文件 exe、还是原来的文件名**（文件名里 `@地址` 原样保留），
可以直接拷到别的电脑。不写注册表，不往用户目录放任何升级要用的东西。

## 选对变体

32 / 64 位、姓名登录版、内置运行库，这三样决定下哪一个附件（`variant()`）。
位数看的是**正在跑的这个 Python**（32 位 exe 在 64 位系统上也还是 32 位），
另外两样是打包时烤进去的。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

INTERVAL = 60                    # 两次检查至少隔这么多秒
QUERY_BUDGET = 5                 # 点一次「检查更新」最多等这么久（DNS、连接、读取、跳转全算上）
TIMEOUT = QUERY_BUDGET           # 单个请求的超时，实际取「还剩多少」
DOWNLOAD_TIMEOUT = 30            # 下载时每读一块最多等这么久
CHUNK = 64 * 1024
USER_AGENT = "wfxxkj-exam-client"
# 附件名末尾的变体后缀：exam-client-4.12.0-name-login-win32-runtime.exe
ASSET_RE = re.compile(r"((?:name-login-)?win(?:32|64)(?:-runtime)?)\.exe$", re.I)
# 用 Release 列表而不是 releases/latest：同一个仓库里还发教师端 APP（tag 以 teacher-v 开头），
# 万一它被标成 Latest，latest 接口返回的就是 APP —— 学生端得自己挑 tag 是 v<数字> 的那个
GITHUB_API = "https://api.github.com/repos/{}/releases?per_page=20"
STUDENT_TAG = re.compile(r"^v\d+(?:\.\d+)*$")
MAX_MOVES = 2                    # 清单里 moved_to 最多跟几次
LAN_PREFIX = "exam-client-lan-"  # Release 里机房版附件名的前缀
SLOW = "规定时间内没有拿到更新信息，请检查这台电脑能不能上网"


class UpdateError(Exception):
    """能原样显示给人看的一句话。"""


class NotWritable(UpdateError):
    """exe 所在的文件夹写不了（网络共享、被锁的桌面）。换哪个更新源都一样，不必再试。"""


class Release:
    """更新源说的"最新版"：版本号、说明、各变体的下载地址。"""

    def __init__(self, version: str, notes: str = "", assets: dict | None = None,
                 page: str = ""):
        self.version = version
        self.notes = notes
        self.assets = assets or {}   # {变体: {"url": ..., "size": int, "sha256": str}}
        self.page = page             # 网页地址：自动升级不了时让人手动去下
        self.source = ""             # 从哪个更新源查到的
        self.fallbacks: list = []    # 排在它后面的更新源：下载失败、缺变体时去那儿找


# ================================================================ 打包时烤进去的
def _baked(name: str, default=None):
    try:
        from . import _build
        return getattr(_build, name, default)
    except Exception:                                   # noqa: BLE001
        return default


def current_version() -> str:
    """这个 exe 的版本号（学生端产品线，如 4.11.1）。没打包时是空串。"""
    return str(_baked("VERSION", "") or "")


def sources() -> list:
    """更新源地址，按顺序（主源在前）。`owner/repo` 的简写展开成 GitHub 的 Release 列表接口。"""
    return [expand_source(s) for s in str(_baked("UPDATE_URL", "") or "").split() if s]


def source() -> str:
    """给人看的一行：主源 → 备用源。"""
    return " → ".join(sources())


def channel() -> str:
    """这个 exe 是联网版（online）还是机房版（lan）。决定在 Release 里认哪一组附件。"""
    return "lan" if str(_baked("CHANNEL", "") or "").lower() == "lan" else "online"


def expand_source(raw: str) -> str:
    raw = str(raw or "").strip()
    if re.fullmatch(r"[\w.-]+/[\w.-]+", raw):
        return GITHUB_API.format(raw)
    return raw


def variant(bits: int | None = None, name_login: bool | None = None,
            runtime: bool | None = None) -> str:
    """这个 exe 对应 release 里的哪个附件后缀，如 `name-login-win32-runtime`。"""
    if bits is None:
        bits = struct.calcsize("P") * 8
    if name_login is None:
        name_login = bool(_baked("NAME_LOGIN", False))
    if runtime is None:
        runtime = bool(_baked("RUNTIME", False))
    return (("name-login-" if name_login else "") + f"win{bits}"
            + ("-runtime" if runtime else ""))


# ================================================================ 版本号
def version_tuple(text: str) -> tuple:
    """`v4.12.0`、`学生端 4.12.0`、`4.12` 都认；认不出返回空元组。"""
    got = re.search(r"\d+(?:\.\d+)*", str(text or ""))
    return tuple(int(x) for x in got.group(0).split(".")) if got else ()


def is_newer(latest: str, current: str) -> bool:
    """latest 比 current 新吗。4.12 和 4.12.0 算一样；认不出版本号的一律不算新。"""
    a, b = version_tuple(latest), version_tuple(current)
    if not a:
        return False
    if not b:
        return True                  # 自己没有版本号（开发版）：有就算新
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


# ================================================================ 限流
class Throttle:
    """两次检查至少隔 interval 秒。只记在内存里 —— 重开程序就清零，这不是防作弊，
    只是别让一个按钮被连点成一串请求。"""

    def __init__(self, interval: float = INTERVAL, clock=time.monotonic):
        self.interval = interval
        self.clock = clock
        self.last: float | None = None

    def wait_left(self) -> int:
        """还要等几秒（向上取整），0 表示现在就能查。"""
        if self.last is None:
            return 0
        left = self.interval - (self.clock() - self.last)
        return max(0, int(left + 0.999))

    def mark(self) -> None:
        self.last = self.clock()


THROTTLE = Throttle()


# ================================================================ 解析两种源
def parse(data, base_url: str = "", chan: str | None = None) -> Release:
    """更新源返回的 JSON → Release。有 tag_name 的按 GitHub 认，否则按自建格式。

    GitHub 的 Release 里联网版、机房版的附件放在一起，按 chan 只取自己那一组
    （机房版带 `exam-client-lan-` 前缀）。自建源是一个渠道一份清单，不用分。
    """
    if isinstance(data, list):                          # GitHub 的 Release 列表
        data = pick_release(data)
    if not isinstance(data, dict):
        raise UpdateError("更新源返回的内容看不懂")
    if "tag_name" in data:
        if not STUDENT_TAG.match(str(data.get("tag_name", ""))):
            raise UpdateError("更新源上最新的发布不是学生端的版本")
        lan = (chan or channel()) == "lan"
        assets = {}
        for a in data.get("assets") or []:
            name = str(a.get("name", "")).lower()
            hit = ASSET_RE.search(name)
            if not hit or not a.get("browser_download_url"):
                continue
            if name.startswith(LAN_PREFIX) != lan:
                continue
            digest = str(a.get("digest") or "")
            assets[hit.group(1).lower()] = {
                "url": a["browser_download_url"], "size": int(a.get("size") or 0),
                "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else ""}
        return Release(str(data.get("tag_name", "")).lstrip("vV"),
                       str(data.get("body") or ""), assets, str(data.get("html_url") or ""))

    version = str(data.get("version") or "").strip()
    if not version_tuple(version):
        raise UpdateError("更新源里没写版本号（version）")
    assets = {}
    for key, val in (data.get("assets") or {}).items():
        item = {"url": val} if isinstance(val, str) else dict(val or {})
        if not item.get("url"):
            continue
        assets[str(key).lower()] = {
            "url": urllib.parse.urljoin(base_url, str(item["url"])),
            "size": int(item.get("size") or 0),
            "sha256": str(item.get("sha256") or "").lower()}
    page = str(data.get("page") or "")
    return Release(version.lstrip("vV"), str(data.get("notes") or ""), assets,
                   urllib.parse.urljoin(base_url, page) if page else "")


def pick_release(items: list) -> dict:
    """Release 列表里挑学生端最新的一个：正式发布（不是草稿、不是预发布）、tag 是 v<数字>。"""
    best, best_v = None, ()
    for r in items:
        if not isinstance(r, dict) or r.get("draft") or r.get("prerelease"):
            continue
        tag = str(r.get("tag_name", ""))
        if not STUDENT_TAG.match(tag):
            continue
        v = version_tuple(tag)
        if v > best_v:
            best, best_v = r, v
    if best is None:
        raise UpdateError("更新源上还没有发布任何版本")
    return best


def _open(url: str, timeout: int):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/vnd.github+json, application/json"})
    return urllib.request.urlopen(req, timeout=timeout)       # noqa: S310


def check_within(seconds: float = QUERY_BUDGET, urls=None) -> Release:
    """查一次更新，**整次 seconds 秒封顶**，拿不到就算了（不重试）。

    urllib 的 timeout 只管连接和每次读，**管不到 DNS 解析** —— 机房里 DNS 不通时
    getaddrinfo 能卡上二三十秒。所以整个查询放进一个线程，等它 seconds 秒，
    没回来就当查不到；那个线程是 daemon，自己慢慢结束，不拦着程序退出。
    """
    box: dict = {}
    deadline = time.monotonic() + seconds

    def run():
        try:
            box["rel"] = check(urls, deadline)
        except UpdateError as exc:
            box["err"] = exc
        except Exception as exc:                        # noqa: BLE001
            box["err"] = UpdateError(f"查更新时出错了：{exc}")

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(seconds)
    if worker.is_alive() or not box:
        raise UpdateError(f"{seconds:g} 秒内没有拿到更新信息，请检查这台电脑能不能上网")
    if "err" in box:
        raise box["err"]
    return box["rel"]


def check(urls=None, deadline: float | None = None) -> Release:
    """按顺序试更新源（主源 → 备用源），返回第一个查得通的。全都不通抛 UpdateError。

    urls 不给就用烤进去的；可以给一个地址（字符串，空格隔开的几个也行）或一个列表。
    """
    if urls is None:
        urls = sources()
    elif isinstance(urls, str):
        urls = [expand_source(u) for u in urls.split()]
    else:
        urls = [expand_source(u) for u in urls if u]
    if not urls:
        raise UpdateError("这个客户端打包时没有设置更新源")
    errors = []
    for i, url in enumerate(urls):
        try:
            rel = check_one(url, deadline)
        except UpdateError as exc:
            errors.append(exc)
            continue
        rel.fallbacks = urls[i + 1:]
        return rel
    if len(errors) == 1:
        raise errors[0]
    raise UpdateError(f"{errors[0]}（{len(errors) - 1} 个备用更新源也没查通）")


def check_one(url: str, deadline: float | None = None) -> Release:
    """查一个更新源。失败抛 UpdateError，话是给人看的。

    清单里写了 `moved_to`（换服务器了），这一次就转去新地址查，最多跳 MAX_MOVES 次 ——
    两个清单互相指来指去时不至于转圈。新地址查不通、而旧清单自己也写着版本的，
    就按旧清单走。**跳转只在这一次检查里生效，什么都不记**（不写注册表、不写用户目录）：
    新地址烤进下一版 exe，升级之后自然就改过来了。
    """
    data = _fetch(url, deadline)
    for _ in range(MAX_MOVES):
        moved = str(data.get("moved_to") or "").strip() if isinstance(data, dict) else ""
        if not moved:
            break
        nxt = urllib.parse.urljoin(url, moved)
        if nxt == url:
            break
        try:
            got = _fetch(nxt, deadline)
        except UpdateError:
            if isinstance(data, dict) and (data.get("version") or data.get("tag_name")):
                break
            raise
        url, data = nxt, got
    else:
        if isinstance(data, dict) and data.get("moved_to") and not data.get("version"):
            raise UpdateError("更新源换了好几次地址还没找到清单，请联系管理员")
    rel = parse(data, url)
    rel.source = url
    return rel


def _fetch(url: str, deadline: float | None = None):
    timeout = TIMEOUT
    if deadline is not None:
        timeout = deadline - time.monotonic()
        if timeout <= 0.05:
            raise UpdateError(SLOW)
    try:
        with _open(url, timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise UpdateError("更新源上还没有发布任何版本") from exc
        if exc.code in (403, 429):
            raise UpdateError("更新源暂时不让查（同一个网络查得太频繁），过一会儿再试") from exc
        raise UpdateError(f"更新源出错了（HTTP {exc.code}）") from exc
    except (urllib.error.URLError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, socket.timeout) or isinstance(exc, socket.timeout):
            raise UpdateError(SLOW) from exc
        raise UpdateError("连不上更新源，请检查这台电脑能不能上网") from exc
    except ValueError as exc:
        raise UpdateError("更新源返回的内容看不懂") from exc
    return data


# ================================================================ 下载与替换
def exe_path() -> Path | None:
    """正在跑的这个 exe。跑源码时是 None —— 没有 exe 可换。"""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve()


def download(asset: dict, dest: Path, progress=None) -> Path:
    """下载到 dest，校验大小、sha256 和 exe 文件头。校验不过就删掉并抛 UpdateError。"""
    want = int(asset.get("size") or 0)
    sha = hashlib.sha256()
    got = 0
    # 先把本地文件开好：开不了（只读的网络共享、被锁的桌面）跟网络无关，换哪个源都一样
    try:
        out = open(dest, "wb")
    except OSError as exc:
        raise NotWritable(f"程序所在的文件夹不能写，没法自动升级：{dest.parent}") from exc
    try:
        with out, _open(asset["url"], DOWNLOAD_TIMEOUT) as resp:
            total = int(resp.headers.get("Content-Length") or 0) or want
            while True:
                block = resp.read(CHUNK)
                if not block:
                    break
                out.write(block)
                sha.update(block)
                got += len(block)
                if progress:
                    progress(got, total)
    except (urllib.error.URLError, OSError) as exc:
        _unlink(dest)
        raise UpdateError("下载中断了，请稍后再试") from exc

    why = ""
    if want and got != want:
        why = f"大小不对（应为 {want} 字节，实际 {got}）"
    elif asset.get("sha256") and sha.hexdigest() != str(asset["sha256"]).lower():
        why = "校验码不对"
    else:
        with open(dest, "rb") as f:
            if f.read(2) != b"MZ":
                why = "不是 exe 文件"
    if why:
        _unlink(dest)
        raise UpdateError(f"下载的文件{why}，已丢弃")
    return dest


def candidates(rel: Release, var: str):
    """这一版的这个变体能从哪儿下：先是查到它的那个源，再依次问备用源（版本一样才算）。

    逐个 yield，用到才去问 —— 主源下得下来，就不去打扰备用源。
    """
    if var in rel.assets:
        yield rel.assets[var]
    for url in rel.fallbacks:
        try:
            other = check_one(url)
        except UpdateError:
            continue
        if version_tuple(other.version) == version_tuple(rel.version) and var in other.assets:
            yield other.assets[var]


def download_any(rel: Release, var: str, dest: Path, progress=None) -> Path:
    """下载这一版的这个变体。主源下不下来（断了、超时、校验不过）就换备用源。"""
    last = None
    for asset in candidates(rel, var):
        try:
            return download(asset, dest, progress)
        except NotWritable:
            raise
        except UpdateError as exc:
            last = exc
    if last is None:
        raise UpdateError(f"更新源里没有这一版（{var}）的安装包，没法自动升级。")
    raise last


def target_name(exe: Path, baked_server: str = "") -> Path:
    """新版叫什么：**原来的名字**。

    只有一种情况要动：旧版把地址烤在 exe 里、文件名里却没写 —— 新版烤的未必是同一个
    地址，那就把地址补进文件名（文件名优先级最高），换完照样连原来那台教师端。
    """
    host = str(baked_server or "").strip().rstrip("/")
    if host.lower().startswith("http://"):
        host = host[len("http://"):]
    if "@" in exe.stem or not host or "://" in host or "/" in host:
        return exe
    return exe.with_name(f"{exe.stem}@{host.replace(':', '_')}{exe.suffix}")


def swap_in(new: Path, exe: Path, final: Path, launch=True) -> Path:
    """把正在跑的 exe 改名成 .old，新版放到 final，启动它。返回 .old 的路径。"""
    old = exe.with_name(exe.name + ".old")
    _unlink(old)
    os.replace(str(exe), str(old))                 # 运行中的 exe 能改名，不能覆盖
    try:
        os.replace(str(new), str(final))
    except OSError:
        os.replace(str(old), str(exe))             # 放不进去就把自己改回来，别把 exe 弄没了
        raise
    if launch:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([str(final)], cwd=str(final.parent), creationflags=flags,
                         close_fds=True)
    return old


def cleanup_old(exe: Path | None = None) -> None:
    """删掉上次升级留下的 `.old`。删不掉（旧进程还没退干净）就下次再说。"""
    exe = exe or exe_path()
    if exe is None:
        return
    for p in exe.parent.glob("*.exe.old"):
        # 只认自己留下的（文件名补了 @地址 时新旧名字不一样，所以按前缀认）
        if p.name == exe.name + ".old" or p.name.startswith(exe.stem.split("@")[0]):
            _unlink(p)


def _unlink(p: Path) -> None:
    try:
        Path(p).unlink()
    except OSError:
        pass
