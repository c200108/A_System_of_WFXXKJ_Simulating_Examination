"""考试包缓存。

## 为什么非有不可

同一场考试，全班下的是**同一份字节**。但每个学生点「开始考试」都会让服务器
重新建一遍包：查题、摘答案、铺文件、把配图从 JPEG 转成 PNG、压 zip。
实测一份 900 KB 的包建一次约 0.5 秒（学校那台小服务器只会更慢）。

五十个人同时开考 = 五十次重建 + 五十份 900 KB 从同一条上行链路挤出去。
学生那边看到的就是"点了开始考试，转很久"。

缓存之后：**第一个学生 0.5 秒，后面的人直接拿现成的字节。**

## 怎么知道包该不该重建

用考试相关那几张表的"最后修改时间"拼一个指纹：老师改了卷子、改了仿真环境、
换了配图，指纹就变，包自动重建。没改就一直用缓存。

**宁可多建一次，也不能发旧包** —— 所以指纹取的是最大修改时间，任何一处变动
都会让它变。

## 还顺手解决了重复下载

指纹同时当 ETag 用。学生重开程序、或者退出考试再进来，浏览器那套条件请求
（`If-None-Match`）在这儿一样有效：包没变就回 304，一个字节都不用再传。
"""

from __future__ import annotations

import hashlib
import threading
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Exam, Paper, PaperItem, Question, SimTask

# 最多缓存几场考试。一次期末考同时开着的场次不会多，几十份足够；
# 每份不到 1 MB，几十兆内存换掉全班的等待很划算
MAX_ENTRIES = 32

_lock = threading.Lock()
_cache: dict[str, tuple[str, bytes]] = {}       # {缓存键: (指纹, 包字节)}


def fingerprint(db: Session, exam: Exam, server: str) -> str:
    """这场考试现在的样子。任何一处变了，这个值就变。

    取的是几张相关表的最大 `updated_at` / `created_at`。比逐条比对便宜得多，
    而且**偏保守**：宁可多建一次包，也不能把旧卷子发给学生。

    `server` 也算进去 —— 同一场考试导给不同地址的包，manifest 里的服务器
    地址不一样，不能混用同一份缓存。
    """
    paper_id = exam.paper_id
    # early_submit 写在包的 manifest 里：开关一改，包也得重建（以前漏了，老师考试中途
    # 打开「允许提前交卷」，后开考的学生拿到的还是缓存里关着的那份）
    marks = [str(exam.id), str(exam.token), str(exam.is_open), str(exam.early_submit), server]

    row = db.execute(
        select(func.max(Paper.created_at)).where(Paper.id == paper_id)
    ).scalar()
    marks.append(str(row))

    # 卷子里的题、题上挂的仿真任务：改了题干、换了配图、改了检查点都要重建
    row = db.execute(
        select(func.max(Question.updated_at), func.max(Question.image_url),
               func.count())
        .select_from(PaperItem)
        .join(Question, Question.id == PaperItem.question_id)
        .where(PaperItem.paper_id == paper_id)
    ).first()
    marks.extend(str(x) for x in (row or ()))

    row = db.execute(
        select(func.max(SimTask.updated_at))
        .select_from(PaperItem)
        .join(Question, Question.id == PaperItem.question_id)
        .join(SimTask, SimTask.id == Question.sim_task_id)
        .where(PaperItem.paper_id == paper_id)
    ).scalar()
    marks.append(str(row))

    # **生成考试包的代码本身**也算进去。操作题的考场文件、拖拽题的结构图都是
    # 按题干现算的（stem.py / drag.py），库里一个字没变、代码升级了，包的内容
    # 照样会变。不算的话，升级后学生机拿着旧包来问，ETag 对得上，服务器回
    # 304 —— 学生考的还是旧题（比如少了一个文件夹的那一版）。
    marks.append(code_mark())

    return hashlib.sha256("|".join(marks).encode("utf-8")).hexdigest()[:16]


_CODE_MARK = ""


def code_mark() -> str:
    """出包那几段代码的指纹：改了哪一个，已经发出去的包就全部作废。"""
    global _CODE_MARK
    if not _CODE_MARK:
        from . import docx_io, drag, sim, stem
        h = hashlib.sha256()
        for mod in (stem, drag, docx_io, sim):
            try:
                h.update(Path(mod.__file__).read_bytes())
            except (OSError, TypeError):
                h.update(mod.__name__.encode("utf-8"))
        _CODE_MARK = h.hexdigest()[:12]
    return _CODE_MARK


def get(key: str, mark: str) -> bytes | None:
    """缓存里有这一版吗。"""
    with _lock:
        got = _cache.get(key)
    return got[1] if got and got[0] == mark else None


def put(key: str, mark: str, data: bytes) -> None:
    with _lock:
        if len(_cache) >= MAX_ENTRIES and key not in _cache:
            # 简单粗暴：满了就丢最早进来的那个。考试场次本来就不多，
            # 用 LRU 之类的没必要
            _cache.pop(next(iter(_cache)), None)
        _cache[key] = (mark, data)


def clear() -> None:
    """只给测试用。"""
    with _lock:
        _cache.clear()
