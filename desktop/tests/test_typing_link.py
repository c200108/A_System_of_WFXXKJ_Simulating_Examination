# -*- coding: utf-8 -*-
"""打字成绩要挂到学生账号上，而且只交会话（服务端 2.23.1）。

学生首页的「练习次数 / 最快速度 / 平均正确率」只统计挂了账号的记录 —— 所以开练、
同步、交成绩都带令牌。2.23.1 起 exe 不再报「敲了多少、对了多少、用了多久」三个数
（改个数字就能交上去一个满分），只交会话 id 和敲出来的内容，其余服务端自己算。
"""

from __future__ import annotations

from client import api


def _fake(monkeypatch, reply=None, error=None):
    seen = []

    def fake_json(url, body=None, timeout=api.TIMEOUT, token="", method=""):
        seen.append({"url": url, "body": body, "token": token})
        if error:
            raise error
        return reply if reply is not None else {}

    monkeypatch.setattr(api, "_json", fake_json)
    return seen


def test_开练带令牌和班级姓名_不限时(monkeypatch):
    seen = _fake(monkeypatch, {"session_id": "s1", "text": "原文"})
    got = api.typing_start("1.2.3.4:80", "中文", "简单",
                           {"no": "26090101", "name": "张三", "cls": "八年级2班"}, token="学生令牌")
    assert got["session_id"] == "s1"
    assert seen[0]["url"].endswith("/api/typing/sessions")
    assert seen[0]["token"] == "学生令牌", "不带令牌，服务端认不出是谁，首页永远是 0"
    body = seen[0]["body"]
    assert (body["student_name"], body["student_class"]) == ("张三", "八年级2班"), "令牌过期时服务端按名单认领"
    assert body["time_limit"] == 0, "exe 不限时"


def test_交成绩只交会话和内容_不报统计数(monkeypatch):
    seen = _fake(monkeypatch, {"speed": 60, "accuracy": 95, "stars": 3})
    api.typing_submit("1.2.3.4:80", "s1", "敲出来的字", token="学生令牌")
    assert seen[0]["url"].endswith("/api/typing/records")
    assert seen[0]["body"] == {"session_id": "s1", "answer": "敲出来的字"}
    assert seen[0]["token"] == "学生令牌"


def test_同步失败不打断_服务端说作废才停(monkeypatch):
    _fake(monkeypatch, {"ok": True})
    assert api.typing_progress("1.2.3.4:80", "s1", "abc") == ""
    _fake(monkeypatch, error=api.NetError("连不上教师端"))
    assert api.typing_progress("1.2.3.4:80", "s1", "abc") == "", "断网：下次再同步"
    _fake(monkeypatch, error=api.ApiError("服务器忙", status=503))
    assert api.typing_progress("1.2.3.4:80", "s1", "abc") == ""
    _fake(monkeypatch, error=api.ApiError("太快了", retry_after=3, status=429))
    assert api.typing_progress("1.2.3.4:80", "s1", "abc") == ""
    _fake(monkeypatch, error=api.ApiError("输入速度异常，这次练习作废", status=400))
    assert "作废" in api.typing_progress("1.2.3.4:80", "s1", "abc")


def test_设备号每次都一样_服务端认得(monkeypatch):
    """「同一台电脑每分钟只能交一次」服务端按 X-Device-Id 认电脑。按机器名和网卡算，
    不存文件 —— 机房还原卡一重启文件就没了。"""
    import re

    assert api._device_id() == api._device_id() == api.DEVICE_ID
    assert re.fullmatch(r"[A-Za-z0-9_-]{8,64}", api.DEVICE_ID), "格式不对服务端就当没带，退回认 IP"
