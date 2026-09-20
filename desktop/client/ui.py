# -*- coding: utf-8 -*-
"""学生端主界面：登录 → 侧边栏 + 首页 / 考试 / 打字练习。

## 和学生网页端长一样

同一批学生，一会儿在家用网页、一会儿在机房用 exe，两边的菜单、页面、说法都
对得上才不会懵。所以这里照搬网页端学生平台的结构：

    左边侧边栏   🏠 首页    📝 考试    ⌨ 打字练习
    右边内容区   打开默认停在首页
    顶栏         姓名班级 · 刷新 · 退出登录

数据也来自**同一套接口**（`/api/student/*`）—— 网页上看到的考试、打字记录、
首页数字，exe 里是同一份，不是另抄一遍。

## 登录是学号 + 密码

初始密码就是学号，和网页端一致。早先桌面端用的是"考号 + 姓名"，那样没法做
改密码 —— 没有密码可改。

## 答题不在这儿

点「开始考试」之后整页沉浸，没有侧边栏（考试中途点走太容易误操作），那一段在
`exam_ui.py`。
"""

from __future__ import annotations

import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import api, cleanup, package, snapshot, states, store
from .exam_ui import DoneFrame, ExamFrame
from .shell import (AMBER, APP_NAME, BG, BLUE, CARD, CLIENT_VER, FONT, GRAY,
                    GREEN, LINE, RED, baked_server, build_stamp, in_thread,
                    server_from_name)


def default_server() -> str:
    """登录页里那个地址栏默认填什么。**顺序是有讲究的：**

        ① exe 文件名里写的      网管刚改的名，是最新的决定
        ② 本机上次保存的        这台机器用过、连通过
        ③ 打包时烤进去的        出厂默认

    命令行 `--server` 比这三个都高，在 `ExamApp` 那儿直接盖掉。

    文件名排在保存值前面是故意的：教师端换了 IP，网管把 exe 改个名 ghost 出去，
    不该被各机器上那个过期的保存值顶掉。
    """
    return server_from_name() or store.remembered_server() or baked_server()

SIDE = "#22303f"                 # 侧边栏底色，比正文暗一档
SIDE_ON = "#2c6fd1"


# ================================================================ 登录
class LoginFrame(ttk.Frame):
    """教师端地址 + 学号 + 密码。"""

    def __init__(self, app):
        super().__init__(app.root, padding=0)
        self.app = app
        self.busy = False
        self._build()

    def _build(self):
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True)

        head = tk.Frame(wrap, bg=BLUE, height=96)
        head.pack(fill="x")
        head.pack_propagate(False)
        tk.Label(head, text=APP_NAME, bg=BLUE, fg="white",
                 font=(FONT, 20, "bold")).pack(pady=(22, 0))
        tk.Label(head, text="用学号和密码登录　·　初始密码就是学号", bg=BLUE,
                 fg="#d8e6ff", font=(FONT, 10)).pack()

        card = tk.Frame(wrap, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        card.place(relx=0.5, rely=0.53, anchor="center", width=470, height=300)

        self.vars = {}
        rows = [("server", "教师端地址", "如 192.168.1.8:8080"),
                ("no", "学　　号", "如 26070101"),
                ("password", "密　　码", "初始密码=学号")]
        for i, (key, label, hint) in enumerate(rows):
            y = 26 + i * 46
            tk.Label(card, text=label, bg=CARD, font=(FONT, 10)).place(x=30, y=y + 4)
            var = tk.StringVar()
            entry = tk.Entry(card, textvariable=var, font=(FONT, 12), relief="solid",
                             bd=1, highlightthickness=0,
                             show="●" if key == "password" else "")
            entry.place(x=118, y=y, width=240, height=30)
            entry.bind("<Return>", lambda _e: self.login())
            tk.Label(card, text=hint, bg=CARD, fg=GRAY,
                     font=(FONT, 8)).place(x=364, y=y + 7)
            self.vars[key] = var
            if key == "no":
                self.no_entry = entry
            if key == "server":
                self.server_entry = entry

        self.vars["server"].set(self.app.server or default_server())

        self.net_lbl = tk.Label(card, text="", bg=CARD, fg=GRAY, font=(FONT, 9), anchor="w")
        self.net_lbl.place(x=30, y=170, width=310)
        self.retry_btn = tk.Button(card, text="补传", font=(FONT, 9), relief="groove",
                                   command=self.do_retry)

        self.msg = tk.Label(card, text="", bg=CARD, fg=RED, font=(FONT, 9),
                            anchor="w", wraplength=410, justify="left")
        self.msg.place(x=30, y=192, width=410)

        self.login_btn = tk.Button(card, text="登 录", bg=BLUE, fg="white",
                                   font=(FONT, 12, "bold"), relief="flat",
                                   cursor="hand2", command=self.login)
        self.login_btn.place(x=30, y=230, width=410, height=34)

        tk.Button(card, text="没有网络？用本地考试包开考", font=(FONT, 8), relief="flat",
                  bg=CARD, fg=GRAY, cursor="hand2", command=self.offline
                  ).place(x=30, y=268, width=410, height=20)

        tk.Label(wrap, text=f"客户端 {CLIENT_VER}　构建 {build_stamp()}　"
                            "操作题在真实系统中完成",
                 bg=BG, fg=GRAY, font=(FONT, 8)).pack(side="bottom", pady=6)

        self.after(80, lambda: (self.no_entry if self.vars["server"].get()
                                else self.server_entry).focus_set())
        self.after(120, self.check_net)

    # ---------------- 服务器状态与补传 ----------------
    def check_net(self):
        pend = store.pending_uploads(self.app.out_dir)
        if pend:
            self.retry_btn.place(x=346, y=166, width=94, height=24)
        else:
            self.retry_btn.place_forget()

        server = api.norm(self.vars["server"].get())
        if not server:
            self.net_lbl.config(text="请填写教师端地址（问监考老师）", fg=GRAY)
            return
        self.net_lbl.config(text=f"正在连 {server} …", fg=GRAY)

        def done(ok, _err):
            tail = f"　有 {len(pend)} 份答卷没传上去" if pend else ""
            if ok:
                self.net_lbl.config(text=f"✓ 已连上教师端{tail}", fg=GREEN)
            else:
                self.net_lbl.config(text=f"✗ 连不上教师端，请叫监考老师{tail}", fg=AMBER)
        in_thread(self, lambda: api.ping(server), done)

    def do_retry(self):
        self.retry_btn.config(state="disabled", text="上传中")
        self.update_idletasks()
        done, total = self.app.retry_pending(api.norm(self.vars["server"].get()))
        self.retry_btn.config(state="normal", text="补传")
        messagebox.showinfo("补传", f"{total} 份里传上去了 {done} 份。"
                                    + ("" if done == total else "\n剩下的等网络好了再试。"))
        self.check_net()

    # ---------------- 登录 ----------------
    def login(self):
        if self.busy:
            return
        server = api.norm(self.vars["server"].get())
        no = self.vars["no"].get().strip()
        pwd = self.vars["password"].get()
        if not server:
            self.msg.config(text="请先填教师端地址，问监考老师")
            return
        if not no or not pwd:
            self.msg.config(text="学号和密码都要填（初始密码就是学号）")
            return

        self.busy = True
        self.msg.config(text="")
        self.login_btn.config(state="disabled", text="正在登录…")

        def done(got, err):
            self.busy = False
            self.login_btn.config(state="normal", text="登 录")
            if err:
                self.msg.config(text=err)
                return
            store.save_config(server=server)
            self.app.server = server
            self.app.token = got.get("access_token", "")
            self.app.student = student_of(got.get("student") or {})
            self.app.enter_shell()
        in_thread(self, lambda: api.login(server, no, pwd), done)

    # ---------------- 离线后路 ----------------
    def offline(self):
        """网真的不通时：拿老师导出来的 .ekb 开考，交卷存本机，事后补传。"""
        got = filedialog.askopenfilename(
            title="选择考试包", filetypes=[("考试包", "*" + package.EXAM_EXT),
                                           ("所有文件", "*.*")])
        if not got:
            return
        no = self.vars["no"].get().strip()
        if not no:
            self.msg.config(text="离线开考也要先填学号")
            return
        try:
            pack = package.ExamPackage(Path(got))
        except Exception as exc:                            # noqa: BLE001
            self.msg.config(text=f"这个考试包打不开：{exc}")
            return

        # 离线时服务器认不了人，只能靠包里的名单
        hit = next((r for r in pack.roster() if str(r.get("no")) == no), None)
        if pack.roster() and not hit:
            self.msg.config(text="名单里没有这个学号，请找监考老师")
            return
        self.app.student = {"no": no, "name": (hit or {}).get("name", no),
                            "cls": (hit or {}).get("cls", "")}
        self.app.server = api.norm(self.vars["server"].get()) or pack.server
        self.app.start_exam(pack)


def no_copy(widget) -> None:
    """把复制粘贴全堵上。

    打字练习**只能一个字一个字敲**：能复制原文、粘贴到答题框，速度和正确率
    就都是假的，这个练习也就没意义了。

    堵四条路，少一条都能绕过去：

      · Ctrl+C / Ctrl+V / Ctrl+X / Ctrl+A（还有大写的，CapsLock 开着时是大写）
      · 中键粘贴（X11 习惯，Tk 在 Windows 上也认）
      · 右键菜单
      · Tk 自带的 <<Cut>> <<Copy>> <<Paste>> 虚拟事件 —— 有些输入法和
        快捷键走的是这一层，只拦 Ctrl+ 字母拦不住
    """
    def block(_event=None):
        return "break"

    for key in ("<Control-c>", "<Control-C>", "<Control-v>", "<Control-V>",
                "<Control-x>", "<Control-X>", "<Control-a>", "<Control-A>",
                "<Control-Insert>", "<Shift-Insert>", "<Button-2>", "<Button-3>"):
        widget.bind(key, block)
    for virtual in ("<<Cut>>", "<<Copy>>", "<<Paste>>", "<<PasteSelection>>"):
        widget.bind(virtual, block)


def student_of(raw: dict) -> dict:
    """后端的学生字段换成客户端一直用的那三个键。"""
    return {"no": raw.get("student_no", ""), "name": raw.get("name", ""),
            "cls": raw.get("student_class", "")}


# ================================================================ 主界面（侧边栏）
class ShellFrame(ttk.Frame):
    """登录之后的壳子：左边侧边栏，右边内容区，**打开默认停在首页**。"""

    PAGES = [("home", "🏠", "首页"), ("exam", "📝", "考试"), ("typing", "⌨", "打字练习")]

    def __init__(self, app, page: str = "home"):
        super().__init__(app.root, padding=0)
        self.app = app
        self.page = page
        self.body = None
        self.reviewing: dict = {}          # 正在回看哪一场（"review" 页用）
        self._build()
        self.go(page)

    def _build(self):
        side = tk.Frame(self, bg=SIDE, width=168)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="学生平台", bg=SIDE, fg="white",
                 font=(FONT, 13, "bold")).pack(pady=(18, 4))
        s = self.app.student
        tk.Label(side, text=f"{s.get('name', '')}\n{s.get('cls', '')}", bg=SIDE,
                 fg="#93a4b7", font=(FONT, 9)).pack(pady=(0, 14))

        self.tabs = {}
        for key, icon, label in self.PAGES:
            b = tk.Button(side, text=f"  {icon}  {label}", bg=SIDE, fg="#cdd8e4",
                          font=(FONT, 11), relief="flat", anchor="w", bd=0,
                          activebackground=SIDE_ON, activeforeground="white",
                          cursor="hand2", command=lambda k=key: self.go(k))
            b.pack(fill="x", ipady=8)
            self.tabs[key] = b

        tk.Button(side, text="退出登录", bg=SIDE, fg="#93a4b7", font=(FONT, 9),
                  relief="flat", bd=0, cursor="hand2", activebackground=SIDE,
                  command=self.app.sign_out).pack(side="bottom", pady=12)

        right = tk.Frame(self, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        top = tk.Frame(right, bg=CARD, height=48, highlightbackground=LINE,
                       highlightthickness=1)
        top.pack(fill="x")
        top.pack_propagate(False)
        self.title_lbl = tk.Label(top, text="", bg=CARD, font=(FONT, 12, "bold"))
        self.title_lbl.pack(side="left", padx=18)
        # 刷新：考试是老师随时发布的，学生不该为了看见新考试去重开程序
        self.refresh_btn = tk.Button(top, text="⟳ 刷新", font=(FONT, 10), relief="groove",
                                     cursor="hand2", command=self.refresh)
        self.refresh_btn.pack(side="right", padx=16, pady=9)
        # 回看页上才出现：回到考试列表
        self.back_btn = tk.Button(top, text="← 返回", font=(FONT, 10), relief="groove",
                                  cursor="hand2", command=lambda: self.go("exam"))
        self.hint = tk.Label(top, text="", bg=CARD, fg=GRAY, font=(FONT, 9))
        self.hint.pack(side="right")

        self.holder = tk.Frame(right, bg=BG)
        self.holder.pack(fill="both", expand=True)

    def go(self, key: str, exam: dict | None = None):
        """换页。`review` 是「考试」下面的一层，不在侧边栏上单列。

        刷新走的也是这里，所以**回看页刷新一次就能看到老师刚批出来的分**。
        """
        self.page = key
        if key == "review":
            self.reviewing = exam or self.reviewing
        else:
            self.reviewing = {}
        lit = "exam" if key == "review" else key
        for k, b in self.tabs.items():
            b.config(bg=SIDE_ON if k == lit else SIDE,
                     fg="white" if k == lit else "#cdd8e4")
        names = dict((k, n) for k, _i, n in self.PAGES)
        self.title_lbl.config(
            text=names[lit] + (f"　·　回看：{self.reviewing.get('title', '')}"
                               if key == "review" else ""))
        self.back_btn.pack_forget()
        if key == "review":
            self.back_btn.pack(side="right", padx=(0, 6), pady=9)
        if self.body:
            self.body.destroy()
        if key == "review":
            self.body = ReviewPage(self.holder, self.app, self.reviewing)
        else:
            self.body = {"home": HomePage, "exam": ExamListPage,
                         "typing": TypingPage}[key](self.holder, self.app)
        self.body.pack(fill="both", expand=True)

    def refresh(self):
        """重新拉一遍当前页的数据。

        考试是老师随时发布的 —— 学生已经登录着，不该为了看见新考试去重开程序。
        """
        self.refresh_btn.config(state="disabled", text="刷新中")
        self.hint.config(text="")
        self.update_idletasks()
        self.go(self.page)
        self.refresh_btn.config(state="normal", text="⟳ 刷新")
        self.hint.config(text=f"已更新 {time.strftime('%H:%M:%S')}")


class Page(tk.Frame):
    """内容页的共同部分：一块放卡片的地方 + 一句状态提示。"""

    def __init__(self, parent, app):
        super().__init__(parent, bg=BG)
        self.app = app
        self.msg = tk.Label(self, text="正在加载…", bg=BG, fg=GRAY, font=(FONT, 10))
        self.msg.pack(anchor="w", padx=28, pady=(14, 0))
        self.box = tk.Frame(self, bg=BG)
        self.box.pack(fill="both", expand=True, padx=28, pady=10)
        self.load()

    def load(self):
        raise NotImplementedError

    def card(self, title: str = "") -> tk.Frame:
        c = tk.Frame(self.box, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        c.pack(fill="x", pady=6)
        if title:
            tk.Label(c, text=title, bg=CARD, font=(FONT, 12, "bold"),
                     anchor="w").pack(fill="x", padx=16, pady=(12, 4))
        return c


# ================================================================ 首页
class HomePage(Page):
    """个人信息 + 几个学习数字 + 改密码。和网页端首页一一对应。"""

    def load(self):
        def done(got, err):
            self.msg.config(text=err or "", fg=RED if err else GRAY)
            if err:
                return
            self.msg.pack_forget()
            self._show(got)
        in_thread(self, lambda: api.home(self.app.server, self.app.token), done)

    def _show(self, got: dict):
        who = got.get("student") or {}
        c = self.card()
        tk.Label(c, text=who.get("name", ""), bg=CARD,
                 font=(FONT, 16, "bold")).pack(anchor="w", padx=16, pady=(14, 0))
        tk.Label(c, text=f"学号 {who.get('student_no', '')}　"
                         f"{who.get('student_class', '')}",
                 bg=CARD, fg=GRAY, font=(FONT, 10)).pack(anchor="w", padx=16, pady=(0, 14))

        # 「已交卷」换成「平均分」：交没交卷，下面的考试列表上一眼就看得见，
        # 首页再数一遍没什么用；学生真正想知道的是"我平时考多少"。
        # 平均分**折成百分制**（各场卷面总分不一样），老师批完操作题，
        # 点一下刷新这个数就变。
        avg = got.get("exam_avg_score")
        nums = tk.Frame(self.box, bg=BG)
        nums.pack(fill="x", pady=4)
        for label, value in (("能参加的考试", got.get("exam_total", 0)),
                             ("平均分", f"{avg} 分" if avg is not None else "—"),
                             ("打字练习", got.get("typing_count", 0)),
                             ("最快速度", f"{got.get('typing_best_speed', 0)} 字/分"),
                             ("平均正确率", f"{got.get('typing_avg_accuracy', 0)}%")):
            cell = tk.Frame(nums, bg=CARD, highlightbackground=LINE, highlightthickness=1)
            cell.pack(side="left", fill="both", expand=True, padx=3)
            tk.Label(cell, text=str(value), bg=CARD, fg=BLUE,
                     font=(FONT, 15, "bold")).pack(pady=(12, 0))
            tk.Label(cell, text=label, bg=CARD, fg=GRAY,
                     font=(FONT, 9)).pack(pady=(0, 12))

        self._password_card()

    def _password_card(self):
        c = self.card("修改密码")
        tk.Label(c, text="初始密码就是学号，建议第一次登录后改掉。", bg=CARD, fg=GRAY,
                 font=(FONT, 9), anchor="w").pack(fill="x", padx=16)
        self.pwd = {}
        for key, label in (("old", "原密码"), ("new", "新密码"), ("again", "再输一遍")):
            row = tk.Frame(c, bg=CARD)
            row.pack(fill="x", padx=16, pady=3)
            tk.Label(row, text=label, bg=CARD, font=(FONT, 10), width=8,
                     anchor="w").pack(side="left")
            var = tk.StringVar()
            tk.Entry(row, textvariable=var, font=(FONT, 11), relief="solid", bd=1,
                     show="●", width=26).pack(side="left")
            self.pwd[key] = var

        self.pwd_msg = tk.Label(c, text="", bg=CARD, fg=RED, font=(FONT, 9), anchor="w")
        self.pwd_msg.pack(fill="x", padx=16, pady=(4, 0))
        self.pwd_btn = tk.Button(c, text="保存新密码", bg=BLUE, fg="white",
                                 font=(FONT, 10, "bold"), relief="flat", cursor="hand2",
                                 command=self.save_password)
        self.pwd_btn.pack(anchor="w", padx=16, pady=(6, 14), ipadx=14, ipady=3)

    def save_password(self):
        old, new, again = (self.pwd[k].get() for k in ("old", "new", "again"))
        if not old or not new:
            return self.pwd_msg.config(text="原密码和新密码都要填", fg=RED)
        if new != again:
            return self.pwd_msg.config(text="两次输入的新密码不一致", fg=RED)
        self.pwd_btn.config(state="disabled", text="保存中…")

        def done(_got, err):
            self.pwd_btn.config(state="normal", text="保存新密码")
            if err:
                return self.pwd_msg.config(text=err, fg=RED)
            for v in self.pwd.values():
                v.set("")
            self.pwd_msg.config(text="密码已修改，下次登录用新密码", fg=GREEN)
        in_thread(self, lambda: api.change_password(self.app.server, self.app.token,
                                                    old, new), done)


# ================================================================ 考试
class ExamListPage(Page):
    def load(self):
        self.exams = []

        def done(got, err):
            self.msg.config(text=err or "", fg=RED if err else GRAY)
            if err:
                return
            self.msg.pack_forget()
            self._show(got or [])
        in_thread(self, lambda: api.my_exams(self.app.server, self.app.token), done)

    def _show(self, exams: list):
        self.exams = exams
        if not exams:
            c = self.card()
            tk.Label(c, text="现在没有你能参加的考试", bg=CARD,
                     font=(FONT, 12, "bold")).pack(pady=(18, 4))
            tk.Label(c, text="老师还没发布，或者这场考试不是发给你们班的。\n"
                             "老师刚发的话，点右上角「刷新」再看看。",
                     bg=CARD, fg=GRAY, font=(FONT, 9), justify="center").pack(pady=(0, 18))
            return

        for e in exams:
            c = self.card()
            left = tk.Frame(c, bg=CARD)
            left.pack(side="left", fill="x", expand=True, padx=16, pady=12)
            tk.Label(left, text=e.get("title", "考试"), bg=CARD,
                     font=(FONT, 13, "bold"), anchor="w").pack(fill="x")
            bits = [f"{e.get('total', 0)} 题"]
            if e.get("submitted"):
                bits.append("已交卷")
                if e.get("submitted_at"):
                    bits.append(str(e["submitted_at"])[:16].replace("T", " "))
                if e.get("score") is None and not e.get("show_score"):
                    bits.append("成绩由老师公布")
                if e.get("pending_manual"):
                    bits.append("操作题待老师评阅")
            tk.Label(left, text="　·　".join(bits), bg=CARD, fg=GRAY,
                     font=(FONT, 9), anchor="w").pack(fill="x")

            can = (not e.get("submitted")) or e.get("allow_retake")
            if can:
                tk.Button(c, text="开始考试", bg=BLUE, fg="white",
                          font=(FONT, 11, "bold"), relief="flat", cursor="hand2",
                          width=12, command=lambda x=e: self.start(x)
                          ).pack(side="right", padx=16)
            else:
                # 交过卷就不该再有「开始考试」—— 点下去只会撞一个 409。
                # 换成「查看」：看自己写了什么，对错要等老师放开才显示。
                tk.Button(c, text="查 看", font=(FONT, 11, "bold"), relief="groove",
                          cursor="hand2", width=12,
                          command=lambda x=e: self.app.frame.go("review", x)
                          ).pack(side="right", padx=16)
            self._score_badge(c, e)

    def _score_badge(self, card, e: dict):
        """卷面右边那个分数。**考完就能看见自己考了多少**，这是学生最想知道的。

        分数来自服务器，不是本机算的 —— 所以老师改完分，点一下刷新这里就跟着变。
        老师关掉「交卷后看分数」时服务器不发分数，这里也就什么都不显示。
        """
        if not e.get("submitted") or e.get("score") is None:
            return
        box = tk.Frame(card, bg=CARD)
        box.pack(side="right", padx=(0, 6))
        pending = e.get("pending_manual")
        tk.Label(box, text=str(e["score"]), bg=CARD, fg=AMBER if pending else GREEN,
                 font=(FONT, 20, "bold")).pack()
        full = e.get("full_score")
        tk.Label(box, text=(f"/ {full} 分" if full else "分") + ("（未批完）" if pending else ""),
                 bg=CARD, fg=GRAY, font=(FONT, 8)).pack()

    def start(self, e: dict):
        self.msg.pack(anchor="w", padx=28, pady=(14, 0))
        self.msg.config(text=f"正在取卷：{e.get('title', '')} …", fg=GRAY)
        self.update_idletasks()
        dest = self.app.out_dir / f"考试包-{str(e.get('token', ''))[:8]}{package.EXAM_EXT}"

        def work():
            path = api.fetch_exam(self.app.server, e.get("token", ""), dest)
            return package.ExamPackage(path)

        def done(pack, err):
            if err:
                return self.msg.config(text=err, fg=RED)
            self.app.start_exam(pack)
        in_thread(self, work, done)


# ================================================================ 交卷后回看
class ReviewPage(Page):
    """交过卷之后回看自己写了什么。

    **默认不显示对错。** 考试常常分批考（上午一个班、下午一个班），先考完的
    学生要是能看到对错，题目当场就传出去了。对错、每题得分、正确答案一律等
    老师在网页后台打开「考后可看答案」之后才出现 —— 而且是**服务器决定发不发**，
    不是客户端自己藏起来：exe 能被反编译，藏在客户端等于没藏。
    """

    def __init__(self, parent, app, exam: dict):
        self.exam = exam or {}
        super().__init__(parent, app)

    def load(self):
        def done(got, err):
            self.msg.config(text=err or "", fg=RED if err else GRAY)
            if err:
                return
            self.msg.pack_forget()
            self._show(got or {})
        in_thread(self, lambda: api.review(self.app.server, self.app.token,
                                           self.exam.get("id")), done)

    def _show(self, got: dict):
        head = self.card()
        tk.Label(head, text=got.get("title") or self.exam.get("title", "考试"), bg=CARD,
                 font=(FONT, 14, "bold"), anchor="w").pack(fill="x", padx=16, pady=(14, 2))
        line = [f"交卷 {str(got.get('submitted_at') or '')[:16].replace('T', ' ')}"]
        if got.get("score") is not None:
            line.append(f"得分 {got['score']}/{got.get('full_score', '')}")
        else:
            line.append("成绩由老师统一公布")
        if got.get("pending_manual"):
            line.append("操作题还在评阅中，分数会变")
        if not got.get("show_answer"):
            line.append("老师尚未开放答案，本页只显示你的作答")
        tk.Label(head, text="　·　".join(line), bg=CARD, fg=GRAY, font=(FONT, 9),
                 anchor="w").pack(fill="x", padx=16, pady=(0, 12))

        wrap = tk.Frame(self.box, bg=BG)
        wrap.pack(fill="both", expand=True)
        canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        bar = tk.Scrollbar(wrap, command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>",
                   lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw", width=760)
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>",
                        lambda ev: canvas.yview_scroll(int(-ev.delta / 120), "units"))

        for g in got.get("groups") or []:
            if g.get("name"):
                tk.Label(inner, text=g["name"], bg=BG, fg=BLUE,
                         font=(FONT, 11, "bold"), anchor="w").pack(fill="x", pady=(10, 2))
            for q in g.get("items") or []:
                self._one(inner, q, bool(got.get("show_answer")))

    def _one(self, parent, q: dict, told: bool):
        c = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        c.pack(fill="x", pady=3)
        top = tk.Frame(c, bg=CARD)
        top.pack(fill="x", padx=12, pady=(10, 0))
        tk.Label(top, text=f"{q.get('no', '')}．{q.get('type', '')}", bg=CARD, fg=GRAY,
                 font=(FONT, 9)).pack(side="left")
        tk.Label(top, text=f"{q.get('score', 0)} 分", bg=CARD, fg=GRAY,
                 font=(FONT, 9)).pack(side="right")
        if told:
            ok = q.get("ok")
            mark = "✓ 正确" if ok else ("✗ 错误" if ok is False else "已评阅")
            tk.Label(top, text=f"{mark}　得 {q.get('earned', 0)} 分", bg=CARD,
                     fg=GREEN if ok else (RED if ok is False else AMBER),
                     font=(FONT, 9, "bold")).pack(side="right", padx=10)

        tk.Label(c, text=q.get("stem", ""), bg=CARD, font=(FONT, 11), anchor="w",
                 justify="left", wraplength=700).pack(fill="x", padx=12, pady=(2, 4))
        if q.get("image_url"):
            # 配图只在考试包里有（转过 PNG 的那份），回看时手上没有。
            # 不声明一句的话，"请仔细读图"的题在这儿看着像少了东西。
            tk.Label(c, text="（本题有配图，考试时显示在题目下方）", bg=CARD, fg=GRAY,
                     font=(FONT, 9), anchor="w").pack(fill="x", padx=12)
        for o in q.get("options") or []:
            tk.Label(c, text=f"{o.get('label', '')}．{o.get('content', '')}", bg=CARD,
                     fg="#4a5563", font=(FONT, 10), anchor="w", justify="left",
                     wraplength=690).pack(fill="x", padx=24)

        mine = str(q.get("mine") or "").strip()
        tk.Label(c, text="我的作答：" + (mine or "（未作答）"), bg=CARD,
                 fg=BLUE if mine else GRAY, font=(FONT, 10, "bold"), anchor="w",
                 justify="left", wraplength=700).pack(fill="x", padx=12, pady=(6, 0))
        if told:
            if q.get("answer"):
                tk.Label(c, text="正确答案：" + str(q["answer"]), bg=CARD, fg=GREEN,
                         font=(FONT, 10), anchor="w", justify="left",
                         wraplength=700).pack(fill="x", padx=12)
            for ck in q.get("checks") or []:
                tk.Label(c, text=("　✓ " if ck.get("ok") else "　✗ ") + ck.get("desc", ""),
                         bg=CARD, fg=GREEN if ck.get("ok") else RED, font=(FONT, 9),
                         anchor="w", justify="left", wraplength=690).pack(fill="x", padx=12)
        tk.Frame(c, bg=CARD, height=8).pack()


# ================================================================ 打字练习
class TypingPage(Page):
    """照搬网页端打字训练：取一段文本，照着敲，交成绩。

    速度、正确率、星级**一律由后端算** —— 客户端只报"敲了多少、对了多少、
    用了多久"，和网页端一个口径，两边的成绩才能放进同一张表里比。
    """

    # 只做中文和英文：取练习文本的接口就这两种。网页端还有一个「键盘」模块，
    # 那个的文本是前端现生成的，搬过来得另写一套，先不做
    MODES = ["中文", "英文"]

    def load(self):
        self.started = None
        self.passage = ""
        self.mode = tk.StringVar(value="中文")
        self.level = tk.StringVar(value="")

        bar = tk.Frame(self.box, bg=BG)
        bar.pack(fill="x", pady=(0, 6))
        tk.Label(bar, text="练习模式", bg=BG, fg=GRAY, font=(FONT, 10)).pack(side="left")
        for m in self.MODES:
            tk.Radiobutton(bar, text=m, value=m, variable=self.mode, bg=BG,
                           font=(FONT, 10), tristatevalue="\x00",
                           command=self.fetch).pack(side="left", padx=6)
        tk.Label(bar, text="难度", bg=BG, fg=GRAY,
                 font=(FONT, 10)).pack(side="left", padx=(14, 4))
        self.level_box = ttk.Combobox(bar, textvariable=self.level, width=10,
                                      state="readonly")
        self.level_box.pack(side="left")
        self.level_box.bind("<<ComboboxSelected>>", lambda _e: self.fetch())
        tk.Button(bar, text="换一段", font=(FONT, 9), relief="groove",
                  command=self.fetch).pack(side="left", padx=10)

        c = self.card()
        self.text_view = tk.Text(c, height=5, font=(FONT, 12), wrap="word",
                                 relief="flat", bg="#fbfcfe")
        self.text_view.pack(fill="x", padx=14, pady=12)
        self.text_view.config(state="disabled")

        tk.Label(self.box, text="在下面照着敲：", bg=BG, fg=GRAY,
                 font=(FONT, 10), anchor="w").pack(fill="x", pady=(8, 2))
        self.entry = tk.Text(self.box, height=5, font=(FONT, 12), wrap="word",
                             relief="solid", bd=1)
        self.entry.pack(fill="x")
        self.entry.bind("<Key>", self.on_key)
        no_copy(self.entry)
        no_copy(self.text_view)      # 原文也不让复制，否则直接粘过去就满分了

        row = tk.Frame(self.box, bg=BG)
        row.pack(fill="x", pady=10)
        self.live = tk.Label(row, text="还没开始", bg=BG, fg=GRAY, font=(FONT, 10))
        self.live.pack(side="left")
        tk.Button(row, text="交成绩", bg=BLUE, fg="white", font=(FONT, 10, "bold"),
                  relief="flat", cursor="hand2", command=self.submit
                  ).pack(side="right", ipadx=14, ipady=3)
        self.load_levels()

    def load_levels(self):
        """难度是后端配的（config.yaml），**不在客户端写死** —— 学校改了难度分档，
        网页和 exe 得跟着变。"""
        def done(got, err):
            if err:
                return self.msg.config(text=err, fg=RED)
            levels = list((got or {}).get("difficulties") or [])
            self.level_box.config(values=levels)
            self.level.set((got or {}).get("default_difficulty") or
                           (levels[0] if levels else ""))
            self.fetch()
        in_thread(self, lambda: api.typing_config(self.app.server), done)

    def fetch(self):
        self.msg.pack(anchor="w", padx=28, pady=(14, 0))
        self.msg.config(text="正在取练习文本…", fg=GRAY)

        def done(got, err):
            if err:
                return self.msg.config(text=err, fg=RED)
            self.msg.pack_forget()
            self.passage = str(got or "")
            self.text_view.config(state="normal")
            self.text_view.delete("1.0", "end")
            self.text_view.insert("end", self.passage or "（这个模式还没有练习文本）")
            self.text_view.config(state="disabled")
            self.entry.delete("1.0", "end")
            self.started = None
            self.live.config(text="还没开始", fg=GRAY)
        # **Tk 变量要在主线程读好再传进去。** 写成
        # `lambda: api.typing_passage(..., self.mode.get())` 的话，那个 .get()
        # 是在工作线程里执行的 —— 那是从非主线程碰 Tcl，直接报
        # "main thread is not in main loop"，而且错误被吞在回调里，界面只会
        # 一直停在"正在加载"。踩过。
        mode, level = self.mode.get(), self.level.get()
        in_thread(self, lambda: api.typing_passage(self.app.server, mode, level), done)

    def on_key(self, _event=None):
        # 第一下敲键才开始计时 —— 从取到文本就计时的话，学生看题的时间也算进去了
        if self.started is None:
            self.started = time.time()
        self.after(10, self.tick)

    def tick(self):
        if self.started is None:
            return
        typed = self.entry.get("1.0", "end-1c")
        right = sum(1 for a, b in zip(typed, self.passage) if a == b)
        used = max(0.001, time.time() - self.started)
        self.live.config(text=f"已敲 {len(typed)} 字　正确 {right}　"
                              f"用时 {int(used)} 秒", fg=GRAY)

    def submit(self):
        typed = self.entry.get("1.0", "end-1c")
        if self.started is None or not typed.strip():
            return self.live.config(text="先敲几个字再交", fg=AMBER)
        right = sum(1 for a, b in zip(typed, self.passage) if a == b)
        used = max(0.001, time.time() - self.started)

        def done(got, err):
            if err:
                return self.live.config(text=err, fg=RED)
            got = got or {}
            self.live.config(
                text=f"已记录：{got.get('speed', 0)} 字/分　正确率 "
                     f"{got.get('accuracy', 0)}%　{'★' * int(got.get('stars', 0) or 0)}",
                fg=GREEN)
            self.started = None
        mode, level = self.mode.get(), self.level.get()      # 同上：主线程里读
        in_thread(self, lambda: api.typing_submit(
            self.app.server, self.app.student, mode, level,
            len(typed), right, used), done)


# ================================================================ 应用
class ExamApp:
    def __init__(self, exam_root: Path, out_dir: Path, server: str = "", root=None):
        # root 留给自检用：一个进程里反复 Tk() 会把 Tcl 弄坏（报错里的文件名
        # 每次都不一样，一看就是内存被踩了）。正式跑的时候它就是 None。
        self.root = root or tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("1000x680")
        self.root.minsize(900, 620)
        self.root.configure(bg=BG)
        self.package: package.ExamPackage | None = None
        self.pictures: dict = {}          # 题目配图：{包里的文件名: 本地路径}
        self.student: dict = {}
        self.token = ""
        self.exam_root = Path(exam_root)
        self.out_dir = Path(out_dir)
        self.server = api.norm(server)
        self.frame: ttk.Frame | None = None
        self.swap(LoginFrame(self))
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def swap(self, frame: ttk.Frame):
        if self.frame:
            self.frame.destroy()
        self.frame = frame
        frame.pack(fill="both", expand=True)

    def enter_shell(self, page: str = "home"):
        """登录之后进主界面，**默认停在首页**。"""
        self.swap(ShellFrame(self, page))

    def sign_out(self):
        self.token = ""
        self.student = {}
        self.swap(LoginFrame(self))

    def start_exam(self, pack: package.ExamPackage):
        """铺考场，然后进答题界面。

        **每场考试都是全新环境**：先把上一场留下的东西连窗口一起清掉，再铺。
        不先关窗口的话，上一场没关的 WPS 还锁着文档，清不干净，这一场就铺不出来
        （症状是"准备考场失败"，得人工去关程序）。
        """
        self.package = pack
        self.server = self.server or pack.server
        try:
            cleanup.wipe(self.exam_root)               # 关掉上一场还开着的文件再清
            snapshot.clear_root(self.exam_root, force=True)
            snapshot.mark_root(self.exam_root)
            pack.deploy_files(self.exam_root)          # 纯客观题的卷子铺 0 个，正常
            # 配图摊到临时目录：它不是考场素材，混进考试文件夹会被快照拍进去
            self.pictures = pack.deploy_images(self.out_dir / "配图")
        except Exception as exc:                            # noqa: BLE001
            messagebox.showerror("准备考场失败",
                                 f"{exc}\n\n考试文件夹：{self.exam_root}\n请叫监考老师处理。")
            return
        self.swap(ExamFrame(self))

    def finish(self, path: Path, shot: dict, auto: bool,
               uploaded: bool = False, msg: str = "",
               clean: bool = True, left: list | None = None):
        self.swap(DoneFrame(self, path, shot, auto, uploaded, msg, clean, left))

    def back_to_shell(self):
        """交完卷回主界面。登录过就回去，离线开考的就只能退出程序。"""
        if self.token:
            self.enter_shell("exam")
        else:
            self.root.destroy()

    # ---------------- 上传 ----------------
    def upload(self, path: Path, answers: dict | None, got: dict | None = None,
               server: str = "") -> tuple[bool, str]:
        """把一份答卷传到教师端。

        answers 传 None 表示"补传"：**要交的东西全部从那个 .ans 里读** ——
        客观题作答、每道操作题的终态、考试口令，一样不少。所以补传不依赖当前
        有没有打开考试包，也**不再回头看考试文件夹**（那时候文件早被下一场清掉了）。
        """
        server = api.norm(server) or self.server
        if not server:
            return False, "没有教师端地址"

        student = self.student
        token = self.package.token if self.package else ""

        if answers is None:
            try:
                answer, _shot = package.read_answer(path)
            except Exception as exc:                        # noqa: BLE001
                return False, f"读不了本地答案包：{exc}"
            answers = answer.get("answers") or {}
            student = answer.get("student") or student
            token = answer.get("token") or token
            got = answer.get("states") or {}

        if not token:
            return False, "这份答卷里没有考试口令，只能由老师手工收取"

        ok, msg, _ = api.submit(server, token, student,
                                states.payload(answers, got or {}))
        store.mark_uploaded(self.out_dir, path.name, ok, msg)
        return ok, msg

    def retry_pending(self, server: str = "") -> tuple[int, int]:
        """把这台机器上没传上去的答卷再传一遍。返回 (成功数, 总数)。"""
        todo = store.pending_uploads(self.out_dir)
        done = 0
        for p in todo:
            ok, _ = self.upload(p, None, server=server)
            done += 1 if ok else 0
        return done, len(todo)

    def on_close(self):
        if isinstance(self.frame, ExamFrame) and not self.frame.submitted:
            if not messagebox.askyesno("退出", "考试还没交卷，确定要退出吗？\n"
                                               "（答案已存草稿，重开可以接着考）"):
                return
        self.root.destroy()

    def run(self):
        self.root.mainloop()
