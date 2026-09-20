"""桌面客户端联网取卷：学生报考号 → 认人 → 拿到自己的考试 → 下载考试包。

这条链路存在的理由是**机房里只分发 exe**。名单和考试都现问现答，老师在网页上
改班级、加转学生、发新考试，考场那边不用重新导包。

盯三件事：
  · 不该考的人拿不到口令（`test_other_class_gets_nothing`）
  · 学生取下来的包里没有答案（`test_student_fetched_package_has_no_answers`）
  · 交过卷的考试会被标出来，别让学生白考一场才被 409 挡回来
"""

import io
import json
import zipfile

import pytest

ROOT = "C:/EXAM"


def _cid(client, auth, grade, name):
    for c in client.get("/api/classes", headers=auth).json():
        if c["grade"] == grade and c["name"] == name:
            return c["id"]
    return client.post("/api/classes", json={"grade": grade, "name": name},
                       headers=auth).json()["id"]


@pytest.fixture(scope="module")
def lab(client, auth):
    """一个班、两个学生、一场只发给这个班的考试。"""
    # 班名要挑**别的测试文件没用过的**：整套测试共用一个库，
    # test_batch_create 就断言了"八年级3班里只有它自己建的那三个人"。
    cid = _cid(client, auth, "八年级", "21班")
    for no, name in (("26083001", "桌面甲"), ("26083002", "桌面乙")):
        client.post("/api/students", json={"student_no": no, "name": name, "class_id": cid},
                    headers=auth)

    other = _cid(client, auth, "八年级", "22班")
    client.post("/api/students", json={"student_no": "26089901", "name": "外班丙",
                                       "class_id": other}, headers=auth)

    task = client.post("/api/sims", json={
        "kind": "win", "title": "机房联网取卷用",
        "env": {"fs": {f"{ROOT}/lab01": {"type": "dir"},
                       f"{ROOT}/lab01/素材": {"type": "dir"},
                       f"{ROOT}/lab01/素材/名单.txt": {"type": "file", "content": "冬奥会"}},
                "recycle": {}},
        "checks": [{"desc": "新建「上交」文件夹", "score": 6,
                    "assert": {"op": "exists", "path": f"{ROOT}/lab01/上交", "is": "dir"}}],
    }, headers=auth).json()

    q = client.post("/api/questions", json={
        "type": "操作题", "stem": "在 lab01 下新建「上交」文件夹。", "answer": "略",
        # 知识范围要挑**卷面结构里给操作题留了槽位**的那几个（见 config.yaml 的
        # sections），否则必出题没地方放，整个组卷会以「抽不到题目」失败。
        # 槽位是全局的，所以下面组完卷立刻把「必出」摘掉。
        "scope": "计算机网络基础", "sim_task_id": task["id"], "is_pinned": True, "options": [],
    }, headers=auth).json()

    paper = client.post("/api/papers/generate", json={
        "title": "机房桌面端测验", "by_sections": True, "use_pinned": True, "save": True},
        headers=auth)
    assert paper.status_code == 200, paper.text
    paper = paper.json()
    assert any(x["id"] == q["id"] for x in paper["questions"]), "必出题没进卷子"
    # 必出是全局状态，卷子存完立刻摘掉，否则别的测试组卷时也会被塞进这道题
    client.put(f"/api/questions/{q['id']}", json={"is_pinned": False}, headers=auth)

    # 目标班级是按**班级 id** 传的，不是班级名 —— 传错字段不会报错，
    # 只会变成"全校统考"，于是外班学生也能拿到口令。踩过一次。
    exam = client.post("/api/exams", json={"paper_id": paper["paper_id"],
                                           "target_class_ids": [cid]}, headers=auth).json()
    assert exam["target_classes"], "目标班级没存上，准入测试就是假的"

    yield {"exam": exam, "qid": q["id"], "cls": exam["target_classes"]}

    # 用完把题从共享题库里删掉。**整套测试共用一个库**，多一道操作题就会改变
    # 后面别的文件抽题的结果 —— 实测把 test_exam 的"这场考试要同时有客观题和
    # 操作题"顶掉过。往公共题库里加东西的，自己收拾干净。
    client.delete(f"/api/questions/{q['id']}", headers=auth)


def signin(client, no, name=""):
    return client.post("/api/desk/signin", json={"student_no": no, "name": name})


# ================================================================ 认人
def test_signin_returns_who_you_are(client, lab):
    got = signin(client, "26083001", "桌面甲")
    assert got.status_code == 200, got.text
    assert got.json()["student"] == {"no": "26083001", "name": "桌面甲", "cls": lab["cls"]}


def test_signin_finds_my_exam(client, lab):
    exams = signin(client, "26083001").json()["exams"]
    mine = next(e for e in exams if e["id"] == lab["exam"]["id"])
    assert mine["token"] == lab["exam"]["token"], "没给口令客户端就取不了卷"
    assert mine["can_take"] is True and mine["submitted"] is False
    assert mine["duration_min"] > 0


def test_unknown_student_no(client, lab):
    assert signin(client, "00000000").status_code == 404


def test_name_must_match(client, lab):
    """考号对、姓名不对：多半是输错了，也可能是替考。挡住并说清楚。"""
    got = signin(client, "26083001", "张冠李戴")
    assert got.status_code == 403
    assert "26083001" in got.json()["detail"]


def test_other_class_gets_nothing(client, lab):
    """**这条是准入**：考试只发给目标班级，外班学生连口令都看不到。"""
    exams = signin(client, "26089901", "外班丙").json()["exams"]
    assert all(e["id"] != lab["exam"]["id"] for e in exams)


def test_submitted_exam_is_flagged(client, lab):
    """交过卷又不许重考的，客户端要能灰掉 —— 不然学生白考一场才被 409 挡回来。"""
    client.post(f"/api/take/{lab['exam']['token']}/submit",
                json={"student_name": "桌面乙", "student_class": lab["cls"],
                      "student_no": "26083002", "answers": {}})
    mine = next(e for e in signin(client, "26083002").json()["exams"]
                if e["id"] == lab["exam"]["id"])
    assert mine["submitted"] is True and mine["can_take"] is False


# ================================================================ 取卷
def test_student_fetches_package_without_login(client, lab):
    res = client.get(f"/api/desk/exam/{lab['exam']['token']}")
    assert res.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(res.content))
    manifest = json.loads(z.read("manifest.json"))
    assert manifest["token"] == lab["exam"]["token"]
    assert manifest["logical_root"] == ROOT, "少了前缀，操作题会全班判 0 分"
    assert "files/lab01/素材/名单.txt" in z.namelist()
    assert "files/lab01/素材/" in z.namelist(), "空文件夹也得铺出去"


def test_student_fetched_package_has_no_answers(client, lab):
    """学生自己下的包和老师导的包是同一条生产线，答案一样不能有。

    别把"题干里出现了目标文件夹名"当泄露 —— 题目本来就要告诉学生去建「上交」。
    该挡的是检查点结构。
    """
    raw = client.get(f"/api/desk/exam/{lab['exam']['token']}").content
    text = raw.decode("utf-8", "ignore")
    for bad in ('"answer"', '"checks"', '"assert"', '"op"', '"desc"'):
        assert bad not in text, f"考试包里出现了 {bad}"


def test_bad_token(client):
    assert client.get("/api/desk/exam/根本不存在的口令").status_code == 404


def test_closed_exam_cannot_be_fetched(client, auth, lab):
    eid = lab["exam"]["id"]
    client.patch(f"/api/exams/{eid}", json={"is_open": False}, headers=auth)
    try:
        assert client.get(f"/api/desk/exam/{lab['exam']['token']}").status_code == 403
        assert all(e["id"] != eid for e in signin(client, "26083001").json()["exams"]), \
            "关掉的考试不该再出现在学生端列表里"
    finally:
        client.patch(f"/api/exams/{eid}", json={"is_open": True}, headers=auth)


def test_server_url_can_be_given_at_fetch_time(client, lab):
    """考场机器上 --server 顶不过来时，取卷这一步也能带地址。"""
    raw = client.get(f"/api/desk/exam/{lab['exam']['token']}",
                     params={"server": "http://10.0.0.9:3315/"}).content
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(raw)).read("manifest.json"))
    assert manifest["server"] == "http://10.0.0.9:3315"
