# -*- coding: utf-8 -*-
"""三类操作题在同一场考试里，交卷后全部自动判分。

这是这条链路的验收：一场考试里同时有

    Windows 系统操作   学生在真的资源管理器里新建/复制/删除 → 判文件夹快照
    WPS 文字（格式）   学生用真 WPS 改文档格式并保存        → 判段落格式
    AI 工具使用        学生把题目要求描述给对话框并提交      → 判提问内容

**三类的终态形状各不相同**，交错了就全判 0 分，而且两边日志都正常 —— 踩过：
HTML 题交文件夹快照上去，判分器拿不到 `files`，整道题判 0。所以这里一道一道
盯住"判出来的分对不对、说的原因对不对"。

AI 工具题还有一条特别的：**老师不用出检查点**，服务器按题干现算。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import sim
from client import api, package, snapshot, states
from conftest import EXAM_ROOT, call, teacher_token

WIN_DIR = f"{EXAM_ROOT}/lab三类"


@pytest.fixture(scope="session")
def exam3(server, exam):
    """老师出三道操作题，一道一类，发成一场考试。

    依赖 `exam`：班级和学生名单是它建的，这里接着用同一个班。
    """
    tk = teacher_token(server)
    cid = next(c["id"] for c in call(server, "GET", "/api/classes", token=tk)
               if c["grade"] == "九年级" and c["name"] == "1班")

    win = call(server, "POST", "/api/sims", {
        "kind": "win", "title": "三类·文件操作",
        "env": {"fs": {WIN_DIR: {"type": "dir"},
                       f"{WIN_DIR}/素材": {"type": "dir"},
                       f"{WIN_DIR}/素材/说明.txt": {"type": "file", "content": "冬奥会"}},
                "recycle": {}},
        "checks": [{"desc": "新建「上交」文件夹", "score": 5,
                    "assert": {"op": "exists", "path": f"{WIN_DIR}/上交", "is": "dir"}},
                   {"desc": "把「说明.txt」复制到「上交」", "score": 5,
                    "assert": {"op": "exists", "path": f"{WIN_DIR}/上交/说明.txt"}}],
    }, tk)

    wps = call(server, "POST", "/api/sims", {
        "kind": "wps", "title": "三类·文字排版",
        "env": {"name": "职业教育大有可为.wps", "paras": [
            {**sim.blank_para(), "text": "让青春在不懈奋斗中绽放绚丽之花"},
            {**sim.blank_para(), "text": "qingchun由磨砺而出彩，人生因奋斗而升华。"},
        ]},
        "checks": [
            {"desc": "标题设为黑体、二号、居中", "score": 4,
             "assert": {"op": "para", "at": {"has": "绽放绚丽之花"},
                        "font": "黑体", "size": "二号", "align": "center"}},
            {"desc": "把「qingchun」替换成「青春」", "score": 3,
             "assert": {"op": "text", "absent": "qingchun", "present": "青春由磨砺"}},
            {"desc": "在文章最后加一段新文字", "score": 3,
             "assert": {"op": "order", "last": "让中华民族伟大复兴梦想成真"}},
        ],
    }, tk)

    ai = call(server, "POST", "/api/sims", {
        "kind": "ai", "title": "三类·AI 工具",
        "env": {}, "checks": [],          # **故意不出检查点**：服务器按题干现算
    }, tk)

    made = {}
    for scope, task, stem in (
        ("Windows系统操作", win, f"打开 lab三类：①新建「上交」文件夹；②把「素材」里的"
                                 "「说明.txt」复制到「上交」。"),
        ("WPS文字操作", wps, "打开「职业教育大有可为.docx」：①将标题设为黑体、二号、"
                             "居中对齐；②把正文里的「qingchun」全部替换为「青春」；"
                             "③在文章最后输入一段新的文字："
                             "「让中华民族伟大复兴梦想成真。」"),
        ("人工智能", ai, "请使用给定的AI工具完成以下操作：①请对「树树皆秋色，山山唯落晖。」"
                         "这句诗，生成一段鉴赏文本。②请为「青州古城」，生成一幅宣传画。"),
    ):
        q = call(server, "POST", "/api/questions", {
            "type": "操作题", "stem": stem, "answer": "略", "scope": scope,
            "sim_task_id": task["id"], "is_pinned": True, "options": []}, tk)
        made[scope] = q

    paper = call(server, "POST", "/api/papers/generate", {
        "title": "三类操作题测验", "by_sections": True, "use_pinned": True,
        "save": True}, tk)
    picked = {scope: next((x for x in paper["questions"] if x["id"] == q["id"]), None)
              for scope, q in made.items()}
    for scope, got in picked.items():
        assert got, f"{scope} 的必出题没进卷子"
    for q in made.values():                    # 必出是全局的，组完卷立刻摘掉
        call(server, "PUT", f"/api/questions/{q['id']}", {"is_pinned": False}, tk)

    ex = call(server, "POST", "/api/exams",
              {"paper_id": paper["paper_id"], "target_class_ids": [cid],
               "show_score": True}, tk)
    yield {"token": tk, "exam": ex,
           "qid": {k: v["id"] for k, v in made.items()},
           "score": {k: (v.get("score") or 0) for k, v in picked.items()}}

    for q in made.values():                    # 别把共享题库越堆越大
        call(server, "DELETE", f"/api/questions/{q['id']}", token=tk)


def sit(server, exam3, lab, no, name, work):
    """一个考生从取卷做到交卷。work(root, chats) 是他做的事。"""
    pack = package.ExamPackage(api.fetch_exam(server, exam3["exam"]["token"],
                                              lab["out"] / "卷.ekb"))
    snapshot.clear_root(lab["root"], force=True)
    snapshot.mark_root(lab["root"])
    pack.deploy_files(lab["root"])

    chats: dict = {}
    work(lab["root"], chats, pack)
    got = states.collect(pack.paper, lab["root"], pack.logical_root, chats)
    student = {"no": no, "name": name, "cls": "九年级1班"}
    ok, msg, _ = api.submit(server, pack.token, student,
                            states.payload({}, got))
    assert ok, msg
    return pack


def marked(server, exam3, no) -> dict:
    """老师阅卷页上看到的那一份：{知识范围: 这道题的判分明细}。"""
    eid = exam3["exam"]["id"]
    subs = call(server, "GET", f"/api/exams/{eid}/submissions", token=exam3["token"])
    sub = next(s for s in subs if s["student_no"] == no)
    detail = call(server, "GET", f"/api/exams/{eid}/submissions/{sub['id']}",
                  token=exam3["token"])
    by_id = {d["id"]: d for d in detail["detail"]}
    return {scope: by_id[qid] for scope, qid in exam3["qid"].items()}


def do_everything(root: Path, chats: dict, pack):
    """一个全做对的考生。"""
    # ① Windows：真的新建文件夹、真的复制文件
    import shutil
    (root / "lab三类" / "上交").mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "lab三类" / "素材" / "说明.txt",
                 root / "lab三类" / "上交" / "说明.txt")

    # ② WPS：改标题格式、替换文字、在最后加一段。真 WPS 存盘的效果等价于重写文档
    from app.services import docx_io
    doc = next(q for q in pack.paper if (q.get("sim") or {}).get("kind") == "wps")
    target = root / doc["sim"]["open"]
    target.write_bytes(docx_io.build_docx({"paras": [
        {**sim.blank_para(), "text": "让青春在不懈奋斗中绽放绚丽之花",
         "font": "黑体", "size": "二号", "align": "center"},
        {**sim.blank_para(), "text": "青春由磨砺而出彩，人生因奋斗而升华。"},
        {**sim.blank_para(), "text": "让中华民族伟大复兴梦想成真。"},
    ]}))

    # ③ AI：把题目要求描述给对话框
    q = next(x for x in pack.paper if (x.get("sim") or {}).get("kind") == "ai")
    chats[str(q["id"])] = [
        {"role": "user", "text": "请对「树树皆秋色，山山唯落晖。」这句诗生成一段鉴赏文本，"
                                 "再为「青州古城」生成一幅宣传画。"},
        {"role": "ai", "text": "好的，我来帮你完成。"},
    ]


# ================================================================ 出包
def test_wps_question_ships_a_real_docx(server, exam3, lab):
    """WPS 题得真铺一个 .docx 出去 —— 仿真环境里那是一串段落，不是文件。"""
    pack = package.ExamPackage(api.fetch_exam(server, exam3["exam"]["token"],
                                              lab["out"] / "卷.ekb"))
    snapshot.clear_root(lab["root"], force=True)
    snapshot.mark_root(lab["root"])
    pack.deploy_files(lab["root"])

    doc = next(q for q in pack.paper if (q.get("sim") or {}).get("kind") == "wps")
    target = lab["root"] / doc["sim"]["open"]
    assert target.suffix == ".docx", "得是 .docx —— .wps 是金山私有格式，我们写的是 OOXML"
    assert target.exists(), "文档没铺出来，学生打开就是空的"
    from client import docx
    assert docx.read_docx(target)["paras"], "铺出去的文档读不回来"


def test_all_three_kinds_are_auto_graded(server, exam3, lab):
    """**核心断言**：三类都不是"人工评阅"，包里也没漏答案。"""
    pack = package.ExamPackage(api.fetch_exam(server, exam3["exam"]["token"],
                                              lab["out"] / "卷.ekb"))
    kinds = {q["sim"]["kind"] for q in pack.paper if q.get("sim")}
    assert {"win", "wps", "ai"} <= kinds
    for q in pack.paper:
        sim_ = q.get("sim") or {}
        if sim_.get("kind") in ("win", "wps", "ai"):
            assert not sim_.get("manual"), f"{sim_['kind']} 还挂着人工评阅"

    raw = (lab["out"] / "卷.ekb").read_bytes().decode("utf-8", "ignore")
    for bad in ('"answer"', '"checks"', '"assert"'):
        assert bad not in raw, f"考试包里出现了 {bad}"


# ================================================================ 全做对
def test_a_perfect_run_scores_full_on_all_three(server, exam3, lab):
    sit(server, exam3, lab, "26090118", "机房18", do_everything)
    got = marked(server, exam3, "26090118")
    for scope, item in got.items():
        assert item["auto"] is True, f"{scope} 没走自动判分"
        assert item["check_passed"] == item["check_total"], \
            (scope, [c for c in item["checks"] if not c["ok"]])
        assert item["earned"] == exam3["score"][scope], scope


def test_ai_question_needs_no_teacher_checkpoints(server, exam3, lab):
    """AI 工具题老师什么都没填，检查点是服务器按题干现算的。"""
    got = marked(server, exam3, "26090118")["人工智能"]
    assert got["check_total"] >= 2, "题干应该现算出至少两条检查点"
    assert any("提交" in c["desc"] for c in got["checks"])


# ================================================================ 做错 / 没做完
def test_each_kind_says_what_went_wrong(server, exam3, lab):
    """没做到的要**逐条指出是哪一步** —— 老师阅卷页和学生的申诉都靠这个。"""
    def sloppy(root: Path, chats: dict, pack):
        (root / "lab三类" / "上交").mkdir(parents=True, exist_ok=True)   # 只做了①
        from app.services import docx_io
        doc = next(q for q in pack.paper if (q.get("sim") or {}).get("kind") == "wps")
        (root / doc["sim"]["open"]).write_bytes(docx_io.build_docx({"paras": [
            {**sim.blank_para(), "text": "让青春在不懈奋斗中绽放绚丽之花"},   # 格式没改
            {**sim.blank_para(), "text": "qingchun由磨砺而出彩。"},          # 没替换
        ]}))
        q = next(x for x in pack.paper if (x.get("sim") or {}).get("kind") == "ai")
        chats[str(q["id"])] = [{"role": "user", "text": "你好"}]            # 太敷衍

    sit(server, exam3, lab, "26090119", "机房19", sloppy)
    got = marked(server, exam3, "26090119")

    win = got["Windows系统操作"]
    assert win["check_passed"] == 1 and "说明.txt" in _first_bad(win)

    wps = got["WPS文字操作"]
    assert wps["check_passed"] == 0
    assert "黑体" in _first_bad(wps), wps["checks"]

    ai = got["人工智能"]
    assert ai["check_passed"] < ai["check_total"]
    assert any("覆盖" in c["why"] or "太短" in c["why"]
               for c in ai["checks"] if not c["ok"]), ai["checks"]


def _first_bad(item: dict) -> str:
    return next(c["why"] for c in item["checks"] if not c["ok"])


def test_doing_nothing_scores_zero_but_does_not_crash(server, exam3, lab):
    sit(server, exam3, lab, "26090120", "机房20", lambda root, chats, pack: None)
    got = marked(server, exam3, "26090120")
    for scope, item in got.items():
        assert item["earned"] == 0, scope
        assert item["checks"], f"{scope} 一条检查点都没跑，等于没判"
