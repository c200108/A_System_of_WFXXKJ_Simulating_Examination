# -*- coding: utf-8 -*-
"""教师端地址（学生端 4.14.1）：输入框不带 http://；IP 直接 http；域名先 https、不通再 http，
试出来的记住；所有请求都走同一个选出来的地址。"""

from __future__ import annotations

import pytest

from client import api, store


@pytest.fixture(autouse=True)
def fresh(monkeypatch, tmp_path):
    """每条用例一份干净的「记住的协议」，配置文件写到临时目录。"""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setattr(store, "here", lambda: tmp_path)
    monkeypatch.setattr(api, "_schemes", {})
    monkeypatch.setattr(api, "_schemes_loaded", False)
    monkeypatch.setattr(api, "_dead", {})


def fake_net(monkeypatch, works: set):
    """假的网络：works 里列出哪些「协议://主机」连得上，记下每次试了谁。"""
    tried = []

    def request(url, *a, **k):
        head = url.split("/api/")[0]
        tried.append(head)
        if head in works:
            return b"{}"
        raise api.NetError("连不上")
    monkeypatch.setattr(api, "_request", request)
    return tried


@pytest.mark.parametrize("raw,want", [
    ("192.168.1.8", True), ("192.168.1.8:8000", True), ("203.0.113.10:8080", True),
    ("localhost:8000", True), ("[::1]:8000", True), ("http://10.0.0.2:80", True),
    ("exam.example.edu.cn", False), ("exam.xxx.edu.cn:8443", False), ("https://exam.example.edu.cn", False),
])
def test_认得出是IP还是域名(raw, want):
    assert api.is_ip_address(raw) is want


def test_输入框里不显示协议前缀():
    assert api.bare("http://192.168.1.8:8000/") == "192.168.1.8:8000"
    assert api.bare("https://exam.example.edu.cn") == "exam.example.edu.cn"
    assert api.bare("exam.example.edu.cn") == "exam.example.edu.cn"


def test_IP直接走http_不试https(monkeypatch):
    tried = fake_net(monkeypatch, set())
    assert api.base("203.0.113.10:8080") == "http://203.0.113.10:8080"   # 烤进 exe 的默认地址
    assert api.base("192.168.1.8") == "http://192.168.1.8"
    assert tried == []


def test_域名先试https_通了就用而且记住(monkeypatch):
    tried = fake_net(monkeypatch, {"https://exam.example.edu.cn"})
    assert api.base("exam.example.edu.cn") == "https://exam.example.edu.cn"
    assert api.base("exam.example.edu.cn") == "https://exam.example.edu.cn"
    assert tried == ["https://exam.example.edu.cn"], "试出来之后不该再试"
    assert store.load_config()["server_schemes"] == {"exam.example.edu.cn": "https"}


def test_域名https不通退http(monkeypatch):
    tried = fake_net(monkeypatch, {"http://exam.school.cn:8080"})
    assert api.base("exam.school.cn:8080") == "http://exam.school.cn:8080"
    assert tried == ["https://exam.school.cn:8080", "http://exam.school.cn:8080"]


def test_服务器回了4xx也算这个协议通(monkeypatch):
    def request(url, *a, **k):
        raise api.ApiError("服务器拒绝了（404）")
    monkeypatch.setattr(api, "_request", request)
    assert api.base("old.server.cn") == "https://old.server.cn"


def test_重开程序直接用记住的协议(monkeypatch):
    store.save_config(server_schemes={"exam.school.cn": "http"})
    tried = fake_net(monkeypatch, set())
    assert api.base("exam.school.cn") == "http://exam.school.cn"
    assert tried == []


def test_两个都不通_三十秒内不再白等(monkeypatch):
    tried = fake_net(monkeypatch, set())
    assert api.base("down.school.cn") == "https://down.school.cn"
    assert api.base("down.school.cn") == "https://down.school.cn"
    assert len(tried) == 2, "第二次不该再试两轮"


def test_自己写了协议的照写的走(monkeypatch):
    tried = fake_net(monkeypatch, set())
    assert api.base("http://exam.example.edu.cn") == "http://exam.example.edu.cn"
    assert tried == []


def test_记住的协议连不上了就忘掉(monkeypatch):
    store.save_config(server_schemes={"exam.example.edu.cn": "https"})
    api.forget("exam.example.edu.cn")
    assert store.load_config()["server_schemes"] == {}


def test_所有请求都走同一个选出来的地址(monkeypatch):
    seen = []
    monkeypatch.setattr(api, "base", lambda s: "https://exam.example.edu.cn")
    monkeypatch.setattr(api, "_json", lambda url, *a, **k: seen.append(url) or {})
    api.ping("exam.example.edu.cn")
    api.login("exam.example.edu.cn", "1", "2")
    api.signin("exam.example.edu.cn", "1")
    api.submit("exam.example.edu.cn", "tok", {"no": "1"}, {})
    api.typing_config("exam.example.edu.cn")
    assert seen and all(u.startswith("https://exam.example.edu.cn/api/") for u in seen)
