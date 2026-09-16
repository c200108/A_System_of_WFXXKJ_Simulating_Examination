# -*- coding: utf-8 -*-
"""试卷 docx → 题库导入表（tools/docx_to_bank.py）。

这个工具不碰数据库，但产出要能被题库的导入解析器原样吃下去，
所以最后一条测试直接拿 app.services.importer.parse_upload 验收 ——
工具改坏了、或者导入那边的规则变了，这条都会红。
"""

import glob
import io
import os
import zipfile

import pytest

from app.services.importer import parse_upload
from tools import docx_to_bank as d2b

SCOPES = [
    "信息基础与信息技术", "计算机硬件", "计算机软件", "Windows系统操作", "WPS文字操作",
    "信息安全与网络道德", "计算机网络基础", "Python编程基础", "人工智能", "物联网",
]

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def make_docx(path, paragraphs):
    """按段落造一个最小的 .docx —— docx 就是个 zip，够这个工具读就行。"""
    body = "".join(
        "<w:p><w:r><w:t xml:space='preserve'>{}</w:t></w:r></w:p>".format(
            p.replace("&", "&amp;").replace("<", "&lt;")
        )
        for p in paragraphs
    )
    xml = f"<?xml version='1.0'?><w:document xmlns:w='{W}'><w:body>{body}</w:body></w:document>"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", xml)
    return str(path)


CHOICE = [
    "一．选择题（共3小题）",
    "1．（2分）·（2024•山东模拟）在Windows中，切换当前活动窗口的快捷键是（　　）",
    "A．Alt+Tab\tB．Ctrl+C",
    "C．Alt+F4\tD．Win+D",
    "【考点】计算机系统．菁优网版权所有",
    "【答案】A",
    "【分析】这一段是出卷网站写的解析，不该被抄进题库。",
]
JUDGE = [
    "二、判断题",
    "2．（2021•济宁模拟）信息必须依附于载体才能进行传播。 　√　 （判断对错）",
    "【考点】信息与信息技术．菁优网版权所有",
    "【答案】√。",
    "【分析】解析文字。",
]
BLANK = [
    "三、填空题",
    "3．在Python中，若要获取用户输入的信息，可使用　input　函数。",
    "【考点】Python程序设计基础．菁优网版权所有",
    "【答案】input",
]
OPERATE = [
    "四、操作题",
    "4．（15分）WPS文字",
    "请打开本题工作目录下名为“范文.wps”的文件，并完成以下操作。",
    "（1）将标题设置为楷体、二号、加粗、居中。",
    "（2）将正文首行缩进2个字符。",
    "请保存文件，并退出。",
    "【考点】Word基本操作．菁优网版权所有",
    "【答案】（1）选中标题，单击工具栏……（2）右键选择段落……（3）……（4）……"
    "这一长串是出卷网站写的操作步骤，足足超过一百二十个字，工具应该换成「略」，"
    "而不是原样抄进题库里去。",
    "【分析】本题为上机操作题。",
]


@pytest.fixture(scope="module")
def parsed(tmp_path_factory):
    d = tmp_path_factory.mktemp("juan")
    make_docx(d / "卷一.docx", CHOICE + JUDGE + BLANK + OPERATE)
    images = {}
    lines = d2b.read_docx(str(d / "卷一.docx"), "p01", images)
    return [d2b.clean_one(b) for b in d2b.split_questions(lines, "卷一.docx")]


def test_four_types_come_out(parsed):
    assert [x["type"] for x in parsed] == ["选择题", "判断题", "填空题", "操作题"]


def test_stem_drops_number_score_and_source(parsed):
    """题号、分值、「（2024•山东模拟）」这类出处都不该留在题干里。"""
    stem = parsed[0]["stem"]
    assert stem.startswith("在Windows中")
    assert "山东模拟" not in stem and "2分" not in stem


def test_options_split_even_when_two_share_a_line(parsed):
    assert parsed[0]["opts"] == [
        ["A", "Alt+Tab"], ["B", "Ctrl+C"], ["C", "Alt+F4"], ["D", "Win+D"]
    ]
    assert parsed[0]["answer"] == "A"


def test_analysis_is_never_copied(parsed):
    """【分析】是出卷网站自己写的解析，一个字都不该进题库。"""
    for x in parsed:
        assert "出卷网站写的解析" not in x["stem"] + x["answer"]


def test_judge_answer_moves_out_of_the_stem(parsed):
    """原卷把答案印在题干里（"…传播。 √ （判断对错）"），要挖干净。"""
    judge = parsed[1]
    assert judge["stem"] == "信息必须依附于载体才能进行传播。"
    assert judge["answer"] == "正确"
    assert "√" not in judge["stem"] and "判断对错" not in judge["stem"]


def test_blank_question_gets_a_blank(parsed):
    fill = parsed[2]
    assert "＿＿＿＿" in fill["stem"]
    assert "input" not in fill["stem"], "答案还留在题干里，等于把答案告诉学生了"
    assert fill["answer"] == "input"


def test_long_operation_answer_becomes_a_placeholder(parsed):
    """操作题的答案是人家写的操作步骤，不抄；这类题本来也是老师人工打分。"""
    op = parsed[3]
    assert op["answer"].startswith("略")
    assert "单击工具栏" not in op["answer"]
    assert "（1）将标题设置为楷体" in op["stem"], "题干里的操作要求要留着"


# ---------------------------------------------------------------- 归类与难度
@pytest.mark.parametrize(
    "stem, expect",
    [
        # 关键词直接命中
        ("在Python中，表达式“3**2”的值为（ ）", "Python编程基础"),
        ("智慧果园中，智能喷头根据（ ）信息自动调节喷水量。", "物联网"),
        ("用软件将图片上的文字识别出来，用的是（ ）技术", "人工智能"),
        ("在WPS文字中，若给一段文字添加双下划线，可以通过（ ）完成。", "WPS文字操作"),
        # 「下列表述」里的"列表"、WPS 的"首行缩进"，都不该被当成编程题
        ("关于“神威•太湖之光”超级计算机，下列表述正确的是（ ）", "计算机硬件"),
        ("将正文段落设置为首行缩进2个字符，行距为固定值22磅。", "WPS文字操作"),
    ],
)
def test_scope_guess(stem, expect):
    item = {"stem": stem, "opts": [], "point": ""}
    assert d2b.guess_scope(item, SCOPES) == expect


def test_options_do_not_drag_the_scope_away():
    """先只看题干：这道题考的是计算机发展史，可某个选项里写着"物联网计算机"。"""
    item = {
        "stem": "计算机的发展经历了电子管计算机、（ ）、集成电路计算机等四个阶段。",
        "opts": [["A", "电子计算机"], ["B", "物联网计算机"],
                 ["C", "晶体管计算机"], ["D", "网络模拟计算机"]],
        "point": "计算机的发展及应用",
    }
    assert d2b.guess_scope(item, SCOPES) == "信息基础与信息技术"


def test_level_is_between_one_and_five_and_ordered():
    """判断题最容易、操作题最难，算一算的题比背一背的题难。"""
    judge = {"type": "判断题", "stem": "文件被删除后一定放到回收站。", "opts": []}
    recall = {"type": "选择题", "stem": "在Internet中电子邮件的缩写是（ ）", "opts": []}
    calc = {"type": "选择题", "stem": "二进制数1011转换为十进制数是（ ）", "opts": []}
    op = {"type": "操作题", "stem": "（1）新建文件夹（2）改名（3）移动（4）删除", "opts": []}

    lv_judge, lv_recall, lv_calc, lv_op = [
        d2b.guess_level(q, "Windows系统操作") for q in (judge, recall, calc, op)
    ]
    assert all(1 <= n <= 5 for n in (lv_judge, lv_recall, lv_calc, lv_op))
    assert lv_judge < lv_calc, "一句话的判断题不该和进制转换一样难"
    assert lv_recall < lv_calc, "背一背的题不该和算一算的题一样难"
    assert lv_op >= 4, "多步骤操作题是最难的一档"


def test_url_slashes_are_not_mistaken_for_a_division():
    """网址里的 // 不是运算符，这道题不该因此被当成要算的题。"""
    item = {"type": "选择题", "opts": [],
            "stem": "从网址“http：//www.chinaedu.edu.cn/”中，可以知道该网站是（ ）"}
    assert d2b.guess_level(item, "计算机网络基础") <= 3


# ---------------------------------------------------------------- 查重
def test_near_duplicates_keep_only_one():
    """两份卷子出了同一道题，只留先出现的那一道。"""
    a = {"stem": "“粘贴”的快捷键是（ ）", "opts": [["A", "Ctrl+C"], ["B", "Ctrl+V"]]}
    b = {"stem": "“粘贴”的快捷键是（　　）", "opts": [["A", "Ctrl+C"], ["B", "Ctrl+V"]]}
    c = {"stem": "“复制”的快捷键是（ ）", "opts": [["A", "Ctrl+C"], ["B", "Ctrl+V"]]}
    kept, dropped = d2b.dedup([a, b, c], 0.95)
    assert kept == [a, c]
    assert dropped == [(b, a)]


def test_same_stem_different_options_is_still_a_duplicate():
    """题库按题干判重，题干一模一样的两道题导进去也只会留一道。"""
    a = {"stem": "下列选项中，正确的域名格式是（ ）", "opts": [["A", "sunlei@baidu.com"]]}
    b = {"stem": "下列选项中，正确的域名格式是（ ）", "opts": [["A", "zaozhuang@baidu.com"]]}
    kept, dropped = d2b.dedup([a, b], 0.95)
    assert kept == [a] and len(dropped) == 1


# ---------------------------------------------------------------- 端到端
def test_output_file_imports_without_errors(tmp_path):
    """产出的 xlsx 必须能被题库的导入解析器原样吃下去，一条错都不能有。"""
    src = tmp_path / "试卷"
    src.mkdir()
    make_docx(src / "卷一.docx", CHOICE + JUDGE + BLANK + OPERATE)
    make_docx(src / "卷二.docx", CHOICE)          # 整份重复，应该被查重去掉

    assert d2b.main([str(src)]) == 0

    out = glob.glob(str(src / "题库导入" / "*.xlsx"))
    assert len(out) == 1, "应该只产出一个 xlsx"
    assert "4题" in os.path.basename(out[0]), "卷二整份重复，不该多出题来"

    good, errors, seen = parse_upload(open(out[0], "rb").read(), out[0], set(SCOPES))
    assert errors == [], f"导入解析器报错了：{errors}"
    assert len(good) == seen == 4
    assert {g["type"] for g in good} == {"选择题", "判断题", "填空题", "操作题"}
    assert all(g["scope"] in SCOPES for g in good)
    assert all(1 <= g["difficulty"] <= 5 for g in good)


def test_folder_without_docx_says_so(tmp_path, capsys):
    assert d2b.main([str(tmp_path)]) == 1
    assert "没找到" in capsys.readouterr().out


def test_unrecognised_paper_says_so(tmp_path, capsys):
    """自己排版的卷子（没有【答案】）认不出来，要明说，不能悄悄产出一个空表。"""
    src = tmp_path / "自排版"
    src.mkdir()
    make_docx(src / "卷.docx", ["班级：____ 姓名：____", "一、请回答下列问题", "谈谈你对信息技术的理解。"])
    assert d2b.main([str(src)]) == 1
    assert "一道题都没拆出来" in capsys.readouterr().out
