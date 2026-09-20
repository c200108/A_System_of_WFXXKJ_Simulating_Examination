# -*- coding: utf-8 -*-
"""WPS 文字题的两半：出题时写成 .docx，判分时读回段落模型。

**这两半必须严丝合缝**，否则症状是"学生明明做对了却判 0 分"，而且两边各自看
都正常。所以这里的主力是往返测试：写出去再读回来，每一项格式都得对得上。

写的那一半在 `backend/app/services/docx_io.py`（服务器出包时用），
读的那一半在 `desktop/client/docx.py`（学生机上交卷时用）。
它们在两个不同的地方、给不同的人用，只有这个文件同时盯着两边。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.services import docx_io, sim
from client import docx


def sample() -> dict:
    """一份把格式项都用上的文档。"""
    return {
        "name": "范文.wps",
        "paras": [
            {**sim.blank_para(), "text": "让青春在不懈奋斗中绽放绚丽之花",
             "font": "黑体", "size": "二号", "align": "center", "bold": True},
            {**sim.blank_para(), "text": "青春由磨砺而出彩，人生因奋斗而升华。",
             "indent": 2, "line": {"type": "fixed", "value": 24}},
            {**sim.blank_para(), "text": "第三段：段前一行，段后半行。",
             "before": 1, "after": 0.5, "line": {"type": "multiple", "value": 1.5}},
            {**sim.blank_para(), "text": "带格式的一段", "italic": True,
             "underline": True, "strike": True, "color": "#ff0000",
             "highlight": "yellow", "align": "right", "size": "小四"},
        ],
        "page": {"left": 3.17, "right": 3.17, "top": 2.54, "bottom": 2.54,
                 "orient": "portrait"},
    }


@pytest.fixture
def written(tmp_path):
    path = tmp_path / "范文.docx"
    path.write_bytes(docx_io.build_docx(sample()))
    return path


# ================================================================ 写出来的是不是真 docx
def test_it_is_a_real_docx(written):
    """WPS 认不认，先看这个包的骨架齐不齐。少一份 WPS 会报"文件已损坏"。"""
    with zipfile.ZipFile(written) as z:
        names = z.namelist()
    for need in ("[Content_Types].xml", "_rels/.rels", "word/document.xml",
                 "word/styles.xml"):
        assert need in names, f"缺 {need}，WPS 打不开"


def test_name_becomes_docx():
    """仿真环境里那个名字常是「范文.wps」—— .wps 是金山私有格式，
    我们写的是标准 OOXML，扩展名不换 WPS 打开就报格式错。"""
    assert docx_io.docx_name({"name": "范文.wps"}) == "范文.docx"
    assert docx_io.docx_name({"name": "职业教育大有可为"}) == "职业教育大有可为.docx"
    assert docx_io.docx_name({}) == "文档.docx"


# ================================================================ 往返
def test_text_survives(written):
    got = docx.read_docx(written)
    assert [p["text"] for p in got["paras"]] == [p["text"] for p in sample()["paras"]]


@pytest.mark.parametrize("index,key,want", [
    (0, "font", "黑体"),
    (0, "size", "二号"),
    (0, "align", "center"),
    (0, "bold", True),
    (1, "indent", 2),
    (3, "italic", True),
    (3, "underline", True),
    (3, "strike", True),
    (3, "align", "right"),
    (3, "size", "小四"),
    (3, "color", "#ff0000"),
    (3, "highlight", "yellow"),
])
def test_format_survives(written, index, key, want):
    got = docx.read_docx(written)["paras"][index]
    assert got[key] == want, f"第 {index + 1} 段的{key}没读回来"


def test_line_spacing_survives(written):
    """行距三种写法各走一条换算：固定值按磅、多倍按 240 分之一。
    换错了的症状是「行距为固定值24磅」这种题全班判错。"""
    paras = docx.read_docx(written)["paras"]
    assert paras[1]["line"] == {"type": "fixed", "value": 24}
    assert paras[2]["line"] == {"type": "multiple", "value": 1.5}


def test_paragraph_spacing_survives(written):
    paras = docx.read_docx(written)["paras"]
    assert paras[2]["before"] == 1
    assert paras[2]["after"] == 0.5


def test_page_survives(written):
    page = docx.read_docx(written)["page"]
    assert page["orient"] == "portrait"
    for key in ("left", "right", "top", "bottom"):
        assert abs(page[key] - sample()["page"][key]) < 0.02, f"{key} 边距差太多"


# ================================================================ 真判一遍
def test_the_grader_accepts_what_we_read_back(written):
    """**最要紧的一条**：读回来的状态，老师在网页仿真器里点出来的检查点判得动。

    检查点这里手写成和网页仿真器一模一样的形状 —— 这正是两套运行时能共用
    一份检查点的原因。
    """
    state = docx.read_docx(written)
    checks = [
        {"desc": "标题设为黑体二号居中", "score": 3,
         "assert": {"op": "para", "at": {"has": "让青春"},
                    "font": "黑体", "size": "二号", "align": "center"}},
        {"desc": "正文首行缩进 2 字符", "score": 3,
         "assert": {"op": "para", "at": {"has": "青春由磨砺"}, "indent": 2}},
        {"desc": "行距固定值 24 磅", "score": 2,
         "assert": {"op": "para", "at": {"has": "青春由磨砺"},
                    "line": {"type": "fixed", "value": 24}}},
        {"desc": "文中有「绽放绚丽之花」", "score": 2,
         "assert": {"op": "text", "present": "绽放绚丽之花"}},
    ]
    got = sim.run_checks("wps", checks, state)
    bad = [r for r in got["results"] if not r["ok"]]
    assert got["score"] == got["full"] == 10, bad


def test_a_wrong_answer_is_told_apart(written, tmp_path):
    """做错了要判错，而且要说出错在哪 —— 不然自动判分没有意义。"""
    wrong = sample()
    wrong["paras"][0]["font"] = "宋体"          # 标题没设黑体
    path = tmp_path / "错的.docx"
    path.write_bytes(docx_io.build_docx(wrong))

    checks = [{"desc": "标题设为黑体", "score": 3,
               "assert": {"op": "para", "at": {"has": "让青春"}, "font": "黑体"}}]
    got = sim.run_checks("wps", checks, docx.read_docx(path))
    assert (got["score"], got["full"]) == (0, 3)
    assert "黑体" in got["results"][0]["why"], got["results"][0]


# ================================================================ 真机上的意外
def test_a_missing_file_is_not_a_crash(tmp_path):
    """学生把文件删了，不该连累整份卷子交不上去。"""
    assert docx.read_docx(tmp_path / "没有这个.docx") == {}


def test_a_non_docx_is_not_a_crash(tmp_path):
    """学生存成了 .doc（二进制复合文档，根本不是 zip），或者存了个空文件。"""
    bad = tmp_path / "其实是doc.docx"
    bad.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1rubbish")
    assert docx.read_docx(bad) == {}
    empty = tmp_path / "空.docx"
    empty.write_bytes(b"")
    assert docx.read_docx(empty) == {}


def test_wps_lock_files_are_skipped(written, tmp_path):
    """WPS 打开文件时会在旁边建一个 `~$xxx.docx` 锁文件。它也是 .docx 结尾，
    但里面不是文档 —— 不跳过的话会把正主顶掉，整道题判 0 分。"""
    (tmp_path / "~$范文.docx").write_bytes(b"lock")
    found = docx.find_docs(tmp_path)
    assert [p.name for p in found] == ["范文.docx"]


def test_paragraph_added_at_the_end_is_seen(written):
    """题目十有八九要求「在文章最后输入一段新的文字」。"""
    state = docx.read_docx(written)
    assert "绽放绚丽之花" in state["paras"][0]["text"]
    checks = [{"desc": "最后一段是新加的那句", "score": 2,
               "assert": {"op": "order", "last": "带格式的一段"}}]
    got = sim.run_checks("wps", checks, state)
    assert got["score"] == got["full"] == 2
