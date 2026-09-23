# -*- coding: utf-8 -*-
"""拖拽题的作答区：流程图补全、结构图热区、设备归类、程序填空 / 排序、本机 IP 查询。

## 画什么，从哪来

图不是原题的截图（那是旧考试系统的界面，素材区烤在图上、说明弹窗挡着半张图），
是服务端按原图**重画的结构**：一串框、线、热区、素材卡片（见后端 services/drag.py）。
这里照着画出来，网页端用同一份数据画 SVG，两边长一个样。

## 状态就是一份映射

    {"placed": {"A": ["i1"], "B": ["i3"]}}      热区 -> 放进去的卡片

每次松手都改这份映射，然后**整块重画** —— 不去一个个挪画布上的图形。几十个图形
重画一次不到一毫秒，换来的是界面永远和状态一致：草稿恢复、交卷、判分看到的都是
同一份东西，不会出现"画面上放进去了、交上去却是空的"。

## 为什么这么拖

按住卡片，它跟着鼠标走；松手时指针落在哪个热区里就放进哪个。热区满了（大多数
热区只能放一张），原来那张退回素材区。从热区里拖出来、松在热区外面，就是拿回来。
比"点一下卡片、再点一下热区"直观，也和原考试系统的操作一致。
"""

from __future__ import annotations

import re
import subprocess
import tkinter as tk
import tkinter.font as tkfont

from .shell import BLUE, CARD, FONT, GRAY, GREEN, LINE

CHIP = "#eef4ff"          # 素材卡片底色
CHIP_EDGE = "#8fb0e6"
SLOT_EDGE = "#2e9e5b"     # 热区边框：原考试系统就是绿色虚线框
SLOT_FILL = "#f6fbf7"
ZONE_EDGE = "#6b7a99"
NOTE = "#fffbe8"
CODE_FONT = ("NSimSun", 11)   # 新宋体：等宽、带中文，中文 Windows 上都有

PAD = 12                   # 素材区四周留白
CHIP_H = 30
DIAMOND_H = 40
GAP = 10


def _pts_round(x1, y1, x2, y2, r):
    """圆角矩形的控制点（配合 smooth=True 画出圆角）。"""
    r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def _outline(cv, shape, x1, y1, x2, y2, **kw):
    """按形状画一个框。返回画出来的那个图形。"""
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    if shape == "diamond":
        return cv.create_polygon(cx, y1, x2, cy, cx, y2, x1, cy, **kw)
    if shape == "para":
        k = min(14, (x2 - x1) / 6)
        return cv.create_polygon(x1 + k, y1, x2, y1, x2 - k, y2, x1, y2, **kw)
    if shape in ("round", "chip"):
        return cv.create_polygon(_pts_round(x1, y1, x2, y2, 12 if shape == "round" else 6),
                                 smooth=True, **kw)
    if shape in ("cloud", "circle"):
        return cv.create_oval(x1, y1, x2, y2, **kw)
    return cv.create_rectangle(x1, y1, x2, y2, **kw)


class DragBoard(tk.Frame):
    """一道拖拽题的作答区。env 是服务端给的图，state 是现在的作答。"""

    def __init__(self, master, env: dict, state: dict | None, on_change, **kw):
        super().__init__(master, bg=CARD, **kw)
        self.env = env or {}
        self.mode = self.env.get("mode") or "diagram"
        placed = (state or {}).get("placed") or {}
        self.placed = {str(k): [str(x) for x in v] for k, v in placed.items()}
        self.on_change = on_change
        self.items = {str(i["id"]): i for i in self.env.get("items") or []}
        self.slots = {str(s["id"]): s for s in self.env.get("slots") or []}
        self.font = tkfont.Font(family=FONT, size=10)
        self.code_font = tkfont.Font(family=CODE_FONT[0], size=CODE_FONT[1])
        self.slot_box = {}         # 热区 id -> 画面上的 (x1, y1, x2, y2)，松手时查落点
        self.drag = None           # 正在拖的那张：{"iid", "tag", "x", "y", "from"}

        tip = self.env.get("tip") or ""
        if tip:
            tk.Label(self, text=tip, bg=CARD, fg=GRAY, font=(FONT, 9), anchor="w",
                     wraplength=700, justify="left").pack(fill="x", padx=4, pady=(2, 4))
        self.cv = tk.Canvas(self, bg="white", highlightthickness=1,
                            highlightbackground=LINE)
        self.cv.pack(fill="x")
        self.cv.tag_bind("chip", "<ButtonPress-1>", self._press)
        self.cv.bind("<B1-Motion>", self._move)
        self.cv.bind("<ButtonRelease-1>", self._release)
        self.redraw()

    # ---------------- 状态 ----------------
    def where(self, iid: str) -> str:
        """卡片现在在哪个热区里，不在任何热区就是 ""。"""
        for sid, got in self.placed.items():
            if iid in got:
                return sid
        return ""

    def place(self, iid: str, sid: str) -> None:
        """把卡片放进热区（sid 为空就是拿回素材区）。一张卡片同一时刻只在一个地方。"""
        for got in self.placed.values():
            if iid in got:
                got.remove(iid)
        if sid:
            cap = int(self.slots.get(sid, {}).get("cap") or 1)
            here = self.placed.setdefault(sid, [])
            while len(here) >= cap:        # 满了：最早放进去的那张退回素材区
                here.pop(0)
            here.append(iid)
        self.placed = {k: v for k, v in self.placed.items() if v}
        self.redraw()
        self.on_change({"placed": {k: list(v) for k, v in self.placed.items()}})

    # ---------------- 画 ----------------
    def redraw(self):
        cv = self.cv
        cv.delete("all")
        self.slot_box = {}
        top = self._palette()
        if self.mode == "code":
            height = self._code(top)
            width = 720
        else:
            width = int(self.env.get("w") or 720)
            height = top + int(self.env.get("h") or 400)
            self._diagram(top)
        cv.config(width=width + 2, height=height + PAD, scrollregion=(0, 0, width, height))

    def _chip_size(self, it: dict) -> tuple:
        text = str(it.get("text") or "")
        font = self.code_font if self.mode == "code" else self.font
        w = max(70, font.measure(text) + 24)
        if it.get("shape") == "diamond":
            return w + 30, DIAMOND_H
        return w, CHIP_H

    def _palette(self) -> int:
        """素材区：还没放进热区的卡片排在最上面，一行放不下就换行。返回素材区的底。"""
        cv = self.cv
        cv.create_text(PAD, PAD, text="素材区", anchor="nw", fill=GRAY, font=(FONT, 9))
        x, y, row_h = PAD, PAD + 20, CHIP_H
        loose = [it for it in self.items.values() if not self.where(str(it["id"]))]
        for it in loose:
            w, h = self._chip_size(it)
            if x + w > 700 and x > PAD:
                x, y = PAD, y + row_h + GAP
                row_h = CHIP_H
            self._chip(it, x, y, w, h)
            x += w + GAP
            row_h = max(row_h, h)
        if not loose:
            cv.create_text(PAD, y + 6, text="（卡片都放上去了。要改的话，把卡片拖回这里）",
                           anchor="nw", fill="#b9c2d0", font=(FONT, 9))
        bottom = y + row_h + PAD
        cv.create_line(0, bottom, 740, bottom, fill=LINE)
        return bottom + PAD

    def _chip(self, it: dict, x, y, w, h, tag_extra=""):
        iid = str(it["id"])
        tag = f"chip-{iid}"
        shape = "diamond" if it.get("shape") == "diamond" else "chip"
        _outline(self.cv, shape, x, y, x + w, y + h, fill=CHIP, outline=CHIP_EDGE,
                 width=1, tags=("chip", tag))
        if self.mode == "code":
            # 代码卡片**左对齐**：行首的空格就是缩进，而缩进正是排序题的考点 ——
            # 居中的话「    money = …」和「money = …」看起来一模一样
            self.cv.create_text(x + 8, y + h / 2, text=str(it.get("text") or ""), anchor="w",
                                font=self.code_font, fill="#1d3557", tags=("chip", tag))
            return
        self.cv.create_text(x + w / 2, y + h / 2, text=str(it.get("text") or ""),
                            font=self.font, fill="#1d3557", tags=("chip", tag))

    def _diagram(self, top: int):
        cv = self.cv
        for s in self.env.get("shapes") or []:
            t = s.get("t")
            if t == "line":
                pts = [c + (top if i % 2 else 0)
                       for p in s.get("pts") or [] for i, c in enumerate(p)]
                if len(pts) >= 4:
                    cv.create_line(*pts, fill="#555555", width=1.5,
                                   arrow=tk.LAST if s.get("arrow") else tk.NONE,
                                   dash=(5, 3) if s.get("dash") else ())
                    if s.get("text"):
                        mx, my = (pts[0] + pts[2]) / 2, (pts[1] + pts[3]) / 2
                        cv.create_text(mx + 10, my - 8, text=s["text"], fill="#333333",
                                       font=(FONT, 9))
            elif t == "zone":
                x, y, w, h = s["x"], s["y"] + top, s["w"], s["h"]
                cv.create_rectangle(x, y, x + w, y + h, outline=ZONE_EDGE, dash=(4, 3))
                cv.create_text(x + 6, y + 4, text=s.get("text") or "", anchor="nw",
                               fill=ZONE_EDGE, font=(FONT, 9))
            elif t == "box":
                x, y, w, h = s["x"], s["y"] + top, s["w"], s["h"]
                shape = s.get("shape") or "rect"
                fill = {"device": "#f4f6fa", "note": NOTE, "cloud": "#e8f1ff",
                        "circle": "#f1f7ff"}.get(shape, "white")
                _outline(cv, shape, x, y, x + w, y + h, fill=fill, outline="#555555", width=1.5)
                cv.create_text(x + w / 2, y + h / 2, text=s.get("text") or "",
                               font=(FONT, 10), fill="#222222", width=max(40, w - 10),
                               justify="center")
        for sid, s in self.slots.items():
            self._slot(sid, s["x"], s["y"] + top, s["w"], s["h"], s.get("shape") or "rect",
                       s.get("label") or sid)

    def _slot(self, sid, x, y, w, h, shape, label):
        """一个热区：绿色虚线框 + 标签；放了卡片就把卡片画在里面。"""
        cv = self.cv
        self.slot_box[sid] = (x, y, x + w, y + h)
        inside = self.placed.get(sid) or []
        _outline(cv, shape, x, y, x + w, y + h, fill=SLOT_FILL if not inside else "white",
                 outline=SLOT_EDGE, dash=(5, 3), width=2)
        if not inside:
            cv.create_text(x + w / 2, y + h / 2, text=label, fill=SLOT_EDGE,
                           font=(FONT, 10, "bold"))
            return
        cap = int(self.slots.get(sid, {}).get("cap") or 1)
        if cap == 1:
            it = self.items.get(inside[0])
            if it:
                cw, ch = self._chip_size(it)
                if self.mode == "code":
                    cw = w - 6               # 占满整行空位，缩进才对得齐
                cw, ch = min(cw, w - 6), min(ch, h - 6)
                self._chip(it, x + (w - cw) / 2, y + (h - ch) / 2, cw, ch)
            return
        # 能放很多张的大框（归类题）：标题写在左上角，卡片排成几行
        cv.create_text(x + 8, y + 6, text=label, anchor="nw", fill=SLOT_EDGE,
                       font=(FONT, 9, "bold"))
        cx, cy = x + 10, y + 30
        for iid in inside:
            it = self.items.get(iid)
            if not it:
                continue
            cw, ch = self._chip_size(it)
            if cx + cw > x + w - 8:
                cx, cy = x + 10, cy + CHIP_H + 8
            self._chip(it, cx, cy, cw, ch)
            cx += cw + 8

    def _code(self, top: int) -> int:
        """程序填空 / 排序：一行一行画，行里的空位就是热区。返回画到哪儿了。"""
        cv = self.cv
        y = top + 4
        for row in self.env.get("rows") or []:
            x = 20
            for seg in row:
                if isinstance(seg, dict):
                    sid = str(seg.get("slot"))
                    s = self.slots.get(sid, {})
                    w = int(s.get("w") or 110)
                    self._slot(sid, x, y, w, 28, "rect", s.get("label") or sid)
                    x += w + 4
                else:
                    text = str(seg)
                    cv.create_text(x, y + 14, text=text, anchor="w", font=self.code_font,
                                   fill="#1f2d3d")
                    x += self.code_font.measure(text)
            y += 34
        return y + 6

    # ---------------- 拖 ----------------
    def _chip_at(self, event) -> str:
        for obj in self.cv.find_withtag("current"):
            for tag in self.cv.gettags(obj):
                if tag.startswith("chip-"):
                    return tag[len("chip-"):]
        return ""

    def _press(self, event):
        iid = self._chip_at(event)
        if not iid:
            return
        tag = f"chip-{iid}"
        self.cv.tag_raise(tag)
        self.drag = {"iid": iid, "tag": tag, "x": event.x, "y": event.y,
                     "from": self.where(iid)}

    def _move(self, event):
        if not self.drag:
            return
        self.cv.move(self.drag["tag"], event.x - self.drag["x"], event.y - self.drag["y"])
        self.drag["x"], self.drag["y"] = event.x, event.y

    def _release(self, event):
        if not self.drag:
            return
        got, self.drag = self.drag, None
        target = self.slot_at(self.cv.canvasx(event.x), self.cv.canvasy(event.y))
        if target:
            self.place(got["iid"], target)
        elif got["from"]:
            self.place(got["iid"], "")     # 从热区拖出来、松在外面：拿回素材区
        else:
            self.redraw()                  # 素材区里挪了挪又放下：回原位

    def slot_at(self, x, y) -> str:
        """这个点落在哪个热区里。重叠时取面积小的那个（大框套小框时要的是小框）。"""
        hits = [(abs((b[2] - b[0]) * (b[3] - b[1])), sid)
                for sid, b in self.slot_box.items()
                if b[0] <= x <= b[2] and b[1] <= y <= b[3]]
        return min(hits)[1] if hits else ""


# ================================================================ 本机 IP 查询
IPV4 = re.compile(r"^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$")


class IpBox(tk.Frame):
    """查本机 IP 并填空。桌面端查的是**这台真机**：打开命令提示符、ipconfig。"""

    def __init__(self, master, env: dict, state: dict | None, on_change, **kw):
        super().__init__(master, bg=CARD, **kw)
        self.on_change = on_change
        tip = (env or {}).get("tip") or ""
        tk.Label(self, text=tip, bg=CARD, fg=GRAY, font=(FONT, 9), anchor="w",
                 wraplength=640, justify="left").pack(fill="x", pady=(2, 8))
        row = tk.Frame(self, bg=CARD)
        row.pack(anchor="w")
        tk.Button(row, text="打开命令提示符", bg=BLUE, fg="white", font=(FONT, 10, "bold"),
                  relief="flat", cursor="hand2", command=self.open_cmd).pack(side="left")
        tk.Label(row, text="查到的 IPv4 地址：", bg=CARD, font=(FONT, 10)).pack(side="left",
                                                                         padx=(16, 4))
        self.var = tk.StringVar(value=str((state or {}).get("ip") or ""))
        box = tk.Entry(row, textvariable=self.var, width=18, font=("Consolas", 12))
        box.pack(side="left")
        self.hint = tk.Label(self, text="", bg=CARD, font=(FONT, 9), anchor="w")
        self.hint.pack(fill="x", pady=(6, 0))
        self.var.trace_add("write", lambda *_: self.changed())
        self.changed(first=True)

    def changed(self, first=False):
        text = re.sub(r"\s+", "", self.var.get())
        if not text:
            self.hint.config(text="", fg=GRAY)
        elif IPV4.match(text):
            self.hint.config(text="格式正确，交卷时一起提交", fg=GREEN)
        else:
            self.hint.config(text="格式不对：IPv4 地址是四组 0～255 的数字，用点隔开",
                             fg="#c8433a")
        if not first:
            self.on_change({"ip": text})

    @staticmethod
    def open_cmd():
        try:
            subprocess.Popen("cmd.exe", creationflags=getattr(subprocess,
                                                              "CREATE_NEW_CONSOLE", 0))
        except OSError:
            pass
