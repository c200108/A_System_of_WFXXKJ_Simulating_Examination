# -*- coding: utf-8 -*-
"""交卷之后清场：把还开着的考试文件关掉，再把考试文件夹抹干净。

## 为什么要强制关

学生做完 WPS 题不一定会关窗口，做完 Windows 题资源管理器还停在那儿。Windows
上**被打开的文件删不掉** —— 于是下一场考试铺不了考场，程序报"准备考场失败"，
监考老师得一台台去关程序。考场里这是最耽误事的一类问题。

## 只关考试文件

按窗口标题匹配：标题里出现了考试文件名或考试文件夹名，才动它。学生自己的东西
不碰。两步走：

    ① 先礼貌关（WM_CLOSE）—— 和点窗口右上角的叉一样
    ② 还在就结束进程 —— 只对**没关掉的、标题匹配上的**那个进程

**explorer.exe 永远只礼貌关，绝不结束进程** —— 它是桌面外壳，杀掉整个桌面就
没了，任务栏、开始菜单、图标全消失，考场会炸。

## 关不掉也不能崩

清场失败顶多是下一场要人工处理，而**交卷已经完成了**。所以这里所有异常都吞掉，
只把"还剩什么没删掉"报出去给界面显示。
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from . import snapshot

WM_CLOSE = 0x0010
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# 结束进程的黑名单：关掉它们的代价比留着脏文件大得多
NEVER_KILL = {"explorer.exe", "dwm.exe", "csrss.exe", "winlogon.exe", "svchost.exe"}


def _win_api():
    """拿 Windows API。不是 Windows（比如在 Linux 上跑测试）就返回 None。"""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        return ctypes, wintypes
    except Exception:                                   # noqa: BLE001
        return None


def target_names(root: Path) -> set[str]:
    """哪些名字算"考试的东西"。

    收考试文件夹里每个文件和文件夹的名字（带扩展名的、不带的都要）：WPS 的标题栏
    写的是不带扩展名的文档名，资源管理器写的是文件夹名。

    **太短的名字不要**，否则会误伤别人的窗口。门槛按字符类型分开定：

      · 带中文的两个字就够独特（「素材」「会徽」都是真实的考场文件夹名）
      · 纯英文数字要四个字符以上 —— 「ab」「a」这种能匹配上一大片
    """
    root = Path(root)
    names = {root.name}
    if root.exists():
        for p in root.rglob("*"):
            names.add(p.name)
            if p.suffix:
                names.add(p.stem)
    return {n for n in names if _distinctive(n)}


def _distinctive(name: str) -> bool:
    if any("一" <= ch <= "鿿" for ch in name):
        return len(name) >= 2
    return len(name) >= 4


def _matched_windows(names: set[str]):
    """标题里出现了这些名字的可见窗口。返回 [(hwnd, 标题, 进程号), …]。"""
    api = _win_api()
    if not api or not names:
        return []
    ctypes, wintypes = api
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found = []
    mine = os.getpid()

    def on_window(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value or ""
            if not any(n in title for n in names):
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value and pid.value != mine:        # 别把自己关了
                found.append((hwnd, title, pid.value))
        except Exception:                               # noqa: BLE001
            pass
        return True

    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                              wintypes.LPARAM)(on_window)
    try:
        user32.EnumWindows(proc, 0)
    except Exception:                                   # noqa: BLE001
        return []
    return found


def _process_name(pid: int) -> str:
    api = _win_api()
    if not api:
        return ""
    ctypes, wintypes = api
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(260)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return Path(buf.value).name.lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def close_exam_windows(root: Path, wait: float = 1.5) -> list[str]:
    """关掉还开着的考试文件。返回关掉了哪些窗口（标题）。

    先 WM_CLOSE，等一会儿；还在的就结束进程 —— 但 explorer 之类只关不杀。
    """
    api = _win_api()
    names = target_names(root)
    if not api or not names:
        return []
    ctypes, _ = api
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    closed = []
    for hwnd, title, _pid in _matched_windows(names):
        try:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            closed.append(title)
        except Exception:                               # noqa: BLE001
            pass
    if not closed:
        return []

    time.sleep(wait)                     # 给程序一点时间自己退

    # 还赖着不走的：结束进程。WPS 有未保存改动时会弹"要保存吗"卡在那儿 ——
    # 快照早在交卷时就拍完了，这时候的改动不影响判分，可以放心关
    for _hwnd, title, pid in _matched_windows(names):
        name = _process_name(pid)
        if name in NEVER_KILL:
            continue                     # 杀 explorer 会把整个桌面带走
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if handle:
            try:
                kernel32.TerminateProcess(handle, 0)
            except Exception:                           # noqa: BLE001
                pass
            finally:
                kernel32.CloseHandle(handle)
    return closed


def wipe(root: Path, tries: int = 3) -> tuple[bool, list[str]]:
    """清空考试文件夹。返回 (干净了没有, 还剩下什么)。

    **清之前先关文件** —— Windows 上打开着的文件删不掉，不关就永远清不干净。
    删一次不成就等一下再来：程序关闭是异步的，句柄不会在窗口消失的同一瞬间释放。
    """
    root = Path(root)
    if not root.exists():
        return True, []
    close_exam_windows(root)

    for i in range(max(1, tries)):
        try:
            snapshot.rmtree_force(root)      # 顺手去掉只读，否则删不动
        except Exception:                                # noqa: BLE001
            pass
        left = [p.name for p in root.iterdir()] if root.exists() else []
        if not left:
            break
        if i < tries - 1:
            time.sleep(0.6)
    left = [p.name for p in root.rglob("*")] if root.exists() else []
    if not left and root.exists():
        try:
            shutil.rmtree(root, ignore_errors=True)
        except Exception:                                # noqa: BLE001
            pass
    return (not left), left[:8]
