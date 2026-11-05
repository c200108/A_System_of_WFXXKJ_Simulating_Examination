# -*- coding: utf-8 -*-
"""选择判断题乱序（学生端 4.14.0）：只在同一大题里换、操作题不动、选项换位置但交原字母。"""

from __future__ import annotations

from client.shuffle import shown_label, shuffle_paper


def _paper():
    ops = [{"label": x, "content": "选项" + x} for x in "ABCD"]
    return (
        [{"id": f"c{i}", "type": "选择题", "section": "一、基础", "options": ops} for i in range(6)]
        + [{"id": "op1", "type": "操作题", "section": "一、基础"}]
        + [{"id": f"j{i}", "type": "判断题", "section": "一、基础",
            "options": [{"label": "A", "content": "正确"}, {"label": "B", "content": "错误"}]}
           for i in range(4)]
        + [{"id": f"d{i}", "type": "选择题", "section": "四、网络", "options": ops} for i in range(5)]
        + [{"id": "op2", "type": "操作题", "section": "五、操作"}]
    )


def test_同一个学生每次一样_不同学生不一样():
    p = _paper()
    a, b = shuffle_paper(p, "9-26090111"), shuffle_paper(p, "9-26090111")
    assert a == b
    others = {tuple(q["id"] for q in shuffle_paper(p, f"9-{n}")) for n in range(20)}
    assert len(others) > 1, "二十个学生顺序全一样，等于没乱"


def test_不跨大题_各题型占原来的位置_操作题不动():
    p = _paper()
    for n in range(30):
        got = shuffle_paper(p, f"exam-{n}")
        assert [q["section"] for q in got] == [q["section"] for q in p]
        assert [q["type"] for q in got] == [q["type"] for q in p]
        for before, after in zip(p, got):
            if before["type"] == "操作题":
                assert after["id"] == before["id"]
        # 第四大题的选择题还是那五道，一道都没跑出去
        assert sorted(q["id"] for q in got if q["section"] == "四、网络") == \
            sorted(q["id"] for q in p if q["section"] == "四、网络")
    assert sorted(q["id"] for q in got) == sorted(q["id"] for q in p)


def test_选项换位置_显示新字母_交原字母():
    p = _paper()
    moved = 0
    for n in range(10):
        for q in shuffle_paper(p, f"s{n}"):
            if q["type"] != "选择题":
                continue
            opts = q["options"]
            assert [o["show"] for o in opts] == list("ABCD")         # 屏幕上还是 A B C D
            assert sorted(o["label"] for o in opts) == list("ABCD")   # 原字母一个不少
            for o in opts:
                assert o["content"] == "选项" + o["label"]           # 内容跟着原字母走
                assert shown_label(q, o["label"]) == o["show"]
            moved += any(o["label"] != o["show"] for o in opts)
    assert moved, "选项从来没换过位置"


def test_判断题的正确错误不换():
    for q in shuffle_paper(_paper(), "x"):
        if q["type"] == "判断题":
            assert [o["label"] for o in q["options"]] == ["A", "B"]
            assert "show" not in q["options"][0]


def test_原卷子不被改动():
    p = _paper()
    snapshot = repr(p)
    shuffle_paper(p, "y")
    assert repr(p) == snapshot
