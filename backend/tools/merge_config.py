# -*- coding: utf-8 -*-
"""还原备份时合并 config.yaml：**旧的值全留着，新版本多出来的配置项补进去**（2.12.1）。

    python -m tools.merge_config 备份里的config.yaml 新版的config.yaml [输出文件]
    python -m tools.merge_config - /app/config.yaml < 备份.yaml > 合并后.yaml     （旧的从标准输入读）

## 为什么不能直接拿备份盖

早期导出的备份里，config.yaml 是当时那个版本的：没有 time（时钟校正）、没有 typing 的防刷
和名单比对、没有组卷里的 sim_kinds 说明……整个盖上去，新功能的配置项全没了 —— 程序照样按内置
默认值跑，但老师打开 config.yaml 根本不知道还有这些能改。

## 怎么合

- 以**备份那份的文字**为底：老师改过的值、写的注释、顺序一律不动；
- 新版本有、备份没有的键，连同它上面的注释整块抄过来，放在新版本里它前一个兄弟键的后面
  （缩进按备份那份的对齐）；
- 两边都有的键：值用备份的。都是一组键（字典）的往下一层接着比；列表（比如 paper.sections）
  整个用备份的 —— 那是学校自己定的卷面结构，不去拆；
- 备份里有、新版本没有的键：留着（新版本可能只是没写出来，程序照样认）。

合完再做两道检查，任一不过就**不输出**（退出码 1），由调用方保留新版本那份：

1. 合出来的文字解析后，必须正好等于「新的打底、旧的覆盖」算出来的那份数据 ——
   文字拼接出了任何差错都会在这一步露出来；
2. 能通过系统的配置校验（app.siteconfig），保证重启后端起得来。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

KEY = re.compile(r"^(\s*)((?:\"[^\"]*\"|'[^']*'|[^\s#\-\"'][^:#]*?))\s*:(?:\s|$)")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _meta(line: str) -> bool:
    """空行或注释行 —— 不算结构。"""
    s = line.strip()
    return not s or s.startswith("#")


def _key_of(line: str) -> str | None:
    m = KEY.match(line)
    return m.group(2).strip().strip("\"'") if m else None


def _block_end(lines: list, idx: int) -> int:
    """键在 idx 行，它的值占到哪一行为止（不含）。末尾的空行和注释归下一个键，不算进来。"""
    k = _indent(lines[idx])
    last = idx
    j = idx + 1
    while j < len(lines):
        line = lines[j]
        if not _meta(line):
            if _indent(line) < k or (_indent(line) == k and not line.lstrip().startswith("- ")):
                break
            last = j
        j += 1
    return last + 1


def _lead_start(lines: list, idx: int) -> int:
    """键上面紧挨着的那几行注释从哪一行开始（遇到空行或别的内容就停）。"""
    i = idx
    while i > 0 and lines[i - 1].strip().startswith("#"):
        i -= 1
    return i


def _children(lines: list, start: int, end: int) -> tuple[int, "dict[str, int]"]:
    """lines[start:end] 这一层的键：(这一层的缩进, {键: 行号})。"""
    indent = None
    found: "dict[str, int]" = {}
    for i in range(start, end):
        line = lines[i]
        if _meta(line):
            continue
        ind = _indent(line)
        if indent is None:
            indent = ind
        if ind == indent:
            key = _key_of(line)
            if key is not None:
                found.setdefault(key, i)
    return (indent or 0), found


def _layer(lines: list, path: list) -> tuple[int, int, int, "dict[str, int]"] | None:
    """path 指的那一组键所在的范围：(开始行, 结束行, 缩进, {键: 行号})。path 为空是最外层。"""
    start, end = 0, len(lines)
    for key in path:
        indent, kids = _children(lines, start, end)
        if key not in kids:
            return None
        idx = kids[key]
        start, end = idx + 1, _block_end(lines, idx)
    indent, kids = _children(lines, start, end)
    return start, end, indent, kids


def _insert(old: list, new: list, path: list, key: str, order: list) -> None:
    """把新版本里 path→key 这一整块（连注释）抄进旧的，放在它前一个兄弟后面。"""
    n_start, n_end, n_indent, n_kids = _layer(new, path)
    idx = n_kids[key]
    top = _lead_start(new, idx)
    block = new[top:_block_end(new, idx)]
    blank_before = top > 0 and not new[top - 1].strip()

    o_start, o_end, o_indent, o_kids = _layer(old, path)
    if not o_kids:                                   # 旧的这一层是空的：按新的缩进来
        o_indent = n_indent
    delta = o_indent - n_indent
    if delta:
        block = [(" " * delta + ln) if delta > 0 and ln.strip() else
                 (ln[-delta:] if delta < 0 and ln[:-delta].strip() == "" else ln) for ln in block]

    before = [k for k in order[:order.index(key)] if k in o_kids]
    if before:
        at = _block_end(old, o_kids[before[-1]])
    elif o_kids:
        at = _lead_start(old, min(o_kids.values()))
        blank_before = False
    else:
        at = o_start
    if blank_before:
        block = [""] + block
    old[at:at] = block


def _merged_data(new, old):
    """「新的打底、旧的覆盖」：两边都是字典的往下一层比，别的一律用旧的。"""
    if isinstance(new, dict) and isinstance(old, dict):
        out = dict(new)
        for k, v in old.items():
            out[k] = _merged_data(new[k], v) if k in new else v
        return out
    return old


def merge_text(old_text: str, new_text: str) -> tuple[str, list]:
    """返回 (合并后的文字, 补进来的键路径列表)。检查不过抛 ValueError。"""
    old_data = yaml.safe_load(old_text) or {}
    new_data = yaml.safe_load(new_text) or {}
    if not isinstance(old_data, dict) or not isinstance(new_data, dict):
        raise ValueError("config.yaml 最外层应该是一组 键: 值")
    old = old_text.replace("\r\n", "\n").split("\n")
    new = new_text.replace("\r\n", "\n").split("\n")
    added: list = []

    def walk(n: dict, o: dict, path: list) -> None:
        order = [str(k) for k in n]
        for k, v in n.items():
            k = str(k)
            if k not in {str(x) for x in o}:
                _insert(old, new, path, k, order)
                added.append(".".join(path + [k]))
            elif isinstance(v, dict) and isinstance(o.get(k), dict):
                walk(v, o[k], path + [k])

    walk(new_data, old_data, [])
    text = "\n".join(old)
    if not text.endswith("\n"):
        text += "\n"
    got = yaml.safe_load(text) or {}
    if got != _merged_data(new_data, old_data):
        raise ValueError("合并出来的文字和预期的数据对不上（多半是 config.yaml 的写法太特别），没有采用")
    return text, added


def check(text: str) -> None:
    """能不能被系统认：和后端启动时同一套校验。"""
    from app.siteconfig import SiteConfig
    from pydantic import ValidationError

    try:
        SiteConfig.model_validate(yaml.safe_load(text) or {})
    except ValidationError as exc:
        where = "；".join(" → ".join(str(x) for x in e["loc"]) + "：" + e["msg"] for e in exc.errors()[:5])
        raise ValueError(f"合并后的配置通不过校验：{where}") from exc


def main(argv: list) -> int:
    if len(argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    old_text = sys.stdin.buffer.read().decode("utf-8-sig") if argv[0] == "-" else \
        Path(argv[0]).read_text(encoding="utf-8-sig")
    new_text = Path(argv[1]).read_text(encoding="utf-8-sig")
    try:
        text, added = merge_text(old_text, new_text)
        check(text)
    except (ValueError, yaml.YAMLError) as exc:
        print(f"[合并 config.yaml] {exc}", file=sys.stderr)
        return 1
    if len(argv) == 3:
        Path(argv[2]).write_text(text, encoding="utf-8", newline="\n")
    else:
        sys.stdout.buffer.write(text.encode("utf-8"))
    print("[合并 config.yaml] " + (f"补进新版本的 {len(added)} 项：" + "、".join(added) if added
                                  else "备份里的配置项已经齐全，不用补"), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
