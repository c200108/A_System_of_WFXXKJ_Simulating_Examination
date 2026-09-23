# -*- coding: utf-8 -*-
"""把真实机器上的成果，变成服务器判分器认识的"终态"。

三类操作题，三种终态，**形状和网页版仿真器交上来的完全一致** —— 所以服务器那边
的检查点一个字都不用改，老师在网页上点出来的检查点，在真机上照样判：

    win   文件夹快照      {"fs": {...}, "recycle": {...}}      snapshot.py 拍
    wps   文档段落模型    {"paras": [...], "page": {...}}      docx.py 读
    html  网页源码        {"files": {"index.html": "…"}}       这里读

**三类要分开走，不能都交一份文件夹快照。** 这是踩过的：HTML 题交文件夹快照
上去，判分器拿不到 `files`，整道题判 0 分，而且两边日志都正常。

还有第四类：

    ai    对话记录          {"messages": [{"role": "user", "text": …}]}

它的"成果"不在文件系统里，是学生和 AI 工具的对话，由界面收集后传进来。
这类题**老师不用出检查点**：服务器按题干现算（提交过 + 提问覆盖了题目要求）。
"""

from __future__ import annotations

import json
import re
import socket
import subprocess
from pathlib import Path

from . import docx, snapshot

# 网页题会把这些文件收进去判。别收二进制，判分器只看源码
WEB_EXT = {".html", ".htm", ".css", ".js", ".txt"}
MAX_WEB_BYTES = 512 * 1024


def prefix_snapshot(shot: dict, logical_root: str) -> dict:
    """给快照里的相对路径加上前缀，对上服务器那边检查点的写法。

    客户端拍的是「win02/会徽/冬梦.txt」（相对考试文件夹，因为考试文件夹在哪台
    机器上都可能不一样）；服务器的检查点是出题时在网页仿真器里点出来的，写的是
    「C:/EXAM/win02/会徽/冬梦.txt」。差的就是这个前缀。

    **不加前缀的话，全班操作题都会判 0 分**，而且原因是"找不到这个文件"——
    最难查的那一种。操作题集体 0 分时，第一个查它。
    """
    root = str(logical_root or "").replace("\\", "/").rstrip("/")
    if not root:
        return shot
    out = {"meta": shot.get("meta", {})}
    for section in ("fs", "recycle"):
        out[section] = {f"{root}/{k}": v for k, v in (shot.get(section) or {}).items()}
    return out


def _web_files(folder: Path) -> dict:
    """把网页题那个文件夹里的源码读成 {文件名: 源码}。

    只读一层加子目录里的网页文件；样式表**必须一起收**，否则「把标题设成红色」
    这类检查点永远判不过 —— 样式在 style.css 里，不在 html 里。
    """
    out: dict[str, str] = {}
    if not folder.exists():
        return out
    base = folder if folder.is_dir() else folder.parent
    for p in sorted(base.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in WEB_EXT:
            continue
        try:
            if p.stat().st_size > MAX_WEB_BYTES:
                continue
            out[p.relative_to(base).as_posix()] = snapshot.read_text(p)
        except OSError:
            continue
    return out


def state_for(kind: str, root: Path, open_rel: str, logical_root: str,
              shot: dict | None = None) -> dict:
    """一道操作题的终态。root 是考试文件夹，open_rel 是这道题打开的东西。"""
    root = Path(root)
    if kind == "win":
        return prefix_snapshot(shot if shot is not None else snapshot.snapshot(root),
                               logical_root)
    if kind == "wps":
        target = root / open_rel if open_rel else root
        if target.is_file():
            got = docx.read_docx(target)
            if got:
                return got
        # 学生把文件另存到别处、或者改了名：在考试文件夹里找一个 .docx 顶上，
        # 总比直接判 0 分强。找不到就交空的，判分器会说"文档是空的"
        found = docx.find_docs(target if target.is_dir() else root)
        return docx.read_docx(found[0]) if found else {}
    if kind == "html":
        target = root / open_rel if open_rel else root
        # open 指到文件时要取它所在的文件夹，否则同目录的 style.css 收不进来
        return {"files": _web_files(target.parent if target.suffix else target)}
    return {}


def auto_graded(paper: list[dict]) -> list[dict]:
    """哪些题由服务器自动判分。

    `manual` 的（现在只剩没配仿真环境的题）留着那句文字说明走人工评阅，
    把状态塞进去反而会把老师的阅卷界面搞乱。
    """
    out = []
    for q in paper:
        sim = q.get("sim") or {}
        if sim.get("kind") and not sim.get("manual"):
            out.append(q)
    return out


def local_ipv4() -> list:
    """这台机器的 IPv4 地址（不含 127.x）。IP 查询题要拿学生填的和它比。

    两条路都走一遍再合起来：按主机名查最省事，但多网卡、装了虚拟网卡的机器
    上它只给一部分；ipconfig 最全，但万一被组策略禁了也不能让交卷卡住。
    """
    got = []
    try:
        got += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    try:
        out = subprocess.run(["ipconfig"], capture_output=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        text = out.decode("gbk", "replace")
        got += re.findall(r"IPv4[^:：]*[:：]\s*([\d.]+)", text)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    seen = []
    for ip in got:
        if ip and not ip.startswith("127.") and ip not in seen:
            seen.append(ip)
    return seen


def collect(paper: list[dict], root: Path, logical_root: str,
            chats: dict | None = None, drags: dict | None = None) -> dict:
    """把这份卷子里所有自动判分的操作题，各自的终态收一遍。

    文件夹快照只拍**一次**给所有 win 题共用：一场考试里 win 题可能有好几道，
    每道都重拍一遍既慢又可能拍出不一致的结果（学生还在动文件）。

    chats 是 AI 工具题的对话记录 `{题号: [{"role","text"}, …]}`，由界面给。
    drags 是拖拽题的作答 `{题号: {"placed": {热区: [卡片]}}}`，也由界面给。
    """
    root = Path(root)
    chats = chats or {}
    drags = drags or {}
    need_shot = any((q.get("sim") or {}).get("kind") == "win" for q in auto_graded(paper))
    shot = snapshot.snapshot(root) if need_shot else None
    out = {}
    for q in auto_graded(paper):
        qid, kind = str(q["id"]), (q["sim"].get("kind") or "")
        if kind == "ai":
            out[qid] = {"messages": list(chats.get(qid) or [])}
        elif kind == "drag":
            # 拖拽题的成果在界面上（哪张卡片放在哪个热区），不在文件系统里
            got = dict(drags.get(qid) or {})
            got.setdefault("placed", {})
            if ((q.get("sim") or {}).get("env") or {}).get("mode") == "ip":
                got["real_ips"] = local_ipv4()      # 学生查的是这台真机
            out[qid] = got
        else:
            out[qid] = state_for(kind, root, q["sim"].get("open") or "",
                                 logical_root, shot)
    return out


def payload(answers: dict, states: dict) -> dict:
    """拼交给服务器的那份作答：客观题原样，操作题换成终态。

    服务器那边的判分函数认的就是 `{"state": 终态}` 这个形状，和网页版仿真器
    交上来的一模一样，所以后端一行都不用改。
    """
    out = dict(answers or {})
    for qid, state in (states or {}).items():
        out[str(qid)] = json.dumps({"state": state}, ensure_ascii=False)
    return out
