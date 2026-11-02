"""数据回收站：删掉的东西先放 7 天，可以原样还原；过期了才真正从库里删掉。

## 怎么做到「原样还原」

删除**之前**，顺着外键把这一删会牵动的东西都拍下来：

- 被删的那几行；
- 跟着一起删掉的子表行（外键 ON DELETE CASCADE）：删考试带走它的答卷，删试卷带走
  试题条目、用这份卷的考试和答卷，删反馈带走回复和点赞……；
- 被置空的引用（外键 SET NULL，或者删除代码里手工置空的）：删班级时学生的 class_id、
  删学生时答卷和打字成绩上的 student_id、删仿真任务时题目上的 sim_task_id。

还原时按表的依赖顺序（父表先、子表后）把行原样插回去（**id 不变**，引用它们的地方
不用改），再把置空的引用接回来。

外键关系是从模型上现读的，不是手写的一张表 —— 以后加了新表、新外键，回收站自动跟上。

## 题目是软删除

题目本来就是打个 is_deleted 标记（试卷快照里还引用着它，真删会坏掉存档试卷），
进回收站时记下 id，还原就是去掉标记。过期后：没被任何试卷引用的才真删，
被引用的保持软删除（题库里看不到，存档试卷照样能打开）。
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from typing import Dict, Iterable, List, Optional, Sequence

from sqlalchemy import DateTime, Date, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import clock
from ..config import settings
from ..models import Base, PaperItem, Question, RecycleItem, User

KEEP_DAYS = 7
CHUNK = 500

KIND_NAMES = {
    "exam": "考试", "submission": "答卷", "paper": "存档试卷", "question": "题目",
    "student": "学生", "class": "班级", "typing_record": "打字成绩", "typing_text": "练习文本",
    "typing_theme": "打字主题",
    "sim": "仿真任务", "feedback": "反馈",
}

# 这些表的东西不进快照：用户账号从来不在这里删（只停用），限流计数、本机状态是临时数据
SKIP_TABLES = {"users", "rate_hits", "app_meta", "recycle_items"}


# ---------------------------------------------------------------- 值的存取
def _plain(value):
    """一格的值 → 能放进 JSON 的样子。"""
    if isinstance(value, datetime):
        return {"$dt": value.isoformat()}
    if isinstance(value, date):
        return {"$d": value.isoformat()}
    return value


def _back(value):
    if isinstance(value, dict):
        if "$dt" in value:
            return datetime.fromisoformat(value["$dt"])
        if "$d" in value:
            return date.fromisoformat(value["$d"])
    return value


def _tables() -> Dict[str, object]:
    return {t.name: t for t in Base.metadata.sorted_tables}


def _referrers(table) -> List[tuple]:
    """哪些表的哪一列引用着这张表：[(子表, 外键列, ondelete)]。"""
    out = []
    for child in Base.metadata.sorted_tables:
        if child.name in SKIP_TABLES:
            continue
        for fk in child.foreign_keys:
            if fk.column.table is table:
                out.append((child, fk.parent, (fk.ondelete or "").upper()))
    return out


def _chunks(ids: Sequence, n: int = CHUNK) -> Iterable[list]:
    ids = list(ids)
    for i in range(0, len(ids), n):
        yield ids[i:i + n]


# ---------------------------------------------------------------- 拍快照
class _Snapshot:
    def __init__(self, db: Session):
        self.db = db
        self.rows: Dict[str, Dict[int, dict]] = {}
        self.relinks: List[list] = []          # [表, id, 列, 原值]

    def take(self, table, ids: Iterable[int]) -> None:
        pk = list(table.primary_key.columns)[0]
        seen = self.rows.setdefault(table.name, {})
        new = [i for i in dict.fromkeys(ids) if i is not None and i not in seen]
        if not new:
            return
        for part in _chunks(new):
            for row in self.db.execute(select(table).where(pk.in_(part))).mappings():
                seen[row[pk.name]] = {k: _plain(v) for k, v in row.items()}
        for child, col, ondelete in _referrers(table):
            child_pk = list(child.primary_key.columns)[0]
            for part in _chunks(new):
                got = self.db.execute(
                    select(child_pk, col).where(col.in_(part))).all()
                if not got:
                    continue
                if ondelete == "CASCADE":
                    self.take(child, [r[0] for r in got])
                elif col.nullable:
                    # SET NULL（或者删除代码手工置空的）：记下原值，还原时接回去
                    self.relinks.extend([child.name, r[0], col.name, r[1]] for r in got)

    def payload(self, soft_questions: Sequence[int] = ()) -> dict:
        return {
            "rows": {t: list(rows.values()) for t, rows in self.rows.items() if rows},
            "relinks": self.relinks,
            "soft_questions": list(soft_questions),
        }

    def count(self, table: str) -> int:
        return len(self.rows.get(table, {}))


def trash(db: Session, user: Optional[User], kind: str, title: str, model=None,
          ids: Iterable[int] = (), *, detail: str = "",
          soft_questions: Sequence[int] = ()) -> RecycleItem:
    """**删除之前**调用：把要删的东西拍进回收站。和删除放在同一个事务里提交。

    model + ids：要删的那几行（会顺着外键把跟着删的、被置空的一起记下）；
    soft_questions：软删除的题目 id。
    """
    snap = _Snapshot(db)
    if model is not None:
        snap.take(model.__table__, list(ids))
    now = clock.now()
    item = RecycleItem(
        kind=kind,
        title=title[:255],
        detail=detail[:255],
        payload=json.dumps(snap.payload(soft_questions), ensure_ascii=False),
        deleted_by=user.id if user else None,
        deleted_by_name=((user.name or user.username) if user else "")[:64],
        deleted_at=now,
        expires_at=now + timedelta(days=KEEP_DAYS),
    )
    db.add(item)
    return item


def names(rows, attr: str, most: int = 5) -> str:
    """「张三、李四、王五 等 12 名」这种摘要。"""
    got = [str(getattr(r, attr, "") or "") for r in rows]
    got = [g for g in got if g]
    text = "、".join(got[:most])
    return text + (f" 等 {len(got)} 项" if len(got) > most else "")


# ---------------------------------------------------------------- 还原
class RestoreError(Exception):
    pass


def restore(db: Session, item: RecycleItem) -> dict:
    """原样插回去。**已经存在的行跳过**（比如答卷早就单独还原过了）。

    撞上唯一约束（删掉以后又新建了同学号的学生、同名的班级）就整条不还原，说清楚原因。
    """
    data = json.loads(item.payload or "{}")
    tables = _tables()
    restored = 0
    try:
        for table in Base.metadata.sorted_tables:         # 父表在前
            rows = (data.get("rows") or {}).get(table.name) or []
            if not rows:
                continue
            pk = list(table.primary_key.columns)[0]
            have = set()
            for part in _chunks([r[pk.name] for r in rows]):
                have.update(db.scalars(select(pk).where(pk.in_(part))))
            todo = [{k: _back(v) for k, v in r.items() if k in table.c}
                    for r in rows if r[pk.name] not in have]
            for part in _chunks(todo, 200):
                db.execute(table.insert(), part)
            restored += len(todo)
        for name, rid, col, value in data.get("relinks") or []:
            table = tables.get(name)
            if table is None or col not in table.c:
                continue
            pk = list(table.primary_key.columns)[0]
            db.execute(update(table).where(pk == rid, table.c[col].is_(None)).values({col: value}))
        soft = data.get("soft_questions") or []
        for part in _chunks(soft):
            db.execute(update(Question).where(Question.id.in_(part)).values(is_deleted=False))
        restored += len(soft)
        db.delete(item)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise RestoreError(
            "还原不了：要么删掉以后又新建了同名（或同学号）的记录，和要还原的撞上了"
            "（先把新建的那条改名或删掉）；要么它所属的考试、试卷也被删了"
            "（先在回收站里还原那一条）。") from exc
    return {"restored": restored}


# ---------------------------------------------------------------- 过期清理
def _drop_files(data: dict) -> None:
    """班级座次表这类磁盘文件：彻底删除时一起删掉。"""
    for row in (data.get("rows") or {}).get("classes") or []:
        name = str(row.get("seat_file") or "")
        if name:
            path = os.path.join(settings.upload_dir, "seats", os.path.basename(name))
            try:
                os.remove(path)
            except OSError:
                pass


def destroy(db: Session, item: RecycleItem) -> None:
    """彻底删除一条（过期了，或者老师手动点了「彻底删除」）。"""
    data = json.loads(item.payload or "{}")
    for qid in data.get("soft_questions") or []:
        q = db.get(Question, qid)
        if not q or not q.is_deleted:
            continue                          # 已经被单独恢复了
        used = db.scalar(select(PaperItem.id).where(PaperItem.question_id == qid).limit(1))
        if not used:
            db.delete(q)
    _drop_files(data)
    db.delete(item)


def purge(db: Session) -> int:
    """把过了 7 天的彻底删掉。返回删了几条。"""
    rows = list(db.scalars(select(RecycleItem).where(RecycleItem.expires_at <= clock.now())))
    for item in rows:
        destroy(db, item)
    if rows:
        db.commit()
    return len(rows)


def delete_ids(db: Session, model, ids: Sequence[int]) -> int:
    """按 id 分批删。**不要写成 DELETE … WHERE id IN (SELECT id FROM 同一张表 …)** ——
    MySQL 不认（错误 1093），SQLite 认，测试里看不出来，一到服务器上就 500。"""
    n = 0
    for part in _chunks(list(ids)):
        n += db.execute(delete(model).where(model.id.in_(part))).rowcount or 0
    return n
