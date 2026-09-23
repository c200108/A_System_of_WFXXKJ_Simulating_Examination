# -*- coding: utf-8 -*-
"""拖拽题的作答区（client/dragboard.py）。

从头到尾走一条链：服务端的题目清单 → 桌面端画出来 → 学生拖卡片 → 交上去的终态
→ 服务端判分。任何一环对不上，学生在考场上拖对了也拿不到分。
"""

from __future__ import annotations

import types

import pytest

from app.services import drag, sim
from client import dragboard, states


def _board(tk_root, entry, state=None, sink=None):
    env = entry["env"]
    kind = dragboard.IpBox if env["mode"] == "ip" else dragboard.DragBoard
    got = kind(tk_root, env, state, (sink.append if sink is not None else (lambda _s: None)))
    tk_root.update_idletasks()
    return got


def _center(board, sid):
    x1, y1, x2, y2 = board.slot_box[sid]
    return (x1 + x2) / 2, (y1 + y2) / 2


def _drop(board, iid, sid):
    """按住卡片、松在热区中间 —— 走的是真正处理松手的那段代码。"""
    board.drag = {"iid": iid, "tag": f"chip-{iid}", "x": 0, "y": 0, "from": board.where(iid)}
    x, y = _center(board, sid) if sid else (5, 5)
    board._release(types.SimpleNamespace(x=x, y=y))


DIAGRAMS = [e for e in drag.BANK if e["env"]["mode"] != "ip"]


@pytest.mark.parametrize("entry", DIAGRAMS, ids=lambda e: e["key"])
def test_每一道题的图都画得出来(tk_root, entry):
    board = _board(tk_root, entry)
    try:
        assert set(board.slot_box) == {s["id"] for s in entry["env"]["slots"]}, \
            "有热区没画出来，学生就没地方放卡片"
        on_canvas = {t for obj in board.cv.find_all() for t in board.cv.gettags(obj)}
        for it in entry["env"]["items"]:
            assert f"chip-{it['id']}" in on_canvas, f"素材区少了卡片 {it['text']}"
    finally:
        board.destroy()


@pytest.mark.parametrize("entry", DIAGRAMS, ids=lambda e: e["key"])
def test_照答案拖完_交上去拿满分(tk_root, entry):
    """桌面端拖出来的终态，服务端要能判满分 —— 两头对得上才算数。"""
    seen = []
    board = _board(tk_root, entry, sink=seen)
    try:
        for c in entry["checks"]:
            a = c["assert"]
            if a["op"] == "slot":
                _drop(board, a["is"][0], a["slot"])
            elif a["op"] == "in":
                free = [s for s in a["slots"] if not board.placed.get(s)]
                _drop(board, a["item"], free[0] if free else a["slots"][0])
        ran = sim.run_checks("drag", entry["checks"], seen[-1])
        assert ran["score"] == ran["full"], ran["results"]
    finally:
        board.destroy()


def test_一个热区只放一张_后放的顶掉先放的(tk_root):
    entry = next(e for e in drag.BANK if e["key"] == "Q322-话费")
    board = _board(tk_root, entry)
    try:
        _drop(board, "i2", "A")
        _drop(board, "i1", "A")
        assert board.placed == {"A": ["i1"]}, "被顶掉的那张应该回到素材区"
        assert board.where("i2") == ""
    finally:
        board.destroy()


def test_从热区拖回素材区就是拿回来(tk_root):
    entry = next(e for e in drag.BANK if e["key"] == "Q322-话费")
    seen = []
    board = _board(tk_root, entry, sink=seen)
    try:
        _drop(board, "i1", "A")
        _drop(board, "i1", "")                 # 松在热区外面
        assert board.placed == {} and seen[-1] == {"placed": {}}
    finally:
        board.destroy()


def test_同一张卡片不会同时出现在两个热区(tk_root):
    entry = next(e for e in drag.BANK if e["key"] == "Q306-校园网")
    board = _board(tk_root, entry)
    try:
        _drop(board, "i1", "H1")
        _drop(board, "i1", "H3")
        assert board.placed == {"H3": ["i1"]}
    finally:
        board.destroy()


def test_归类题的大框能放很多张(tk_root):
    entry = next(e for e in drag.BANK if e["key"] == "Q338-智能家居归类")
    board = _board(tk_root, entry)
    try:
        for iid in ("i2", "i3", "i6", "i7", "i11", "i12"):
            _drop(board, iid, "Z")
        assert len(board.placed["Z"]) == 6
    finally:
        board.destroy()


def test_草稿恢复_上次放好的还在原位(tk_root):
    entry = next(e for e in drag.BANK if e["key"] == "Q325-成绩")
    board = _board(tk_root, entry, state={"placed": {"A": ["i1"], "B": ["i3"]}})
    try:
        assert board.where("i1") == "A" and board.where("i3") == "B"
    finally:
        board.destroy()


def test_IP题_填的地址和本机真实地址一起交上去(tk_root):
    entry = next(e for e in drag.BANK if e["key"] == "Q310-本机IP")
    seen = []
    box = _board(tk_root, entry, sink=seen)
    try:
        real = states.local_ipv4()
        box.var.set(real[0] if real else "10.0.0.8")
        assert seen and seen[-1]["ip"]
    finally:
        box.destroy()

    paper = [{"id": 9, "sim": {"kind": "drag", "manual": False, "env": {"mode": "ip"}}}]
    got = states.collect(paper, "C:/不存在的考试目录", "", drags={"9": seen[-1]})
    assert "real_ips" in got["9"], "交卷时要顺手记下本机真实地址，服务端拿它比"
    ran = sim.run_checks("drag", entry["checks"], got["9"])
    if real:
        assert ran["score"] == ran["full"]


def test_交卷时拖拽题的作答跟着交上去():
    paper = [{"id": 5, "sim": {"kind": "drag", "manual": False, "env": {"mode": "diagram"}}},
             {"id": 6, "sim": {"kind": "drag", "manual": False, "env": {"mode": "diagram"}}}]
    got = states.collect(paper, "C:/不存在的考试目录", "",
                         drags={"5": {"placed": {"A": ["i1"]}}})
    assert got["5"] == {"placed": {"A": ["i1"]}}
    assert got["6"] == {"placed": {}}, "没作答的也要交一份空的，判 0 分而不是报错"
