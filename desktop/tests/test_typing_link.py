# -*- coding: utf-8 -*-
"""打字成绩要挂到学生账号上。

学生首页的「练习次数 / 最快速度 / 平均正确率」只统计挂了账号的记录。
exe 原来交成绩**不带令牌也不带学号**，服务端认不出是谁，记录的 student_id
是空的 —— 老师在成绩页看得见，学生自己的首页却永远是 0（机房和线上都一样）。
"""

from __future__ import annotations

from client import api


def test_交打字成绩带上令牌和学号(monkeypatch):
    seen = {}

    def fake_json(url, body=None, timeout=api.TIMEOUT, token="", method=""):
        seen.update(url=url, body=body, token=token)
        return {"speed": 60, "accuracy": 95, "stars": 3}

    monkeypatch.setattr(api, "_json", fake_json)
    api.typing_submit("1.2.3.4:80", {"no": "26090101", "name": "张三", "cls": "八年级2班"},
                      "中文", "简单", 100, 95, 60.0, token="学生令牌")

    assert seen["url"].endswith("/api/typing/records")
    assert seen["token"] == "学生令牌", "不带令牌，服务端认不出是谁，首页永远是 0"
    assert seen["body"]["student_no"] == "26090101", "令牌过期时服务端靠学号认领"
