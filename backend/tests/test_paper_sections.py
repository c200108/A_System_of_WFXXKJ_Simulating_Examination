"""按卷面结构组卷、难度、分值分摊、主观题人工赋分。

这个文件保护 2.4.0 的三条承诺：
1. 六个大题按配置的顺序出，一道题不会在同一张卷子上出现两次；
2. 每个大题的分**精确**等于配置值，且同一大题里操作题的分最高；
3. 学生交卷先拿客观题得分，老师批完操作题总分自动补上。
"""

import itertools

import pytest

from app.services.blueprint import allocate_scores
from app.services.difficulty import estimate

_made: list[int] = []
_seq = itertools.count(1)


@pytest.fixture(scope="module", autouse=True)
def _cleanup(client, auth):
    """跑完把本模块建的题清掉，不给后面的模块留垃圾（题库统计是全局的）。"""
    yield
    for qid in _made:
        client.delete(f"/api/questions/{qid}", headers=auth)


def _add(client, auth, qtype, scope, stem, *, answer=None, difficulty=None, image=None):
    body = {
        "type": qtype,
        "stem": f"{stem}（用例 {next(_seq)}）",
        "scope": scope,
        "answer": answer if answer is not None else ("A" if qtype == "选择题" else "正确"),
    }
    if qtype == "选择题":
        body["options"] = [
            {"label": "A", "content": "甲"},
            {"label": "B", "content": "乙"},
            {"label": "C", "content": "丙"},
            {"label": "D", "content": "丁"},
        ]
    if qtype == "操作题":
        body["answer"] = answer if answer is not None else "操作要点：略"
    if difficulty:
        body["difficulty"] = difficulty
    if image:
        body["image_url"] = image

    res = client.post("/api/questions", json=body, headers=auth)
    assert res.status_code == 200, res.text
    qid = res.json()["id"]
    _made.append(qid)
    return qid


@pytest.fixture(scope="module")
def stocked(client, auth):
    """把六个大题都能抽满的题备齐。数量按 config.yaml 的默认结构来。"""
    for i in range(34):
        _add(client, auth, "选择题", "计算机硬件", f"通用选择题{i}")
    for i in range(12):
        _add(client, auth, "判断题", "计算机软件", f"通用判断题{i}")
    for scope in ("Windows系统操作", "WPS文字操作", "人工智能"):
        for i in range(2):
            _add(client, auth, "操作题", scope, f"{scope}操作{i}")
    # 算法：长题干和短题干各备一些，用来验 prefer: long_or_image
    for i in range(4):
        _add(client, auth, "选择题", "Python编程基础", "短题" + str(i))
    for i in range(4):
        _add(client, auth, "选择题", "Python编程基础", "长" * 80 + str(i))
    for i in range(5):
        _add(client, auth, "选择题", "计算机网络基础", "网络长题" + "网" * 80 + str(i))
    for i in range(5):
        _add(client, auth, "操作题", "计算机网络基础", f"网络操作{i}")
    for i in range(4):
        _add(client, auth, "操作题", "物联网", f"物联网操作{i}")
    for i in range(5):
        _add(client, auth, "选择题", "物联网", f"物联网选择{i}")
    return True


def _generate(client, auth, **extra):
    res = client.post(
        "/api/papers/generate",
        json={"title": "卷面结构测试", **extra},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    return res.json()


# ---------- 分值分摊（纯函数，不碰数据库） ----------
def test_scores_add_up_exactly():
    """除不尽是常态，但每个大题的分必须精确等于配置值，否则卷面总分对不上。"""
    for total in (10, 13, 20, 30, 7):
        for n in (1, 3, 4, 6, 7, 10):
            items = [{"type": "选择题", "difficulty": (i % 5) + 1} for i in range(n)]
            got = allocate_scores(items, total)
            assert sum(got) == total, (total, n, got)


def test_every_question_is_worth_at_least_one_point():
    items = [{"type": "选择题", "difficulty": 1} for _ in range(6)]
    assert min(allocate_scores(items, 10)) >= 1


def test_operation_question_always_scores_highest():
    """用户定的第一原则：同一个大题里操作题的分最高。"""
    items = [
        {"type": "选择题", "difficulty": 5},
        {"type": "选择题", "difficulty": 5},
        {"type": "选择题", "difficulty": 5},
        {"type": "操作题", "difficulty": 1},   # 难度最低的操作题也要压过选择题
        {"type": "操作题", "difficulty": 1},
        {"type": "操作题", "difficulty": 1},
    ]
    got = allocate_scores(items, 10)
    assert sum(got) == 10
    assert min(got[3:]) > max(got[:3]), got


def test_harder_questions_get_more_points():
    items = [
        {"type": "选择题", "difficulty": 1},
        {"type": "选择题", "difficulty": 3},
        {"type": "选择题", "difficulty": 5},
    ]
    got = allocate_scores(items, 12)
    assert got[0] <= got[1] <= got[2] and got[0] < got[2], got


def test_equal_split_ignores_difficulty():
    """选择题大题 30 题 30 分，就该一题一分，不按难度拉开。"""
    items = [{"type": "选择题", "difficulty": (i % 5) + 1} for i in range(30)]
    assert allocate_scores(items, 30, by_difficulty=False) == [1] * 30


def test_judge_section_is_two_points_each():
    items = [{"type": "判断题", "difficulty": 2} for _ in range(10)]
    assert allocate_scores(items, 20, by_difficulty=False) == [2] * 10


# ---------- 难度估算 ----------
def test_difficulty_is_between_one_and_five():
    for qtype in ("选择题", "判断题", "操作题", "填空题", "没见过的题型"):
        for stem in ("", "短", "长" * 300):
            assert 1 <= estimate(qtype, stem, "物联网") <= 5


def test_operation_is_harder_than_judgement():
    same = ("一样长的题干" * 3, "计算机硬件")
    assert estimate("操作题", *same) > estimate("判断题", *same)


# ---------- 按卷面结构组卷 ----------
def test_six_sections_in_order(client, auth, stocked):
    body = _generate(client, auth)
    names = [g["name"] for g in body["groups"]]
    assert names == [
        "选择题", "判断题", "操作题", "算法与程序设计", "互联网原理与创新", "物联网实践与探索"
    ], body["warnings"]
    assert body["by_sections"] is True


def test_full_score_is_one_hundred(client, auth, stocked):
    body = _generate(client, auth)
    assert body["full_score"] == 100
    assert sum(q["score"] for q in body["questions"]) == 100
    assert [g["score"] for g in body["groups"]] == [30, 20, 20, 10, 10, 10]


def test_no_question_appears_twice(client, auth, stocked):
    ids = [q["id"] for q in _generate(client, auth)["questions"]]
    assert len(ids) == len(set(ids))


def test_operation_section_keeps_the_fixed_scope_order(client, auth, stocked):
    """第三大题三道题的顺序钉死：Windows → WPS 文字 → 人工智能。"""
    body = _generate(client, auth)
    ops = next(g for g in body["groups"] if g["name"] == "操作题")
    assert [q["scope"] for q in ops["items"]] == [
        "Windows系统操作", "WPS文字操作", "人工智能"
    ]


def test_scope_limited_sections_are_not_starved(client, auth, stocked):
    """不限范围的「选择题」大题先抽 30 道，不能把物联网的选择题抽光。

    限定了知识范围的 slot 先抽，就是为了防这件事。
    """
    body = _generate(client, auth)
    iot = next(g for g in body["groups"] if g["name"] == "物联网实践与探索")
    assert len([q for q in iot["items"] if q["type"] == "选择题"]) == 3
    assert all(q["scope"] == "物联网" for q in iot["items"])


def test_long_or_image_preference(client, auth, stocked):
    """「算法与程序设计」要长题干或带图的选择题，库里够就不该抽到短的。"""
    body = _generate(client, auth, seed="prefer-check")
    algo = next(g for g in body["groups"] if g["name"] == "算法与程序设计")
    assert len(algo["items"]) == 3
    for q in algo["items"]:
        assert len(q["stem"]) >= 60 or q["image_url"], q["stem"][:30]


def test_mixed_section_gives_operation_more_points(client, auth, stocked):
    """第五大题里既有选择题又有操作题，操作题必须分最高。"""
    body = _generate(client, auth)
    net = next(g for g in body["groups"] if g["name"] == "互联网原理与创新")
    ops = [q["score"] for q in net["items"] if q["type"] == "操作题"]
    picks = [q["score"] for q in net["items"] if q["type"] == "选择题"]
    assert ops and picks
    assert min(ops) > max(picks), net["items"]


def test_section_counts_can_be_overridden(client, auth, stocked):
    body = _generate(client, auth, section_counts={"选择题/0": 5, "判断题/0": 2})
    choice = next(g for g in body["groups"] if g["name"] == "选择题")
    judge = next(g for g in body["groups"] if g["name"] == "判断题")
    assert len(choice["items"]) == 5 and len(judge["items"]) == 2
    # 题少了分不变：这个大题还是 30 分，只是摊到 5 道题上
    assert choice["score"] == 30


def test_section_scores_can_be_overridden(client, auth, stocked):
    body = _generate(client, auth, section_scores={"选择题": 40, "判断题": 10})
    by_name = {g["name"]: g["score"] for g in body["groups"]}
    assert by_name["选择题"] == 40 and by_name["判断题"] == 10
    assert body["full_score"] == 100


def test_preview_reports_shortfall(client, auth, stocked):
    res = client.post(
        "/api/papers/preview-plan",
        json={"section_counts": {"操作题/0": 99}},
        headers=auth,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["full_score"] == 100
    assert any("Windows" in s for s in body["shortfall"]), body["shortfall"]


def test_saved_section_paper_reopens_with_scores(client, auth, stocked):
    made = _generate(client, auth, save=True)
    again = client.get(f"/api/papers/{made['paper_id']}", headers=auth).json()
    assert again["full_score"] == 100
    assert [g["name"] for g in again["groups"]] == [g["name"] for g in made["groups"]]
    assert {q["id"]: q["score"] for q in again["questions"]} == {
        q["id"]: q["score"] for q in made["questions"]
    }


# ---------- 判分：客观题当场算，主观题等老师 ----------
@pytest.fixture(scope="module")
def scored_exam(client, auth, stocked):
    paper = _generate(client, auth, save=True)
    res = client.post(
        "/api/exams",
        json={"paper_id": paper["paper_id"], "title": "赋分测验", "show_score": True},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    return {"exam": res.json(), "paper": paper}


def test_student_sees_per_question_score_but_no_answer(client, scored_exam):
    body = client.get(f"/api/take/{scored_exam['exam']['token']}").json()
    assert body["full_score"] == 100
    assert '"answer"' not in client.get(f"/api/take/{scored_exam['exam']['token']}").text
    for g in body["groups"]:
        for q in g["items"]:
            assert q["score"] >= 1


def test_submit_reports_objective_first(client, scored_exam):
    """交卷当场只能拿客观题的分，操作题那一段要等老师。"""
    paper = scored_exam["paper"]
    answers = {}
    for q in paper["questions"]:
        if q["type"] == "判断题":
            answers[str(q["id"])] = "A" if q["answer"] == "正确" else "B"
        elif q["type"] == "选择题":
            answers[str(q["id"])] = q["answer"]
        else:
            answers[str(q["id"])] = "我的操作步骤"

    res = client.post(
        f"/api/take/{scored_exam['exam']['token']}/submit",
        json={"student_name": "满分同学", "student_no": "SEC0001", "answers": answers},
    )
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["objective_total"] + body["subjective_total"] == 100
    assert body["objective_score"] == body["objective_total"]  # 客观题全对
    assert body["score"] == body["objective_score"]            # 主观题还没批
    assert body["subjective_total"] > 0
    assert body["pending_manual"] > 0
    assert "操作题" in body["message"] and "评阅" in body["message"]


def test_teacher_grades_and_total_updates(client, auth, scored_exam):
    eid = scored_exam["exam"]["id"]
    subs = client.get(f"/api/exams/{eid}/submissions", headers=auth).json()
    mine = next(s for s in subs if s["student_no"] == "SEC0001")
    assert mine["pending_manual"] > 0
    assert mine["full_score"] == 100
    before = mine["score"]

    detail = client.get(f"/api/exams/{eid}/submissions/{mine['id']}", headers=auth).json()
    manual = [d for d in detail["detail"] if d["manual"]]
    assert manual, "这份卷子应该有要人工评阅的题"

    # 每道主观题都给满分，总分就该是 100
    res = client.patch(
        f"/api/exams/{eid}/submissions/{mine['id']}/manual",
        json={"scores": {str(d["id"]): d["score"] for d in manual}},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["pending_manual"] == 0
    assert body["subjective_score"] == sum(d["score"] for d in manual)
    assert body["score"] == 100 > before

    again = client.get(f"/api/exams/{eid}/submissions", headers=auth).json()
    assert next(s for s in again if s["student_no"] == "SEC0001")["score"] == 100


def test_manual_score_cannot_exceed_the_question(client, auth, scored_exam):
    """老师手滑多打一位，也不能让总分冒出卷面。"""
    eid = scored_exam["exam"]["id"]
    subs = client.get(f"/api/exams/{eid}/submissions", headers=auth).json()
    mine = next(s for s in subs if s["student_no"] == "SEC0001")
    detail = client.get(f"/api/exams/{eid}/submissions/{mine['id']}", headers=auth).json()
    manual = [d for d in detail["detail"] if d["manual"]]

    body = client.patch(
        f"/api/exams/{eid}/submissions/{mine['id']}/manual",
        json={"scores": {str(d["id"]): 999 for d in manual}},
        headers=auth,
    ).json()
    assert body["subjective_score"] == sum(d["score"] for d in manual)
    assert body["score"] <= 100

    # 负分按 0 算
    body = client.patch(
        f"/api/exams/{eid}/submissions/{mine['id']}/manual",
        json={"scores": {str(d["id"]): -5 for d in manual}},
        headers=auth,
    ).json()
    assert body["subjective_score"] == 0


def test_exam_list_shows_how_many_are_unmarked(client, auth, scored_exam):
    eid = scored_exam["exam"]["id"]
    client.post(
        f"/api/take/{scored_exam['exam']['token']}/submit",
        json={"student_name": "没批的同学", "student_no": "SEC0002", "answers": {}},
    )
    row = next(e for e in client.get("/api/exams", headers=auth).json() if e["id"] == eid)
    assert row["full_score"] == 100
    assert row["ungraded_count"] >= 1


def test_old_papers_still_use_percentage(client, auth, stocked):
    """2.4.0 之前组的卷子没有分值，判分要退回按正确率折百分制，历史成绩不能变。"""
    paper = _generate(client, auth, by_sections=False, counts={"选择题": 2}, save=True)
    assert paper["full_score"] == 0
    exam = client.post(
        "/api/exams", json={"paper_id": paper["paper_id"], "title": "老式卷子"}, headers=auth
    ).json()

    answers = {str(q["id"]): q["answer"] for q in paper["questions"]}
    body = client.post(
        f"/api/take/{exam['token']}/submit",
        json={"student_name": "老卷同学", "student_no": "OLD001", "answers": answers},
    ).json()
    assert body["score"] == 100
    assert body["pending_manual"] == 0

    subs = client.get(f"/api/exams/{exam['id']}/submissions", headers=auth).json()
    mine = next(s for s in subs if s["student_no"] == "OLD001")
    assert mine["full_score"] == 100 and mine["subjective_total"] == 0

    # 老卷子没有可评阅的题，调赋分接口要说清楚为什么
    res = client.patch(
        f"/api/exams/{exam['id']}/submissions/{mine['id']}/manual",
        json={"scores": {}},
        headers=auth,
    )
    assert res.status_code == 400
    assert "人工评阅" in res.json()["detail"]


# ---------- 题库的难度列 ----------
def test_new_question_gets_an_estimated_difficulty(client, auth):
    qid = _add(client, auth, "操作题", "物联网", "没填难度的操作题")
    got = client.get(f"/api/questions/{qid}", headers=auth).json()
    assert 1 <= got["difficulty"] <= 5
    assert got["difficulty"] >= 4, "操作题 + 物联网，估出来不该是简单题"


def test_difficulty_can_be_set_and_filtered(client, auth):
    qid = _add(client, auth, "选择题", "计算机硬件", "指定难度的题", difficulty=5)
    assert client.get(f"/api/questions/{qid}", headers=auth).json()["difficulty"] == 5

    listed = client.get("/api/questions", params={"difficulty": 5}, headers=auth).json()
    assert qid in [q["id"] for q in listed["items"]] or listed["total"] > 0
    assert all(q["difficulty"] == 5 for q in listed["items"])

    client.put(f"/api/questions/{qid}", json={"difficulty": 2}, headers=auth)
    assert client.get(f"/api/questions/{qid}", headers=auth).json()["difficulty"] == 2


def test_difficulty_out_of_range_is_refused(client, auth):
    res = client.post(
        "/api/questions",
        json={"type": "判断题", "stem": "难度填 9 的题", "scope": "物联网",
              "answer": "正确", "difficulty": 9},
        headers=auth,
    )
    assert res.status_code == 422


def test_stats_report_difficulty_spread(client, auth):
    stats = client.get("/api/questions/stats", headers=auth).json()
    assert stats["by_difficulty"]
    assert sum(stats["by_difficulty"].values()) == stats["total"]


def test_difficulty_does_not_collapse_to_one_level():
    """一批题型、范围、长度都不同的题，估出来不能全是同一个难度。

    这是 2.4.3 服务器上真出过的问题：灌库脚本建题时没传难度，331 道题
    全吃了模型默认值 3，"按难度分摊分值"就等于没生效 —— 每道题分数一样。
    盯住"有区分度"这条，比盯某道题该是几分更有意义。
    """
    sample = [
        ("判断题", "计算机由硬件和软件组成。", "信息基础与信息技术"),
        ("判断题", "所有网站都可以随意转载他人作品。", "信息安全与网络道德"),
        ("选择题", "下列哪个是操作系统？", "计算机软件"),
        ("选择题", "在 Windows 中切换窗口的快捷键是（ ）。", "Windows系统操作"),
        ("选择题", "阅读下面这段较长的情境材料" + "并回答问题。" * 12, "Python编程基础"),
        ("操作题", "把文档另存为 PDF。", "WPS文字操作"),
        ("操作题", "配置一台路由器，" + "使两个网段互通。" * 12, "计算机网络基础"),
    ]
    levels = {estimate(t, stem, scope) for t, stem, scope in sample}
    assert len(levels) >= 3, f"难度没有区分度，估出来只有 {sorted(levels)}"
    assert min(levels) < 3 < max(levels), f"难度全挤在中间：{sorted(levels)}"


# ---------- 启动时自动补难度的判定规则 ----------
def test_auto_backfill_only_fires_on_a_uniform_bank():
    """--auto 动不动手，只看"全库是不是同一个难度"。

    这条规则是刻意选的：老师完全可能特意把某道题标成 3。要是每次启动都把
    "难度是 3"的题重估一遍，人工判断就被悄悄覆盖了。而"全库一个难度"不可能
    是人标出来的，只可能是灌库时没评过 —— 那时候重估才是纯收益。
    """
    from tools.fix_difficulty import uniform_level

    # 全库一个值 → 认定没评过，要动手
    assert uniform_level([3, 3, 3, 3]) == 3
    assert uniform_level([1, 1]) == 1
    # 有区分度 → 评过了，不碰
    assert uniform_level([1, 2, 3, 4, 5]) is None
    assert uniform_level([3, 3, 3, 4]) is None, "只要有一道不一样就该收手"
    # 空库 / 单题不在判定范围内，交给调用方挡掉
    assert uniform_level([]) is None
