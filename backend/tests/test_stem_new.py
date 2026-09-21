# -*- coding: utf-8 -*-
"""题干解析：2026-09-21 这批新题带出来的规则。

题干全部是老师后来补进题库的**真题原文**，一个字没改 —— 编出来的题干只能
证明正则写对了，证明不了它认得真题。

这个文件盯着两件事：

  · **该判的判出来**：重命名、建文件夹、删文件夹、页眉页脚、纸张、页边距、
    按原文定位段落、颜色/加粗/下划线。
  · **别判错人**：文件操作题不要被当成 WPS 排版题（反过来也一样）。
    这条比上一条更要紧 —— 判错类别的后果是整道题一个检查点都出不来，
    而且题目照出、文件照铺，表面上看不出毛病。
"""

from __future__ import annotations

from app.services import stem


def sim_of(text: str, scope: str = "") -> dict:
    """走**出卷和判分真正用的那个入口**（auto_sim），不是底层的 parse。

    两者差一层：parse 给的是相对路径，auto_sim 会补上 C:/EXAM 前缀 ——
    考场上铺文件、判分对路径，用的都是补过前缀的那一份。
    """
    return stem.auto_sim(text, scope) or {}


def asserts_of(got: dict) -> list[dict]:
    return [c["assert"] for c in (got or {}).get("checks") or []]


def descs_of(got: dict) -> str:
    return "　".join(c["desc"] for c in (got or {}).get("checks") or [])


# 真题原文
WIN06 = """请打开本题工作目录下的win06文件夹，按要求请完成以下操作：
（1）把“重阳节.doc”文件重命名为“老人节.doc”。
（2）在“外国节日”文件夹中建立一个新的文件夹“圣诞节”。
（3）将“情人节.doc”文件移动到“外国节日”文件夹中。"""

WIN02 = """请打开本题工作目录下的win02文件夹，按要求请完成以下操作：
（1）在“会徽”文件夹中新建文本文件，文件名为“冬梦.txt”，输入内容为“北京冬奥会会徽”。
（2）将“吉祥物.jpg”重命名为“冰墩墩.jpg”。
（3）删除“赛区”文件夹中的图片文件。
（4）将“新增项目.txt”复制到“冰上项目”文件夹中。"""

WIN04 = """请打开本题工作目录下的win04文件夹，按要求请完成以下操作：
（1）在“盆地”文件夹中，新建名为“四川盆地”的文件夹。
（3）将名为“黄土高原”的文件夹复制到“高原”文件夹中。
（4）将名为“三江平原.txt”的文件移动到“东北平原”文件夹中。
（5）删除“塔里木盆地”文件夹。"""

SPRING = """请打开本题工作目录下的文件“我见到了春天.docx”，按下列要求进行操作：
（1）为文档添加页眉为“春天”，右对齐显示。
（2）将文章第2自然段（“远处的群山……线上系的花瓣儿。”）字体格式化为绿色；楷体；斜体；四号字；加双波浪形下划线。
（3）将自然段（“春雨过后，……一幅秀丽的山水图。”）移动到最后，形成一个新的自然段。
（5）为文档添加页脚，内容为“1”，右对齐显示。
保存文件并退出。"""

AFTER00 = """WPS文字
请打开本题工作目录（C：\\EXAM\\WPS文字）下名为“00后，自我崛起的一代.wps”的WPS文字文件，并完成以下操作。
（1）将文章题目“00后，自我崛起的一代”，设置字体为楷体，字号为二号，字形为加粗，对齐方式为居中对齐。
（2）将文中所有的“10后”改为“00后”。
（5）将页面设置调整为：左右页边距为2.5厘米，上下页边距为2厘米。
请保存文件，并退出。"""

KONGZI = """Word操作题
①将文章的标题设置为“标题”样式；
②设置纸张大小为A4，并在页面底端插入页码“普通数字2”；
完成以上操作后，保存并关闭Word。"""


# ================================================================ 别判错类别
def test_renaming_a_doc_is_still_a_file_task():
    """**踩过的坑**：「打开 win06 文件夹……把"重阳节.doc"重命名为"老人节.doc"」——
    "打开"后面四十个字内出现了 .doc，整道题被当成 WPS 文字题，于是配了个文档
    环境，五问一问也判不出来，而题目照出、文件照铺，表面上看不出毛病。"""
    assert stem.guess_kind(WIN06, "Windows系统操作") == "win"


def test_moving_a_paragraph_is_not_a_file_task():
    """反过来也一样：「把第四段移动到文章末尾」里的"移动"是排版，不是文件管理。
    光看动词会把排版题拖进文件操作那条路，一个检查点也出不来。"""
    text = "请打开“风中的一棵树.docx”：把文章的第4自然段移动到文档的最后，形成一个新的自然段。"
    assert stem.guess_kind(text, "WPS文字操作") == "wps"


def test_file_tasks_filed_under_wps_still_parse_as_file_tasks():
    """题库里知识范围填错的不少：这道明明是文件管理，却挂在「WPS文字操作」下。
    **以题干为准**。"""
    got = sim_of(WIN04, "WPS文字操作")
    assert got["kind"] == "win"


# ================================================================ Windows
def test_rename_needs_both_halves():
    """重命名要判两头：新名字在、**旧名字不在**。只判前一半的话，
    学生复制一份改名也算对。"""
    got = sim_of(WIN06)
    ops = asserts_of(got)
    assert {"op": "exists", "path": "C:/EXAM/win06/老人节.doc"} in ops
    assert {"op": "missing", "path": "C:/EXAM/win06/重阳节.doc"} in ops
    # 原件必须铺出来，否则学生打开文件夹里根本没有要改名的那个文件
    assert "C:/EXAM/win06/重阳节.doc" in got["env"]["fs"]


def test_build_a_new_folder_inside_another():
    """「在"外国节日"文件夹中建立一个新的文件夹"圣诞节"」——"建立"和"新建"
    是一回事，真题两种写法都有。"""
    ops = asserts_of(sim_of(WIN06))
    assert {"op": "exists", "path": "C:/EXAM/win06/外国节日/圣诞节", "is": "dir"} in ops


def test_copy_without_the_word_file():
    """「将"新增项目.txt"复制到"冰上项目"文件夹中」——中间没有"文件"两个字。
    正则原来写成 `文件?`（文 + 可选的件），这种说法整条漏判。"""
    ops = asserts_of(sim_of(WIN02))
    assert {"op": "exists", "path": "C:/EXAM/win02/冰上项目/新增项目.txt"} in ops


def test_delete_a_picture_file_gets_a_real_file_to_delete():
    """「删除"赛区"文件夹中的图片文件」没点名是哪一个 —— 那就**铺一个出来**，
    学生看到的和判分看的是同一个文件，题目才做得成。"""
    got = sim_of(WIN02)
    seeded = [p for p in got["env"]["fs"] if p.startswith("C:/EXAM/win02/赛区/")]
    assert seeded, "该铺一个图片文件出来"
    assert {"op": "missing", "path": seeded[0]} in asserts_of(got)


def test_delete_a_whole_folder():
    ops = asserts_of(sim_of(WIN04, "WPS文字操作"))
    assert {"op": "missing", "path": "C:/EXAM/win04/塔里木盆地"} in ops


def test_named_folder_copy():
    """「将名为"黄土高原"的文件夹复制到"高原"文件夹中」—— 名为…的写法。"""
    got = sim_of(WIN04, "WPS文字操作")
    assert {"op": "exists", "path": "C:/EXAM/win04/高原/黄土高原"} in asserts_of(got)
    assert got["env"]["fs"]["C:/EXAM/win04/黄土高原"]["type"] == "dir"


# ================================================================ WPS 文字
def test_header_and_footer():
    ops = asserts_of(sim_of(SPRING))
    assert {"op": "header", "has": "春天"} in ops
    assert {"op": "footer", "has": "1"} in ops


def test_paragraph_is_found_by_its_own_words():
    """段落按**原文**定位，不按序号。

    同一道题里往往还有"把某段移到最后"，段落一挪，按序号定位的检查点就全指错
    —— 学生做对了反而判错。所以题干把原文抄在括号里时一律按内容找。
    """
    got = sim_of(SPRING)
    at = [a["at"] for a in asserts_of(got) if a["op"] == "para"]
    assert at and all(isinstance(x, dict) and x.get("has") for x in at), at
    # 那句原文还得真出现在生成的正文里，否则学生找不到要改的那一段
    whole = "".join(p["text"] for p in got["env"]["paras"])
    assert "远处的群山" in whole


def test_colour_underline_and_italic():
    ops = [a for a in asserts_of(sim_of(SPRING)) if a["op"] == "para"]
    keys = {k for a in ops for k in a if k not in ("op", "at")}
    assert {"color", "underline", "italic", "font", "size"} <= keys, keys


def test_move_a_paragraph_to_the_end():
    ops = asserts_of(sim_of(SPRING))
    assert any(a["op"] == "order" and "春雨过后" in str(a.get("last")) for a in ops)


def test_wps_file_and_article_title():
    """文件名是 .wps（金山自己的后缀），题干里叫它"文章题目"而不是"标题"。
    两样都要认，否则这道题的第一问判不了。"""
    got = sim_of(AFTER00)
    assert got["env"]["name"].startswith("00后"), got["env"]["name"]
    assert got["env"]["paras"][0]["text"] == "00后，自我崛起的一代"
    para = [a for a in asserts_of(got) if a["op"] == "para"]
    assert para and para[0]["at"] == {"has": "00后，自我崛起的一"}, para[0]["at"]
    assert {"font": "楷体"}.items() <= {k: v for a in para for k, v in a.items()}.items()


def test_page_margins_in_pairs():
    """「左右页边距为2.5厘米，上下页边距为2厘米」—— 一句话两组边距。"""
    ops = [a for a in asserts_of(sim_of(AFTER00)) if a["op"] == "page"]
    merged = {k: v for a in ops for k, v in a.items() if k != "op"}
    assert merged == {"left": 2.5, "right": 2.5, "top": 2.0, "bottom": 2.0}, merged


def test_paper_size_and_heading_style():
    ops = asserts_of(sim_of(KONGZI))
    assert {"op": "page", "size": "A4"} in ops
    assert any(a.get("style") == "标题1" for a in ops), ops


def test_replace_needs_the_word_to_be_there():
    """「把文中所有的"10后"改为"00后"」——要被替换的词必须出现在生成的正文里，
    否则这一问谁也做不出来。"""
    got = sim_of(AFTER00)
    whole = "".join(p["text"] for p in got["env"]["paras"])
    assert "10后" in whole
    assert {"op": "text", "absent": "10后", "present": "00后"} in asserts_of(got)
