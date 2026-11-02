# -*- coding: utf-8 -*-
"""检查更新：版本比较、限流、选变体、两种更新源、下载校验、原地换 exe、登录页按钮。

更新源用一个本机临时 HTTP 服务模拟（GitHub 格式和自建 JSON 各一份），
不连真的 GitHub —— 测试不该依赖外网，也不该吃掉 GitHub 每小时 60 次的额度。
"""

from __future__ import annotations

import hashlib
import http.server
import json
import sys
import threading
from pathlib import Path
from tkinter import messagebox

import pytest

import build
from client import update, ui
from test_ui import app, settle          # noqa: F401  （fixture）

EXE = b"MZ" + b"\0" * 2000               # 像个 exe 的假文件


# ================================================================ 本机更新源
class Source:
    """临时 HTTP 服务：files 里放什么，GET 就回什么。"""

    def __init__(self):
        self.files: dict = {}
        self.delay = 0.0                         # 模拟慢网：每个请求先睡这么久
        files = self.files
        me = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):                       # noqa: N802
                if me.delay:
                    import time
                    time.sleep(me.delay)
                body = files.get(self.path.split("?")[0])
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def put(self, path: str, body) -> str:
        self.files[path] = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        return self.url + path


@pytest.fixture
def src():
    s = Source()
    yield s
    s.httpd.shutdown()
    s.httpd.server_close()


def github_release(url: str, version: str = "4.12.0") -> dict:
    names = ["win32-runtime", "win64-runtime", "win32", "win64",
             "name-login-win32-runtime", "name-login-win64"]
    lan = ["win32-runtime", "name-login-win64-runtime"]
    sha = "sha256:" + hashlib.sha256(EXE).hexdigest()
    return {"tag_name": f"v{version}", "body": "修了几处问题", "html_url": url + "/page",
            "assets": [{"name": f"exam-client-{version}-{n}.exe", "size": len(EXE),
                        "browser_download_url": f"{url}/dl/{n}.exe", "digest": sha} for n in names]
            + [{"name": f"exam-client-lan-{version}-{n}.exe", "size": len(EXE),
                "browser_download_url": f"{url}/dl/lan-{n}.exe", "digest": sha} for n in lan]
            + [{"name": "notes.txt", "size": 1, "browser_download_url": url + "/n"}]}


# ================================================================ 版本号
@pytest.mark.parametrize("latest,current,newer", [
    ("4.12.0", "4.11.1", True),
    ("v4.11.10", "4.11.9", True),          # 按数字比，不按字符串比
    ("4.11.1", "4.11.1", False),
    ("4.11", "4.11.0", False),             # 补零后相同
    ("4.10.9", "4.11.0", False),
    ("学生端 5.0.0", "4.11.1", True),
    ("", "4.11.1", False),                 # 认不出的不算新
    ("4.12.0", "", True),                  # 开发版：有就算新
])
def test_版本比较(latest, current, newer):
    assert update.is_newer(latest, current) is newer


def test_版本号解析():
    assert update.version_tuple("v4.12.0") == (4, 12, 0)
    assert update.version_tuple("机房版 4.10.0：说明") == (4, 10, 0)
    assert update.version_tuple("没有数字") == ()


# ================================================================ 限流
def test_限流_60秒内只能查一次():
    now = [1000.0]
    t = update.Throttle(60, clock=lambda: now[0])
    assert t.wait_left() == 0
    t.mark()
    assert t.wait_left() == 60
    now[0] += 0.5
    assert t.wait_left() == 60                 # 向上取整：还差 59.5 秒说 60
    now[0] += 30
    assert t.wait_left() == 30
    now[0] += 29.5
    assert t.wait_left() == 0


# ================================================================ 变体
@pytest.mark.parametrize("bits,name_login,runtime,want", [
    (32, False, True, "win32-runtime"),
    (64, False, False, "win64"),
    (32, True, False, "name-login-win32"),
    (64, True, True, "name-login-win64-runtime"),
])
def test_变体后缀(bits, name_login, runtime, want):
    assert update.variant(bits, name_login, runtime) == want


def test_变体后缀和发版附件名对得上():
    """发版.py 的附件名是 exam-client-<版本>-<后缀>.exe，这里得认得回来。"""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fabu", str(Path(build.__file__).with_name("发版.py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    suffixes = {suffix for _, suffix, _ in mod.VARIANTS}
    combos = {update.variant(b, n, r) for b in (32, 64) for n in (False, True)
              for r in (False, True)}
    assert suffixes == combos
    for s in suffixes:
        assert update.ASSET_RE.search(f"exam-client-4.12.0-{s}.exe").group(1) == s


def test_烤进去的标记(monkeypatch):
    import client
    mod = type(sys)("client._build")
    mod.VERSION, mod.UPDATE_URL, mod.NAME_LOGIN, mod.RUNTIME = "4.11.1", "c200108/x", True, True
    mod.CHANNEL = "lan"
    monkeypatch.setitem(sys.modules, "client._build", mod)
    monkeypatch.setattr(client, "_build", mod, raising=False)
    assert update.current_version() == "4.11.1"
    assert update.source() == "https://api.github.com/repos/c200108/x/releases/latest"
    assert update.channel() == "lan"
    mod.UPDATE_URL = "c200108/x  http://10.0.0.8/api/client/update.json?channel=lan"
    assert update.sources() == ["https://api.github.com/repos/c200108/x/releases/latest",
                                "http://10.0.0.8/api/client/update.json?channel=lan"]
    bits = 64 if sys.maxsize > 2 ** 32 else 32
    assert update.variant() == f"name-login-win{bits}-runtime"


# ================================================================ 两种源
def test_解析GitHub():
    rel = update.parse(github_release("http://h"), chan="online")
    assert rel.version == "4.12.0" and rel.notes == "修了几处问题"
    assert rel.page == "http://h/page"
    assert set(rel.assets) == {"win32-runtime", "win64-runtime", "win32", "win64",
                               "name-login-win32-runtime", "name-login-win64"}
    a = rel.assets["win32-runtime"]
    assert a["url"] == "http://h/dl/win32-runtime.exe" and a["size"] == len(EXE)
    assert a["sha256"] == hashlib.sha256(EXE).hexdigest()


def test_解析GitHub_机房版只认带lan前缀的():
    rel = update.parse(github_release("http://h"), chan="lan")
    assert set(rel.assets) == {"win32-runtime", "name-login-win64-runtime"}
    assert rel.assets["win32-runtime"]["url"] == "http://h/dl/lan-win32-runtime.exe"
    # 联网版那边一个 lan 的都不认
    online = update.parse(github_release("http://h"), chan="online")
    assert all("lan-" not in a["url"] for a in online.assets.values())


def test_解析自建JSON_相对地址和简写():
    rel = update.parse({"version": "v4.12.0", "notes": "说明", "page": "index.html",
                        "assets": {"win32-runtime": {"url": "x/a.exe", "size": 5, "sha256": "AB"},
                                   "WIN64": "http://other/b.exe", "bad": {}}},
                       "http://192.168.1.8:8080/client/latest.json")
    assert rel.version == "4.12.0" and rel.page == "http://192.168.1.8:8080/client/index.html"
    assert rel.assets["win32-runtime"] == {
        "url": "http://192.168.1.8:8080/client/x/a.exe", "size": 5, "sha256": "ab"}
    assert rel.assets["win64"]["url"] == "http://other/b.exe"
    assert "bad" not in rel.assets


def test_自建JSON没写版本号就报错():
    with pytest.raises(update.UpdateError):
        update.parse({"notes": "x"})


def test_从本机源查_两种格式(src):
    gh = src.put("/repos/o/r/releases/latest", github_release(src.url))
    assert update.check(gh).version == "4.12.0" and update.check(gh).source == gh
    own = src.put("/client/latest.json", {"version": "4.13.0",
                                          "assets": {"win64": "/dl/win64.exe"}})
    rel = update.check(own)
    assert rel.version == "4.13.0" and rel.assets["win64"]["url"] == src.url + "/dl/win64.exe"


def test_查不到给人话(src):
    with pytest.raises(update.UpdateError, match="还没有发布"):
        update.check(src.url + "/nothing.json")
    with pytest.raises(update.UpdateError, match="连不上更新源"):
        update.check("http://127.0.0.1:9/x.json")
    with pytest.raises(update.UpdateError, match="没有设置更新源"):
        update.check("")


# ================================================================ 下载
def test_下载并校验(src, tmp_path):
    url = src.put("/dl/a.exe", EXE)
    sha = hashlib.sha256(EXE).hexdigest()
    seen = []
    got = update.download({"url": url, "size": len(EXE), "sha256": sha},
                          tmp_path / "a.download", lambda g, t: seen.append((g, t)))
    assert got.read_bytes() == EXE and seen[-1] == (len(EXE), len(EXE))


@pytest.mark.parametrize("asset,body,why", [
    ({"size": 99}, EXE, "大小不对"),
    ({"sha256": "00"}, EXE, "校验码不对"),
    ({}, b"<html>not found</html>", "不是 exe"),
])
def test_下载校验不过就丢掉(src, tmp_path, asset, body, why):
    asset = dict(asset, url=src.put("/dl/b.exe", body))
    dest = tmp_path / "b.download"
    with pytest.raises(update.UpdateError, match=why):
        update.download(asset, dest)
    assert not dest.exists()


# ================================================================ 换 exe
def test_文件名不变_地址在文件名里的原样保留(tmp_path):
    exe = tmp_path / "考试客户端-32位-内置运行库@111.170.33.3_3315.exe"
    assert update.target_name(exe, "111.170.33.3:3315") == exe
    plain = tmp_path / "考试客户端-64位-内置运行库.exe"
    assert update.target_name(plain, "") == plain               # 机房版：没烤地址
    # 地址只烤在 exe 里：补进文件名，新版照样连这台教师端
    assert update.target_name(plain, "http://10.0.0.8:8080").name == \
        "考试客户端-64位-内置运行库@10.0.0.8_8080.exe"


def test_原地替换并清理旧版(tmp_path):
    exe = tmp_path / "考试客户端-32位@1.2.3.4_80.exe"
    exe.write_bytes(b"MZ old")
    new = tmp_path / (exe.name + ".download")
    new.write_bytes(b"MZ new")
    old = update.swap_in(new, exe, exe, launch=False)
    assert exe.read_bytes() == b"MZ new" and old.read_bytes() == b"MZ old"
    assert not new.exists()
    (tmp_path / "别人的.exe.old").write_bytes(b"x")
    update.cleanup_old(exe)
    assert not old.exists()
    assert (tmp_path / "别人的.exe.old").exists()               # 不是自己留下的不碰
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([exe.name, "别人的.exe.old"])


def test_放不进去就把自己改回来(tmp_path, monkeypatch):
    exe = tmp_path / "考试客户端.exe"
    exe.write_bytes(b"MZ old")
    missing = tmp_path / "没下载下来.download"
    with pytest.raises(OSError):
        update.swap_in(missing, exe, exe, launch=False)
    assert exe.read_bytes() == b"MZ old"


# ================================================================ 打包
def test_打包取更新日志里最新的学生端版本():
    got = build.latest_client_version()
    assert update.version_tuple(got)[0] == 4


def test_打包默认只查联网版公开仓库(monkeypatch):
    """两版都查联网版公开仓库（机房版仓库是私有的，匿名查不到）；自建源预留，默认不加。"""
    assert build.UPDATE_SERVER == ""
    for ch in ("online", "lan"):
        monkeypatch.setattr(build, "update_channel", lambda ch=ch: ch)
        assert build.default_update_url() == "c200108/A_System_of_WFXXKJ_Simulating_Examination"
    # 以后启用自建源：填上 UPDATE_SERVER 就自动排在 GitHub 后面当备用，渠道各是各的
    monkeypatch.setattr(build, "UPDATE_SERVER", "http://update.example.cn/")
    assert build.default_update_url().split() == [
        build.GITHUB_REPO, "http://update.example.cn/api/client/update.json?channel=lan"]


# ================================================================ 好几个更新源：主源不通换备用
def test_主源不通换备用源(src):
    backup = src.put("/backup.json", {"version": "4.12.0", "assets": {"win64": "a.exe"}})
    rel = update.check(["http://127.0.0.1:9/x.json", backup])
    assert rel.version == "4.12.0" and rel.source == backup and rel.fallbacks == []
    rel = update.check([backup, "http://127.0.0.1:9/x.json"])
    assert rel.fallbacks == ["http://127.0.0.1:9/x.json"]


def test_都不通_说第一个的原因(src):
    with pytest.raises(update.UpdateError, match="连不上更新源.*1 个备用"):
        update.check(["http://127.0.0.1:9/a.json", src.url + "/nothing.json"])


def test_下载_主源断了换备用源的同一版本(src, tmp_path):
    good = src.put("/dl/good.exe", EXE)
    backup = src.put("/b.json", {"version": "4.12.0",
                                 "assets": {"win64": {"url": good, "size": len(EXE)}}})
    older = src.put("/old.json", {"version": "4.11.0", "assets": {"win64": good}})
    rel = update.Release("4.12.0", assets={"win64": {"url": src.url + "/dl/gone.exe"}})
    rel.fallbacks = [older, backup]                  # 版本不一样的那个不用
    got = update.download_any(rel, "win64", tmp_path / "x.download")
    assert got.read_bytes() == EXE


def test_下载_主源缺这个变体去备用源找(src, tmp_path):
    good = src.put("/dl/lan.exe", EXE)
    rel = update.Release("4.12.0", assets={})
    rel.fallbacks = [src.put("/b.json", {"version": "4.12.0", "assets": {"win32-runtime": good}})]
    assert update.download_any(rel, "win32-runtime", tmp_path / "y.download").exists()
    with pytest.raises(update.UpdateError, match="没有这一版"):
        update.download_any(rel, "win64", tmp_path / "z.download")


def test_下载_文件夹写不了不换源(src, tmp_path, monkeypatch):
    rel = update.Release("4.12.0", assets={"win64": {"url": src.put("/a.exe", EXE)}})
    rel.fallbacks = ["http://127.0.0.1:9/never.json"]
    asked = []
    monkeypatch.setattr(update, "check_one", lambda *a, **k: asked.append(1))
    with pytest.raises(update.NotWritable):
        update.download_any(rel, "win64", tmp_path / "没有这个目录" / "x.download")
    assert not asked


# ================================================================ 5 秒封顶
def test_查询整次封顶_慢了就算了不重试(src):
    import time
    url = src.put("/slow.json", {"version": "4.12.0"})
    src.delay = 3
    t0 = time.monotonic()
    with pytest.raises(update.UpdateError, match="没有拿到更新信息"):
        update.check_within(1, url)
    assert time.monotonic() - t0 < 2.0
    src.delay = 0
    assert update.check_within(5, url).version == "4.12.0"


def test_查询封顶_好几个源和跳转共用一份时间(src):
    """deadline 是整次的：第一个源耗光了时间，后面的就不再试了。"""
    import time
    src.delay = 0.6
    a = src.put("/a.json", {"moved_to": "b.json"})
    src.put("/b.json", {"moved_to": "c.json"})
    src.put("/c.json", {"version": "4.12.0"})
    with pytest.raises(update.UpdateError):
        update.check(a, deadline=time.monotonic() + 1.0)

def test_打包按仓库认渠道():
    """联网版仓库 → online，机房版仓库（…_LAN）→ lan。"""
    origin = __import__("subprocess").run(
        ["git", "-C", str(Path(build.__file__).parent), "remote", "get-url", "origin"],
        capture_output=True, text=True).stdout.strip()
    assert build.update_channel() == ("lan" if origin.rstrip("/").endswith(("_LAN", "_LAN.git"))
                                      else "online")


# ================================================================ 换服务器：moved_to
def test_moved_to_转去新地址查(src):
    new = src.put("/new/update.json", {"version": "4.12.0", "assets": {"win64": "a.exe"}})
    old = src.put("/old/update.json", {"moved_to": new})
    rel = update.check(old)
    assert rel.version == "4.12.0"
    assert rel.assets["win64"]["url"] == src.url + "/new/a.exe"   # 相对地址按新清单算


def test_moved_to_相对地址_最多跳两次(src):
    src.put("/c.json", {"version": "4.13.0"})
    src.put("/b.json", {"moved_to": "c.json"})
    assert update.check(src.put("/a.json", {"moved_to": "b.json"})).version == "4.13.0"
    # 三跳：第三次不跟了，最后那份还没版本号 → 说清楚
    src.put("/z.json", {"moved_to": "a.json"})
    with pytest.raises(update.UpdateError, match="换了好几次地址"):
        update.check(src.url + "/z.json")


def test_moved_to_互相指不会转圈(src):
    src.put("/p.json", {"moved_to": "q.json"})
    src.put("/q.json", {"moved_to": "p.json"})
    with pytest.raises(update.UpdateError):
        update.check(src.url + "/p.json")
    src.put("/self.json", {"version": "4.12.0", "moved_to": "self.json"})   # 指向自己：直接用
    assert update.check(src.url + "/self.json").version == "4.12.0"


def test_moved_to_新地址不通就用旧清单(src):
    old = src.put("/old.json", {"version": "4.12.0", "moved_to": "http://127.0.0.1:9/x.json"})
    assert update.check(old).version == "4.12.0"
    gone = src.put("/gone.json", {"moved_to": "http://127.0.0.1:9/x.json"})
    with pytest.raises(update.UpdateError, match="连不上更新源"):
        update.check(gone)


# ================================================================ 生成更新包
def test_生成更新包(tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gen", str(Path(build.__file__).parent / "tools" / "生成更新包.py"))
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    pub = tmp_path / "发布"
    pub.mkdir()
    (pub / "考试客户端-32位-内置运行库@1.2.3.4_80.exe").write_bytes(EXE)    # 联网版：带地址
    (pub / "考试客户端-姓名登录-64位-内置运行库.exe").write_bytes(EXE + b"x")  # 机房版：不带
    (pub / "考试客户端-32位@1.2.3.4_80.exe").write_bytes(EXE)                # 不含运行库那份别认混
    out = tmp_path / "更新包"
    monkeypatch.setattr(sys, "argv", ["gen", "4.12.0", "--渠道", "lan", "--发布目录", str(pub),
                                      "--输出", str(out), "--不核对", "--说明", "说明",
                                      "--搬到", "http://new.example.cn/u.json"])
    assert gen.main() == 0
    data = json.loads((out / "update.json").read_text(encoding="utf-8"))
    assert data["version"] == "4.12.0" and data["moved_to"] == "http://new.example.cn/u.json"
    assert set(data["assets"]) == {"win32-runtime", "name-login-win64-runtime", "win32"}
    a = data["assets"]["name-login-win64-runtime"]
    assert a["url"] == "exam-client-4.12.0-name-login-win64-runtime.exe"
    assert a["size"] == len(EXE) + 1 and a["sha256"] == hashlib.sha256(EXE + b"x").hexdigest()
    assert (out / a["url"]).read_bytes() == EXE + b"x"
    # 解析回来就是学生端能用的那份
    rel = update.parse(data, "http://h/api/client/update.json?channel=lan")
    assert rel.assets["win32"]["url"] == "http://h/api/client/exam-client-4.12.0-win32.exe"


# ================================================================ 登录页按钮
def test_登录页检查更新_有新版就提示_然后限流(app, src, monkeypatch):
    monkeypatch.setattr(update, "THROTTLE", update.Throttle(60))
    monkeypatch.setattr(update, "current_version", lambda: "4.11.1")
    monkeypatch.setattr(update, "sources", lambda: [src.put("/latest.json", {
        "version": "4.12.0", "notes": "新功能", "assets": {}})])
    shown = []
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: shown.append(a[1]))
    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: shown.append(a[1]))
    frame = app.frame
    assert isinstance(frame, ui.LoginFrame) and frame.upd_btn["text"] == "检查更新"

    frame.check_update()
    settle(app, 10, until=lambda: shown)
    # 跑源码时没有 exe 可换：提示新版本，说明不能自动升级
    assert "发现新版本 4.12.0" in shown[-1] and "新功能" in shown[-1]
    assert str(frame.upd_btn["state"]) == "disabled" and "秒后可再查" in frame.upd_btn["text"]

    n = len(shown)
    frame.check_update()                       # 间隔内再点：不联网、不弹窗
    settle(app, 0.5)
    assert len(shown) == n


def test_登录页检查更新_已是最新和网络失败(app, src, monkeypatch):
    shown = []
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: shown.append(("info", a[1])))
    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: shown.append(("warn", a[1])))
    monkeypatch.setattr(update, "current_version", lambda: "4.12.0")

    monkeypatch.setattr(update, "THROTTLE", update.Throttle(60))
    monkeypatch.setattr(update, "sources", lambda: [src.put("/l.json", {"version": "4.12.0"})])
    app.frame.check_update()
    settle(app, 10, until=lambda: shown)
    assert shown[-1] == ("info", "已经是最新版本（4.12.0）。")

    monkeypatch.setattr(update, "THROTTLE", update.Throttle(60))
    monkeypatch.setattr(update, "sources", lambda: ["http://127.0.0.1:9/x.json"])
    app.frame.check_update()
    settle(app, 10, until=lambda: len(shown) > 1)
    assert shown[-1][0] == "warn" and "连不上更新源" in shown[-1][1]
