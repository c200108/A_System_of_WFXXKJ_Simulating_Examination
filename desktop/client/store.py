# -*- coding: utf-8 -*-
"""这台机器上存的那点东西：教师端地址、答题草稿、还没传上去的答卷。

考试数据一律来自服务器，本地只留三样：

  设置    教师端地址。**机房里一台一台输地址太折腾**，第一次输完记下来，
          以后开机直接连。存在 exe 旁边，整个文件夹 ghost 到全机房就都有了。
  草稿    每次作答都写一份。机房跳闸不是小概率事件，重开要能接着考。
  补传    哪些 .ans 已经传上去了。考完监考老师一眼看出谁还没传上。
  记录    这台机器上考过的每一场，一场一行。按中考的做法，**每台机器都要留下
          一份能核对的考试文件** —— 谁在几点用这台机器考的、交没交上、传没传走。
          排查"这个学生说他考了但成绩里没有"时，第一个翻它。

三样都是"丢了也不影响正确性"的东西，所以读写一律吞掉异常 ——
写不了草稿不该让学生考不成试。
"""

from __future__ import annotations

import json
import os
import socket
import sys
from datetime import datetime
from pathlib import Path

CONFIG_NAME = "客户端设置.json"
UPLOAD_NAME = "上传状态.json"
LOG_NAME = "考试记录.csv"


def here() -> Path:
    """exe 所在目录（打包后）或脚本所在目录（开发时）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass                      # 存不下不是错，下次再输一遍地址就是了


# ================================================================ 设置
def load_config() -> dict:
    return _read(here() / CONFIG_NAME)


def save_config(**kw) -> None:
    got = load_config()
    got.update({k: v for k, v in kw.items() if v is not None})
    _write(here() / CONFIG_NAME, got)


def remembered_server() -> str:
    return str(load_config().get("server") or "")


# ================================================================ 草稿
def draft_path(exam_id: str, student_no: str) -> Path:
    safe = "".join(c for c in f"{exam_id}-{student_no}" if c.isalnum() or c in "-_")
    return Path(os.environ.get("TEMP", ".")) / f"exam-draft-{safe}.json"


def save_draft(exam_id: str, student_no: str, data: dict) -> None:
    _write(draft_path(exam_id, student_no), data)


def load_draft(exam_id: str, student_no: str) -> dict:
    return _read(draft_path(exam_id, student_no))


def drop_draft(exam_id: str, student_no: str) -> None:
    try:
        draft_path(exam_id, student_no).unlink()
    except OSError:
        pass


# ================================================================ 补传
def upload_state(out_dir: Path) -> dict:
    return _read(Path(out_dir) / UPLOAD_NAME)


def mark_uploaded(out_dir: Path, name: str, ok: bool, msg: str) -> None:
    got = upload_state(out_dir)
    got[name] = {"ok": ok, "msg": msg, "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    _write(Path(out_dir) / UPLOAD_NAME, got)


# ================================================================ 考试记录
LOG_HEAD = "机器,考号,姓名,班级,考试,开始时间,交卷时间,答案文件,上传\n"


def log_sitting(out_dir: Path, student: dict, exam_title: str,
                started: str, answer_file: str, uploaded: bool) -> None:
    """记一场考试。一场一行，追加，不覆盖。

    用 CSV 是因为监考老师最可能拿 Excel 打开它。**GBK 落盘**：考场机器是
    Win7/Win10 的中文系统，Excel 双击打开 UTF-8 的 CSV 会是一屏乱码。
    """
    path = Path(out_dir) / LOG_NAME
    row = ",".join(_csv(x) for x in (
        socket.gethostname(),
        student.get("no", ""), student.get("name", ""), student.get("cls", ""),
        exam_title, started, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        answer_file, "已上传" if uploaded else "待补传",
    ))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with open(path, "a", encoding="gbk", errors="replace", newline="") as f:
            if new:
                f.write(LOG_HEAD)
            f.write(row + "\n")
    except OSError:
        pass                      # 记不下来不该影响交卷


def _csv(value) -> str:
    text = str(value or "").replace('"', "'")
    return f'"{text}"' if ("," in text or "\n" in text) else text


def read_log(out_dir: Path) -> list[str]:
    """把记录读回来（给自检和监考老师用）。"""
    try:
        return (Path(out_dir) / LOG_NAME).read_text(encoding="gbk",
                                                    errors="replace").splitlines()
    except OSError:
        return []


def pending_uploads(out_dir: Path) -> list[Path]:
    """还没传上去的答案包。"""
    out_dir = Path(out_dir)
    if not out_dir.exists():
        return []
    got = upload_state(out_dir)
    return [p for p in sorted(out_dir.glob("*.ans"))
            if not got.get(p.name, {}).get("ok")]
