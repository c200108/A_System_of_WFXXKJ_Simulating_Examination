"""核心逻辑测试：跑 `pytest` 即可。

覆盖两块最容易改错的地方——Excel 校验归一化、均衡抽题名额分配。
改抽题策略或导入规则时，先看这里的断言还过不过。
"""

import random
from types import SimpleNamespace

from app.services.importer import (
    build_template,
    norm_answer,
    norm_type,
    parse_upload,
    parse_options,
    stem_hash,
)
from app.services.paper import right_letter, shuffle_options
from app.services.sampler import allocate, pick

SCOPES = [
    "信息基础与信息技术",
    "计算机硬件",
    "计算机软件",
    "Windows系统操作",
    "WPS文字操作",
    "信息安全与网络道德",
    "计算机网络基础",
    "Python编程基础",
    "人工智能",
    "物联网",
]


def q(qid, scope, qtype="选择题", pinned=False):
    return SimpleNamespace(id=qid, type=qtype, scope=scope, is_pinned=pinned)


# ---------- 导入校验 ----------
def test_norm_type():
    assert norm_type("单项选择") == "选择题"
    assert norm_type("判断") == "判断题"
    assert norm_type("上机操作题") == "操作题"
    assert norm_type("简答") == ""


def test_norm_answer_judge():
    for raw in ("√", "对", "T", "true", "正确"):
        assert norm_answer(raw, "判断题") == "正确"
    for raw in ("×", "x", "错", "F", "false", "错误"):
        assert norm_answer(raw, "判断题") == "错误"
    # 选择题答案原样保留
    assert norm_answer(" B ", "选择题") == "B"


def test_parse_options():
    got = parse_options("A.Alt+Tab\nB.Ctrl+C\nC．Alt+F4\nD、Win+D", "选择题")
    assert got == [("A", "Alt+Tab"), ("B", "Ctrl+C"), ("C", "Alt+F4"), ("D", "Win+D")]
    # 没写字母时按顺序补 A/B/C/D
    assert parse_options("红\n绿\n蓝", "选择题") == [("A", "红"), ("B", "绿"), ("C", "蓝")]
    # 判断题不用填选项
    assert parse_options("", "判断题") == [("A", "正确"), ("B", "错误")]
    # 最多四个
    assert len(parse_options("\n".join("abcdef"), "选择题")) == 4


def test_stem_hash_ignores_whitespace():
    assert stem_hash("下列说法正确的是()。") == stem_hash(" 下列说法 正确的是()。\n")
    assert stem_hash("甲") != stem_hash("乙")


# ---------- 均衡抽题 ----------
def test_allocate_is_balanced():
    pool = [q(i, SCOPES[i % 10]) for i in range(100)]  # 每个范围 10 题
    quota = allocate(pool, 20, SCOPES)
    assert sum(quota.values()) == 20
    assert set(quota.values()) == {2}  # 十个范围各 2 题


def test_allocate_gives_quota_away_when_pool_is_small():
    # 「物联网」只有 1 题，多出来的名额要让给别人
    pool = [q(i, "人工智能") for i in range(10)] + [q(99, "物联网")]
    quota = allocate(pool, 6, SCOPES)
    assert quota["物联网"] == 1
    assert quota["人工智能"] == 5
    assert sum(quota.values()) == 6


def test_pick_never_exceeds_pool():
    pool = [q(i, SCOPES[i % 10]) for i in range(30)]
    got = pick(pool, 9999, SCOPES, random.Random(1))
    assert len(got) == 30
    assert len({x.id for x in got}) == 30  # 不重复


def test_pinned_questions_always_included():
    pool = [q(i, SCOPES[i % 10], pinned=(i < 3)) for i in range(50)]
    got = pick(pool, 10, SCOPES, random.Random(2), use_pinned=True)
    assert {0, 1, 2} <= {x.id for x in got}
    assert len(got) == 10


def test_same_seed_same_paper():
    pool = [q(i, SCOPES[i % 10]) for i in range(80)]
    a = [x.id for x in pick(pool, 20, SCOPES, random.Random("2026期末"))]
    b = [x.id for x in pick(pool, 20, SCOPES, random.Random("2026期末"))]
    assert a == b


def test_empty_pool():
    assert pick([], 10, SCOPES, random.Random()) == []
    assert allocate([], 10, SCOPES) == {}


# ---------- 打乱选项，答案跟着走 ----------
def test_shuffle_keeps_answer_pointing_at_the_same_content():
    opts = [("A", "甲"), ("B", "乙"), ("C", "丙"), ("D", "丁")]
    for seed in range(30):
        new_opts, new_ans = shuffle_options(opts, "C", random.Random(seed))
        # 标签始终是 A/B/C/D 顺序，只有内容换了位置
        assert [lb for lb, _ in new_opts] == ["A", "B", "C", "D"]
        # 新答案指向的内容，必须还是原来那个「丙」
        content = dict(new_opts)[new_ans]
        assert content == "丙", (seed, new_opts, new_ans)
        assert sorted(c for _, c in new_opts) == ["丁", "丙", "乙", "甲"]


def test_shuffle_actually_changes_order_sometimes():
    opts = [("A", "甲"), ("B", "乙"), ("C", "丙"), ("D", "丁")]
    seen = {shuffle_options(opts, "A", random.Random(s))[1] for s in range(40)}
    assert len(seen) > 1  # 不是每次都落在同一个位置


def test_shuffle_skips_when_answer_is_not_a_single_letter():
    opts = [("A", "甲"), ("B", "乙")]
    # 判断题、多选、空答案都不动
    assert shuffle_options(opts, "正确", random.Random(1)) == (opts, "正确")
    assert shuffle_options(opts, "AB", random.Random(1)) == (opts, "AB")
    assert shuffle_options(opts, "", random.Random(1)) == (opts, "")
    assert shuffle_options([("A", "甲")], "A", random.Random(1)) == ([("A", "甲")], "A")


def test_right_letter_maps_judge_answers():
    assert right_letter({"type": "判断题", "answer": "正确"}) == "A"
    assert right_letter({"type": "判断题", "answer": "错误"}) == "B"
    assert right_letter({"type": "选择题", "answer": "C"}) == "C"


# ---------- CSV 导入 ----------
def test_csv_import_follows_the_same_rules():
    csv_text = (
        "题型,题干,可选项,答案,知识范围,图片\n"
        '选择题,下列属于输入设备的是（ ）。,"A.鼠标\nB.显示器",A,计算机硬件,\n'
        "判断题,U 盘属于外存储器。,,正确,计算机硬件,\n"
        "简答题,这个题型不认识,,略,计算机硬件,\n"
    )
    good, errors, rows = parse_upload(csv_text.encode("utf-8"), "x.csv", set(SCOPES))
    assert rows == 3
    assert len(good) == 2
    assert good[1]["answer"] == "正确"
    assert good[1]["options"] == [("A", "正确"), ("B", "错误")]
    assert len(errors) == 1 and "题型" in errors[0]["reason"]


def test_csv_accepts_gbk():
    """WPS / Excel 存出来的 CSV 多半是 GBK。"""
    csv_text = "题型,题干,可选项,答案,知识范围,图片\n判断题,计算机病毒会自我复制。,,正确,信息安全与网络道德,\n"
    good, _, _ = parse_upload(csv_text.encode("gbk"), "x.csv", set(SCOPES))
    assert len(good) == 1
    assert good[0]["stem"] == "计算机病毒会自我复制。"


# ---------- 工作表识别 ----------
def test_our_own_template_parses_without_errors():
    """自带模板里的「对照表」没有题干列，不能被当成失败行。"""
    data = build_template(SCOPES, ["选择题", "判断题", "操作题", "填空题"])
    good, errors, rows = parse_upload(data, "x.xlsx", set(SCOPES))
    assert len(good) == 3
    assert rows == 3
    assert errors == []


def test_workbook_with_no_question_sheet_reports_error():
    """整本都没有题目表时，要明确告诉用户表头不对。"""
    import io

    from openpyxl import Workbook

    wb = Workbook()
    wb.active.title = "使用说明"
    wb.active.append(["这里没有题干列"])
    buf = io.BytesIO()
    wb.save(buf)

    good, errors, _ = parse_upload(buf.getvalue(), "x.xlsx", set(SCOPES))
    assert good == []
    assert len(errors) == 1
    assert "表头" in errors[0]["reason"]
