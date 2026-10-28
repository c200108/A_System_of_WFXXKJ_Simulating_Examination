"""题库里的 WPS 文字题（wps_bank 逐题写死的）：文档和题干对得上、检查点判得准。

题干原文在 fixtures/wps_stems.json，和老师给的题库一字不差。每道题查四件事：

1. 题干里「……」引的原文，开头和结尾都在文档的同一段里（学生找得到要改的那段）；
   题干说是「最后一段」的，在文档里就真是最后一段；
2. 学生什么都不做，一分不得（初始格式没有已经满足要求的）；
3. 照着要求做完的「标准答案」，每一问都判对、拿满分；
4. 文档写成 .docx 再用客户端读回来，文字、文本框、图片都还在。
"""

import copy
import json
import re
import sys
from pathlib import Path

import pytest

from app.services import docx_io, sim, stem, wps_bank

STEMS = json.loads((Path(__file__).parent / "fixtures" / "wps_stems.json").read_text("utf-8"))


def _loose(text) -> str:
    return sim.loose_text(text)


@pytest.mark.parametrize("code", sorted(STEMS))
def test_bank_covers_every_wps_question(code):
    got = stem.auto_sim(STEMS[code])
    assert got and got["kind"] == "wps", f"{code} 没认成 WPS 题"
    assert wps_bank.lookup(STEMS[code]), f"{code} 没走写死的那份"
    assert got["checks"], f"{code} 一条检查点都没有"


# 题干里引原文的写法：（“开头……结尾”）、“开头......结尾”、（开头……结尾）
QUOTE = re.compile(r"[“\"（(]([^“”\"（）()]{2,60}?)(?:…{1,2}|\.{3,6})([^“”\"（）()]{0,60}?)[”\"）)]")


@pytest.mark.parametrize("code", sorted(STEMS))
def test_quoted_text_is_really_in_the_document(code):
    text = STEMS[code]
    env = stem.auto_sim(text)["env"]
    paras = [_loose(p["text"]) for p in env["paras"]]
    for m in QUOTE.finditer(text):
        head, tail = _loose(m.group(1)), _loose(m.group(2))
        if not head:
            continue
        hits = [i for i, p in enumerate(paras) if head in p and (not tail or tail in p)
                and (not tail or p.index(head) < p.rindex(tail))]
        assert hits, f"{code}：题干引的「{m.group(1)}……{m.group(2)}」在文档里找不到完整的一段"
        # 「最后一段（……）」就得真是最后一段
        before = text[max(0, m.start() - 12):m.start()]
        if "最后一段" in before:
            last = max(i for i, p in enumerate(paras) if p)
            assert hits[-1] == last, f"{code}：题干说是最后一段，文档里却不是"


def _blank_state(env: dict) -> dict:
    """学生一点没动交上来的状态：文档原样写出去、再按客户端的读法读回来。"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))
    from client import docx as reader
    path = Path(__file__).parent / "_tmp_wps_bank.docx"
    try:
        path.write_bytes(docx_io.build_docx(env))
        got = reader.read_docx(path)
    finally:
        path.unlink(missing_ok=True)
    got["files"] = [docx_io.docx_name(env)]
    return got


@pytest.mark.parametrize("code", sorted(STEMS))
def test_untouched_document_scores_nothing(code):
    got = stem.auto_sim(STEMS[code])
    state = _blank_state(got["env"])
    ran = sim.run_checks("wps", got["checks"], state)
    free = [r["desc"] for r, c in zip(ran["results"], got["checks"])
            if r["ok"] and "once" not in c["assert"]]
    assert not free, f"{code}：什么都没做就判对了：{free}"


def _roundtrip_keeps_content(code):
    got = stem.auto_sim(STEMS[code])
    env, state = got["env"], _blank_state(got["env"])
    want = [_loose(p["text"]) for p in env["paras"] if p["text"]]
    have = [_loose(p["text"]) for p in state["paras"] if p["text"]]
    assert want == have
    kinds = sorted(s["kind"] for s in env.get("shapes") or [])
    assert kinds == sorted(s["kind"] for s in state.get("shapes") or [])


@pytest.mark.parametrize("code", sorted(STEMS))
def test_docx_roundtrip(code):
    _roundtrip_keeps_content(code)


# ---------------------------------------------------------------- 标准答案
# 「把 A 换成 B」：判分只写了 absent（A）和 present（B 的一句），标准答案得知道 B 是什么
REPLACE = {"qingchun": "青春", "Deepsek": "DeepSeek", "智慧": "智能", "智能城市": "智慧城市",
           "10后": "00后"}
# 题目要求输入的那段新文字（判分的 order.last 里写的就是它）
CHAR = ("font", "size", "bold", "italic", "underline", "u", "strike", "color")
U_VALUE = {"双下划线": "double", "双波浪线": "wavyDouble"}
COLOR = {"红色": "#ff0000", "绿色": "#00b050"}
WRAP = {"四周型": "square", "紧密型": "tight", "上下型": "topAndBottom"}


def _find(paras, at):
    if isinstance(at, dict) and "any" in at:
        at = at["any"][-1]
    if isinstance(at, dict):
        key = _loose(at.get("has"))
        return next(p for p in paras if key in _loose(p["text"]))
    return paras[int(at)]


def _set(p, a):
    for k, v in a.items():
        if k in ("op", "at", "has"):
            continue
        if k == "u":
            v = U_VALUE[v]
            p["underline"] = True
        if k == "color":
            v = COLOR.get(v, v)
        p[k] = v
        for r in p.get("runs") or []:
            if k in CHAR or k == "underline":
                r[k] = v
                if k == "u":
                    r["underline"] = True


def solve(checks: list, state: dict) -> dict:
    """照着检查点把文档改成"全做对"的样子。只用来验证检查点自洽，不是判分逻辑。"""
    st = copy.deepcopy(state)
    paras = st["paras"]
    for c in checks:
        a = c["assert"]
        op = a["op"]
        if op == "text" and "absent" in a:
            new = REPLACE[a["absent"]]
            for p in paras:
                p["text"] = p["text"].replace(a["absent"], new)
                for r in p.get("runs") or []:
                    r["text"] = r["text"].replace(a["absent"], new)
    for c in checks:
        a = c["assert"]
        op = a["op"]
        if op == "order" and "last" in a:
            key = _loose(a["last"])
            hit = [p for p in paras if key in _loose(p["text"])]
            if hit:
                p = hit[0]
                if _loose(p["text"]) != key:       # 一段里的一句话：拆出来另起一段
                    p["text"] = p["text"].replace(a["last"], "")
                    p["runs"] = [{"text": p["text"]}]
                    paras.append({**sim.blank_para(), "text": a["last"], "runs": []})
                else:
                    paras.remove(p)
                    paras.append(p)
            else:
                paras.append({**sim.blank_para(), "text": a["last"], "runs": []})
        if op == "order" and "first" in a and _loose(a["first"]) not in _loose(paras[0]["text"]):
            paras.insert(0, {**sim.blank_para(), "text": a["first"], "runs": []})
    for c in checks:
        a = c["assert"]
        op = a["op"]
        if op == "para":
            _set(_find(paras, a["at"]), a)
        elif op == "paras":
            for key in a["has"]:
                _set(_find(paras, {"has": key}), a)
        elif op == "span":
            _set(_find(paras, {"has": a["has"]}), a)
        elif op == "page":
            page = st.setdefault("page", {})
            for k in ("left", "right", "top", "bottom", "size"):
                if k in a:
                    page[k] = a[k]
            if a.get("same_tb"):
                page["bottom"] = page.get("top")
            if "border_color" in a:
                page["border"] = {"val": a.get("border_val", "single"),
                                  "color": COLOR[a["border_color"]]}
        elif op in ("header", "footer"):
            st[op] = a["has"]
            st[op + "_align"] = a["align"]
        elif op == "page_number":
            st["page_number"] = a["align"]
        elif op == "file":
            st.setdefault("files", []).append(a["exists"])
        elif op == "cols":
            p = _find(paras, a["at"])
            p["cols"] = {"num": a["num"], "equal": True, "space": 420}
        elif op == "shape":
            shapes = st.setdefault("shapes", [])
            hit = [s for s in shapes if (a["kind"] == "wordart" or s["kind"] == a["kind"])
                   and _loose(a.get("has", "")) in _loose(s.get("text", ""))]
            if not hit:
                shapes.append({"kind": a["kind"], "text": a.get("has", ""), "fonts": [],
                               "wrap": "inline", "para": len(paras) - 1})
                hit = shapes[-1:]
            sh = hit[0]
            for k in ("width_mm", "height_mm"):
                if k in a:
                    sh[k] = a[k]
            if "wrap" in a:
                sh["wrap"] = WRAP[a["wrap"]]
            if "font" in a:
                sh["fonts"] = [a["font"]] * max(1, len(sh.get("fonts") or []))
            if "near" in a:
                sh["para"] = next(i for i, p in enumerate(paras)
                                  if _loose(a["near"]) in _loose(p["text"]))
    return st


@pytest.mark.parametrize("code", sorted(STEMS))
def test_model_answer_scores_full_marks(code):
    got = stem.auto_sim(STEMS[code])
    state = solve(got["checks"], _blank_state(got["env"]))
    ran = sim.run_checks("wps", got["checks"], state)
    wrong = [f"{r['desc']}：{r['why']}" for r in ran["results"] if not r["ok"]]
    assert not wrong, f"{code}：照要求做完还有判错的：{wrong}"
    assert ran["score"] == ran["full"]


def test_old_generic_task_is_switched_to_the_bank():
    """库里存的是旧的通用规则生成的（stem_to_sim 配的、或导入的旧数据）：换成写死的这份。"""
    text = STEMS["C0456"]
    old = stem.parse_wps_generic(text)
    got = stem.refresh_wps(text, old["env"], old["checks"])
    assert got and any(s["kind"] == "textbox" for s in got["env"].get("shapes") or [])


def test_teacher_edited_task_is_kept():
    text = STEMS["C0456"]
    old = stem.parse_wps_generic(text)
    edited = [{**old["checks"][0], "desc": "老师改过的"}] + old["checks"][1:]
    assert stem.refresh_wps(text, old["env"], edited) is None
