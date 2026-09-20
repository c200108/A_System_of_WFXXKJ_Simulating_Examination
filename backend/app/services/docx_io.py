"""把 WPS 仿真环境写成一个真的 .docx，铺到考场机器上。

## 为什么要这个

网页版的 WPS 仿真题，文档存的是 `env["paras"]` —— 一串段落加格式，不是文件。
桌面端要让学生在**真的 WPS 里**做题，就得先有一个真文件。

于是这条线是对称的：

    出题：老师在网页仿真器里排好版  →  这里写成 .docx  →  铺到 C:\\EXAM
    判分：学生用真 WPS 改完存盘     →  客户端读回 paras →  原样喂给判分器

两头用的是**同一套段落模型**（`sim.py` 的 `blank_para()`），所以检查点一个字
都不用改 —— 老师在网页上点出来的检查点，在真机上照样判。

读那一半在 `desktop/client/docx.py`。两边会不会走偏，由
`desktop/tests/test_docx.py` 的往返测试盯着：写出去再读回来，格式必须一模一样。

## 为什么自己拼 XML 而不用 python-docx

后端本来就不该为了这点事多一个依赖；.docx 说到底就是个 zip 装着几份 XML，
我们要写的又只有段落和页面设置这一小块。**读**的那一半在客户端，那边更不能
带依赖 —— 它要打进 exe。

## 单位

OOXML 里长度基本都是 twip（1/20 磅）：

    1 磅   = 20 twip
    1 厘米 = 567 twip（1440 twip/英寸 ÷ 2.54）
    字号「五号」= 10.5 磅 = w:sz 21（w:sz 用的是半磅）

「缩进 2 字符」「段前 1 行」这类以字符/行为单位的，WPS 会同时写一个
`w:firstLineChars="200"`（百分之一字符）和一个 twip 值。**写的时候两个都写**，
读的时候优先认带 Chars 的那个 —— 只有它才是"2 字符"的原意，twip 值会随字号变。
"""

from __future__ import annotations

import io
import zipfile

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# 字号名 → 磅。和 sim.py 里那张表对齐，改要一起改
SIZE_PT = {
    "初号": 42, "小初": 36, "一号": 26, "小一": 24, "二号": 22, "小二": 18,
    "三号": 16, "小三": 15, "四号": 14, "小四": 12, "五号": 10.5, "小五": 9,
    "六号": 7.5, "小六": 6.5, "七号": 5.5, "八号": 5,
}
ALIGN_XML = {"left": "left", "center": "center", "right": "right",
             "justify": "both", "distribute": "distribute"}
# 样式：WPS 存的是样式 id，界面上显示的是中文名
STYLE_ID = {"正文": "Normal", "标题1": "Heading1", "标题2": "Heading2",
            "标题3": "Heading3"}
LINE_RULE = {"fixed": "exact", "least": "atLeast", "multiple": "auto"}

CM = 567.0                      # 1 厘米多少 twip


def pt_of(size) -> float:
    """「五号」「10.5」都变成磅。"""
    if size is None or size == "":
        return 10.5
    s = str(size).strip()
    if s in SIZE_PT:
        return SIZE_PT[s]
    try:
        return float(s)
    except ValueError:
        return 10.5


def esc(text: str) -> str:
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _rpr(p: dict) -> str:
    """段落里那一串字符格式。

    模型把格式挂在段落上（中考的 WPS 题九成是「把某段设成……」），所以这里
    把它同时写进 pPr/rPr 和每个 run 的 rPr —— 学生在 WPS 里点段落任何位置，
    看到的格式都对得上。
    """
    font, bits = str(p.get("font") or "宋体"), []
    bits.append(f'<w:rFonts w:ascii="{esc(font)}" w:hAnsi="{esc(font)}" '
                f'w:eastAsia="{esc(font)}" w:cs="{esc(font)}"/>')
    if p.get("bold"):
        bits.append("<w:b/><w:bCs/>")
    if p.get("italic"):
        bits.append("<w:i/><w:iCs/>")
    if p.get("underline"):
        bits.append('<w:u w:val="single"/>')
    if p.get("strike"):
        bits.append("<w:strike/>")
    if p.get("sup"):
        bits.append('<w:vertAlign w:val="superscript"/>')
    if p.get("sub"):
        bits.append('<w:vertAlign w:val="subscript"/>')
    if p.get("color"):
        bits.append(f'<w:color w:val="{esc(str(p["color"]).lstrip("#"))}"/>')
    if p.get("highlight"):
        bits.append(f'<w:highlight w:val="{esc(p["highlight"])}"/>')
    if p.get("shading"):
        bits.append(f'<w:shd w:val="clear" w:color="auto" '
                    f'w:fill="{esc(str(p["shading"]).lstrip("#"))}"/>')
    half = int(round(pt_of(p.get("size")) * 2))
    bits.append(f'<w:sz w:val="{half}"/><w:szCs w:val="{half}"/>')
    return "".join(bits)


def _ppr(p: dict) -> str:
    pt = pt_of(p.get("size"))
    bits = []

    style = STYLE_ID.get(str(p.get("style") or "正文"))
    if style and style != "Normal":
        bits.append(f'<w:pStyle w:val="{style}"/>')

    bullet = str(p.get("bullet") or "none")
    if bullet in ("dot", "number"):
        num = 1 if bullet == "dot" else 2
        bits.append(f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr>')

    if p.get("border"):
        side = '<w:{0} w:val="single" w:sz="4" w:space="1" w:color="auto"/>'
        bits.append("<w:pBdr>" + "".join(side.format(s) for s in
                                         ("top", "left", "bottom", "right")) + "</w:pBdr>")

    # 缩进：Chars 是原意（2 字符），twip 是给不认 Chars 的阅读器兜底
    ind = []
    for key, chars_attr, twip_attr in (("indent", "firstLineChars", "firstLine"),
                                       ("left", "leftChars", "left"),
                                       ("right", "rightChars", "right")):
        val = float(p.get(key) or 0)
        if val:
            ind.append(f'w:{chars_attr}="{int(round(val * 100))}" '
                       f'w:{twip_attr}="{int(round(val * pt * 20))}"')
    if ind:
        bits.append(f'<w:ind {" ".join(ind)}/>')

    # 间距：段前段后按行、行距按类型
    sp = []
    for key, chars_attr, twip_attr in (("before", "beforeLines", "before"),
                                       ("after", "afterLines", "after")):
        val = float(p.get(key) or 0)
        if val:
            sp.append(f'w:{chars_attr}="{int(round(val * 100))}" '
                      f'w:{twip_attr}="{int(round(val * 240))}"')
    line = p.get("line")
    if isinstance(line, dict) and line.get("value"):
        kind = str(line.get("type") or "multiple")
        value = float(line["value"])
        # 多倍行距的 240 是"一倍"，固定值/最小值按磅换 twip
        twips = int(round(value * 240)) if kind == "multiple" else int(round(value * 20))
        sp.append(f'w:line="{twips}" w:lineRule="{LINE_RULE.get(kind, "auto")}"')
    if sp:
        bits.append(f'<w:spacing {" ".join(sp)}/>')

    align = ALIGN_XML.get(str(p.get("align") or "left"), "left")
    if align != "left":
        bits.append(f'<w:jc w:val="{align}"/>')

    bits.append(f"<w:rPr>{_rpr(p)}</w:rPr>")
    return f"<w:pPr>{''.join(bits)}</w:pPr>"


def _para_xml(p: dict) -> str:
    text = str(p.get("text") or "")
    run = ""
    if text:
        run = (f'<w:r><w:rPr>{_rpr(p)}</w:rPr>'
               f'<w:t xml:space="preserve">{esc(text)}</w:t></w:r>')
    return f"<w:p>{_ppr(p)}{run}</w:p>"


def _sect_xml(page: dict, columns: int) -> str:
    page = page or {}
    orient = str(page.get("orient") or "portrait")
    # A4：21 × 29.7 厘米
    wide, tall = (11906, 16838) if orient == "portrait" else (16838, 11906)
    def tw(key, default_cm):
        return int(round(float(page.get(key, default_cm) or default_cm) * CM))
    cols = f'<w:cols w:num="{max(1, int(columns or 1))}"/>' if int(columns or 1) > 1 else \
           '<w:cols w:space="425"/>'
    return (f'<w:sectPr><w:pgSz w:w="{wide}" w:h="{tall}"'
            + (' w:orient="landscape"' if orient != "portrait" else "") + "/>"
            + f'<w:pgMar w:top="{tw("top", 2.54)}" w:right="{tw("right", 3.17)}" '
              f'w:bottom="{tw("bottom", 2.54)}" w:left="{tw("left", 3.17)}" '
              f'w:header="851" w:footer="992" w:gutter="0"/>'
            + cols + "</w:sectPr>")


CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>
</Types>"""

ROOT_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""

DOC_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>
</Relationships>"""

# 只定义题目用得到的那几个样式。w:name 给中文别名，WPS 的样式下拉里看到的就是它
STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="%s">
<w:docDefaults><w:rPrDefault><w:rPr>
<w:rFonts w:ascii="宋体" w:eastAsia="宋体" w:hAnsi="宋体"/><w:sz w:val="21"/>
</w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="正文"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="标题 1"/>
<w:pPr><w:outlineLvl w:val="0"/></w:pPr><w:rPr><w:b/><w:sz w:val="44"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="标题 2"/>
<w:pPr><w:outlineLvl w:val="1"/></w:pPr><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="标题 3"/>
<w:pPr><w:outlineLvl w:val="2"/></w:pPr><w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
</w:styles>""" % W

# numId 1 = 项目符号，numId 2 = 编号。够用了，题目不会考到多级列表
NUMBERING = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:numbering xmlns:w="%s">
<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0">
<w:numFmt w:val="bullet"/><w:lvlText w:val="&#8226;"/><w:start w:val="1"/>
</w:lvl></w:abstractNum>
<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0">
<w:numFmt w:val="decimal"/><w:lvlText w:val="%%1."/><w:start w:val="1"/>
</w:lvl></w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>
<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>
</w:numbering>""" % W


def build_docx(state: dict) -> bytes:
    """把 WPS 仿真环境写成一个真的 .docx。

    state 就是 `sim_tasks.env_json`：`{"name": …, "paras": [...], "page": {...}}`。
    """
    paras = [p for p in (state.get("paras") or []) if isinstance(p, dict)]
    if not paras:
        paras = [{"text": ""}]
    body = "".join(_para_xml(p) for p in paras)
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>{body}'
        f'{_sect_xml(state.get("page") or {}, state.get("columns") or 1)}'
        "</w:body></w:document>"
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("word/document.xml", document)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/styles.xml", STYLES)
        z.writestr("word/numbering.xml", NUMBERING)
    return buf.getvalue()


def docx_name(state: dict, fallback: str = "文档") -> str:
    """考场里那个文件叫什么。

    仿真环境里存的名字可能是「范文.wps」——**一律换成 .docx**：.wps 是金山的
    私有格式，我们写的是标准 OOXML，扩展名对不上的话 WPS 打开会报格式错。
    """
    name = str(state.get("name") or "").strip() or fallback
    for ext in (".wps", ".doc", ".docx", ".txt"):
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
            break
    return (name or fallback) + ".docx"
