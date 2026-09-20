# -*- coding: utf-8 -*-
"""界面上的字，Win7 的字体里得有。

机房里还有 Win7 机器，而 **Win7 没有 Segoe UI Emoji**：🏠 📝 ⌨ ✓ ⚠ 这些字符
在那儿会画成一个个空方框（豆腐块）。在自己的 Win10/11 上看不出来 —— 这台机器
字体全，怎么看都正常，**问题只在考场上出现**。

判据用得上现成的：**能编进 GBK 的字符，任何中文 Windows 的字体都有字形**。
GB2312/GBK 是中文 Windows 的基本字符集，宋体、微软雅黑对它的覆盖是完整的。
所以规则很简单 —— 源码里不许出现 GBK 装不下的字符。

顺带也把另一件事守住了：交卷记录（CSV）和装机自检报告都是 **GBK 落盘**的，
好让老师在考场机器上双击就能看（记事本打开 UTF-8 的中文 txt 是一屏乱码）。
真写进一个 GBK 编不出来的字符，那两份文件里就会出现「?」。
"""

from __future__ import annotations

from pathlib import Path

import pytest

DESKTOP = Path(__file__).resolve().parent.parent
FILES = sorted(DESKTOP.joinpath("client").glob("*.py")) + [DESKTOP / "exam_client.py"]


def _outside_gbk(text: str) -> set:
    out = set()
    for ch in set(text):
        try:
            ch.encode("gbk")
        except UnicodeEncodeError:
            out.add(ch)
    return out


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_源码里没有Win7显示不出来的字符(path):
    bad = _outside_gbk(path.read_text(encoding="utf-8"))
    assert not bad, (
        f"{path.name} 里有 GBK 装不下的字符：" +
        " ".join(f"U+{ord(c):04X} {c}" for c in sorted(bad)) +
        "　—— Win7 上会显示成方框，换成 √ × ◎ ◆ ★ ※ 这类 GBK 里有的"
    )


def test_替换用的符号确实在GBK里():
    """现在界面上用的那几个：换的时候别又换回方框去。"""
    for ch in "√×◎◆★※●○■←→":
        ch.encode("gbk")        # 编不出来就抛异常，用例当场失败


def test_侧边栏图标没有用表情():
    """侧边栏那三个图标最容易被顺手换成 emoji —— 看着好看，Win7 上是方框。"""
    from client.ui import ShellFrame

    for _key, icon, _label in ShellFrame.PAGES:
        assert not _outside_gbk(icon), f"侧边栏图标 {icon} 在 Win7 上会是方框"
