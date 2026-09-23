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
              # 也不能用「计算机网络基础」：那个槽位现在只收拖拽题（见
              # config.yaml 的 sim_kinds），这道 win 题进不去，组卷会空。
              "answer": "略", "scope": "物联网", "sim_task_id": task["id"],
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


@pytest.fixture(scope="module")
def web_exam(client, auth):
    """一场带网页题的考试。网页题的文件要单独进「网页」文件夹。"""
    task = client.post("/api/sims", json={
        "kind": "html", "title": "网页题",
        "env": {"files": {"index.html": "<html><title></title><body></body></html>",
                          "style.css": "/* 样式 */"}},
        "checks": [{"desc": "网页标题改成「校园网」", "score": 5,
                    "assert": {"op": "title", "equals": "校园网"}}],
    }, headers=auth).json()
    q = client.post("/api/questions", json={
        "type": "操作题", "stem": "把网页标题修改为“校园网”。", "answer": "略",
        "scope": "物联网", "sim_task_id": task["id"], "is_pinned": True, "options": [],
    }, headers=auth).json()
    paper = client.post("/api/papers/generate", json={
        "title": "网页题测验", "by_sections": True, "use_pinned": True, "save": True},
        headers=auth).json()
    client.put(f"/api/questions/{q['id']}", json={"is_pinned": False}, headers=auth)
    exam = client.post("/api/exams", json={"paper_id": paper["paper_id"]},
                       headers=auth).json()
    return {"exam": exam, "qid": q["id"]}


def test_web_question_gets_its_own_folder(client, auth, web_exam):
    """网页题的文件铺在「网页」文件夹里，「打开」按钮打开的也是这个文件夹。

    早先是直接铺在考试文件夹根上，两个毛病：学生点开要在一堆别的题的素材里
    翻 index.html；一张卷子上两道网页题时，后一道的 index.html 会把前一道盖掉，
    交上去的源码是同一份，必有一道判错。
    """
    raw = client.get(f"/api/desk/export/{web_exam['exam']['id']}", headers=auth).content
    _, paper, names, _ = open_pkg(raw)
    op = next(q for q in paper if str(q["id"]) == str(web_exam["qid"]))
    assert op["sim"]["kind"] == "html"
    assert op["sim"]["open"] == "网页"
    assert "files/网页/index.html" in names
    assert "files/网页/style.css" in names
    # 根目录上不该再有这两个文件
    assert "files/index.html" not in names


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


# ================================================================ 全卷共用一个前缀
# 一张卷子上有好几道 win 题时，它们的初始文件全铺在**同一个**考试文件夹里，
# 学生交上来的也是这一个文件夹的快照。所以"铺文件时剥掉的那一段"和
# "判分时拼回去的那一段"（logical_root）必须是同一个，而且全卷只能有一个。
#
# 两道题的工作目录算出来不一定一样：环境里带不带"自己那层文件夹"这个节点，
# 算出来就差一层（_common_root 是按父目录取公共前缀的）。原来的写法是
# 每道题各剥各的、前缀取第一道题的 —— 除第一道之外全判 0 分。
def _env_with_own_dir_node():
    """环境里带自己那层文件夹 → 工作目录算出来是 C:/EXAM"""
    return {"fs": {f"{EXAM_ROOT}/win21": {"type": "dir"},
                   f"{EXAM_ROOT}/win21/说明.txt": {"type": "file", "content": "甲"}},
            "recycle": {}}


def _env_without_own_dir_node():
    """环境里只有文件夹**里面**的东西 → 工作目录算出来深一层，是 C:/EXAM/win22"""
    return {"fs": {f"{EXAM_ROOT}/win22/素材.txt": {"type": "file", "content": "乙"},
                   f"{EXAM_ROOT}/win22/成品": {"type": "dir"}},
            "recycle": {}}


def test_两道win题的工作目录算出来本来就可能不一样():
    """先把前提钉住：不是我编的，真会差一层。"""
    from app.routers.desk import _root_of

    assert _root_of("win", _env_with_own_dir_node()) == EXAM_ROOT
    assert _root_of("win", _env_without_own_dir_node()) == f"{EXAM_ROOT}/win22"


def test_全卷共用一个前缀_加回去要能还原绝对路径():
    """**这条是整件事的要害**：把 logical_root 拼回相对路径，要一字不差地
    还原成环境里那条绝对路径 —— 检查点比的就是它。差一层就是"找不到文件"，
    那道题判 0 分，而两边日志都正常。"""
    from app.routers.desk import _common_dir, _files_of, _root_of

    envs = [_env_with_own_dir_node(), _env_without_own_dir_node()]
    root = _common_dir(_root_of("win", e) for e in envs)
    assert root == EXAM_ROOT, "两道题的公共目录应该是考试文件夹本身"

    for env in envs:
        rels = _files_of("win", env, root=root)
        assert rels, "这道题一个文件都没铺出来"
        for rel in rels:
            assert f"{root}/{rel}" in env["fs"], (
                f"{rel} 加回前缀后是 {root}/{rel}，环境里没这条路径 —— 这道题会判 0 分"
            )


def test_一道题算不出目录不连累同卷别的题():
    from app.routers.desk import _common_dir, _root_of

    broken = {"fs": {"C:": {"type": "dir"}}}          # 只有光杆盘符，算不出目录
    roots = [_root_of("win", e) for e in (_env_with_own_dir_node(), broken)]
    assert _common_dir(r for r in roots if r) == EXAM_ROOT


def test_工具脚本不传前缀时还是按这道题自己算():
    """backend/tools 下的两个脚本一次只处理一道题，走的是这条老路，别改坏了。"""
    from app.routers.desk import _files_of

    rels = _files_of("win", _env_without_own_dir_node())
    assert set(rels) == {"素材.txt", "成品"}


def test_两道win题一起发包_前缀对得上(client, auth):
    """真发一次包：两道工作目录不一样的 win 题在同一张卷子上。

    组卷是随机抽的，凑不出"这两道题一定同卷"，所以这里直接拼一份存档试卷 ——
    要测的是打包这一步，不是抽题。
    """
    import zipfile as _zip

    from app.database import SessionLocal
    from app.models import Exam, Paper, PaperItem, Question, SimTask
    from app.routers.desk import build_package

    db = SessionLocal()
    try:
        qids = []
        for env, title in ((_env_with_own_dir_node(), "甲题"),
                           (_env_without_own_dir_node(), "乙题")):
            root = f"{EXAM_ROOT}/win21" if title == "甲题" else f"{EXAM_ROOT}/win22"
            task = SimTask(kind="win", title=title,
                           env_json=json.dumps(env, ensure_ascii=False),
                           checks_json=json.dumps(
                               [{"desc": "新建「作业」", "score": 5,
                                 "assert": {"op": "exists", "path": f"{root}/作业",
                                            "is": "dir"}}], ensure_ascii=False))
            db.add(task)
            db.flush()
            q = Question(type="操作题", stem=f"{title}：新建「作业」文件夹。",
                         stem_hash=f"desk-root-{title}", answer="", scope="物联网",
                         sim_task_id=task.id)
            db.add(q)
            db.flush()
            qids.append(q.id)

        paper = Paper(title="两道win题", school="昌邑市实验中学", duration="40")
        for i, qid in enumerate(qids):
            paper.items.append(PaperItem(question_id=qid, order_no=i,
                                         section="操作题", score=10))
        db.add(paper)
        db.flush()
        exam = Exam(paper_id=paper.id, title=paper.title, token=f"desk-root-{paper.id}")
        db.add(exam)
        db.commit()

        raw = build_package(db, exam)
    finally:
        db.close()

    z = _zip.ZipFile(io.BytesIO(raw))
    manifest = json.loads(z.read("manifest.json"))
    names = [n[len("files/"):] for n in z.namelist() if n.startswith("files/")]

    assert manifest["logical_root"] == EXAM_ROOT
    # 两道题的东西各在各的文件夹里，谁也没被剥掉一层
    assert "win21/说明.txt" in names
    assert "win22/素材.txt" in names
    for rel in names:
        rel = rel.rstrip("/")
        assert f"{EXAM_ROOT}/{rel}" in (_env_with_own_dir_node()["fs"]
                                        | _env_without_own_dir_node()["fs"]), \
            f"{rel} 加回前缀后对不上任何一道题的环境"


# ================================================================ 拖拽题进考试包
def test_拖拽题的图进包_答案和仿真地址不进包(client, auth):
    """桌面端要自己画图，所以结构图、热区、素材卡片要进包；检查点（答案）不能进。
    IP 查询题的仿真地址也不能进 —— 那是网页端仿真命令行用的，桌面端查真机，
    留在包里等于把一个"对"的答案放在学生机的硬盘上。"""
    import zipfile as _zip

    from app.database import SessionLocal
    from app.models import Exam, Paper, PaperItem, Question
    from app.routers.desk import build_package
    from tests.test_drag import REAL_STEMS

    db = SessionLocal()
    try:
        paper = Paper(title="拖拽题进包", school="昌邑市实验中学", duration="40")
        for i, key in enumerate(("Q322-话费", "Q310-本机IP")):
            q = Question(type="操作题", stem=REAL_STEMS[key], stem_hash=f"desk-drag-{key}",
                         answer="", scope="计算机网络基础", image_url="/uploads/images/旧图.jpg")
            db.add(q)
            db.flush()
            paper.items.append(PaperItem(question_id=q.id, order_no=i, section="操作题", score=10))
        db.add(paper)
        db.flush()
        exam = Exam(paper_id=paper.id, title=paper.title, token=f"desk-drag-{paper.id}")
        db.add(exam)
        db.commit()
        raw = build_package(db, exam)
    finally:
        db.close()

    z = _zip.ZipFile(io.BytesIO(raw))
    rows = json.loads(z.read("paper.json"))
    flow, ip = rows
    assert flow["sim"]["kind"] == "drag" and not flow["sim"]["manual"]
    assert flow["sim"]["env"]["slots"] and flow["sim"]["env"]["items"], "图没进包，桌面端画不出来"
    assert "image" not in flow, "旧考试系统的截图不再发"
    assert ip["sim"]["env"]["mode"] == "ip"
    assert "sim_ip" not in ip["sim"]["env"], "仿真地址进了包，学生解压就能抄"
    text = raw.decode("utf-8", "ignore") + json.dumps(rows, ensure_ascii=False)
    for bad in ('"op"', '"assert"', '"checks"', "192.168.1.108"):
        assert bad not in text, f"考试包里出现了 {bad}"
