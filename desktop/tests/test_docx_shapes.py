"""客户端读文档的新本事：文本框/图片/艺术字、分栏、页码、页面边框、按 run 读格式。

这些是 WPS 文字题（见 backend/app/services/wps_bank.py）要判的东西。文档是手写的
XML，模仿 Word / WPS / LibreOffice 存盘后的几种真实写法。
"""

from __future__ import annotations

import zipfile

from app.services import docx_io, sim
from client import docx

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
      'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
      'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w10="urn:schemas-microsoft-com:office:word"')


def write(tmp_path, body: str, footer: str = "", styles: str = "") -> dict:
    path = tmp_path / "t.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f"<w:document {NS}><w:body>{body}</w:body></w:document>")
        if footer:
            z.writestr("word/footer1.xml", f"<w:ftr {NS}>{footer}</w:ftr>")
        if styles:
            z.writestr("word/styles.xml", f"<w:styles {NS}>{styles}</w:styles>")
    return docx.read_docx(path)


def anchor(wrap: str, text: str = "", extra: str = "", behind: str = "0") -> str:
    box = (f"<wps:txbx><w:txbxContent><w:p><w:r><w:rPr><w:rFonts w:eastAsia=\"宋体\"/></w:rPr>"
           f"<w:t>{text}</w:t></w:r></w:p></w:txbxContent></wps:txbx>") if text else ""
    return (f'<w:r><mc:AlternateContent><mc:Choice Requires="wps"><w:drawing>'
            f'<wp:anchor behindDoc="{behind}"><wp:extent cx="1800000" cy="2160000"/>{wrap}'
            f'<a:graphic><a:graphicData><wps:wsp>{box}<wps:bodyPr{extra}/></wps:wsp>'
            f"</a:graphicData></a:graphic></wp:anchor></w:drawing></mc:Choice>"
            f'<mc:Fallback><w:pict><v:rect style="width:10pt;height:10pt"><v:textbox>'
            f"<w:txbxContent><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:txbxContent>"
            f"</v:textbox></v:rect></w:pict></mc:Fallback></mc:AlternateContent></w:r>")


def test_textbox_size_wrap_and_text_not_mixed_into_paragraph(tmp_path):
    got = write(tmp_path, f"<w:p>{anchor('<wp:wrapTopAndBottom/>', '锄禾日当午')}"
                          "<w:r><w:t>正文</w:t></w:r></w:p>")
    assert got["paras"][0]["text"] == "正文", "文本框里的字不该拼进锚着它的那一段"
    assert len(got["shapes"]) == 1, "新格式 + 兼容 VML 是同一个框，只算一个"
    sh = got["shapes"][0]
    assert (sh["kind"], sh["wrap"], sh["width_mm"], sh["height_mm"]) == ("textbox", "topAndBottom", 50, 60)
    assert sh["text"] == "锄禾日当午" and sh["fonts"] == ["宋体"]


def test_wordart_and_wrap_kinds(tmp_path):
    got = write(tmp_path, "<w:p>" + anchor('<wp:wrapSquare wrapText="bothSides"/>', "家国情怀",
                                           ' fromWordArt="1"')
                + anchor("<wp:wrapNone/>", "浮", behind="1") + "</w:p>")
    kinds = [(s["kind"], s["wrap"]) for s in got["shapes"]]
    assert kinds == [("wordart", "square"), ("textbox", "behind")]


def test_runs_and_east_asian_font_default(tmp_path):
    """Word/LibreOffice 中文字体等于默认时不写 eastAsia，只剩西文的 ascii —— 中文按默认字体算。"""
    styles = ('<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:eastAsia="宋体"/></w:rPr>'
              "</w:rPrDefault></w:docDefaults>")
    body = ('<w:p><w:r><w:rPr><w:rFonts w:ascii="楷体" w:hAnsi="楷体"/></w:rPr><w:t>中文字</w:t></w:r>'
            '<w:r><w:rPr><w:rFonts w:eastAsia="黑体"/><w:u w:val="double"/></w:rPr><w:t>加线的</w:t></w:r></w:p>')
    p = write(tmp_path, body, styles=styles)["paras"][0]
    assert [r["font"] for r in p["runs"]] == ["宋体", "黑体"]
    assert p["runs"][1]["u"] == "double" and "u" not in p["runs"][0]
    state = {"paras": [p]}
    ok = sim.run_checks("wps", [{"score": 1, "assert": {"op": "span", "has": "加线的", "u": "双下划线"}}], state)
    assert ok["score"] == 1
    bad = sim.run_checks("wps", [{"score": 1, "assert": {"op": "span", "has": "中文字加线", "u": "双下划线"}}], state)
    assert bad["score"] == 0, "一句话只有一半加了线，不算"


def test_section_columns_belong_to_their_paragraphs(tmp_path):
    body = ('<w:p><w:r><w:t>标题</w:t></w:r><w:pPr><w:sectPr><w:cols w:space="425"/></w:sectPr></w:pPr></w:p>'
            '<w:p><w:pPr><w:sectPr><w:cols w:num="2" w:space="420"/></w:sectPr></w:pPr>'
            '<w:r><w:t>第一段</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>第二段</w:t></w:r></w:p><w:sectPr><w:cols w:space="425"/></w:sectPr>')
    got = write(tmp_path, body)
    assert [p["cols"]["num"] for p in got["paras"]] == [1, 2, 1]
    chk = {"op": "cols", "at": {"has": "第一段"}, "num": 2, "space_chars": 2}
    assert sim.run_checks("wps", [{"score": 1, "assert": chk}], got)["score"] == 1


def test_page_number_and_border(tmp_path):
    footer = ('<w:p><w:pPr><w:jc w:val="center"/></w:pPr><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
              '<w:r><w:instrText> PAGE \\* MERGEFORMAT </w:instrText></w:r><w:r><w:t>1</w:t></w:r></w:p>')
    body = ('<w:p><w:r><w:t>x</w:t></w:r></w:p><w:sectPr><w:pgBorders><w:top w:val="single" '
            'w:color="FF0000"/></w:pgBorders></w:sectPr>')
    got = write(tmp_path, body, footer=footer)
    assert got["page_number"] == "center"
    assert got["page"]["border"] == {"val": "single", "color": "#ff0000"}


def test_image_written_by_server_reads_back(tmp_path):
    env = {"paras": [{**sim.blank_para(), "text": "a"}, {**sim.blank_para(), "text": ""}],
           "shapes": [{"kind": "image", "name": "大树", "width_mm": 30, "para": 1}]}
    path = tmp_path / "img.docx"
    path.write_bytes(docx_io.build_docx(env))
    got = docx.read_docx(path)
    assert [(s["kind"], s["wrap"], s["para"]) for s in got["shapes"]] == [("image", "inline", 1)]
