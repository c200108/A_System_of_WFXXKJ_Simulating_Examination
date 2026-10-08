# -*- coding: utf-8 -*-
r"""只发一个 exe 到学生机 —— 这件事成不成立，靠的就是这几条。

机房里的分发方式是"把一个文件拷过去"，不是"把一个文件夹 ghost 过去"。要让它
成立，得同时满足三条，缺一条就又变回发文件夹：

  ① exe 旁边**不长东西**。设置和答案包写到 %LOCALAPPDATA%，不写在 exe 边上。
  ② 教师端地址**跟着 exe 走**。烤进去，或者写在文件名里。
  ③ exe 放在**只读位置也能跑**（网络共享、被组策略锁住的桌面）—— ① 顺带解决。

第 ② 条是打包脚本写、客户端读，**两头分处两个文件**，改一头忘一头就是"学生
双击之后地址栏空着"。所以这里专门验一遍往返。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import build
from client import shell, store, ui


# ================================================================ ① 往哪写
def test_数据写在LOCALAPPDATA不写在exe旁边(tmp_path, monkeypatch):
    beside = tmp_path / "U盘"
    beside.mkdir()
    monkeypatch.setattr(store, "here", lambda: beside)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData"))
    (tmp_path / "AppData").mkdir()

    got = store.data_dir()
    assert got == tmp_path / "AppData" / store.APP_DIR_NAME
    assert got.is_dir()                      # 拿到路径就该能直接写
    assert list(beside.iterdir()) == []      # exe 旁边干干净净


def test_没有LOCALAPPDATA就退到APPDATA再退到TEMP(tmp_path, monkeypatch):
    """机房里遇到过精简版系统把 LOCALAPPDATA 抹掉的。退一步，别崩。"""
    for name in ("漫游", "临时"):
        (tmp_path / name).mkdir()
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "漫游"))
    monkeypatch.setenv("TEMP", str(tmp_path / "临时"))
    assert store.data_dir() == tmp_path / "漫游" / store.APP_DIR_NAME

    monkeypatch.delenv("APPDATA", raising=False)
    assert store.data_dir() == tmp_path / "临时" / store.APP_DIR_NAME


def test_三个位置都写不了就退回exe目录(tmp_path, monkeypatch):
    """极端情况也要有地方落脚：宁可写回 exe 旁边，也不能让学生考不成试。"""
    blocked = tmp_path / "这是个文件"
    blocked.write_text("不是目录", encoding="utf-8")
    monkeypatch.setattr(store, "here", lambda: tmp_path / "exe所在")
    monkeypatch.setenv("LOCALAPPDATA", str(blocked / "子"))
    monkeypatch.setenv("APPDATA", str(blocked / "子"))
    monkeypatch.setenv("TEMP", str(blocked / "子"))
    assert store.data_dir() == tmp_path / "exe所在"


def test_exe旁边已有设置文件时仍然用它(tmp_path, monkeypatch):
    """早先是整个文件夹 ghost 到全机房的。那些机器换上新 exe 之后，不该突然
    忘掉教师端地址 —— 旁边那份设置继续算数。"""
    beside = tmp_path / "旧机器"
    beside.mkdir()
    (tmp_path / "AppData").mkdir()
    monkeypatch.setattr(store, "here", lambda: beside)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData"))

    assert store.config_path().parent != beside          # 没有那份就走新位置
    (beside / store.CONFIG_NAME).write_text(
        '{"server": "10.0.0.9:8000"}', encoding="utf-8")
    assert store.config_path() == beside / store.CONFIG_NAME
    assert store.remembered_server() == "10.0.0.9:8000"


# ================================================================ ② 地址跟着 exe 走
@pytest.mark.parametrize("name, want", [
    ("考试客户端@192.168.1.8_8080", "192.168.1.8:8080"),
    ("考试客户端@111.170.33.3_3315", "111.170.33.3:3315"),
    ("考试客户端@192.168.1.8:8080", "192.168.1.8:8080"),   # 手写成冒号的也认
    ("考试客户端@192.168.1.8", "192.168.1.8"),             # 不写端口
    ("考试客户端@exam_school_edu", "exam.school.edu"),     # 没端口时下划线当点
    ("考试客户端", ""),
    ("考试客户端@", ""),
    ("考试客户端 (1)", ""),                                # 浏览器下载重名
])
def test_从exe文件名里读地址(monkeypatch, tmp_path, name, want):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / (name + ".exe")))
    assert shell.server_from_name() == want


@pytest.mark.parametrize("server", [
    "192.168.1.8:8080", "111.170.33.3:3315", "10.0.0.9", "http://192.168.1.8:8080",
])
@pytest.mark.parametrize("mark", ["", "-32位", "-64位"])
def test_打包写的文件名客户端读得回来(monkeypatch, tmp_path, server, mark):
    """**这条是这个文件的核心。** 打包脚本写文件名、客户端解析文件名，分处两个
    文件；改一头忘一头，症状是学生双击之后地址栏空着，而打包过程一切正常。

    位数标在 `@` 前面就是为了这条：解析只认 `@` 之后那一段，加不加位数都不影响。
    """
    name = build.exe_name(server, mark)
    assert mark in name
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / name))
    assert shell.server_from_name() == server.replace("http://", "")


def test_两种位数的exe互不覆盖(tmp_path, monkeypatch):
    """机房里 32 位和 64 位两版并存：重打一版不能把另一版删掉。

    32 位那份两种机器都能跑，64 位那份只能跑 64 位 Windows —— 老机房两样都要
    留着，而 `build.py` 每次打包都会先清「发布」。
    """
    dist = tmp_path / "发布"
    (dist / "答案包").mkdir(parents=True)
    (dist / "答案包" / "张三.ans").write_text("卷子", encoding="utf-8")
    a = dist / build.exe_name("1.2.3.4:80", "-32位")
    b = dist / build.exe_name("1.2.3.4:80", "-64位")
    for f in (a, b):
        f.write_text("exe", encoding="utf-8")
    (dist / "考场使用说明.txt").write_text("旧说明", encoding="utf-8")

    monkeypatch.setattr(build, "DIST", dist)
    build.clear_dist(b.name)                    # 重打 64 位那一版

    assert not b.exists(), "这次要重写的那一个没清掉"
    assert a.exists(), "32 位那份被顺手删了"
    assert (dist / "答案包" / "张三.ans").exists(), "收上来的卷子被删了"
    assert not (dist / "考场使用说明.txt").exists(), "说明该重写"


def test_两种位数的图标不一样(monkeypatch, tmp_path):
    """32 位用蓝红那枚，64 位用金红那枚 —— 拿到手不用看文件名就知道是哪一份。

    文件名会被改（教师端换了 IP，网管改个名就完事），图标不会。而发错的后果
    不对称：64 位那份在 32 位机器上双击根本不出来。
    """
    box = tmp_path / "图标"
    box.mkdir()
    for name in ("考试客户端.ico", "考试客户端-蓝红.ico"):
        (box / name).write_bytes(b"ico")
    monkeypatch.setattr(build, "ICONS", box)

    assert build.icon_for(32).name == "考试客户端-蓝红.ico"
    assert build.icon_for(64).name == "考试客户端.ico"


def test_少一枚图标就用另一枚顶上(monkeypatch, tmp_path):
    """图标是锦上添花，**不能因为它打不出包**。少一枚用另一枚，一枚都没有
    就用 PyInstaller 的默认图标。"""
    box = tmp_path / "图标"
    box.mkdir()
    monkeypatch.setattr(build, "ICONS", box)
    assert build.icon_for(32) is None and build.icon_for(64) is None

    (box / "考试客户端.ico").write_bytes(b"ico")
    assert build.icon_for(32).name == "考试客户端.ico"     # 蓝红那枚还没做


def test_打进包里的图标一律叫考试客户端ico(monkeypatch, tmp_path):
    """窗口左上角那个图标是运行时**按固定名字**从附带文件里读的
    （`shell.asset("考试客户端.ico")`）。蓝红那枚在仓库里另有其名，原样打进去
    运行时就找不着，窗口会退回 Tk 那根羽毛 —— 所以打包前改名复制一份。
    """
    monkeypatch.setattr(build, "HERE", tmp_path)
    src = tmp_path / "考试客户端-蓝红.ico"
    src.write_bytes("蓝红那枚".encode("utf-8"))

    staged = build.stage_icon(src)
    assert staged.name == "考试客户端.ico"
    assert staged.read_bytes() == src.read_bytes()

    spec = build.write_spec(tmp_path / "t.spec", icon=staged, ucrt=None, onefile=True)
    body = spec.read_text(encoding="utf-8")
    assert f"icon=r'{staged}'" in body, "exe 自己的图标没钉上"
    assert f"datas=[(r'{staged}', '图标')]" in body, "窗口图标没打进包"


def test_仓库里两枚图标都在而且各有七个尺寸():
    """两枚都得进仓库，而且**每枚都带全 7 个尺寸**。

    只塞一张 256 的进去，Windows 会自己缩 —— 缩出来的 16×16 是一团糊，任务栏上
    认不出是什么。所以 48 及以下另画了简笔版，ico 允许每个尺寸放不一样的图。
    少了哪个尺寸就是这一步没做（见 图标/制作图标.py 的 SIZES）。
    """
    got = {}
    for name in ("考试客户端.ico", "考试客户端-蓝红.ico"):
        ico = build.ICONS / name
        assert ico.is_file(), f"{name} 不在仓库里，打包会退回 PyInstaller 的默认图标"
        blob = ico.read_bytes()
        count = int.from_bytes(blob[4:6], "little")
        # 目录项每条 16 字节，第 0 字节是宽；0 按 ico 的规矩表示 256
        sizes = {blob[6 + i * 16] or 256 for i in range(count)}
        assert sizes == {16, 24, 32, 48, 64, 128, 256}, f"{name} 少了尺寸：{sizes}"
        got[name] = blob

    assert got["考试客户端.ico"] != got["考试客户端-蓝红.ico"], \
        "两枚长一样，那按位数分图标就没有意义了"


@pytest.mark.parametrize("server", ["https://exam.school.edu.cn", "1.2.3.4:80/exam", ""])
def test_写不进文件名的地址就不写(server):
    """https 的域名和带路径的地址写进文件名会走样（冒号斜杠都非法）。宁可不写
    —— 地址已经烤在 _build.py 里，文件名只是个可选的覆盖手段。"""
    assert build.exe_name(server) == "考试客户端.exe"


def test_打包烤进去的地址读得到(monkeypatch):
    """`build.py --server` 把地址写进 client/_build.py，学生双击就连得上。"""
    import client

    mod = type(sys)("client._build")
    mod.SERVER = "111.170.33.3:3315"
    mod.BUILT_AT = "2026-09-20 10:00"
    monkeypatch.setitem(sys.modules, "client._build", mod)
    monkeypatch.setattr(client, "_build", mod, raising=False)
    assert shell.baked_server() == "111.170.33.3:3315"
    assert shell.build_stamp() == "2026-09-20 10:00"


def test_没打包时不装死(monkeypatch):
    """_build.py 是打包时生成的，不进仓库。开发机上导不到它，得当成"没烤地址"
    而不是抛异常 —— 否则直接跑源码就崩在登录页上。"""
    import client

    monkeypatch.delattr(client, "_build", raising=False)
    monkeypatch.setitem(sys.modules, "client._build", None)    # 导入时报 ImportError
    assert shell.baked_server() == ""
    assert shell.build_stamp() == "开发版"


def test_地址的优先顺序(monkeypatch):
    """文件名 > 本机保存 > 烤进去的。

    文件名排在保存值前面是故意的：教师端换了 IP，网管把 exe 改个名 ghost 出去，
    不该被各机器上那个过期的保存值顶掉。
    """
    monkeypatch.setattr(ui, "server_from_name", lambda: "1.1.1.1:1")
    monkeypatch.setattr(store, "remembered_server", lambda: "2.2.2.2:2")
    monkeypatch.setattr(ui, "baked_server", lambda: "3.3.3.3:3")
    assert ui.default_server() == "1.1.1.1:1"

    monkeypatch.setattr(ui, "server_from_name", lambda: "")
    assert ui.default_server() == "2.2.2.2:2"

    monkeypatch.setattr(store, "remembered_server", lambda: "")
    assert ui.default_server() == "3.3.3.3:3"

    monkeypatch.setattr(ui, "baked_server", lambda: "")
    assert ui.default_server() == ""        # 三个都没有：学生自己输


# ================================================================ ③ 默认落点
def test_默认答案包目录在LOCALAPPDATA下(tmp_path, monkeypatch):
    """`--out` 不给时答案包写哪儿。写在 exe 旁边的话，"只发一个 exe"就不成立了。"""
    import exam_client

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    out = exam_client.data_dir() / "答案包"
    assert out.parent == tmp_path / store.APP_DIR_NAME


def test_姓名登录版_开关烤得进去也读得回来(monkeypatch):
    """`build.py --name-login` 写 NAME_LOGIN = True；没打包时当普通版。"""
    import client

    mod = type(sys)("client._build")
    mod.NAME_LOGIN = True
    monkeypatch.setitem(sys.modules, "client._build", mod)
    monkeypatch.setattr(client, "_build", mod, raising=False)
    assert shell.baked_name_login() is True
    mod.NAME_LOGIN = False
    assert shell.baked_name_login() is False


def test_姓名登录版的文件名和普通版分得开():
    name = build.exe_name("192.168.1.8:8080", "-姓名登录-32位")
    assert name == "考试客户端-姓名登录-32位@192.168.1.8_8080.exe"
