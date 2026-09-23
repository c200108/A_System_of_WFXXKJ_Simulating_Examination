# -*- coding: utf-8 -*-
"""把学生用真 WPS 改过的 .docx 读回成判分器认识的段落模型。

## 这是「文件快照」的 WPS 版

Windows 操作题交上去的是文件夹快照，WPS 文字题交上去的就是这份文档状态：

    {"paras": [{"text": …, "font": …, "size": …, "align": …, "indent": …,
                "before": …, "after": …, "line": {...}, …}],
     "page": {"left","right","top","bottom","orient"},
     "header": …, "footer": …, "columns": …}

形状和网页版 WPS 仿真器交上来的**完全一致** —— 服务器那边的检查点因此一个字
都不用改。老师在网页仿真器里点出来的「标题设为黑体二号居中」，学生在真 WPS 里
做出来，判的是同一件事。

写的那一半在 `backend/app/services/docx_io.py`。往返一致由
`desktop/tests/test_docx.py` 盯着。

## 为什么不用 python-docx

要打进 exe，多一个依赖就多几 MB、多一处装不上的风险。`.docx` 就是个 zip 装着
几份 XML，标准库的 `zipfile` + `xml.etree` 够用。

## 读的时候比写的时候松

我们写出去的 XML 是规规矩矩的，但**学生存盘之后就不是我们写的了** —— WPS 会
按自己的习惯重排：格式可能挂在段落上，也可能挂在每个 run 上；缩进可能只有
twip 没有 Chars；字体可能只写 eastAsia。所以这里每一项都要多处找、都要有兜底，
**读不出来就用默认值，绝不抛异常** —— 判分环节炸掉会让整份卷子交不上去。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
CM = 567.0                       # 1 厘米多少 twip

# 磅 → 字号名。判分器两种写法都认，这里回中文名，老师看报告更顺眼
PT_SIZE = {42: "初号", 36: "小初", 26: "一号", 24: "小一", 22: "二号", 18: "小二",
           16: "三号", 15: "小三", 14: "四号", 12: "小四", 10.5: "五号", 9: "小五",
           7.5: "六号", 6.5: "小六", 5.5: "七号", 5: "八号"}
ALIGN_BACK = {"left": "left", "start": "left", "center": "center",
              "right": "right", "end": "right", "both": "justify",
              "distribute": "distribute"}
STYLE_BACK = {"Normal": "正文", "Heading1": "标题1", "Heading2": "标题2",
              "Heading3": "标题3", "a": "正文"}


def style_name(raw) -> str:
    """样式名 → 判分用的写法：「标题 1」「heading 1」都成「标题1」。

    **和 sim.py 的 style_name 一模一样，改要一起改** —— 客户端只用标准库，
    不能 import 后端那边的代码。
    """
    s = re.sub(r"\s+", "", str(raw or ""))
    low = s.lower()
    m = re.match(r"(?:heading|标题)(\d)$", low)
    if m:
        return f"标题{m.group(1)}"
    return {"title": "标题", "subtitle": "副标题", "normal": "正文"}.get(low, s)


def read_styles(zf: zipfile.ZipFile) -> dict:
    """styles.xml → {样式 ID: 规范化后的样式名}。

    **样式 ID 本身什么都说明不了**，得按 styles.xml 里记的名字认：

        WPS            ID 是数字，"2" 是它的「标题 1」
        中文版 Word    "1"、"2" 是标题 1、标题 2，"a" 是正文
        英文版 Word    "Heading1"、"Normal"

    同一个 "2"，在 WPS 里是标题 1、在中文 Word 里是标题 2，只看 ID 必然判错。
    原来就是只看 ID：学生在 WPS 里明明选的「标题 1」，判分说「样式是 2」。

    名字也缺的（手搓的文档里可能有），退回看大纲级别：级别 0 就是标题 1。
    """
    try:
        root = ET.fromstring(zf.read("word/styles.xml"))
    except (KeyError, ET.ParseError):
        return {}
    out = {}
    for st in root.iter(W + "style"):
        sid = st.get(W + "styleId")
        if not sid:
            continue
        name = _val(st, "name")
        if name:
            out[sid] = style_name(name)
            continue
        level = _val(st.find(W + "pPr"), "outlineLvl")
        if level is not None and str(level).isdigit() and int(level) < 9:
            out[sid] = f"标题{int(level) + 1}"
    return out
RULE_BACK = {"exact": "fixed", "atLeast": "least", "auto": "multiple"}


def blank_para() -> dict:
    """和 `sim.py` 的 `blank_para()` 保持一致。**改要一起改。**"""
    return {"text": "", "font": "宋体", "size": "五号", "bold": False,
            "italic": False, "underline": False, "color": "", "align": "left",
            "indent": 0, "left": 0, "right": 0, "line": None, "before": 0,
            "after": 0, "strike": False, "sup": False, "sub": False,
            "highlight": "", "shading": "", "border": False, "bullet": "none",
            "style": "正文"}


def _val(node, tag: str, attr: str = "val"):
    """取 <w:tag w:attr="…"> 的值。找不到返回 None。"""
    got = node.find(W + tag) if node is not None else None
    return None if got is None else got.get(W + attr)


def _on(node, tag: str) -> bool:
    """`<w:b/>` 这种开关标签。写成 `w:val="0"`/`"false"` 表示关掉。"""
    if node is None:
        return False
    got = node.find(W + tag)
    if got is None:
        return False
    return str(got.get(W + "val", "1")).lower() not in ("0", "false", "off")


def _num(text, default=0.0) -> float:
    try:
        return float(text)
    except (TypeError, ValueError):
        return default


def _size_name(half_points) -> str:
    """w:sz 是半磅。22 → 「小二」(11 磅? 不是) ——  22 半磅 = 11 磅，没有对应
    的中文名就直接回磅数，判分器认数字。"""
    pt = _num(half_points, 21) / 2
    for value, name in PT_SIZE.items():
        if abs(value - pt) < 0.01:
            return name
    return str(int(pt) if float(pt).is_integer() else pt)


def _font_of(rpr) -> str:
    """字体优先取中文字体（eastAsia）—— 题目说的「黑体」「宋体」都是中文字体，
    而 WPS 会把西文字体单独记一份。"""
    fonts = rpr.find(W + "rFonts") if rpr is not None else None
    if fonts is None:
        return ""
    for attr in ("eastAsia", "ascii", "hAnsi", "cs"):
        got = fonts.get(W + attr)
        if got:
            return got
    return ""


def _apply_rpr(para: dict, rpr) -> None:
    """把一段字符格式读进段落。只填**还没填过**的项 —— 先读的是段落级
    (pPr/rPr)，再读第一个 run；段落级为准，run 只补空缺。"""
    if rpr is None:
        return
    font = _font_of(rpr)
    if font and para["font"] == "宋体":
        para["font"] = font
    size = _val(rpr, "sz")
    if size and para["size"] == "五号":
        para["size"] = _size_name(size)
    for key, tag in (("bold", "b"), ("italic", "i"), ("strike", "strike")):
        if _on(rpr, tag):
            para[key] = True
    if rpr.find(W + "u") is not None:
        para["underline"] = str(_val(rpr, "u") or "single") != "none"
    vert = _val(rpr, "vertAlign")
    if vert == "superscript":
        para["sup"] = True
    elif vert == "subscript":
        para["sub"] = True
    color = _val(rpr, "color")
    if color and color.lower() not in ("auto", "000000") and not para["color"]:
        para["color"] = "#" + color.lower()
    high = _val(rpr, "highlight")
    if high and high != "none" and not para["highlight"]:
        para["highlight"] = high
    shd = rpr.find(W + "shd")
    if shd is not None and not para["shading"]:
        fill = shd.get(W + "fill") or ""
        if fill and fill.lower() not in ("auto", "ffffff"):
            para["shading"] = "#" + fill.lower()


def _read_ppr(para: dict, ppr, styles: dict | None = None) -> None:
    if ppr is None:
        return
    style = _val(ppr, "pStyle")
    if style:
        para["style"] = ((styles or {}).get(style) or STYLE_BACK.get(style)
                         or style_name(style))
    if ppr.find(W + "numPr") is not None:
        num = _val(ppr.find(W + "numPr"), "numId") or "1"
        para["bullet"] = "number" if str(num) == "2" else "dot"
    if ppr.find(W + "pBdr") is not None:
        para["border"] = True
    align = _val(ppr, "jc")
    if align:
        para["align"] = ALIGN_BACK.get(align, "left")

    pt = 10.5      # 换算 twip→字符要用字号；这一步还不知道，先按默认，下面再校正
    rpr = ppr.find(W + "rPr")
    if rpr is not None:
        size = _val(rpr, "sz")
        if size:
            pt = _num(size, 21) / 2

    ind = ppr.find(W + "ind")
    if ind is not None:
        # 带 Chars 的才是「2 字符」的原意；纯 twip 要按字号折算，会有零头
        for key, chars_attr, twip_attr in (("indent", "firstLineChars", "firstLine"),
                                           ("left", "leftChars", "left"),
                                           ("right", "rightChars", "right")):
            chars = ind.get(W + chars_attr)
            if chars is not None:
                para[key] = round(_num(chars) / 100, 2)
            elif ind.get(W + twip_attr) is not None:
                para[key] = round(_num(ind.get(W + twip_attr)) / (pt * 20), 2)

    sp = ppr.find(W + "spacing")
    if sp is not None:
        for key, lines_attr, twip_attr in (("before", "beforeLines", "before"),
                                           ("after", "afterLines", "after")):
            lines = sp.get(W + lines_attr)
            if lines is not None:
                para[key] = round(_num(lines) / 100, 2)
            elif sp.get(W + twip_attr) is not None:
                para[key] = round(_num(sp.get(W + twip_attr)) / 240, 2)
        line, rule = sp.get(W + "line"), sp.get(W + "lineRule")
        if line is not None:
            kind = RULE_BACK.get(str(rule or "auto"), "multiple")
            # 多倍行距里 240 是「一倍」；固定值/最小值是磅
            value = _num(line) / 240 if kind == "multiple" else _num(line) / 20
            para["line"] = {"type": kind, "value": round(value, 2)}

    _apply_rpr(para, rpr)


def _read_para(node, styles: dict | None = None) -> dict:
    para = blank_para()
    _read_ppr(para, node.find(W + "pPr"), styles)

    texts, first_rpr = [], None
    for run in node.iter(W + "r"):
        if first_rpr is None:
            first_rpr = run.find(W + "rPr")
        for t in run.iter(W + "t"):
            texts.append(t.text or "")
    # 制表符和软换行在 WPS 里是独立标签，漏了会让「替换后文字对不对」判错
    for br in node.iter(W + "tab"):
        texts.append("\t")
    _apply_rpr(para, first_rpr)
    para["text"] = "".join(texts)
    return para


# 纸张尺寸（twip）。**和 sim.py 的 PAPER_SIZES 保持一致，改要一起改** ——
# 客户端只用标准库，不能 import 后端那边的表。
PAPER_SIZES = {
    "A3": (16838, 23811), "A4": (11906, 16838), "A5": (8391, 11906),
    "B4": (14570, 20636), "B5": (9978, 14173),
    "Letter": (12240, 15840), "16开": (10433, 14740),
}


def _paper_name(width, height) -> str:
    """这一对宽高是什么纸。认不出来返回空串 —— 判分那边就当"没这一项"。

    留几毫米的余量：不同版本的 WPS / Word 对同一种纸的尺寸差零点几毫米。
    """
    w, h = _num(width), _num(height)
    if not w or not h:
        return ""
    w, h = min(w, h), max(w, h)              # 横排竖排当同一种纸
    for name, (pw, ph) in PAPER_SIZES.items():
        if abs(w - pw) <= 220 and abs(h - ph) <= 220:
            return name
    return ""


def _read_sect(sect) -> tuple[dict, int]:
    page, columns = {}, 1
    if sect is None:
        return page, columns
    mar = sect.find(W + "pgMar")
    if mar is not None:
        for key in ("left", "right", "top", "bottom"):
            got = mar.get(W + key)
            if got is not None:
                page[key] = round(_num(got) / CM, 2)
    size = sect.find(W + "pgSz")
    if size is not None:
        page["orient"] = "landscape" if size.get(W + "orient") == "landscape" else "portrait"
        got = _paper_name(size.get(W + "w"), size.get(W + "h"))
        if got:
            page["size"] = got
    cols = sect.find(W + "cols")
    if cols is not None:
        columns = int(_num(cols.get(W + "num"), 1) or 1)
    return page, columns


def _part_text(zf: zipfile.ZipFile, pattern: str) -> str:
    """页眉/页脚：把所有 header*.xml 里的文字拼起来。"""
    out = []
    for name in zf.namelist():
        if re.fullmatch(pattern, name):
            try:
                root = ET.fromstring(zf.read(name))
            except ET.ParseError:
                continue
            out.append("".join(t.text or "" for t in root.iter(W + "t")))
    return "\n".join(x for x in out if x.strip()).strip()


def read_docx(path) -> dict:
    """读一个 .docx，返回判分器认识的状态。**读不了就返回空的，不抛异常。**

    交卷路上任何一个异常都会让整份卷子交不上去 —— 学生把文件删了、存成了
    .doc、WPS 正锁着文件，都不该连累别的题。
    """
    path = Path(path)
    if not path.exists():
        return {}
    try:
        with zipfile.ZipFile(path) as zf:
            try:
                root = ET.fromstring(zf.read("word/document.xml"))
            except KeyError:
                # 老式 .doc 是二进制复合文档，根本不是 zip；.wps 同理
                return {}
            body = root.find(W + "body")
            if body is None:
                return {}
            styles = read_styles(zf)
            paras = [_read_para(node, styles) for node in body.findall(W + "p")]
            # 表格里的段落也算：题目有「在表格中输入……」的写法
            for cell_para in body.iter(W + "tbl"):
                paras.extend(_read_para(node, styles) for node in cell_para.iter(W + "p"))
            page, columns = _read_sect(body.find(W + "sectPr"))
            return {
                "paras": paras,
                "page": page,
                "columns": columns,
                "header": _part_text(zf, r"word/header\d*\.xml"),
                "footer": _part_text(zf, r"word/footer\d*\.xml"),
            }
    except (zipfile.BadZipFile, ET.ParseError, OSError, ValueError):
        return {}


def find_docs(root) -> list[Path]:
    """考试文件夹里所有能判的文档。

    `~$` 开头的是 WPS 打开文件时建的临时锁文件，**必须跳过** —— 它也是 .docx
    结尾，但里面不是文档，读出来是空的，会把正主顶掉。
    """
    root = Path(root)
    if not root.exists():
        return []
    return sorted(p for p in root.rglob("*")
                  if p.is_file() and p.suffix.lower() == ".docx"
                  and not p.name.startswith("~$"))
