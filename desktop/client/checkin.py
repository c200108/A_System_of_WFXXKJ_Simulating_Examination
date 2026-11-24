# -*- coding: utf-8 -*-
"""课堂签到（学生端 4.15.0，配合服务端 2.24.0）。

登录后（侧边栏那个壳子在的时候）每隔几秒问一次教师端「有没有签到」。老师在班级详情里发起签到，
这边就弹出签到框并**锁住整个窗口**：选自己的座号、点「签到」才能接着用；签到时间到了框自己关掉。
签到时间里才登录的，问到的就是剩下的时间。

一台电脑一次签到只能签一个人（服务端按设备号认）：给自己签完再换别人的号登录，签不了。

按机器号自动认座（4.16.0，服务端 2.26.0）：问的时候带上电脑名和内网 IP。服务端按老师设的认座规则
（电脑名最后一段 / 末尾数字 / IP 末段）或「绑座」认得出这台电脑的座号，就**直接签上**，这边不弹选择框，
只在右下角提示几秒；认出来了但签不上（同一个座号被另一台电脑签了），弹框只给这一个座号、写明原因。
老师开了绑座模式、这台电脑还没绑，弹「这台电脑是几号座位」让选一次（能关）。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import api
from .shell import BLUE, CARD, FONT, GRAY, GREEN, RED, in_thread

FIRST = 1500            # 登录后多久问第一次（毫秒）
IDLE = 5000             # 服务端没说的话，多久问一次


class Watcher:
    """挂在登录后的壳子上：定时问、弹框、关框。壳子销毁时调 stop()。"""

    def __init__(self, shell):
        self.shell = shell
        self.app = shell.app
        self.job = None
        self.busy = False
        self.dialog: CheckinDialog | None = None
        self.binder: BindDialog | None = None
        self.notice = None
        self.told: set = set()          # 已经提示过「自动签到了」的签到 id
        self.bind_off = False           # 学生把绑座框关了：这一轮绑座模式里不再弹
        self.stopped = False
        self.job = shell.after(FIRST, self.tick)

    def stop(self):
        self.stopped = True
        if self.job:
            try:
                self.shell.after_cancel(self.job)
            except tk.TclError:
                pass
        if self.dialog:
            self.dialog.close()
        if self.binder:
            self.binder.close()
        self._drop_notice()

    def later(self, ms: int):
        if not self.stopped:
            self.job = self.shell.after(ms, self.tick)

    def tick(self):
        self.job = None
        if self.stopped or self.busy or not self.app.token:
            return self.later(IDLE)
        self.busy = True
        server, token = self.app.server, self.app.token

        def done(got, err):
            self.busy = False
            if self.stopped:
                return
            if err or not isinstance(got, dict):
                return self.later(IDLE)          # 连不上 / 老服务端没这个接口：照常用，过会儿再问
            self.show(got)
            self.later(max(2, int(got.get("poll") or 5)) * 1000)
        in_thread(self.shell, lambda: api.checkin_status(server, token), done)

    def show(self, got: dict):
        need = got.get("active") and not got.get("signed")
        if need and not self.dialog:
            self.dialog = CheckinDialog(self, got)
        elif need:
            self.dialog.update_from(got)
        elif self.dialog:
            self.dialog.close()
        signed = got.get("signed") or {}
        if signed.get("limit") and got.get("checkin_id") not in self.told:
            self.told.add(got.get("checkin_id"))
            self.tell("你已经在两台电脑上签过到了，这台电脑不再签到", ms=6000, bg=RED)
        elif signed.get("how") in ("auto", "bind") and got.get("checkin_id") not in self.told:
            self.told.add(got.get("checkin_id"))
            self.tell(f"已按这台电脑的座号自动签到：{signed.get('seat', '')}")
        bind = got.get("bind")
        if not bind:
            self.bind_off = False
            if self.binder:
                self.binder.close()
        elif self.binder:
            self.binder.update_from(bind)
        elif not need and not self.bind_off:
            self.binder = BindDialog(self, bind)

    def tell(self, text: str, ms: int = 4000, bg: str = GREEN):
        """右下角提示几秒，不抢焦点、不锁窗口。"""
        self._drop_notice()
        root = self.app.root
        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=bg)
        tk.Label(win, text=text, bg=bg, fg="white", font=(FONT, 11, "bold"), padx=18, pady=10).pack()
        win.update_idletasks()
        x = root.winfo_rootx() + root.winfo_width() - win.winfo_width() - 24
        y = root.winfo_rooty() + root.winfo_height() - win.winfo_height() - 24
        win.geometry(f"+{max(0, x)}+{max(0, y)}")
        self.notice = win
        win.after(ms, self._drop_notice)

    def _drop_notice(self):
        if self.notice is not None:
            try:
                self.notice.destroy()
            except tk.TclError:
                pass
            self.notice = None


class CheckinDialog:
    """签到框：模态、置顶、关不掉，选座号签到。"""

    def __init__(self, watcher: Watcher, got: dict):
        self.w = watcher
        root = watcher.app.root
        self.win = tk.Toplevel(root)
        self.win.title("课堂签到")
        self.win.configure(bg=CARD)
        self.win.resizable(False, False)
        self.win.transient(root)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self.nag)     # 点 × 不让关
        self.checkin_id = got.get("checkin_id")
        self.left = int(got.get("remaining") or 0)
        self.remind = int(got.get("remind") or 60)
        self.red = False
        self.sending = False
        self.tick_job = None

        # 外面一圈边框：快结束了还没签就变红（4.16.0）
        self.frame = tk.Frame(self.win, bg=CARD, padx=4, pady=4)
        self.frame.pack(fill="both", expand=True)
        box = tk.Frame(self.frame, bg=CARD, padx=22, pady=16)
        box.pack(fill="both", expand=True)
        self.title = tk.Label(box, text="老师发起了课堂签到", bg=CARD, font=(FONT, 14, "bold"))
        self.title.pack(anchor="w", pady=(0, 12))
        s = watcher.app.student or {}
        tk.Label(box, text=f"我是：{s.get('name', '')}", bg=CARD, font=(FONT, 11)).pack(anchor="w")

        row = tk.Frame(box, bg=CARD)
        row.pack(anchor="w", pady=(10, 4))
        tk.Label(row, text="我的座号", bg=CARD, font=(FONT, 11)).pack(side="left")
        self.seat = tk.StringVar()
        self.combo = ttk.Combobox(row, textvariable=self.seat, state="readonly", width=12,
                                  font=(FONT, 11))
        self.combo.pack(side="left", padx=8)
        self.btn = tk.Button(row, text="签 到", bg=BLUE, fg="white", font=(FONT, 11, "bold"),
                             relief="flat", cursor="hand2", command=self.send)
        self.btn.pack(side="left", ipadx=12)

        self.msg = tk.Label(box, text="", bg=CARD, fg=GRAY, font=(FONT, 10), wraplength=360,
                            justify="left")
        self.msg.pack(anchor="w", pady=(8, 0))
        self.clock = tk.Label(box, text="", bg=CARD, fg=RED, font=(FONT, 10))
        self.clock.pack(anchor="w", pady=(6, 0))
        tk.Label(box, text="签到完成之前不能使用客户端。看座位上贴的座号选，不要选别人的。",
                 bg=CARD, fg=GRAY, font=(FONT, 9)).pack(anchor="w", pady=(10, 0))

        self.update_from(got)
        self.win.update_idletasks()
        x = root.winfo_rootx() + max(0, (root.winfo_width() - self.win.winfo_width()) // 2)
        y = root.winfo_rooty() + max(0, (root.winfo_height() - self.win.winfo_height()) // 3)
        self.win.geometry(f"+{x}+{y}")
        try:
            self.win.grab_set()                 # 锁住主窗口
        except tk.TclError:
            pass
        self.win.focus_force()
        self.count()

    def update_from(self, got: dict):
        """每次问回来刷新：剩余时间、哪些座号还空着（别人刚签走的就从下拉框里拿掉）。"""
        self.checkin_id = got.get("checkin_id", self.checkin_id)
        self.left = int(got.get("remaining") or 0)
        self.remind = int(got.get("remind") or self.remind)
        auto = got.get("auto") or {}
        if auto.get("seat"):
            # 认出了这台电脑的座号但签不上：只能签这个座号，原因写给学生看
            self.combo.config(values=[auto["seat"]])
            self.seat.set(auto["seat"])
            self.msg.config(text=f"这台电脑是 {auto['seat']} 号座位，{auto.get('error') or '没签上'}", fg=RED)
            return
        free = [x["seat"] for x in got.get("seats") or [] if not x.get("taken")]
        self.combo.config(values=free)
        if self.seat.get() and self.seat.get() not in free:
            self.seat.set("")
            self.msg.config(text="你刚才选的座号被别人签走了，请重新选", fg=RED)
        if not free:
            self.msg.config(text="座次表里的座号都被签完了，请找老师", fg=RED)
        elif got.get("elsewhere") and not self.msg.cget("text"):
            self.msg.config(text=f"你在别的电脑上签过（{'、'.join(got['elsewhere'])}），换到这台电脑要在这里再签一次",
                            fg=GRAY)

    def count(self):
        if self.left <= 0:
            self.clock.config(text="签到时间到了")
            return
        m, s = divmod(self.left, 60)
        self.clock.config(text=f"剩余时间 {m:02d}:{s:02d}")
        if self.left <= self.remind and not self.red:
            self.red = True               # 快结束了：边框变红、标题改成催签
            self.frame.config(bg=RED)
            self.title.config(text="签到快结束了，请马上签到！", fg=RED)
            self.clock.config(font=(FONT, 12, "bold"))
            try:
                self.win.deiconify()
                self.win.lift()
            except tk.TclError:
                pass
        self.left -= 1
        self.tick_job = self.win.after(1000, self.count)

    def nag(self):
        self.msg.config(text="请先选座号签到，签完这个框会自己关掉", fg=RED)

    def send(self):
        seat = self.seat.get().strip()
        if not seat:
            return self.msg.config(text="先在下拉框里选你的座号", fg=RED)
        if self.sending:
            return
        self.sending = True
        self.btn.config(state="disabled")
        self.msg.config(text="正在签到…", fg=GRAY)
        app, cid = self.w.app, self.checkin_id

        def done(got, err):
            self.sending = False
            try:
                self.btn.config(state="normal")
            except tk.TclError:
                return
            if err:
                return self.msg.config(text=str(err), fg=RED)
            self.msg.config(text=f"签到成功：座号 {got.get('seat', seat)}", fg=GREEN)
            self.win.after(900, self.close)
        in_thread(self.win, lambda: api.checkin_sign(app.server, app.token, cid, seat), done)

    def close(self):
        if self.w.dialog is self:
            self.w.dialog = None
        try:
            if self.tick_job:
                self.win.after_cancel(self.tick_job)
            self.win.grab_release()
            self.win.destroy()
        except tk.TclError:
            pass


class BindDialog:
    """绑座模式（4.16.0）：老师开着的时候，这台电脑还没绑座号就弹出来选一次。能关，不锁窗口。"""

    def __init__(self, watcher: Watcher, bind: dict):
        self.w = watcher
        root = watcher.app.root
        self.win = tk.Toplevel(root)
        self.win.title("绑定座号")
        self.win.configure(bg=CARD)
        self.win.resizable(False, False)
        self.win.transient(root)
        self.win.attributes("-topmost", True)
        self.win.protocol("WM_DELETE_WINDOW", self.dismiss)
        self.sending = False

        box = tk.Frame(self.win, bg=CARD, padx=26, pady=20)
        box.pack(fill="both", expand=True)
        tk.Label(box, text="老师在给机房的电脑绑座号", bg=CARD, font=(FONT, 14, "bold")).pack(anchor="w", pady=(0, 10))
        tk.Label(box, text=f"这台电脑：{api.HOST_NAME or '（没有电脑名）'}", bg=CARD, fg=GRAY,
                 font=(FONT, 10)).pack(anchor="w")
        row = tk.Frame(box, bg=CARD)
        row.pack(anchor="w", pady=(10, 4))
        tk.Label(row, text="这台电脑的座号", bg=CARD, font=(FONT, 11)).pack(side="left")
        self.seat = tk.StringVar()
        self.combo = ttk.Combobox(row, textvariable=self.seat, state="readonly", width=10, font=(FONT, 11))
        self.combo.pack(side="left", padx=8)
        self.btn = tk.Button(row, text="绑 定", bg=BLUE, fg="white", font=(FONT, 11, "bold"),
                             relief="flat", cursor="hand2", command=self.send)
        self.btn.pack(side="left", ipadx=12)
        self.msg = tk.Label(box, text="", bg=CARD, fg=GRAY, font=(FONT, 10), wraplength=360, justify="left")
        self.msg.pack(anchor="w", pady=(8, 0))
        tk.Label(box, text="看桌上贴的座号选。绑好以后签到时这台电脑自动签到这个座位，不用再选。",
                 bg=CARD, fg=GRAY, font=(FONT, 9), wraplength=360, justify="left").pack(anchor="w", pady=(10, 0))
        self.update_from(bind)
        self.win.update_idletasks()
        x = root.winfo_rootx() + max(0, (root.winfo_width() - self.win.winfo_width()) // 2)
        y = root.winfo_rooty() + max(0, (root.winfo_height() - self.win.winfo_height()) // 3)
        self.win.geometry(f"+{x}+{y}")

    def update_from(self, bind: dict):
        free = [x["seat"] for x in bind.get("seats") or [] if not x.get("taken")]
        try:
            self.combo.config(values=free)
        except tk.TclError:
            return
        if self.seat.get() and self.seat.get() not in free:
            self.seat.set("")
            self.msg.config(text="你选的座号刚被别的电脑绑了，请重新选", fg=RED)

    def send(self):
        seat = self.seat.get().strip()
        if not seat:
            return self.msg.config(text="先在下拉框里选这台电脑的座号", fg=RED)
        if self.sending:
            return
        self.sending = True
        self.btn.config(state="disabled")
        app = self.w.app

        def done(got, err):
            self.sending = False
            try:
                self.btn.config(state="normal")
            except tk.TclError:
                return
            if err:
                return self.msg.config(text=str(err), fg=RED)
            self.msg.config(text=f"绑好了：这台电脑是 {got.get('seat', seat)} 号座位", fg=GREEN)
            self.win.after(1200, self.close)
        in_thread(self.win, lambda: api.seat_bind(app.server, app.token, seat), done)

    def dismiss(self):
        self.w.bind_off = True
        self.close()

    def close(self):
        if self.w.binder is self:
            self.w.binder = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass
