# -*- coding: utf-8 -*-
"""交卷后清场：关掉还开着的考试文件，抹干净考试文件夹。

考场里最耽误事的一类问题就是这个：学生做完 WPS 题不关窗口，Windows 上**被打开
的文件删不掉**，下一场铺不了考场，监考老师得一台台去关程序。

这里验两件事：**该清的清干净了**，以及**不该动的一律不碰**（窗口匹配要够窄，
explorer 永远不杀）。真去开一个 WPS 窗口没法在测试里做，所以杀进程那一段靠
黑名单和匹配规则来守。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from client import cleanup


@pytest.fixture
def exam_folder(tmp_path):
    """一个铺好的考场：两层目录、几个文件。"""
    root = tmp_path / "EXAM"
    (root / "win02" / "素材").mkdir(parents=True)
    (root / "win02" / "会徽").mkdir(parents=True)
    (root / "win02" / "素材" / "冬奥介绍.txt").write_bytes("北京冬奥会".encode("gbk"))
    (root / "职业教育大有可为.docx").write_bytes(b"PK\x03\x04fake")
    return root


# ================================================================ 匹配谁
def test_names_cover_files_and_folders(exam_folder):
    """WPS 的标题栏写的是不带扩展名的文档名，资源管理器写的是文件夹名，
    两种都得认得出来。"""
    names = cleanup.target_names(exam_folder)
    assert "职业教育大有可为.docx" in names
    assert "职业教育大有可为" in names, "WPS 标题栏不带扩展名"
    assert "win02" in names and "素材" in names
    assert "EXAM" in names


def test_short_names_are_ignored(tmp_path):
    """名字太短会误伤别人的窗口。门槛按字符类型分开：中文两个字就够独特
    （「素材」「会徽」都是真实的考场文件夹名），纯英文数字得四个字符以上。"""
    root = tmp_path / "EXAM"
    (root / "ab").mkdir(parents=True)
    (root / "a.txt").write_text("x", encoding="utf-8")
    (root / "素材").mkdir()
    names = cleanup.target_names(root)
    assert "ab" not in names and "a" not in names
    assert "a.txt" in names           # 带扩展名的够长，留着
    assert "素材" in names            # 中文两个字，留着


def test_explorer_is_never_killed():
    """**杀 explorer 会把整个桌面带走** —— 任务栏、开始菜单、图标全没。
    关它可以，杀它绝对不行。"""
    assert "explorer.exe" in cleanup.NEVER_KILL


# ================================================================ 清干净
def test_wipe_removes_everything(exam_folder):
    ok, left = cleanup.wipe(exam_folder)
    assert ok and not left
    assert not exam_folder.exists() or not list(exam_folder.rglob("*"))


def test_wipe_gets_past_read_only_files(exam_folder):
    """上一场学生把文件设成只读，不去掉属性就删不动 —— 考场里真撞过。"""
    victim = exam_folder / "win02" / "素材" / "冬奥介绍.txt"
    os.chmod(victim, 0o444)
    ok, left = cleanup.wipe(exam_folder)
    assert ok, f"只读文件挡住了清场：{left}"


def test_wipe_on_a_missing_folder_is_fine(tmp_path):
    """第一次开考时考试文件夹还不存在。"""
    ok, left = cleanup.wipe(tmp_path / "还没有这个")
    assert ok and not left


@pytest.mark.skipif(os.name != "nt", reason="按住文件句柄这件事只在 Windows 上成立")
def test_a_locked_file_is_reported_not_crashed(exam_folder):
    """**清不干净也不能崩** —— 交卷已经完成了，清场失败顶多是下一场要人工处理。

    这里故意自己按住一个文件（我们自己的进程会被跳过，不会自杀），
    于是它必然删不掉，看程序报不报得清楚。
    """
    victim = exam_folder / "win02" / "素材" / "冬奥介绍.txt"
    with open(victim, "rb"):
        ok, left = cleanup.wipe(exam_folder, tries=1)
    assert ok is False
    assert left, "没清干净就得说出还剩什么，不能默默算成功"


def test_closing_windows_never_touches_our_own_process(exam_folder):
    """自检窗口的标题里未必有考试文件名，但万一有，**不能把自己关了**。"""
    got = cleanup._matched_windows(cleanup.target_names(exam_folder))
    assert all(pid != os.getpid() for _h, _t, pid in got)


def test_close_is_a_no_op_without_names(tmp_path):
    assert cleanup.close_exam_windows(tmp_path / "不存在") == []
