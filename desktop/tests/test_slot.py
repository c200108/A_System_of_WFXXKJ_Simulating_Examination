# -*- coding: utf-8 -*-
"""网站导出 exe 时写进去的教师端地址（地址槽，学生端 4.15.0）。"""

from __future__ import annotations

from client import shell, slot, update


def _exe(addr=""):
    data = b"MZ" + b"\x00" * 500 + slot.placeholder().encode(slot.ENC) + b"\xff" * 500
    return slot.write(data, addr) if addr else data


def test_占位读出来是空_写了读得回来_长度不变():
    raw = _exe()
    assert slot.read(raw) == ""
    out = slot.write(raw, "https://exam.school.cn:8443")
    assert len(out) == len(raw) and slot.read(out) == "https://exam.school.cn:8443"
    assert slot.read(b"MZ no slot here") is None


def test_打包写的版本信息里带着占位():
    import build
    text = build.write_version_file(build.HERE / "build" / "版本信息-测试.txt", "4.15.0").read_text("utf-8")
    assert slot.placeholder() in text and "(4, 15, 0, 0)" in text


def test_地址优先级_文件名_网站写入_本机记录_打包内置(monkeypatch):
    from client import store, ui

    monkeypatch.setattr(ui, "server_from_name", lambda: "")
    monkeypatch.setattr(ui, "slot_server", lambda: "https://exam.school.cn")
    monkeypatch.setattr(store, "remembered_server", lambda: "10.0.0.9")
    monkeypatch.setattr(ui, "baked_server", lambda: "1.1.1.1")
    assert ui.default_server() == "https://exam.school.cn"
    monkeypatch.setattr(ui, "server_from_name", lambda: "192.168.1.8:8080")
    assert ui.default_server() == "192.168.1.8:8080", "文件名最优先（网管改名换地址）"


def test_源码里跑_没有地址槽():
    shell._SLOT.clear()
    assert shell.slot_server() == ""


def test_自动更新把地址带进新版(tmp_path):
    new = tmp_path / "新版.exe"
    new.write_bytes(_exe())
    assert update.carry_slot(new, "http://10.0.0.5:3315")
    assert slot.read_file(new) == "http://10.0.0.5:3315"
    old_style = tmp_path / "老版.exe"
    old_style.write_bytes(b"MZ no slot")
    assert not update.carry_slot(old_style, "http://10.0.0.5:3315"), "没有槽的退回改文件名"
