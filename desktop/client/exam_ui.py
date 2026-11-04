# -*- coding: utf-8 -*-
"""考试中的两屏：答题和交完。

**整页沉浸，没有侧边栏** —— 和学生网页端一个规矩：考试中途点走太容易误操作。
学生只有交完卷才回到主界面。

界面之外的三件事都不在这儿：
  · 终态怎么收（三类操作题各一种）  → states.py
  · 交卷之后怎么清场                → cleanup.py
  · 和服务器说话                    → api.py
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from . import api, cleanup, package, snapshot, states, store
from .dragboard import DragBoard, IpBox
from .shell import (AMBER, APP_NAME, BG, BLUE, CARD, CLIENT_VER, FONT, GRAY,
                    GREEN, LINE, RED, ai_reply, in_thread, open_in_system)


# ================================================================ 三、答题
def submit_needs(total_questions: int, total_seconds: int) -> tuple[int, int]:
    """至少要答几题、至少要考几秒：都是一半，向上取整（30 题答满 15 题，45 分钟考满 22 分 30 秒）。"""
    return -(-total_questions // 2), -(-total_seconds // 2)


def exam_minsize(screen_w: int, screen_h: int) -> tuple[int, int]:
    """答题窗口最小能拉到多大：宽 = 屏幕宽的 1/8，高 = 屏幕高的 1/3。

    1920×1080 的屏幕是 240×360。再小内容就靠滚动条，「交卷」始终摆在最前面。
    """
    return max(1, screen_w // 8), max(1, screen_h // 3)


# 一键收缩只给这两类题：学生要在真系统（资源管理器 / WPS）里照着题干做，
# 窗口挡在前面碍事。网页、AI、拖拽题和客观题都在本窗口里作答，收起来反而没法答
SHRINK_KINDS = ("win", "wps")


def can_shrink(q: dict) -> bool:
    return (q.get("type") not in ("选择题", "判断题", "填空题")
            and (q.get("sim") or {}).get("kind") in SHRINK_KINDS)


class ExamFrame(ttk.Frame):
    FOLD_TEXT = "←"            # 答题卡展开着：点了往左收
    UNFOLD_TEXT = "→"          # 答题卡收起了：点了往右展开
    SHRINK_TEXT = "一键收缩"
    RESTORE_TEXT = "还原"
    SHRUNK_WIDTH = 460         # 收缩后的小窗口：只放题干，贴在屏幕右上角

    def __init__(self, app):
        super().__init__(app.root, padding=0)
        self.app = app
        self.paper = app.package.paper
        self.answers: dict[str, str] = {}
        # AI 工具题的对话记录，一题一份。交卷时当作那道题的"终态"交上去
        self.chats: dict[str, list] = {}
        # 拖拽题的作答，一题一份：{"placed": {热区: [卡片]}} 或 {"ip": "…"}。
        # 和 AI 对话一样，交卷时当作那道题的"终态"交上去
        self.drags: dict[str, dict] = {}
        self.index = 0
        self.left = app.package.duration_min * 60
        self.started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.submitted = False
        self._build()
        # 考试窗口允许拉得很小（学生要一边看题一边在 WPS 里做）：高到屏幕的 1/3、
        # 宽到屏幕的 1/8。离开答题界面时换回原来的下限，主界面还是原来那个大小
        root = app.root
        self._shell_minsize = tuple(root.minsize())
        self._exam_minsize = exam_minsize(root.winfo_screenwidth(),
                                          root.winfo_screenheight())
        root.minsize(*self._exam_minsize)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.restore_draft()
        self.show(0)
        self.tick()

    # ---------------- 骨架 ----------------
    def _build(self):
        top = tk.Frame(self, bg=BLUE, height=54)
        top.pack(fill="x")
        top.pack_propagate(False)
        self.topbar = top
        # **「交卷」和倒计时先 pack**：窗口被拉窄时，pack 先满足先摆的，后摆的被挤掉。
        # 原来标题先摆，窗口一窄「交卷」就被挤没了 —— 现在挤掉的是标题和姓名
        self.btn_submit = tk.Button(top, text="交 卷", bg="#ffffff", fg=BLUE,
                                    font=(FONT, 11, "bold"), relief="flat",
                                    cursor="hand2", command=self.confirm_submit)
        self.btn_submit.pack(side="right", padx=(6, 12), pady=11)
        self.clock = tk.Label(top, text="", bg=BLUE, fg="white", font=(FONT, 13, "bold"))
        self.clock.pack(side="right", padx=4)
        tk.Label(top, text=self.app.package.title, bg=BLUE, fg="white",
                 font=(FONT, 13, "bold")).pack(side="left", padx=(16, 6))
        s = self.app.student
        tk.Label(top, text=f"{s.get('cls', '')}　{s.get('name', '')}　{s.get('no', '')}",
                 bg=BLUE, fg="#d8e6ff", font=(FONT, 10)).pack(side="left", padx=6)

        # **页脚先 pack，而且钉在底部。** 放在 body 后面 pack 的话，题干一长，
        # Tk 先把空间分给上面的内容，「上一题/下一题」就被挤扁甚至挤没了 ——
        # 学生只剩答题卡能跳题，还以为程序坏了。钉死在底部，高度 48 谁也抢不走。
        foot = tk.Frame(self, bg=CARD, height=48, highlightbackground=LINE,
                        highlightthickness=1)
        foot.pack(side="bottom", fill="x")
        foot.pack_propagate(False)
        self.foot = foot
        tk.Button(foot, text="上一题", font=(FONT, 10), relief="groove", width=10,
                  command=lambda: self.show(self.index - 1)).pack(side="left", padx=16, pady=8)
        tk.Button(foot, text="下一题", font=(FONT, 10), relief="groove", width=10,
                  command=lambda: self.show(self.index + 1)).pack(side="left")
        self.tip = tk.Label(foot, text="", bg=CARD, fg=GRAY, font=(FONT, 9))
        self.tip.pack(side="right", padx=16)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)
        self.body = body
        # 窗口拉窄了，答题卡（196 宽）会把题目挤成一条缝 —— 窄到放不下就自动收起，
        # 让出位置给题目；拉宽回来、而且是自动收的，再自动展开
        self._auto_folded = False
        body.bind("<Configure>", self._body_resized)

        side = tk.Frame(body, bg=CARD, width=196, highlightbackground=LINE,
                        highlightthickness=1)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        self.side = side
        tk.Label(side, text="答题卡", bg=CARD, font=(FONT, 11, "bold")).pack(pady=(10, 2))
        self.progress = tk.Label(side, text="", bg=CARD, fg=GRAY, font=(FONT, 9))
        self.progress.pack()
        grid = tk.Frame(side, bg=CARD)
        grid.pack(fill="both", expand=True, padx=10, pady=8)
        self.num_btns = []
        for i in range(len(self.paper)):
            b = tk.Button(grid, text=str(i + 1), width=3, font=(FONT, 9),
                          relief="groove", command=lambda n=i: self.show(n))
            b.grid(row=i // 5, column=i % 5, padx=2, pady=2)
            self.num_btns.append(b)
        tk.Label(side, text="蓝=已答　白=未答", bg=CARD, fg=GRAY,
                 font=(FONT, 8)).pack(side="bottom", pady=6)

        # 答题卡折叠按钮：一个小方块，贴在答题卡右边。收起后答题卡整条拿掉，
        # 题目区占满宽度；按钮本身留着（箭头换个方向），再点就展开。
        # 箭头用 ← →：Win7 的字体里有（实心三角那类箭头在 GBK 外，Win7 上是方框）
        self.card_folded = False
        self.fold_col = tk.Frame(body, bg=BG)
        self.fold_col.pack(side="left", fill="y")
        self.btn_fold = tk.Button(self.fold_col, text=self.FOLD_TEXT, width=2,
                                  font=(FONT, 9), relief="groove", cursor="hand2",
                                  command=self.toggle_card)
        self.btn_fold.pack(side="top", padx=(2, 0), pady=(8, 0))

        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        self.main = main

        # **题干可能很长**（真题里有三四百字的），加上配图和一排选项，一屏放不下。
        # 所以整块内容放进一个画布里，右边给一条滚动条 —— 不给的话下面的选项
        # 直接看不见，学生以为这题没选项。
        self.canvas = tk.Canvas(main, bg=BG, highlightthickness=0)
        self.bar = tk.Scrollbar(main, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.bar.set)
        self.bar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.page = tk.Frame(self.canvas, bg=BG)
        self._page_id = self.canvas.create_window((0, 0), window=self.page, anchor="nw")
        self.page.bind("<Configure>", self._page_resized)
        self.canvas.bind("<Configure>", self._canvas_resized)
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.bind("<Destroy>", lambda _e: self._drop_wheel())

        # 题目标题栏：左边「第几题 / 题型 / 分值」，右边空白处放「一键收缩」
        # （只有 Windows 操作题、WPS 文字题才出现，见 show）
        self.head_row = tk.Frame(self.page, bg=BG)
        self.head_row.pack(fill="x", padx=(18, 12), pady=(8, 0))
        self.head = tk.Label(self.head_row, text="", bg=BG, fg=GRAY, font=(FONT, 9),
                             anchor="w")
        self.head.pack(side="left", fill="x", expand=True)
        self.btn_shrink = tk.Button(self.head_row, text=self.SHRINK_TEXT, font=(FONT, 9),
                                    relief="groove", cursor="hand2",
                                    command=self.toggle_shrink)
        self.shrunk = False
        self._before_shrink: dict = {}
        self.stem = tk.Message(self.page, text="", bg=BG, font=(FONT, 12), anchor="w",
                               justify="left", width=700)
        self.stem.pack(fill="x", padx=16, pady=(4, 6))
        # 题目配图。**引用要留着**：Tkinter 的 PhotoImage 一旦没人引用就会被
        # 回收，图片当场变成一块空白 —— 这是 Tkinter 最经典的坑
        self.pic_label = tk.Label(self.page, bg=BG)
        self.pic = None
        self.area = tk.Frame(self.page, bg=BG)
        self.area.pack(fill="both", expand=True, padx=18)

    # ---------------- 滚动 ----------------
    def _page_resized(self, _event=None):
        """内容高度变了，重算可滚动范围；内容短到不用滚时把滚动条收起来。"""
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        need = self.page.winfo_reqheight() > self.canvas.winfo_height()
        # 用 winfo_manager() 判"现在摆出来没有"，**不用 winfo_ismapped()**：
        # 后者在窗口还没显示出来时恒为 0，于是"该收起来"那一支永远进不去
        showing = self.bar.winfo_manager() == "pack"
        if need and not showing:
            self.bar.pack(side="right", fill="y")
        elif not need and showing:
            self.bar.pack_forget()

    def _canvas_resized(self, event):
        """画布宽了窄了，里面那页跟着宽窄 —— 不跟的话题干按 700 像素硬换行，
        窗口再宽也挤在左边一条。"""
        self.canvas.itemconfigure(self._page_id, width=event.width)
        # 下限放到 160：窗口现在能拉到屏幕宽的 1/8，按 360 硬换行的话右半截题干直接被裁掉
        self.stem.configure(width=max(160, event.width - 40))
        wrap = max(140, event.width - 60)
        for w in self.area.winfo_children():
            if isinstance(w, tk.Radiobutton):
                w.configure(wraplength=wrap)

    def _wheel(self, event):
        try:
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:                       # 画布已经销毁（交完卷换屏了）
            self._drop_wheel()

    def _drop_wheel(self):
        try:
            self.canvas.unbind_all("<MouseWheel>")
        except tk.TclError:
            pass

    def _option_wrap(self) -> int:
        """选项文字按画布宽度换行；画布还没量出来（刚建、隐藏）就按 680。"""
        w = self.canvas.winfo_width()
        return 680 if w <= 1 else max(140, w - 60)

    # ---------------- 答题卡折叠 ----------------
    AUTO_FOLD_WIDTH = 520       # 答题区比这窄就自动收起答题卡

    def _body_resized(self, event):
        if self.shrunk or event.width <= 1:      # 还没显示出来（自检里窗口是隐藏的）不算
            return
        narrow = event.width < self.AUTO_FOLD_WIDTH
        if narrow and not self.card_folded:
            self.toggle_card()
            self._auto_folded = True
        elif not narrow and self.card_folded and self._auto_folded:
            self.toggle_card()

    def toggle_card(self):
        """收起 / 展开答题卡。收起后题目区占满宽度，按钮箭头换成朝右。"""
        self._auto_folded = False           # 学生自己点过，就按学生的来
        if self.card_folded:
            self.side.pack(side="left", fill="y", before=self.fold_col)
            self.btn_fold.config(text=self.FOLD_TEXT)
        else:
            self.side.pack_forget()
            self.btn_fold.config(text=self.UNFOLD_TEXT)
        self.card_folded = not self.card_folded

    # ---------------- 一键收缩 ----------------
    def toggle_shrink(self):
        if self.shrunk:
            self.unshrink()
        else:
            self.shrink()

    def shrink(self):
        """只留题干，窗口缩成一小条贴在屏幕右上角并且置顶 —— 学生在资源管理器 /
        WPS 里做题时，题目要求一直看得见，又不挡着操作。

        收缩前的大小、位置、最大化与否、答题卡折没折都记下来，还原时原样放回。
        """
        if self.shrunk or self.submitted or not can_shrink(self.paper[self.index]):
            return
        root = self.app.root
        self._before_shrink = {"geometry": root.geometry(), "state": root.state()}
        self.shrunk = True
        self.topbar.pack_forget()
        self.foot.pack_forget()
        self.side.pack_forget()
        self.fold_col.pack_forget()
        self.pic_label.pack_forget()
        self.area.pack_forget()
        self.btn_shrink.config(text=self.RESTORE_TEXT)

        # 临时放开最小尺寸：不放开的话缩不到这么小
        root.minsize(1, 1)
        if root.state() == "zoomed":
            root.state("normal")
        self.update_idletasks()
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w = min(self.SHRUNK_WIDTH, max(240, sw // 3))
        self.stem.configure(width=max(160, w - 40))
        self.update_idletasks()
        need = self.head_row.winfo_reqheight() + self.stem.winfo_reqheight() + 30
        h = max(120, min(need, sh // 2))
        x, y = max(0, sw - w - 16), 40
        root.geometry(f"{w}x{h}+{x}+{y}")
        # 位置再设一遍：刚拆掉一堆控件、刚改完最小尺寸，Windows 上第一次的位置
        # 会被吞掉（大小变了、窗口还停在原地）—— 本机实测撞上过
        self.update_idletasks()
        root.geometry(f"+{x}+{y}")
        root.attributes("-topmost", True)
        self.canvas.yview_moveto(0)
        self.after_idle(self._page_resized)

    def unshrink(self):
        """还原：大小、位置、答题卡折叠状态放回去，取消置顶，最小尺寸恢复。"""
        if not self.shrunk:
            return
        self.shrunk = False
        root = self.app.root
        try:
            root.attributes("-topmost", False)
        except tk.TclError:
            pass
        root.minsize(*self._exam_minsize)
        before = self._before_shrink or {}
        if before.get("geometry"):
            root.geometry(before["geometry"])
        if before.get("state") == "zoomed":
            root.state("zoomed")

        self.topbar.pack(fill="x", before=self.body)
        self.foot.pack(side="bottom", fill="x", before=self.body)
        self.fold_col.pack(side="left", fill="y", before=self.main)
        if not self.card_folded:
            self.side.pack(side="left", fill="y", before=self.fold_col)
        self.area.pack(fill="both", expand=True, padx=18)
        if self.pic is not None:
            self.pic_label.pack(anchor="w", padx=18, pady=(0, 6), before=self.area)
        self.btn_shrink.config(text=self.SHRINK_TEXT)
        self.update_idletasks()
        self.after_idle(self._page_resized)

    def _on_destroy(self, event):
        """答题界面没了（交完卷换屏、退出）：置顶取消、最小尺寸换回主界面那个。"""
        if event.widget is not self:
            return
        try:
            self.app.root.attributes("-topmost", False)
            self.app.root.minsize(*self._shell_minsize)
        except tk.TclError:
            pass

    # ---------------- 渲染 ----------------
    def show(self, i: int):
        if not (0 <= i < len(self.paper)):
            return
        q = self.paper[i]
        # 收缩着切到一道不能收缩的题（网页 / AI / 拖拽 / 客观题）：先还原，
        # 不然学生面对一个只剩题干的小窗口，没地方作答。切到另一道 win/wps 题就接着缩着
        if self.shrunk and not can_shrink(q):
            self.unshrink()
        self.index = i
        qid = str(q["id"])
        self.head.config(text=f"第 {i + 1} / {len(self.paper)} 题　"
                              f"{q.get('section') or q['type']}　{q.get('score', 0)} 分")
        self.stem.config(text=q.get("stem", ""))
        self._show_picture(q)
        for w in self.area.winfo_children():
            w.destroy()

        qtype = q.get("type")
        if qtype in ("选择题", "判断题"):
            self._render_choice(q, qid)
            self.tip.config(text="选完自动跳下一题")
        elif qtype == "填空题":
            self._render_blank(q, qid)
            self.tip.config(text="")
        else:
            self._render_operation(q, qid)
            self.tip.config(text="")
        if can_shrink(q):
            self.btn_shrink.pack(side="right", before=self.head)   # 窗口窄了先挤标题，别挤按钮
        else:
            self.btn_shrink.pack_forget()
        if self.shrunk:                 # 缩着换了一道 win/wps 题：照样只留题干
            self.pic_label.pack_forget()
            self.area.pack_forget()
        # 换一题从头看起：上一题要是拉到了底，这一题的题干会被藏在上面看不见
        self.canvas.yview_moveto(0)
        self.after_idle(self._page_resized)
        self.refresh_marks()

    def _show_picture(self, q):
        """有配图就显示在题干下面。

        图在出包时已经由服务器转成 PNG 并缩到位了（Tkinter 不认 JPEG），
        这里只管贴。**图坏了不能影响答题** —— 读不出来就当没有图，
        学生还能做别的题，总比整个界面崩掉强。
        """
        self.pic = None
        name = q.get("image")
        path = self.app.pictures.get(name) if name else None
        if not path or not Path(path).exists():
            self.pic_label.pack_forget()
            return
        try:
            self.pic = tk.PhotoImage(file=str(path))
        except tk.TclError:
            self.pic_label.pack_forget()
            return
        self.pic_label.config(image=self.pic)
        if self.shrunk:                 # 收缩时只留题干，图等还原了再摆
            return
        # before=area：不写的话图会排到作答区下面去，离题干隔着一整块选项
        self.pic_label.pack(anchor="w", padx=18, pady=(0, 6), before=self.area)

    # 「没作答」在界面上用的值。**不能用空串**：Tk 的 Radiobutton 有个"第三态"
    # —— 绑定变量正好等于 `tristatevalue`（默认就是空串）时，它画成"值未定"的
    # 样子，在 Windows 上就是一个实心黑点。于是学生一进题就看见四个选项全是
    # 黑点，以为自己选过了。
    NOT_ANSWERED = "\x00未作答"

    def _render_choice(self, q, qid):
        """选择题 / 判断题。**没选时每个选项都得是空框。**

        两道保险一起上：

          · 变量初值给一个选项里绝不会出现的值（不是空串）
          · `tristatevalue` 也换掉

        只做后者其实就够，但这一条坏掉的表现是"全班看见四个黑点"，而代码和
        测试都看不出毛病 —— 多一道保险便宜。
        """
        picked = self.answers.get(qid) or self.NOT_ANSWERED
        var = tk.StringVar(value=picked)
        opts = q.get("options") or ([{"label": "A", "content": "正确"},
                                     {"label": "B", "content": "错误"}]
                                    if q["type"] == "判断题" else [])
        for o in opts:
            tk.Radiobutton(
                self.area, text=f"{o['label']}．{o['content']}", value=o["label"],
                variable=var, bg=BG, font=(FONT, 11), anchor="w", justify="left",
                wraplength=self._option_wrap(), tristatevalue="\x01",
                command=lambda v=var, k=qid: self._picked(k, v.get()),
            ).pack(fill="x", pady=3)

    def _picked(self, qid: str, value: str) -> None:
        """选完一个选项，**自动跳下一题** —— 中考的机考客户端就是这么走的。

        停 220 毫秒再跳：立刻跳的话学生看不见自己刚点上的那个点，会以为没点上，
        回头再点一次。最后一题不跳（没有下一题了）。

        回头改答案照样会跳 —— 改完想接着改，从左边答题卡点回来就是。
        """
        self.answer(qid, value)
        if self.index < len(self.paper) - 1:
            self.after(220, self._jump_after_pick)

    def _jump_after_pick(self) -> None:
        # 这 220 毫秒里可能已经交卷了（时间到自动交），交完这一屏就没了
        if self.submitted or not self.winfo_exists():
            return
        self.show(self.index + 1)

    def _render_blank(self, q, qid):
        tk.Label(self.area, text="在下面填写答案：", bg=BG, fg=GRAY,
                 font=(FONT, 9)).pack(anchor="w")
        var = tk.StringVar(value=self.answers.get(qid, ""))
        e = tk.Entry(self.area, textvariable=var, font=(FONT, 12), relief="solid", bd=1)
        e.pack(fill="x", pady=6)
        e.bind("<KeyRelease>", lambda _e, k=qid, v=var: self.answer(k, v.get()))

    def _render_operation(self, q, qid):
        """操作题按类型分岔。

        win / wps / html 都是"去真系统里做"，给一个「打开」按钮；
        AI 工具题的成果不在文件系统里，给一个对话框。
        """
        sim = q.get("sim") or {}
        if sim.get("kind") == "ai":
            self._render_ai(q, qid)
            return
        if sim.get("kind") == "drag" or not sim.get("kind"):
            self._render_drag(q, qid)
            return
        rel = sim.get("open") or ""
        target = self.app.exam_root / rel if rel else self.app.exam_root

        box = tk.Frame(self.area, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        box.pack(fill="x", pady=4)
        tk.Label(box, text="这道题在真实系统中完成", bg=CARD, fg=BLUE,
                 font=(FONT, 11, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
        tk.Label(box, text=f"考试文件位置：{target}", bg=CARD, fg=GRAY,
                 font=(FONT, 9), anchor="w").pack(fill="x", padx=14)
        how = {"win": "在资源管理器里按题目要求操作文件和文件夹。",
               "wps": "用 WPS 文字打开这个文档，按要求改好后**原名原位置保存**。",
               "html": "打开「网页」文件夹，用记事本改里面的 index.html 和 style.css，"
                       "按要求改好后原名保存。"}
        note = (how.get(sim.get("kind"), "按题目要求操作。")
                + "完成后回到本窗口继续答题。"
                + ("这道题由老师评阅。" if sim.get("manual")
                   else "交卷时系统自动检查并评分。"))
        tk.Label(box, text=note, bg=CARD, fg=GRAY, font=(FONT, 9), anchor="w",
                 wraplength=640, justify="left").pack(fill="x", padx=14, pady=(2, 8))

        row = tk.Frame(box, bg=CARD)
        row.pack(anchor="w", padx=14, pady=(0, 12))
        tk.Button(row, text="打 开", bg=BLUE, fg="white", font=(FONT, 11, "bold"),
                  relief="flat", cursor="hand2", width=12,
                  command=lambda: self.open_target(target, qid)).pack(side="left")
        tk.Button(row, text="打开考试主文件夹", font=(FONT, 10), relief="groove",
                  command=lambda: self.open_target(self.app.exam_root, None)
                  ).pack(side="left", padx=8)

        self._op_state = tk.Label(
            box, text="已打开，操作结果以交卷时的检查为准" if self.answers.get(qid) else "",
            bg=CARD, fg=GREEN, font=(FONT, 9))
        self._op_state.pack(anchor="w", padx=14, pady=(0, 8))

    # ---------------- 拖拽题（流程图 / 热区 / 归类 / 程序填空 / IP 查询）----------------
    def _render_drag(self, q, qid):
        """拖拽题的作答区。图是服务端按原题重画的（见 client/dragboard.py）。

        判分那头和别的操作题一样：交一份终态上去 —— 这里是「哪张卡片放在哪个热区」
        （IP 查询题是填的地址），服务端按检查点判。
        """
        sim = q.get("sim") or {}
        env = sim.get("env") or {}
        box = tk.Frame(self.area, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        box.pack(fill="both", expand=True, pady=4)
        if not env:
            # 老考试包、或者服务端认不出来的拖拽题：没有图可画，老实说清楚，
            # **别给「打开」按钮** —— 它只会打开一个空的考试文件夹
            tk.Label(box, text="这道题由老师评阅", bg=CARD, fg=AMBER,
                     font=(FONT, 11, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
            tk.Label(box, text="这道题在本机没有可操作的作答区，可以先做别的题，不影响交卷。",
                     bg=CARD, fg=GRAY, font=(FONT, 9), anchor="w", wraplength=640,
                     justify="left").pack(fill="x", padx=14, pady=(0, 10))
            return

        mode = env.get("mode") or "diagram"
        title = {"ip": "查询本机 IP 地址", "code": "把代码块拖到程序里"}.get(mode, "拖拽作答")
        tk.Label(box, text=title, bg=CARD, fg=BLUE,
                 font=(FONT, 11, "bold")).pack(anchor="w", padx=12, pady=(8, 0))

        def changed(new: dict) -> None:
            self.drags[qid] = dict(self.drags.get(qid) or {}, **new)
            self.answer(qid, self._drag_mark(qid))

        kind = IpBox if mode == "ip" else DragBoard
        kind(box, env, self.drags.get(qid), changed).pack(fill="x", padx=12, pady=(4, 12))

    def _drag_mark(self, qid: str) -> str:
        """答题卡上的进度：放了几张 / 填没填。空串表示还没作答。"""
        got = self.drags.get(qid) or {}
        if got.get("ip"):
            return "已填写 IP 地址"
        n = sum(len(v) for v in (got.get("placed") or {}).values())
        return f"已放 {n} 张卡片" if n else ""

    # ---------------- AI 工具题 ----------------
    def _render_ai(self, q, qid):
        """AI 工具题：一个通用对话框，学生把题目要求描述给 AI 工具并提交。

        **考点是"会不会把需求说清楚"**，不是 AI 答得好不好 —— 所以判分只看学生
        提交了什么（提交过 + 提问覆盖了题目要求），由服务器按题干现算，老师不用
        出标准答案，也不用出检查点。

        回复是本地模板拼的，不联网调真模型：考试机不该往外发请求，真模型的回复
        也不可控，更不该由学生为它负责。界面和措辞跟网页版那个对话框保持一致。
        """
        chat = self.chats.setdefault(qid, [])

        box = tk.Frame(self.area, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        box.pack(fill="both", expand=True, pady=4)
        head = tk.Frame(box, bg=CARD)
        head.pack(fill="x", padx=12, pady=(8, 2))
        tk.Label(head, text="AI 工具", bg=CARD, fg=BLUE,
                 font=(FONT, 11, "bold")).pack(side="left")
        tk.Label(head, text="把题目要求描述给它并发送　·　回复由本地模板生成，不联网",
                 bg=CARD, fg=GRAY, font=(FONT, 8)).pack(side="left", padx=8)

        wrap = tk.Frame(box, bg=CARD)
        wrap.pack(fill="both", expand=True, padx=12)
        bar = tk.Scrollbar(wrap)
        bar.pack(side="right", fill="y")
        view = tk.Text(wrap, bg="#fbfcfe", font=(FONT, 10), relief="solid", bd=1,
                       wrap="word", height=9, yscrollcommand=bar.set)
        view.pack(side="left", fill="both", expand=True)
        bar.config(command=view.yview)
        view.tag_config("me", foreground=BLUE, font=(FONT, 10, "bold"))
        view.tag_config("it", foreground="#333333")

        def repaint():
            view.config(state="normal")
            view.delete("1.0", "end")
            if not chat:
                view.insert("end", "（还没有提问。在下面输入你的要求，点发送）\n", "it")
            for m in chat:
                me = m.get("role") == "user"
                view.insert("end", ("我：" if me else "AI："), "me" if me else "it")
                view.insert("end", str(m.get("text") or "") + "\n\n", "me" if me else "it")
            view.config(state="disabled")
            view.see("end")

        row = tk.Frame(box, bg=CARD)
        row.pack(fill="x", padx=12, pady=8)
        draft = tk.Text(row, height=3, font=(FONT, 10), relief="solid", bd=1, wrap="word")
        draft.pack(side="left", fill="both", expand=True)

        def send(_event=None):
            text = draft.get("1.0", "end").strip()
            if not text:
                return "break"
            chat.append({"role": "user", "text": text})
            chat.append({"role": "ai", "text": ai_reply(text)})
            draft.delete("1.0", "end")
            repaint()
            # 提交过就算答过了，答题卡上要能看出进度；**真正算分的是对话内容**
            self.answer(qid, f"已向 AI 工具提交 {sum(1 for m in chat if m['role'] == 'user')} 次")
            return "break"

        # 回车发送、Shift+回车换行 —— 和常见的聊天框一个习惯
        draft.bind("<Return>", send)
        draft.bind("<Shift-Return>", lambda e: None)
        tk.Button(row, text="发 送", bg=BLUE, fg="white", font=(FONT, 10, "bold"),
                  relief="flat", cursor="hand2", width=8, command=send
                  ).pack(side="left", padx=(8, 0))
        repaint()

    def open_target(self, path: Path, qid: str | None):
        err = open_in_system(path)
        if err:
            self.unshrink()
            messagebox.showwarning("打不开", err)
            return
        if qid:
            # 操作题不填文本答案，记一笔"打开过"，答题卡上好看出进度；
            # **真正算分的是交卷时拍的文件快照**，不是这一笔
            self.answer(qid, "已在系统中操作")
            if getattr(self, "_op_state", None):
                self._op_state.config(text="已打开，操作结果以交卷时的检查为准")

    # ---------------- 作答与草稿 ----------------
    def answer(self, qid: str, value: str):
        self.answers[qid] = value
        self.refresh_marks()
        self.save_draft()

    def refresh_marks(self):
        done = 0
        # zip 而不是按下标取：答题卡的按钮数和题数万一对不上（自检里会这么摆），
        # 按下标取会直接 IndexError 把整页打断，而这只是个进度显示
        for i, (q, b) in enumerate(zip(self.paper, self.num_btns)):
            filled = bool(self.answers.get(str(q["id"])))
            done += 1 if filled else 0
            b.config(bg=BLUE if filled else CARD, fg="white" if filled else "black",
                     relief="solid" if i == self.index else "groove")
        done += sum(1 for q in self.paper[len(self.num_btns):]
                    if self.answers.get(str(q["id"])))
        self.progress.config(text=f"已答 {done} / {len(self.paper)}")

    def save_draft(self):
        store.save_draft(self.app.package.exam_id, self.app.student.get("no", ""),
                         {"answers": self.answers, "drags": self.drags,
                          "started": self.started, "left": self.left})

    def restore_draft(self):
        got = store.load_draft(self.app.package.exam_id, self.app.student.get("no", ""))
        if not got.get("answers"):
            return
        if messagebox.askyesno("接着考", "发现上次没交完的答卷（可能是断电或程序关闭）。\n"
                                         "要接着考吗？\n\n选「否」则从头开始。"):
            self.answers = {str(k): v for k, v in got["answers"].items()}
            self.drags = {str(k): v for k, v in (got.get("drags") or {}).items()}
            self.started = got.get("started", self.started)
            self.left = int(got.get("left") or self.left)

    # ---------------- 倒计时 ----------------
    def tick(self):
        if self.submitted:
            return
        if self.left <= 0:
            self.unshrink()             # 弹窗、交卷之前先还原：缩着的小窗口里看不全
            messagebox.showinfo("时间到", "考试时间结束，系统将自动交卷。")
            self.do_submit(auto=True)
            return
        self.left -= 1
        m, s = divmod(max(0, self.left), 60)
        h, m = divmod(m, 60)
        self.clock.config(text=f"{h:02d}:{m:02d}:{s:02d}",
                          fg="#ffd9d6" if self.left < 300 else "white")
        if self.left % 15 == 0:
            self.save_draft()
        # 页脚提示交卷门槛，学生不用点了「交卷」才知道还差什么
        need_q, need_sec = submit_needs(len(self.paper), self.app.package.duration_min * 60)
        wait = max(0, need_sec - (self.app.package.duration_min * 60 - self.left))
        more_q = max(0, need_q - self.answered_count())
        # 每 60 秒问一次教师端：老师考试中途打开「允许提前交卷」，这边要跟上。
        # 每台机器随机错开：全班同一秒开考的话，不错开就是几十台在同一秒一起问
        if not hasattr(self, "_live_slot"):
            import random
            self._live_slot = random.randrange(60)
        if self.left % 60 == self._live_slot:
            self.sync_live()
        self.tip.config(text="" if self.early_submit() or not (wait or more_q) else
                        f"答满 {need_q} 题、并且开考 {-(-need_sec // 60)} 分钟后才能交卷")
        self.after(1000, self.tick)

    # ---------------- 交卷 ----------------
    def answered_count(self) -> int:
        return sum(1 for q in self.paper if self.answers.get(str(q["id"])))

    def gate_reason(self) -> str:
        """交卷门槛：考试时间过了一半、**并且**答完一半的题才能交。能交返回空串。

        和网页端（frontend/src/submitGate.js）是同一条规矩，改一边记得改另一边。
        时间到自动交卷不受这个限制（do_submit(auto=True) 不经过这里）。
        """
        if self.early_submit():
            return ""                   # 老师开了「允许提前交卷」
        total_sec = self.app.package.duration_min * 60
        need_q, need_sec = submit_needs(len(self.paper), total_sec)
        more_q = max(0, need_q - self.answered_count())
        wait = max(0, need_sec - (total_sec - self.left))
        if not more_q and not wait:
            return ""
        parts = []
        if more_q:
            parts.append(f"还要再答 {more_q} 题")
        if wait:
            m, sec = divmod(wait, 60)
            parts.append(f"还要再等 {m} 分 {sec:02d} 秒" if m else f"还要再等 {sec} 秒")
        return (f"考试时间过了一半、并且答完一半的题（至少 {need_q} 题）才能交卷。\n\n"
                + "，".join(parts) + "。")

    # ---------------- 考试中途老师改的设置 ----------------
    def early_submit(self) -> bool:
        """允许提前交卷：考试包里开考时那份，被教师端最新的覆盖（问到过的话）。"""
        live = getattr(self, "_live_early", None)
        return self.app.package.early_submit if live is None else live

    def sync_live(self, then=None):
        """后台问一次教师端最新设置。连不上就算了，按原来的走 —— 断网照样能考。"""
        pack = self.app.package
        server = getattr(self.app, "server", "") or pack.server
        if not server or not pack.token or getattr(self, "_live_busy", False):
            if then:
                then()
            return
        self._live_busy = True

        def done(got, _err):
            self._live_busy = False
            if isinstance(got, dict) and "early_submit" in got:
                self._live_early = bool(got["early_submit"])
            if then:
                then()
        in_thread(self, lambda: api.exam_live(server, pack.token), done)

    def confirm_submit(self):
        self.unshrink()
        why = self.gate_reason()
        if why and not getattr(self, "_asked_live", False):
            # 被门槛拦住时当场再问一次：老师刚打开「允许提前交卷」，不用等下一个 60 秒
            self._asked_live = True
            self.sync_live(then=self._confirm_after_live)
            return
        self._asked_live = False
        if why:
            messagebox.showinfo("还不能交卷", why)
            return
        blank = [i + 1 for i, q in enumerate(self.paper)
                 if not self.answers.get(str(q["id"]))]
        text = "确定交卷吗？交卷后不能再修改。"
        if blank:
            text = (f"还有 {len(blank)} 题没有作答：第 " +
                    "、".join(str(n) for n in blank[:12]) +
                    ("…" if len(blank) > 12 else "") + " 题。\n\n" + text)
        if messagebox.askyesno("交卷", text):
            self.do_submit()

    def _confirm_after_live(self):
        if not self.submitted:
            self.confirm_submit()

    def do_submit(self, auto: bool = False):
        if self.submitted:
            return
        self.unshrink()
        self.submitted = True
        self.btn_submit.config(state="disabled", text="交卷中…")
        self.tip.config(text="正在检查考试文件夹，请稍候…")
        self.update_idletasks()

        # 操作题各收各的终态：win 拍文件夹快照、wps 读文档格式、html 读源码、
        # AI 题交对话记录。**三类不能都交一份文件夹快照** —— 判分器认的形状不同
        got = states.collect(self.paper, self.app.exam_root,
                             self.app.package.logical_root, self.chats, self.drags)
        shot = snapshot.snapshot(self.app.exam_root)   # 存档用的整机快照，老师能核
        name = f"{self.app.student.get('no', '')}-{self.app.student.get('name', '')}"
        try:
            path = package.write_answer(
                self.app.out_dir / name, self.app.package, self.app.student,
                self.answers, shot, self.started, f"{APP_NAME} {CLIENT_VER}", got)
        except OSError as exc:
            self.submitted = False
            self.btn_submit.config(state="normal", text="交 卷")
            messagebox.showerror("交卷失败", f"答案包写不出来：{exc}\n\n请立刻叫监考老师。")
            return

        store.drop_draft(self.app.package.exam_id, self.app.student.get("no", ""))

        # **落地之后才轮到上传**。传不上去不算交卷失败 —— 卷子已经在硬盘上，
        # 之后能补传。考场里最怕的不是慢，是丢卷。
        self.tip.config(text="正在上传到教师端…")
        self.update_idletasks()
        ok, msg = self.app.upload(path, self.answers, got)
        # 这台机器上留一份考试记录 —— 中考的做法，出了事第一个翻它
        store.log_sitting(self.app.out_dir, self.app.student,
                          self.app.package.title, self.started, path.name, ok)

        # **清场**：快照已经拍完、答卷已经落地，考试文件夹没有留着的理由了。
        # 还开着的考试文件会被强制关掉 —— 不然下一场铺不进来，得人工一台台处理。
        self.tip.config(text="正在清理考场…")
        self.update_idletasks()
        clean, left = cleanup.wipe(self.app.exam_root)
        self.app.finish(path, shot, auto, ok, msg, clean, left)


# ================================================================ 四、交完
class DoneFrame(ttk.Frame):
    def __init__(self, app, path: Path, shot: dict, auto: bool,
                 uploaded: bool = False, msg: str = "",
                 clean: bool = True, left: list | None = None):
        super().__init__(app.root, padding=0)
        self.app, self.path, self.shot = app, path, shot
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill="both", expand=True)

        tk.Label(wrap, text="√", bg=BG, fg=GREEN, font=(FONT, 46)).pack(pady=(52, 0))
        tk.Label(wrap, text="交卷成功" + ("（时间到，自动交卷）" if auto else ""),
                 bg=BG, font=(FONT, 18, "bold")).pack(pady=6)
        tk.Label(wrap, text=f"本机备份：{path.name}　"
                            f"已记录考试文件夹里的 {shot['meta']['count']} 个对象",
                 bg=BG, fg=GRAY, font=(FONT, 9)).pack()

        # 上传成没成，学生和监考老师都得一眼看见
        box = tk.Frame(wrap, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        box.pack(pady=16, ipadx=20, ipady=12)
        if uploaded:
            tk.Label(box, text="√ 已上传到教师端", bg=CARD, fg=GREEN,
                     font=(FONT, 12, "bold")).pack()
            tk.Label(box, text=msg or "老师那边已经能看到你的答卷", bg=CARD, fg=GRAY,
                     font=(FONT, 9), wraplength=540, justify="left").pack(pady=(3, 0))
        elif app.server:
            tk.Label(box, text="※ 答卷已存到本机，但没能上传", bg=CARD, fg=AMBER,
                     font=(FONT, 12, "bold")).pack()
            tk.Label(box, text=(msg or "") + "　卷子没丢，网络恢复后可以补传。请举手告诉监考老师。",
                     bg=CARD, fg=GRAY, font=(FONT, 9), wraplength=540,
                     justify="left").pack(pady=(3, 8))
            self.retry_btn = tk.Button(box, text="重 试 上 传", bg=BLUE, fg="white",
                                       font=(FONT, 10, "bold"), relief="flat",
                                       cursor="hand2", command=self.retry)
            self.retry_btn.pack()
        else:
            tk.Label(box, text="答卷已存到本机", bg=CARD, font=(FONT, 12, "bold")).pack()
            tk.Label(box, text="这是离线开考，交卷文件由监考老师统一收取。",
                     bg=CARD, fg=GRAY, font=(FONT, 9)).pack(pady=(3, 0))

        # 清场结果也要让监考老师看见 —— 没清干净的机器下一场会铺不进去
        if clean:
            tk.Label(wrap, text="考试文件夹已自动清空，可以直接关机或交给下一位考生。",
                     bg=BG, fg=GRAY, font=(FONT, 9)).pack()
        else:
            tk.Label(wrap, text="※ 考试文件夹没清干净，还剩：" + "、".join(left or []),
                     bg=BG, fg=AMBER, font=(FONT, 9), wraplength=560,
                     justify="left").pack()
            tk.Button(wrap, text="再清一次", font=(FONT, 9), relief="groove",
                      command=self.clean_again).pack(pady=2)

        tk.Label(wrap, text="成绩由老师统一评定后公布。请举手示意监考老师。",
                 bg=BG, fg=GRAY, font=(FONT, 10)).pack(pady=8)
        tk.Button(wrap, text="返回首页", bg=BLUE, fg="white", font=(FONT, 11, "bold"),
                  relief="flat", cursor="hand2", width=12,
                  command=app.back_to_shell).pack()

    def clean_again(self):
        clean, left = cleanup.wipe(self.app.exam_root)
        messagebox.showinfo("清理考场",
                            "清干净了。" if clean
                            else "还有文件删不掉：" + "、".join(left or []) +
                                 "\n多半是有程序锁着它，请叫监考老师。")

    def retry(self):
        self.retry_btn.config(state="disabled", text="上传中…")
        self.update_idletasks()
        ok, msg = self.app.upload(self.path, None)
        if ok:
            messagebox.showinfo("上传成功", msg or "答卷已经传到教师端")
            self.app.finish(self.path, self.shot, False, True, msg)
        else:
            self.retry_btn.config(state="normal", text="重 试 上 传")
            messagebox.showwarning("还是没传上去", msg)
