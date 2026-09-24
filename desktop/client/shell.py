# -*- coding: utf-8 -*-
"""界面的公共件：配色、字体，以及几个到处都要用的小工具。

拆出来是因为 ui.py（主界面）和 exam_ui.py（答题页）都要用它们，而那两个
互相不该 import —— 答题页是主界面打开的，反过来引用会绕成一个环。
"""

from __future__ import annotations

import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import api

APP_NAME = "信息技术考试系统"
CLIENT_VER = "2.1"


def baked_server() -> str:
    """打包时烤进去的教师端地址（`build.py --server`）。

    **只发一个 exe 的关键一环。** 不烤的话，机房每台机器都得人工输一次地址；
    烤进去之后双击就能用，学生只填学号密码。

    地址变了也不用重打包 —— 见 `server_from_name()` 和登录页那个输入框。
    """
    try:
        from . import _build
        return str(getattr(_build, "SERVER", "") or "")
    except Exception:                                   # noqa: BLE001
        return ""


def server_from_name() -> str:
    """从 exe 的**文件名**里读地址。

    把 exe 改名成 `考试客户端@192.168.1.8_8080.exe`，程序就连那个地址。
    这是给"教师端换了 IP，但不想重新打包"准备的：网管改一个文件名，
    整个机房 ghost 过去就完事。

    写法：`@` 之后是地址，冒号在文件名里非法，所以用下划线代替端口分隔符。
    """
    try:
        name = Path(sys.executable if getattr(sys, "frozen", False) else __file__).stem
    except Exception:                                   # noqa: BLE001
        return ""
    if "@" not in name:
        return ""
    tail = name.split("@", 1)[1].strip()
    if not tail:
        return ""
    # 192.168.1.8_8080 → 192.168.1.8:8080；已经写成冒号的也认
    if "_" in tail and ":" not in tail:
        host, _, port = tail.rpartition("_")
        tail = f"{host}:{port}" if port.isdigit() else tail.replace("_", ".")
    return tail


def asset(name: str) -> Path | None:
    """找一个随 exe 一起打包的附带文件（图标之类）。找不到返回 None。

    onefile 的 exe 跑起来会把附带文件解到一个临时目录，路径在 `sys._MEIPASS`；
    直接跑源码时就在 desktop/ 下面。两种都要认 —— 开发时看得见图标，机房里
    也看得见。
    """
    roots = []
    box = getattr(sys, "_MEIPASS", "")
    if box:
        roots.append(Path(box))
    roots.append(Path(__file__).resolve().parent.parent)
    for root in roots:
        for rel in (name, f"图标/{name}"):
            got = root / rel
            if got.is_file():
                return got
    return None


def set_window_icon(root) -> None:
    """给窗口换上校徽图标。

    exe 本身的图标是打包时 `--icon` 定的，那管的是文件和任务栏上的图；**窗口
    左上角那个小图标是 Tk 自己的**（不设就是 Tk 那根羽毛），得在运行时设。
    图标坏了、缺了都不该影响考试，所以整段吞掉异常。
    """
    ico = asset("考试客户端.ico")
    if not ico:
        return
    try:
        root.iconbitmap(default=str(ico))
    except Exception:                                       # noqa: BLE001
        pass


def build_stamp() -> str:
    """这个 exe 是什么时候打的。

    机房里常常同时存在好几份 exe（ghost 过去的、U 盘拷的、上次留下的），
    "修好的问题怎么还在"十有八九是跑了旧的那份。**把构建时间显示在登录页**，
    一眼就能对上，不用去比文件日期。
    """
    try:
        from . import _build
        return _build.BUILT_AT
    except Exception:                                   # noqa: BLE001
        return "开发版"

BG = "#f2f5fa"
CARD = "#ffffff"
LINE = "#d8dfea"
BLUE = "#2c6fd1"
GREEN = "#2e9e5b"
RED = "#c8433a"
AMBER = "#b8860b"
GRAY = "#7a828e"
FONT = "Microsoft YaHei"


AI_HEAD = "好的，我来帮你完成。以下是根据你的要求生成的内容："
AI_TAIL = "\n\n以上内容由考试环境按模板生成，仅用于演示 AI 工具的使用流程。"


def ai_reply(ask: str) -> str:
    """按提问里的关键词拼一段像模像样的回复。**纯本地，不联网。**

    为什么不接真模型：考试机不该往外发请求；真模型的回复不可控，考场里出现
    什么内容没人兜得住；而且这类题考的是"会不会把需求说清楚"，AI 答得好不好
    不该由学生负责。

    措辞和网页版那个对话框（SimAi.vue 的 reply）保持一致 —— 学生在机房和在家
    练习时看到的是同一个东西。
    """
    t = str(ask or "")
    if re.search(r"代码|程序|python|编程|函数", t, re.I):
        body = ("\n\n# 参考代码\nfor i in range(1, 11):\n    print(i)\n\n"
                "说明：上面的程序按你的要求输出结果，可按需修改变量和范围。")
    elif re.search(r"表格|统计|清单|列出", t):
        body = ("\n\n序号 | 项目 | 说明\n1 | 第一项 | 按你的要求整理\n"
                "2 | 第二项 | 可继续补充\n3 | 第三项 | 可继续补充")
    elif re.search(r"图|海报|封面|设计|宣传画", t):
        body = ("\n\n已按你的描述给出设计思路：主体元素、配色、版式各一条，"
                "可据此再细化提示词。")
    elif re.search(r"翻译", t):
        body = "\n\n（译文）这里是按你提供的原文生成的译文，语序与用词已按中文习惯调整。"
    elif re.search(r"鉴赏|赏析|诗|词", t):
        body = ("\n\n可以从三个角度展开：一是字面意象与画面，二是手法与语言特色，"
                "三是情感与意境。结合具体词句逐层说明，最后落到整体感受。")
    else:
        n = len(re.sub(r"\s+", "", t))
        body = ("\n\n围绕你提出的要求，可以从三个方面展开：一是背景与意义，"
                "二是具体内容与做法，三是总结与延伸。"
                f"你的要求共 {n} 个字，其中的关键信息我已经全部采纳。")
    return AI_HEAD + body + AI_TAIL


def open_in_system(path: Path) -> str:
    """用系统默认方式打开：文件夹进资源管理器，文件进对应的程序。

    这一句就是"真机操作"和"网页仿真"的分界线。
    """
    path = Path(path)
    if not path.exists():
        return f"找不到：{path}"
    try:
        if os.name == "nt":
            os.startfile(str(path))            # noqa: S606
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return ""
    except OSError as exc:
        return f"打不开：{exc}"


class Why(str):
    """in_thread 交给回调的出错原因：就是一句中文，照旧当字符串用。

    多带一个 wait：服务器说「过 N 秒再来」（429）时的秒数，别的是 0。
    """

    wait = 0


def _why(text: str, wait: int = 0) -> Why:
    got = Why(text)
    got.wait = wait
    return got


def in_thread(widget, work, then, every: int = 60):
    """把慢活儿丢到后台线程，结果回主线程处理。

    网络不通时 urlopen 要等上好几秒。卡在主线程上窗口会变白、会"未响应"，
    学生以为程序挂了就会去点关闭 —— 考场里这是真会出事的。

    **工作线程一行 Tcl 都不碰**：它只把结果塞进队列，主线程 after 轮询取走。
    常见写法是在工作线程里调 `widget.after(0, ...)`，那其实是从非主线程操作
    Tcl 解释器 —— Tk 不是线程安全的，跑起来多半没事，偶尔就是一个没有栈的
    硬崩溃。考场里崩一次就是一个学生的一场考试。
    """
    box: queue.Queue = queue.Queue(maxsize=1)

    def run():
        try:
            box.put((work(), ""))
        except api.ApiError as exc:
            box.put((None, _why(str(exc), getattr(exc, "retry_after", 0))))
        except Exception as exc:                            # noqa: BLE001
            box.put((None, _why(f"出错了：{exc}")))

    def poll():
        try:
            got, err = box.get_nowait()
        except queue.Empty:
            try:
                widget.after(every, poll)
            except tk.TclError:
                pass                   # 窗口已经关了，不用管
            return
        then(got, err)

    threading.Thread(target=run, daemon=True).start()
    widget.after(every, poll)
