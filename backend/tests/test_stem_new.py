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

import pytest
from app.services import stem


@pytest.fixture(autouse=True)
def generic_rules_only(monkeypatch):
    """这里测的是**通用规则**。题库原题现在按 wps_bank 写死的来（见 test_wps_bank.py），
    把那张表拿掉，题干就只能走通用规则。"""
    from app.services import wps_bank
    monkeypatch.setattr(wps_bank, "BANK", [])
    stem.auto_sim.cache_clear()
    yield
    stem.auto_sim.cache_clear()


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
    # 题干说的是「标题」样式；判分时「标题」「标题 1」都认（见 sim.same_style）
    assert any(a.get("style") == "标题" for a in ops), ops


def test_replace_needs_the_word_to_be_there():
    """「把文中所有的"10后"改为"00后"」——要被替换的词必须出现在生成的正文里，
    否则这一问谁也做不出来。"""
    got = sim_of(AFTER00)
    whole = "".join(p["text"] for p in got["env"]["paras"])
    assert "10后" in whole
    assert {"op": "text", "absent": "10后", "present": "00后"} in asserts_of(got)


# ================================================================ 老师验收时指出的那几条
WIN操作 = """Win操作题
请打开本题工作目录（C：\EXAM\Win操作）按照要求进行作答。
（1）打开网页文件“安全教育网.htm”，在网页中找到“火灾逃生方法”视频资料，以“火灾逃生.rar”为名保存到“ks\消防安全”下。
（2）在“ks”文件夹中，新建一个名为“校园安全”的文件夹。
（3）将“ks”文件夹中的“安全乘车.docx”文件移动到“交通安全”文件夹中。
（4）将“ks”文件夹中“实验安全”文件夹中不合适的文件删除。
作答完成后，请关闭所有的文件和文件夹。"""

WIN09 = """请打开本题工作目录下的win09文件夹，按要求请完成以下操作：
（1）在“3D打印材料”文件夹中新建一个word文档，文件名为“打印材料”，输入以下内容：3D打印机内装有金属、陶瓷、塑料、砂等不同的“打印材料”。
（2）将文件“3D打印头盖骨”移动到对应的文件夹中。
（4）删除“医学”文件夹中不属于3D在医学领域应用的文件。
（5）将文件“房屋”重命名为“3D打印别墅”。"""

KONGZI_FULL = """Word操作题
李雯正在编辑“孔子对中华文明的贡献”文稿，请帮助她进行如下编辑修饰：
①将文章的标题设置为“标题”样式，并为正文第一自然段中的文字“孔子整理的《诗经》和孔子的诗论，是两千多年来中国文学的源头活水。”添加“双下划线”；
②设置纸张大小为A4，并在页面底端插入页码“普通数字2”；
③在文章末尾插入艺术字“家国情怀”（样式不限），并设置环绕方式为“四周型环绕”；
④将该文件以“孔子对中华文明的五大贡献.pdf”为名输出到工作目录。
完成以上操作后，保存并关闭Word。"""


def test_working_folder_can_be_written_as_a_full_path():
    r"""「请打开本题工作目录（C：\EXAM\Win操作）」—— 路径写在括号里。

    不认的话整道题的文件全落在考试根目录下，而题干说的是 C:\EXAM\Win操作 ——
    学生打开工作目录，里面空空如也。
    """
    fs = sim_of(WIN操作, "Windows系统操作")["env"]["fs"]
    assert any(p.startswith("C:/EXAM/Win操作/") for p in fs), sorted(fs)


def test_everything_the_stem_names_is_on_disk():
    """**题干点过名的东西，考场里都得有。**

    认不出某一问不要紧（那一问不判分），但不能让学生打开文件夹发现题目说的
    文件根本不存在 —— 他会以为自己找错了地方，在那一问上耗掉整场考试。
    """
    fs = sim_of(WIN操作, "Windows系统操作")["env"]["fs"]
    for path in ("C:/EXAM/Win操作/安全教育网.htm",
                 "C:/EXAM/Win操作/ks/消防安全",
                 "C:/EXAM/Win操作/ks/交通安全",
                 "C:/EXAM/Win操作/ks/安全乘车.docx",
                 "C:/EXAM/Win操作/ks/实验安全"):
        assert path in fs, f"{path} 没铺出来\n现有：{sorted(fs)}"


def test_the_answer_is_never_pre_created():
    """要学生做出来的东西一个都不能预先铺出来 —— 铺了就是把题做了。"""
    fs = sim_of(WIN操作, "Windows系统操作")["env"]["fs"]
    assert not [p for p in fs if p.endswith("火灾逃生.rar")], "答案文件被预先铺出来了"
    assert not [p for p in fs if p.endswith("校园安全")], "要新建的文件夹被预先铺出来了"


def test_the_web_page_really_has_the_material():
    """「打开网页文件……在网页中找到 X 资料」——网页里就得真有 X，而且真能下下来。

    铺一个占位文本的 .htm 等于告诉学生"自己编一个吧"，他只能新建个空文件蒙过去。
    """
    fs = sim_of(WIN操作, "Windows系统操作")["env"]["fs"]
    page = fs["C:/EXAM/Win操作/安全教育网.htm"]["content"]
    assert "火灾逃生方法" in page and "<a href=" in page, page[:120]
    assert any(p.endswith("火灾逃生方法.rar") for p in fs), "网页里链的那份资料不存在"


def test_a_vague_destination_is_not_a_folder_name():
    """「移动到**对应的**文件夹中」—— 目标是泛指，要学生自己判断放哪儿。

    机器判不了这种题。硬判会判错，更糟的是会在考场里建一个真叫「对应的」的
    文件夹，学生看了一脸问号。
    """
    got = sim_of(WIN09, "WPS文字操作")
    assert not [p for p in got["env"]["fs"] if p.endswith("对应的")], "建了个叫「对应的」的文件夹"
    assert not [a for a in asserts_of(got) if "对应的" in str(a.get("path"))]


def test_deleting_inside_a_folder_is_not_deleting_the_folder():
    """「删除"医学"文件夹中不属于……的文件」—— 删的是里面那个文件，
    不是把「医学」整个删掉。判错了学生按题做反而丢分。"""
    got = sim_of(WIN09, "WPS文字操作")
    ops = asserts_of(got)
    assert {"op": "missing", "path": "C:/EXAM/win09/医学"} not in ops
    assert "C:/EXAM/win09/医学" in got["env"]["fs"]
    assert any(a["op"] == "missing" and a["path"].startswith("C:/EXAM/win09/医学/")
               for a in ops), ops


def test_a_file_stays_a_file_when_the_stem_says_file():
    """「将**文件**"房屋"重命名为……」—— 没有扩展名，但题干说了是文件。
    铺成文件夹的话，学生看到的类型都不对。"""
    fs = sim_of(WIN09, "WPS文字操作")["env"]["fs"]
    assert fs["C:/EXAM/win09/房屋"]["type"] == "file"


def test_new_word_document_without_an_extension():
    """「新建一个 word 文档，文件名为"打印材料"」—— 题干不写扩展名，补 .docx。"""
    ops = asserts_of(sim_of(WIN09, "WPS文字操作"))
    assert {"op": "exists", "path": "C:/EXAM/win09/3D打印材料/打印材料.docx",
            "is": "file"} in ops, ops


# ================================================================ WPS 正文
def test_the_style_name_is_not_mistaken_for_the_title():
    """「将文章的标题设置为"标题"样式」—— 引号里是**样式名**。

    不单独认的话，正则会从"标题"的后引号一路捞到下一个前引号，造出一个
    「样式，并为正文第一自然段中的文字」这样的假标题，整篇文档跟着跑偏。
    """
    got = sim_of(KONGZI_FULL)
    assert got["env"]["paras"][0]["text"] == "孔子对中华文明的贡献"
    assert {"op": "para", "at": 0, "style": "标题"} in asserts_of(got)


def test_the_document_really_contains_the_quoted_sentence():
    """题干抄出来的原文必须**原样出现在文档里**，否则学生翻遍文档也找不到
    要改的那一段 —— 这一问就成了死题，而判分还"通过"了。"""
    got = sim_of(KONGZI_FULL)
    whole = "\n".join(p["text"] for p in got["env"]["paras"])
    assert "孔子整理的《诗经》和孔子的诗论，是两千多年来中国文学的源头活水。" in whole, whole
    # 检查点指的就是这一段
    hit = [a for a in asserts_of(got) if a.get("underline")]
    assert hit and hit[0]["at"]["has"] in whole, hit


def test_the_article_is_about_the_topic():
    """正文要围着这道题的题目写。「XX正在深刻改变我们的学习与生活」这种
    谁都套得上的模板，学生一看就知道文章和题目没关系。"""
    got = sim_of(KONGZI_FULL)
    body = "\n".join(p["text"] for p in got["env"]["paras"][1:])
    assert body.count("孔子对中华文明的贡献") >= 2, body


def test_word_art_text_does_not_leak_into_the_article():
    """「在文章末尾插入艺术字"家国情怀"」——那是要学生插进去的，
    不是文档里本来就有的话。"""
    got = sim_of(KONGZI_FULL)
    whole = "\n".join(p["text"] for p in got["env"]["paras"])
    assert "家国情怀" not in whole, whole


def test_a_filename_is_never_read_as_a_font():
    """「孔子对中华文明的五大贡献.pdf」里有"华文明的五"。字体名用通配写法时
    它会被当成字体，造出一条**谁也做不到**的检查点。"""
    for a in asserts_of(sim_of(KONGZI_FULL)):
        assert "华文明" not in str(a.get("font", "")), a


# ================================================================ win04：按名称排序的中间一个
WIN04 = """请打开本题工作目录下的win04文件夹，按要求请完成以下操作：
（1）在“盆地”文件夹中，新建名为“四川盆地”的文件夹。
（2）在“长江中下游平原”文件夹中，将按名称排序后的中间一个文件改名为“长江三角洲.doc”。
（3）将名为“黄土高原”的文件夹复制到“高原”文件夹中。
（4）将名为“三江平原.txt”的文件移动到“东北平原”文件夹中。
（5）删除“塔里木盆地”文件夹。"""


def test_中间一个文件那一问_文件夹和文件都铺出来():
    """老师在考场里做到第 (2) 问，打开工作目录发现根本没有「长江中下游平原」
    —— 那一整句原来没有规则认得，兜底铺文件的逻辑又恰好跳过了它。"""
    got = sim_of(WIN04)
    fs = got["env"]["fs"]
    folder = "C:/EXAM/win04/长江中下游平原"
    assert fs.get(folder, {}).get("type") == "dir", "「长江中下游平原」没铺出来"
    inside = sorted(p.rsplit("/", 1)[-1] for p in fs if p.startswith(folder + "/"))
    assert len(inside) == 3, f"要有一组文件才说得清哪个是「中间一个」：{inside}"
    assert "长江三角洲.doc" not in inside, "改名后的名字是答案，不能预先铺"

    ops = asserts_of(got)
    assert {"op": "exists", "path": folder + "/长江三角洲.doc", "is": "file"} in ops
    middle = sorted(inside)[1]
    assert {"op": "missing", "path": f"{folder}/{middle}"} in ops, "检查的得是中间那一个"


def test_中间一个按拼音排和按码位排是同一个():
    """资源管理器（中文 Windows）按**拼音**排，程序按**码位**排。铺的名字两种
    排法结果必须一样，不然学生照着屏幕改对了，判分却说错了。
    拼音：巢(chao) < 江(jiang) < 鄱(po)；码位：5DE2 < 6C5F < 9131。"""
    trio = stem._sorted_trio("长江中下游平原", "doc")
    assert list(trio) == sorted(trio), "码位顺序和铺的顺序不一致"
    pinyin = {"巢": "chao", "江": "jiang", "鄱": "po"}
    assert [pinyin[n[0]] for n in trio] == sorted(pinyin[n[0]] for n in trio)
    # 没见过的文件夹：只差一个英文字母，两种排法都是 A < B < C
    assert stem._sorted_trio("随便什么", "txt") == ("资料A.txt", "资料B.txt", "资料C.txt")


def test_在某文件夹中这句没认出来_那个文件夹也要铺():
    """兜底那一层原来会跳过句子自己的那个文件夹（本意是别把它铺进它自己里），
    结果哪儿都没铺。这里拿一句**没有规则认得**的话来验兜底。"""
    got = sim_of("请打开本题工作目录下的win77文件夹，完成以下操作："
                 "（1）在“冷门文件夹”文件夹中，把里面的东西按大小重新整理一遍。"
                 "（2）删除“旧资料”文件夹。")
    assert got and got["env"]["fs"].get("C:/EXAM/win77/冷门文件夹", {}).get("type") == "dir"


# ================================================================ 「标题」样式
def test_标题样式那一问_标题和标题1都算对():
    """老师在机房实际做这道题：用的是 WPS 样式栏里的「标题 1」，判分却说错了。
    题干写的是「设置为"标题"样式」—— Word 里叫「标题」的是 Title 样式，可 WPS
    样式栏最前面的就是「标题 1」，说"标题样式"多半指它，两个都得认。"""
    from app.services import sim

    got = sim_of(KONGZI_FULL)
    style_checks = [c for c in got["checks"] if "style" in (c.get("assert") or {})]
    assert style_checks, "「标题」样式那一问没出检查点"
    check = style_checks[0]

    def run(style):
        paras = [dict(p) for p in got["env"]["paras"]]
        paras[0]["style"] = style
        return sim.run_checks("wps", [check], {"paras": paras, "page": got["env"].get("page", {})})

    for ok in ("标题1", "标题 1", "heading 1", "标题", "Title"):
        assert run(ok)["results"][0]["ok"], f"用「{ok}」样式应该算对"
    for bad in ("正文", "标题2", "2"):
        assert not run(bad)["results"][0]["ok"], f"用「{bad}」样式不该算对"


def test_要求标题1的只认标题1():
    from app.services import sim

    assert sim.same_style("标题 1", "标题1")
    assert not sim.same_style("标题", "标题1"), "明确要求「标题1」时，Title 样式不算"
