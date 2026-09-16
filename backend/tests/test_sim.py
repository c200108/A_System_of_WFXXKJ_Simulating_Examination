"""仿真操作题：环境、检查点、判分，以及和考试的整条链路。

三条最要紧的：
  · **检查点不能出现在给学生的任何响应里** —— 检查点就是答案
    （test_checks_never_reach_the_student）
  · 判分只看终态，同一件事换条路径做也得分（test_same_result_other_path_still_scores）
  · 机器判出来的分只是预填，老师改了要以老师的为准（test_teacher_can_override）
"""

import json

import pytest

from app.services import sim
from app.services.exam import scale_sim


# ================================================================ 单元：win
WIN_ENV = {"fs": {"C:/EXAM": {"type": "dir"}, "C:/EXAM/会徽": {"type": "dir"}}, "recycle": {}}


def win_state(**paths):
    fs = dict(WIN_ENV["fs"])
    fs.update(paths)
    return {"fs": fs, "recycle": {}}


def test_win_exists_and_type():
    state = win_state(**{"C:/EXAM/会徽/冬梦.txt": {"type": "file", "content": ""}})
    ok, _ = sim._check_win({"op": "exists", "path": "C:/EXAM/会徽/冬梦.txt", "is": "file"}, state)
    assert ok
    ok, why = sim._check_win({"op": "exists", "path": "C:/EXAM/会徽/冬梦.txt", "is": "dir"}, state)
    assert not ok and "文件夹" in why, "建成了文件却要求文件夹，得说清楚"


def test_win_path_written_either_way_is_the_same_place():
    """老师写 C:\\EXAM\\会徽，学生点出来的是 C:/EXAM/会徽 —— 得当成同一个。"""
    state = win_state(**{"C:/EXAM/会徽/冬梦.txt": {"type": "file"}})
    ok, _ = sim._check_win({"op": "exists", "path": "c:\\EXAM\\会徽\\冬梦.txt"}, state)
    assert ok


def test_win_missing_and_recycle():
    state = {"fs": {"C:/EXAM": {"type": "dir"}},
             "recycle": {"C:/EXAM/旧的.txt": {"type": "file"}}}
    assert sim._check_win({"op": "missing", "path": "C:/EXAM/旧的.txt"}, state)[0]
    assert sim._check_win({"op": "in_recycle", "path": "C:/EXAM/旧的.txt"}, state)[0]


def test_win_content_and_attr():
    state = win_state(**{"C:/EXAM/a.txt": {"type": "file", "content": "北京冬奥会", "readonly": True}})
    assert sim._check_win({"op": "content", "path": "C:/EXAM/a.txt", "has": "冬奥"}, state)[0]
    assert not sim._check_win({"op": "content", "path": "C:/EXAM/a.txt", "has": "夏奥"}, state)[0]
    assert sim._check_win({"op": "attr", "path": "C:/EXAM/a.txt", "readonly": True}, state)[0]
    assert not sim._check_win({"op": "attr", "path": "C:/EXAM/a.txt", "readonly": False}, state)[0]


# ================================================================ 单元：wps
def para(text, **fmt):
    return {"text": text, **sim.blank_para(), **fmt}


WPS_STATE = {
    "paras": [
        para("00后，自我崛起的一代", font="楷体", size="二号", bold=True, align="center"),
        para("深圳男孩晏劭廷在演讲中带来了极大的震撼", indent=2, line={"type": "fixed", "value": 22}),
        para("不得不说，他们有更多的发展自由。"),
    ],
    "page": {"left": 2.5, "right": 2.5, "top": 2, "bottom": 2, "orient": "portrait"},
    "header": "春天", "footer": "", "columns": 2,
}


def test_wps_paragraph_format():
    ok, _ = sim._check_wps(
        {"op": "para", "at": 0, "font": "楷体", "size": "二号", "bold": True, "align": "center"},
        WPS_STATE,
    )
    assert ok
    ok, why = sim._check_wps({"op": "para", "at": 0, "align": "left"}, WPS_STATE)
    assert not ok and "居中" in why


def test_wps_size_written_as_number_or_name():
    """老师写「二号」还是写 22，判分得认同一个字号。"""
    assert sim._check_wps({"op": "para", "at": 0, "size": 22}, WPS_STATE)[0]
    assert sim.same_size("二号", 22) and not sim.same_size("二号", 16)


def test_wps_paragraph_found_by_its_text():
    """按内容找段落：学生在前面插了段落，段落序号会变，按序号判就冤枉人了。"""
    moved = {**WPS_STATE, "paras": [para("新插的一段")] + WPS_STATE["paras"]}
    ok, _ = sim._check_wps(
        {"op": "para", "at": {"has": "深圳男孩"}, "indent": 2,
         "line": {"type": "fixed", "value": 22}},
        moved,
    )
    assert ok


def test_wps_text_replace_and_page_and_header():
    assert sim._check_wps({"op": "text", "absent": "10后", "present": "00后"}, WPS_STATE)[0]
    assert sim._check_wps({"op": "page", "left": 2.5, "top": 2}, WPS_STATE)[0]
    assert not sim._check_wps({"op": "page", "left": 3.18}, WPS_STATE)[0]
    assert sim._check_wps({"op": "header", "equals": "春天"}, WPS_STATE)[0]
    assert sim._check_wps({"op": "columns", "equals": 2}, WPS_STATE)[0]


def test_wps_order_for_move_to_end():
    ok, _ = sim._check_wps({"op": "order", "last": "不得不说"}, WPS_STATE)
    assert ok


# ================================================================ 单元：html
HTML = """<html><head><title>我的主页</title></head>
<body><h1 class="t">欢迎</h1>
<a href="http://www.moe.gov.cn">教育部</a>
<img src="logo.png" alt="校徽">
<table border="1"><tr><td>一</td></tr></table>
</body></html>"""


def test_html_select_tag_and_attr():
    state = {"files": {"index.html": HTML}}
    assert sim._check_html({"op": "sel", "selector": "a[href]", "min": 1}, state)[0]
    assert sim._check_html({"op": "attr", "selector": "img", "name": "src", "equals": "logo.png"}, state)[0]
    assert sim._check_html({"op": "title", "equals": "我的主页"}, state)[0]
    assert sim._check_html({"op": "sel", "selector": "table[border]", "min": 1}, state)[0]
    assert not sim._check_html({"op": "sel", "selector": "marquee", "min": 1}, state)[0]


def test_html_descendant_and_class():
    state = {"files": {"index.html": HTML}}
    assert sim._check_html({"op": "sel", "selector": "body h1.t", "min": 1}, state)[0]
    assert sim._check_html({"op": "sel", "selector": "table td", "min": 1}, state)[0]


def test_html_formatting_does_not_matter():
    """缩进、引号单双、属性顺序都不该影响得分 —— 判的是解析出来的树。"""
    messy = {"files": {"index.html": "<BODY>\n   <A   HREF='logo.htm'\n  target='_blank'>走</A>"}}
    assert sim._check_html({"op": "sel", "selector": "a[href]", "min": 1}, messy)[0]


def test_html_unclosed_tags_still_parse():
    """学生忘了写 </p> 是常事，不该整道题判 0 分。"""
    state = {"files": {"index.html": "<body><p>一<p>二<img src=x.png>"}}
    assert sim._check_html({"op": "sel", "selector": "p", "min": 2}, state)[0]
    assert sim._check_html({"op": "sel", "selector": "img", "min": 1}, state)[0]


# ================================================================ 判分与折算
def test_partial_credit():
    checks = [
        {"desc": "建文件夹", "score": 3, "assert": {"op": "exists", "path": "C:/EXAM/新建"}},
        {"desc": "建文件", "score": 3, "assert": {"op": "exists", "path": "C:/EXAM/新建/a.txt"}},
    ]
    half = win_state(**{"C:/EXAM/新建": {"type": "dir"}})
    got = sim.run_checks("win", checks, half)
    assert got["score"] == 3 and got["full"] == 6
    assert [r["ok"] for r in got["results"]] == [True, False]


def test_a_broken_check_does_not_kill_the_question():
    """一条检查点写错了，只是这一条不得分，别的照常判。"""
    checks = [
        {"desc": "好的", "score": 2, "assert": {"op": "exists", "path": "C:/EXAM"}},
        {"desc": "坏的", "score": 2, "assert": {"op": "没有这种检查"}},
    ]
    got = sim.run_checks("win", checks, win_state())
    assert got["score"] == 2
    assert not got["results"][1]["ok"]


def test_score_is_scaled_to_the_paper():
    """检查点满分 8、卷面只给 7 分，得按比例折算，不能判出 8 分。"""
    assert scale_sim({"score": 8, "full": 8}, 7) == 7
    assert scale_sim({"score": 4, "full": 8}, 7) == 4      # 一半 → 3.5 → 四舍五入 4
    assert scale_sim({"score": 0, "full": 8}, 7) == 0
    assert scale_sim({"score": 8, "full": 0}, 7) == 0      # 没有检查点就不给分


def test_state_that_will_not_parse_scores_zero_instead_of_exploding():
    """学生交上来的东西坏了，这道题 0 分，但不能把整份卷子的判分带崩。"""
    assert sim.load_state("这不是 json") == {}
    # 学生交的是 {state, log}，判分只认里面的 state
    assert sim.load_state(json.dumps({"state": {"fs": {}}, "log": [1, 2]})) == {"fs": {}}
    assert sim.load_state(json.dumps({"fs": {}})) == {"fs": {}}   # 直接给终态也认
    assert sim.load_state(None) == {}
    assert sim.load_state("x" * (sim.MAX_STATE_BYTES + 10)) == {}
    got = sim.run_checks("win", [{"score": 3, "assert": {"op": "exists", "path": "C:/EXAM"}}], {})
    assert got["score"] == 0


# ================================================================ 出题辅助
def test_propose_then_run_gives_full_marks():
    """老师把题做一遍生成检查点，再拿同一份终态试判，应该是满分。

    这条其实是在测「出题台那个流程本身站不站得住」。
    """
    done = win_state(**{
        "C:/EXAM/会徽/冬梦.txt": {"type": "file", "content": "北京冬奥"},
        "C:/EXAM/作业": {"type": "dir"},
    })
    checks = sim.propose("win", WIN_ENV, done)
    assert checks, "做了改动就该生成得出检查点"
    got = sim.run_checks("win", checks, done)
    assert got["score"] == got["full"] > 0

    # 什么都不做应该是 0 分
    assert sim.run_checks("win", checks, WIN_ENV)["score"] == 0


def test_propose_wps_picks_up_format_changes():
    env = {"paras": [para("标题"), para("正文")], "page": {}, "header": "", "columns": 1}
    done = {
        "paras": [para("标题", font="楷体", size="二号", bold=True, align="center"), para("正文")],
        "page": {"left": 2.5}, "header": "春天", "columns": 2,
    }
    checks = sim.propose("wps", env, done)
    kinds = {c["assert"]["op"] for c in checks}
    assert {"para", "page", "header", "columns"} <= kinds
    assert sim.run_checks("wps", checks, done)["score"] > 0


def test_propose_html_notices_new_tags():
    env = {"files": {"index.html": "<html><head><title></title></head><body></body></html>"}}
    done = {"files": {"index.html": "<html><head><title>我的主页</title></head>"
                                    "<body><h1>你好</h1><a href='a.htm'>链接</a></body></html>"}}
    checks = sim.propose("html", env, done)
    assert sim.run_checks("html", checks, done)["score"] > 0
    assert any(c["assert"].get("op") == "title" for c in checks)


# ================================================================ 接口
@pytest.fixture(scope="module")
def task(client, auth):
    """一个现成的仿真任务：在「会徽」文件夹里新建 冬梦.txt。"""
    res = client.post(
        "/api/sims",
        json={
            "kind": "win",
            "title": "新建文本文件",
            "env": WIN_ENV,
            "checks": [
                {"desc": "在「会徽」里新建文本文件「冬梦.txt」", "score": 6,
                 "assert": {"op": "exists", "path": "C:/EXAM/会徽/冬梦.txt", "is": "file"}},
                {"desc": "文件里写上「北京冬奥」", "score": 4,
                 "assert": {"op": "content", "path": "C:/EXAM/会徽/冬梦.txt", "has": "北京冬奥"}},
            ],
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_sim_crud_needs_login(client, task):
    assert client.get("/api/sims").status_code == 401
    assert client.get(f"/api/sims/{task['id']}").status_code == 401
    assert client.post("/api/sims", json={"kind": "win"}).status_code == 401


def test_blank_env_gives_a_usable_start(client, auth):
    for kind in ("win", "wps", "html"):
        got = client.get("/api/sims/blank", params={"kind": kind}, headers=auth).json()
        assert got["kind"] == kind and got["env"]


def test_try_run_tells_the_teacher_where_it_failed(client, auth, task):
    done = win_state(**{"C:/EXAM/会徽/冬梦.txt": {"type": "file", "content": "北京冬奥"}})
    full = client.post(f"/api/sims/{task['id']}/try", json={"state": done}, headers=auth).json()
    assert full["score"] == full["full"] == 10

    empty = client.post(f"/api/sims/{task['id']}/try", json={"state": WIN_ENV}, headers=auth).json()
    assert empty["score"] == 0
    assert "找不到" in empty["results"][0]["why"]


def test_propose_endpoint(client, auth):
    done = win_state(**{"C:/EXAM/会徽/冬梦.txt": {"type": "file"}})
    res = client.post("/api/sims/propose",
                      json={"kind": "win", "env": WIN_ENV, "state": done}, headers=auth)
    assert res.status_code == 200
    assert res.json()["count"] >= 1


# ================================================================ 端到端
@pytest.fixture(scope="module")
def sim_exam(client, auth, task):
    """一道挂了仿真任务的操作题 → 组卷 → 发布考试。"""
    q = client.post(
        "/api/questions",
        json={
            "type": "操作题",
            "stem": "请打开本题工作目录，在「会徽」文件夹中新建文本文件「冬梦.txt」，并按黑板上给出的内容填写。",
            "answer": "略",
            "scope": "Windows系统操作",
            "difficulty": 4,
            "sim_task_id": task["id"],
            # 设成必出题，组卷时才保证抽得到它（不然一百多道操作题里随机抽）
            "is_pinned": True,
            "options": [],
        },
        headers=auth,
    )
    assert q.status_code == 200, q.text
    qid = q.json()["id"]
    assert q.json()["sim_task"]["kind"] == "win"

    # 必须按大题组卷：只有这种卷子才有每题分值，没有分值就谈不上给几分
    # （老式组卷 by_sections=False 不设分值，判分按正确率折百分制，仿真题也就无分可给）
    paper = client.post(
        "/api/papers/generate",
        json={"title": "仿真测验", "by_sections": True, "use_pinned": True, "save": True},
        headers=auth,
    ).json()
    picked = next((x for x in paper["questions"] if x["id"] == qid), None)
    assert picked, "必出题没进卷子，组卷那边的 use_pinned 可能坏了"

    exam = client.post("/api/exams", json={"paper_id": paper["paper_id"], "show_score": True},
                       headers=auth).json()
    return {"exam": exam, "qid": qid, "score": picked.get("score") or 0}


def test_checks_never_reach_the_student(client, sim_exam):
    """**核心安全断言**：检查点就是答案，一个字都不能发给学生。"""
    raw = client.get(f"/api/take/{sim_exam['exam']['token']}").text
    assert "checks" not in raw
    assert "sim_checks" not in raw
    assert "北京冬奥" not in raw, "检查点里的关键字也不能露出去"

    body = client.get(f"/api/take/{sim_exam['exam']['token']}").json()
    for g in body["groups"]:
        for q in g["items"]:
            assert set(q.keys()) <= {
                "id", "code", "type", "stem", "scope", "image_url", "score", "options", "sim"
            }
            if "sim" in q:
                # 学生要拿到初始环境（不然没法做），但只能拿到这些
                assert set(q["sim"].keys()) == {"id", "kind", "title", "env"}


def test_student_submission_is_graded_on_the_spot(client, auth, sim_exam):
    token = sim_exam["exam"]["token"]
    done = win_state(**{"C:/EXAM/会徽/冬梦.txt": {"type": "file", "content": "北京冬奥"}})
    answer = json.dumps({"state": done, "log": [{"op": "mkdir"}]}, ensure_ascii=False)

    res = client.post(
        f"/api/take/{token}/submit",
        json={"student_name": "甲同学", "student_class": "九年级1班", "student_no": "26990101",
              "answers": {str(sim_exam["qid"]): answer}},
    )
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["pending_manual"] == 0, "仿真题当场就判完了，不该还挂着待评阅"
    assert out["score"] == sim_exam["score"] > 0, "全做对就该拿满这道题的分"

    # 老师那边看得到每一问的结果
    subs = client.get(f"/api/exams/{sim_exam['exam']['id']}/submissions", headers=auth).json()
    sub = next(s for s in subs if s["student_no"] == "26990101")
    detail = client.get(
        f"/api/exams/{sim_exam['exam']['id']}/submissions/{sub['id']}", headers=auth
    ).json()
    item = next(d for d in detail["detail"] if d["id"] == sim_exam["qid"])
    assert item["auto"] is True
    assert item["check_passed"] == item["check_total"] == 2
    assert all(c["ok"] for c in item["checks"])


def test_same_result_other_path_still_scores(client, sim_exam):
    """判的是终态：先在别处建好再移过去，和直接在目标文件夹里建，一样得分。"""
    done = win_state(**{
        "C:/EXAM/会徽/冬梦.txt": {"type": "file", "content": "北京冬奥"},
        "C:/EXAM/草稿": {"type": "dir"},          # 中间步骤留下的东西，不影响
    })
    res = client.post(
        f"/api/take/{sim_exam['exam']['token']}/submit",
        json={"student_name": "乙同学", "student_class": "九年级1班", "student_no": "26990102",
              "answers": {str(sim_exam["qid"]): json.dumps({"state": done, "log": []})}},
    )
    assert res.json()["score"] == sim_exam["score"]


def test_half_done_gets_half(client, sim_exam):
    """建了文件但没写内容：只拿第一问的分。"""
    half = win_state(**{"C:/EXAM/会徽/冬梦.txt": {"type": "file", "content": ""}})
    res = client.post(
        f"/api/take/{sim_exam['exam']['token']}/submit",
        json={"student_name": "丙同学", "student_class": "九年级1班", "student_no": "26990103",
              "answers": {str(sim_exam["qid"]): json.dumps({"state": half, "log": []})}},
    )
    out = res.json()
    assert 0 < out["score"] < sim_exam["score"]


def test_nothing_done_scores_zero(client, sim_exam):
    res = client.post(
        f"/api/take/{sim_exam['exam']['token']}/submit",
        json={"student_name": "丁同学", "student_class": "九年级1班", "student_no": "26990104",
              "answers": {str(sim_exam["qid"]): ""}},
    )
    assert res.json()["score"] == 0


def test_teacher_can_override(client, auth, sim_exam):
    """机器判的只是预填。老师改了分，以老师的为准。"""
    subs = client.get(f"/api/exams/{sim_exam['exam']['id']}/submissions", headers=auth).json()
    sub = next(s for s in subs if s["student_no"] == "26990104")   # 原本 0 分
    res = client.patch(
        f"/api/exams/{sim_exam['exam']['id']}/submissions/{sub['id']}/manual",
        json={"scores": {str(sim_exam["qid"]): sim_exam["score"]}},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    after = client.get(f"/api/exams/{sim_exam['exam']['id']}/submissions", headers=auth).json()
    assert next(s for s in after if s["student_no"] == "26990104")["score"] == sim_exam["score"]


def test_deleting_a_task_leaves_the_question_alone(client, auth):
    """删仿真任务不该把题删了，只是退回人工评阅。"""
    task = client.post("/api/sims", json={"kind": "html", "title": "待删",
                                          "checks": [{"desc": "x", "score": 1,
                                                      "assert": {"op": "raw", "has": "<p"}}]},
                       headers=auth).json()
    q = client.post(
        "/api/questions",
        json={"type": "操作题", "stem": "临时题：写一个段落标签。", "answer": "略",
              "scope": "计算机网络基础", "sim_task_id": task["id"], "options": []},
        headers=auth,
    ).json()

    assert client.delete(f"/api/sims/{task['id']}", headers=auth).json()["detached"] == 1
    again = client.get(f"/api/questions/{q['id']}", headers=auth).json()
    assert again["sim_task_id"] is None, "题目还在，只是不挂仿真任务了"
