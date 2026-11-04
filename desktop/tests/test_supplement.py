# -*- coding: utf-8 -*-
"""补充题（app/services/supplement.py）在真机上的整条链路。

两道题都是照着老师给的真机考场出的：

    B001 Windows：win 文件夹里真的 jpg/png/txt，学生在资源管理器里新建、复制、移动、删除
    B002 WPS 文字：「人工智能改变生活.docx」，学生用真 WPS 查找替换、排版、输入、保存

每道题查三件事：
1. 铺出来的考场和老师给的素材一致（图片是真图片，不是占位文字）；
2. 学生什么都不做，**一分不得**；
3. 照题目做完（在真文件夹里动手 / 存一份真 .docx），拍快照交上去判**满分**；
   常见的错法（复制做成了移动、没保存）扣在对应那一问上。

另外查补充题入库：每次启动补一遍不重复；全新部署时不挡原题库的导入。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.routers.desk import _files_of, _root_of
from app.services import docx_io, sim, stem, supplement
from client import states

STEMS = {q["code"]: q for q in supplement.QUESTIONS}
ASSETS = Path(__file__).resolve().parents[2] / "backend" / "app" / "assets" / "supplement"


def _lay(kind: str, env: dict, box: Path) -> None:
    for rel, data in _files_of(kind, env).items():
        target = box / rel
        if data is None:
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


def _judge(kind: str, got: dict, box: Path) -> dict:
    open_rel = "win" if kind == "win" else docx_io.docx_name(got["env"])
    state = states.state_for(kind, box, open_rel, _root_of(kind, got["env"]))
    return sim.run_checks(kind, got["checks"], state)


# ================================================================ B001 Windows
@pytest.fixture()
def win(tmp_path):
    q = STEMS["B001"]
    got = stem.auto_sim(q["stem"], q["scope"])
    assert got and got["kind"] == "win"
    _lay("win", got["env"], tmp_path)
    return got, tmp_path


def test_win_room_has_the_real_files(win):
    got, box = win
    w = box / "win"
    assert sorted(p.name for p in w.iterdir()) == sorted(
        ["学习笔记.txt", "废弃文件.txt", "智慧课堂.jpg", "机器人比赛.png"])
    # 图片是老师给的那两张，原样的字节
    assert (w / "智慧课堂.jpg").read_bytes() == (ASSETS / "win_ai_life/zhihui_ketang.jpg").read_bytes()
    assert (w / "机器人比赛.png").read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    # 记事本默认 ANSI：按 GBK 落盘
    assert "人脸识别属于计算机视觉" in (w / "学习笔记.txt").read_bytes().decode("gbk")
    # 要学生做出来的东西一样都不能预先铺好
    assert not (w / "图片资料").exists() and not (w / "文档资料").exists()


def test_win_untouched_scores_zero(win):
    got, box = win
    ran = _judge("win", got, box)
    assert ran["full"] == 50
    assert ran["score"] == 0, [r["desc"] for r in ran["results"] if r["ok"]]


def _do_win(box: Path, copy_pics=True) -> None:
    w = box / "win"
    (w / "图片资料").mkdir()
    (w / "文档资料").mkdir()
    for name in ("智慧课堂.jpg", "机器人比赛.png"):
        (shutil.copyfile if copy_pics else shutil.move)(str(w / name), str(w / "图片资料" / name))
    shutil.move(str(w / "学习笔记.txt"), str(w / "文档资料" / "学习笔记.txt"))
    (w / "文档资料" / "人工智能学习心得.docx").write_bytes(b"")   # 右键新建出来就是空文件
    (w / "图片资料" / "科技节汇报.pptx").write_bytes(b"")
    (w / "废弃文件.txt").unlink()


def test_win_done_right_scores_full(win):
    got, box = win
    _do_win(box)
    ran = _judge("win", got, box)
    assert ran["score"] == ran["full"] == 50, [r for r in ran["results"] if not r["ok"]]


def test_win_move_instead_of_copy_loses_part3(win):
    got, box = win
    _do_win(box, copy_pics=False)
    ran = _judge("win", got, box)
    lost = [r["desc"] for r in ran["results"] if not r["ok"]]
    assert ran["score"] == 40 and all(d.startswith("③") for d in lost), lost


# ================================================================ B002 WPS 文字
@pytest.fixture()
def wps(tmp_path):
    q = STEMS["B002"]
    got = stem.auto_sim(q["stem"], q["scope"])
    assert got and got["kind"] == "wps"
    _lay("wps", got["env"], tmp_path)
    return got, tmp_path


def test_wps_document_is_the_teachers_text(wps):
    got, box = wps
    doc = box / "人工智能改变生活.docx"
    assert doc.is_file()
    texts = [p["text"] for p in states.state_for("wps", box, doc.name, "")["paras"] if p["text"]]
    assert texts[0] == "人工智能改变生活" and len(texts) == 5
    assert texts[1].startswith("从智彗家居") and texts[1].endswith("必修课。")
    assert all(w in "".join(texts) for w in ("智彗", "深渡", "科计"))


def test_wps_untouched_scores_zero(wps):
    got, box = wps
    ran = _judge("wps", got, box)
    assert ran["full"] == 50
    assert ran["score"] == 0, [r["desc"] for r in ran["results"] if r["ok"]]


LAST = ("作为新时代的中学生，我们要努力学习科学知识，积极动手实践，迎接人工智能时代的到来。"
        "对于人工智能的应用，我们要合理使用，认真辨别。我们应该遵守法律法规，成为数字时代的"
        "合法公民。这也意味着在享受技术便利的同时，主动承担起维护网络秩序的责任。")


def _do_wps(env: dict) -> dict:
    """学生在 WPS 里照题目做完、按原名保存后的文档。"""
    paras = [dict(p) for p in env["paras"]]
    for p in paras:
        p["text"] = p["text"].replace("智彗", "智慧").replace("深渡", "深度").replace("科计", "科技")
    paras[0].update(font="黑体", size="二号", align="center")
    paras[1].update(left=2, right=2, before=1, after=0.5, line={"type": "multiple", "value": 1.5})
    for p in paras[2:]:
        p.update(font="宋体", size="四号", indent=2, line={"type": "fixed", "value": 24})
    paras.append({**sim.blank_para(), "text": LAST})
    paras.append({**sim.blank_para(), "text": ""})      # 打完字顺手敲的回车
    return {**env, "paras": paras}


def test_wps_done_right_scores_full(wps):
    got, box = wps
    (box / "人工智能改变生活.docx").write_bytes(docx_io.build_docx(_do_wps(got["env"])))
    ran = _judge("wps", got, box)
    assert ran["score"] == ran["full"] == 50, [r for r in ran["results"] if not r["ok"]]


def test_wps_not_saved_scores_zero(wps):
    """改完没存盘：交卷时读到的还是原件。"""
    got, box = wps
    (box / "另存的.docx").write_bytes(docx_io.build_docx(_do_wps(got["env"])))
    assert _judge("wps", got, box)["score"] == 0


# ================================================================ 入库
def test_seed_supplement_is_idempotent(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.models import Base, Question

    engine = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    assert supplement.seed_supplement(db) == 2
    db.commit()
    assert supplement.seed_supplement(db) == 0, "第二次启动不该再插"
    rows = db.scalars(select(Question)).all()
    assert {q.code for q in rows} == {"B001", "B002"}
    assert {q.source for q in rows} == {"补充题"}
    assert {q.scope for q in rows} == {"Windows系统操作", "WPS文字操作"}

    # 老师删到回收站（软删除）：不会再被补回来
    for q in rows:
        q.is_deleted = True
    db.commit()
    assert supplement.seed_supplement(db) == 0
