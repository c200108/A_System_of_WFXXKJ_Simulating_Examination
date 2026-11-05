# -*- coding: utf-8 -*-
"""选择判断题乱序：每个学生看到的选择题、判断题顺序和选择题选项顺序各不相同。

和网页答题（frontend/src/shuffle.js）是同一套规矩：

  · **只在同一大题里换**（按题型组卷时一个大题就是一种题型）。同一大题里选择题
    和选择题换、判断题和判断题换，各占原来的位置；操作题一道都不动。
  · 选择题的选项也打乱。**交上去的还是原来的选项字母**（"label"），屏幕上显示的是
    新位置的字母（"show"）—— 判分在服务端按原字母，不受乱序影响。
  · 种子是「考试 + 学号」：同一个学生重开程序、断电接着考，看到的顺序不变。
    判断题的「正确 / 错误」两个选项不换。

考试包里有 "shuffle": true 才打乱（老师组卷时开了「选择判断题乱序」）。
"""

from __future__ import annotations

import random

TYPES = ("选择题", "判断题")


def _options(q: dict, rnd: random.Random) -> dict:
    opts = q.get("options") or []
    if q.get("type") != "选择题" or len(opts) < 2:
        return q
    order = list(opts)
    rnd.shuffle(order)
    return dict(q, options=[dict(o, show=opts[i]["label"]) for i, o in enumerate(order)])


def shuffle_paper(paper: list, seed: str) -> list:
    """按种子打乱一份卷子（paper.json 那个扁平列表，每题带 section）。原列表不动。"""
    rnd = random.Random(str(seed))
    out = list(paper)
    sections: list = []                      # 按出现的先后，保证每次打乱的次序一样
    for q in out:
        sec = q.get("section") or q.get("type")
        if sec not in sections:
            sections.append(sec)
    for sec in sections:
        for kind in TYPES:
            at = [i for i, q in enumerate(out)
                  if (q.get("section") or q.get("type")) == sec and q.get("type") == kind]
            moved = [out[i] for i in at]
            rnd.shuffle(moved)
            for pos, q in zip(at, moved):
                out[pos] = q
    return [_options(q, rnd) for q in out]


def shown_label(q: dict, label: str) -> str:
    """原选项字母 → 学生屏幕上看到的字母（没乱序就是它自己）。"""
    for o in q.get("options") or []:
        if o.get("label") == label:
            return o.get("show") or label
    return label
