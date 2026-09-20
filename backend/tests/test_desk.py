"""桌面客户端：导出考试包 + 真机答卷交回来。

这条链路的要点是**桌面端不是另一套系统**：它交卷走的还是
/api/take/{token}/submit，和网页端交上来的形状一样，所以后端的判分、成绩页、
阅卷界面一行都不用改。这里就盯着这个契约。

最要紧的两条：
  · 考试包里不能有答案和检查点（test_package_has_no_answers）
  · 真机快照交上来要能判出分（test_desktop_submission_is_graded）
"""

import json
import io
import zipfile

import pytest

EXAM_ROOT = "C:/EXAM"


@pytest.fixture(scope="module")
def desk_exam(client, auth):
    """一场带 Windows 操作题的考试，和网页端发布的一模一样。"""
    task = client.post(
        "/api/sims",
        json={
            "kind": "win",
            "title": "桌面端用的文件操作",
            "env": {"fs": {f"{EXAM_ROOT}/win09": {"type": "dir"},
                           f"{EXAM_ROOT}/win09/素材": {"type": "dir"},
                           f"{EXAM_ROOT}/win09/素材/说明.txt": {
                               "type": "file", "content": "冬奥会"}},
                    "recycle": {}},
            "checks": [
                {"desc": "新建「作业」文件夹", "score": 5,
                 "assert": {"op": "exists", "path": f"{EXAM_ROOT}/win09/作业", "is": "dir"}},
                {"desc": "把「说明.txt」复制到「作业」里", "score": 5,
                 "assert": {"op": "exists", "path": f"{EXAM_ROOT}/win09/作业/说明.txt"}},
            ],
        },
        headers=auth,
    )
    assert task.status_code == 200, task.text
    task = task.json()

    q = client.post(
        "/api/questions",
        json={"type": "操作题", "stem": "在 win09 下新建「作业」文件夹，把「说明.txt」复制进去。",
              # 知识范围刻意不用「Windows系统操作」：那个必出题槽位被 test_sim
              # 占着，两边抢同一个槽，后跑的那个就进不了卷子。
              "answer": "略", "scope": "计算机网络基础", "sim_task_id": task["id"],
              "is_pinned": True, "options": []},
        headers=auth,
    ).json()

    paper = client.post(
        "/api/papers/generate",
        json={"title": "桌面端测验", "by_sections": True, "use_pinned": True, "save": True},
        headers=auth,
    ).json()
    picked = next((x for x in paper["questions"] if x["id"] == q["id"]), None)
    assert picked, "必出题没进卷子"

    # 卷子已经存档了，这里马上把「必出」摘掉。
    # **必出题是全局状态**：留着它，后面别的测试文件组卷时也会被塞进这道题，
    # 把人家"这场考试里没有仿真题"的断言搞挂 —— 实测撞过一次。
    client.put(f"/api/questions/{q['id']}", json={"is_pinned": False}, headers=auth)

    exam = client.post("/api/exams", json={"paper_id": paper["paper_id"], "show_score": True},
                       headers=auth).json()
    return {"exam": exam, "qid": q["id"], "score": picked.get("score") or 0}


def open_pkg(raw: bytes):
    z = zipfile.ZipFile(io.BytesIO(raw))
    return (json.loads(z.read("manifest.json")), json.loads(z.read("paper.json")),
            z.namelist(), z)


# ================================================================ 导出
def test_export_needs_login(client, desk_exam):
    assert client.get(f"/api/desk/export/{desk_exam['exam']['id']}").status_code == 401


def test_package_has_no_answers(client, auth, desk_exam):
    """**核心安全断言**：考试包要发到几十台学生机上，里面不能有答案。

    注意别把"题干里出现了目标文件夹名"当成泄露 —— 题目本来就要告诉学生
    去建「作业」文件夹。该挡的是**检查点结构**（answer / checks / assert）。
    """
    raw = client.get(f"/api/desk/export/{desk_exam['exam']['id']}", headers=auth).content
    manifest, paper, names, _ = open_pkg(raw)
    text = raw.decode("utf-8", "ignore")
    for bad in ('"answer"', '"checks"', '"assert"', '"op"', '"desc"'):
        assert bad not in text, f"考试包里出现了 {bad}，检查点漏出去了"
    for q in paper:
        assert set(q.keys()) <= {"id", "no", "type", "stem", "score", "section",
                                 "options", "sim"}
        assert set((q.get("sim") or {}).keys()) <= {"kind", "open", "manual"}


def test_package_carries_what_the_client_needs(client, auth, desk_exam):
    raw = client.get(f"/api/desk/export/{desk_exam['exam']['id']}", headers=auth).content
    manifest, paper, names, _ = open_pkg(raw)

    # 交卷要用的：服务器地址在包里可以为空（由 --server 指定），口令必须有
    assert manifest["token"] == desk_exam["exam"]["token"]
    assert manifest["logical_root"] == EXAM_ROOT, "快照前缀没带上，操作题会全判 0 分"
    assert manifest["count"] == len(paper) > 0

    # 初始文件要铺出来，**空文件夹也得在**
    assert "files/win09/素材/说明.txt" in names
    assert "files/win09/素材/" in names


def test_operation_question_tells_the_client_what_to_open(client, auth, desk_exam):
    raw = client.get(f"/api/desk/export/{desk_exam['exam']['id']}", headers=auth).content
    _, paper, _, _ = open_pkg(raw)
    op = next(q for q in paper if str(q["id"]) == str(desk_exam["qid"]))
    assert op["sim"]["kind"] == "win"
    assert op["sim"]["open"] == "win09"
    assert not op["sim"].get("manual")


def test_server_url_can_be_given_at_export_time(client, auth, desk_exam):
    raw = client.get(f"/api/desk/export/{desk_exam['exam']['id']}",
                     params={"server": "http://10.0.0.9:3315/"}, headers=auth).content
    manifest, _, _, _ = open_pkg(raw)
    assert manifest["server"] == "http://10.0.0.9:3315"


# ================================================================ 交卷
def desktop_answer(done: bool) -> str:
    """桌面客户端交上来的东西：整份真机快照，路径已经加好前缀。

    形状和网页版仿真器交的完全一致 —— 这正是后端不用改的原因。
    """
    fs = {f"{EXAM_ROOT}/win09": {"type": "dir"},
          f"{EXAM_ROOT}/win09/素材": {"type": "dir"},
          f"{EXAM_ROOT}/win09/素材/说明.txt": {"type": "file", "content": "冬奥会"}}
    if done:
        fs[f"{EXAM_ROOT}/win09/作业"] = {"type": "dir"}
        fs[f"{EXAM_ROOT}/win09/作业/说明.txt"] = {"type": "file", "content": "冬奥会"}
    return json.dumps({"state": {"fs": fs, "recycle": {}}}, ensure_ascii=False)


def test_desktop_submission_is_graded(client, auth, desk_exam):
    res = client.post(
        f"/api/take/{desk_exam['exam']['token']}/submit",
        json={"student_name": "桌面甲", "student_class": "九年级1班", "student_no": "26880101",
              "answers": {str(desk_exam["qid"]): desktop_answer(True)}},
    )
    assert res.status_code == 200, res.text
    assert res.json()["score"] == desk_exam["score"] > 0

    # 老师那边看得到，而且每个检查点过没过都在
    subs = client.get(f"/api/exams/{desk_exam['exam']['id']}/submissions", headers=auth).json()
    sub = next(s for s in subs if s["student_no"] == "26880101")
    detail = client.get(
        f"/api/exams/{desk_exam['exam']['id']}/submissions/{sub['id']}", headers=auth
    ).json()
    item = next(d for d in detail["detail"] if d["id"] == desk_exam["qid"])
    assert item["auto"] is True
    assert item["check_passed"] == item["check_total"] == 2


def test_half_done_desktop_submission_gets_part(client, desk_exam):
    res = client.post(
        f"/api/take/{desk_exam['exam']['token']}/submit",
        json={"student_name": "桌面乙", "student_class": "九年级1班", "student_no": "26880102",
              "answers": {str(desk_exam["qid"]): desktop_answer(False)}},
    )
    assert 0 <= res.json()["score"] < desk_exam["score"]


def test_missing_prefix_would_score_zero(client, desk_exam):
    """把前缀去掉（客户端忘了对齐路径），操作题就全判 0 —— 这条记着，
    出问题时第一个查它。"""
    bad = json.dumps({"state": {"fs": {"win09/作业": {"type": "dir"},
                                       "win09/作业/说明.txt": {"type": "file"}}, "recycle": {}}})
    res = client.post(
        f"/api/take/{desk_exam['exam']['token']}/submit",
        json={"student_name": "桌面丙", "student_class": "九年级1班", "student_no": "26880103",
              "answers": {str(desk_exam["qid"]): bad}},
    )
    assert res.json()["score"] == 0


def test_ping(client):
    assert client.get("/api/desk/ping").json()["ok"] is True
