"""学生平台与学生账号管理。

最要紧的两条：
1. 学生令牌绝不能调通任何教师接口（反过来也一样）；
2. 学生那边永远拿不到答案。
其余是账号管理的日常操作。
"""

import pytest


@pytest.fixture(scope="module")
def exam(client, auth):
    """本模块自己造题、自己发考试，单独跑这个文件也能过。"""
    # 不依赖别的测试模块先把题导进去 —— 那样单跑本文件会因为题库空而失败
    for i in range(6):
        client.post(
            "/api/questions",
            json={
                "type": "选择题" if i < 4 else "判断题",
                "stem": f"学生平台测验用题 {i}：下面哪个说法正确？",
                "answer": "A" if i < 4 else "对",
                "scope": "信息基础与信息技术",
                "options": (
                    [{"label": "A", "content": "甲"}, {"label": "B", "content": "乙"}]
                    if i < 4
                    else []
                ),
            },
            headers=auth,
        )

    res = client.post(
        "/api/papers/generate",
        json={"title": "学生平台测验", "counts": {"选择题": 3, "判断题": 2}, "save": True},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    paper = res.json()
    assert paper["paper_id"], "组卷要先存档才能发布考试"

    res = client.post(
        "/api/exams",
        json={"paper_id": paper["paper_id"], "show_score": True},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    return res.json()


def _class_id(client, auth, grade="七年级", name="1班"):
    """拿一个班的 id，没有就建。班级现在是一张表，学生从下拉里选。"""
    for c in client.get("/api/classes", headers=auth).json():
        if c["grade"] == grade and c["name"] == name:
            return c["id"]
    res = client.post("/api/classes", json={"grade": grade, "name": name}, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()["id"]


def _mk_student(client, auth, no="20260101", name="张三", grade="七年级", cls="1班"):
    res = client.post(
        "/api/students",
        json={
            "student_no": no,
            "name": name,
            "class_id": _class_id(client, auth, grade, cls),
        },
        headers=auth,
    )
    assert res.status_code == 200, res.text
    return res.json()


def _slogin(client, no, pwd):
    return client.post("/api/student/login", params={"student_no": no, "password": pwd})


def _stoken(client, auth, no="20260101", grade="七年级", cls="1班"):
    _mk_student(client, auth, no=no, grade=grade, cls=cls)
    res = _slogin(client, no, no)  # 初始密码就是学号
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


# ---------- 账号管理 ----------
def test_create_and_login_with_initial_password(client, auth):
    _mk_student(client, auth, no="20260001", name="李四")
    res = _slogin(client, "20260001", "20260001")
    assert res.status_code == 200
    body = res.json()
    assert body["student"]["name"] == "李四"
    assert "password" not in str(body).lower() or "password_hash" not in str(body)


def test_duplicate_student_no_rejected(client, auth):
    _mk_student(client, auth, no="20260002")
    res = client.post(
        "/api/students",
        json={"student_no": "20260002", "name": "重名", "class_id": _class_id(client, auth)},
        headers=auth,
    )
    assert res.status_code == 400
    assert "已经有账号" in res.json()["detail"]


@pytest.mark.parametrize(
    "no, expect",
    [("", "不能为空"), ("学号一号", "字母"), ("has space", "字母")],
)
def test_bad_student_no_explains_why(client, auth, no, expect):
    res = client.post(
        "/api/students", json={"student_no": no, "name": "某某"}, headers=auth
    )
    assert res.status_code == 400
    assert expect in res.json()["detail"]


def test_batch_create(client, auth):
    text = "20260011 王五\n20260012 赵六\n\n20260013  钱 七\nbadline\n"
    res = client.post(
        "/api/students/batch",
        json={"class_id": _class_id(client, auth, "八年级", "3班"), "text": text},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["added"] == 3
    assert body["error_count"] == 1  # badline 只有一段
    # 姓名里的空格要保住
    rows = client.get("/api/students", params={"student_class": "八年级3班"}, headers=auth).json()
    assert {r["name"] for r in rows} == {"王五", "赵六", "钱 七"}


def test_batch_skips_existing(client, auth):
    _mk_student(client, auth, no="20260021")
    res = client.post(
        "/api/students/batch",
        json={"student_class": "八(1)班", "text": "20260021 已存在\n20260022 新的"},
        headers=auth,
    )
    assert res.json() == {"added": 1, "skipped": 1, "errors": [], "error_count": 0}


def test_bulk_reset_password(client, auth):
    s = _mk_student(client, auth, no="20260031")
    client.patch(f"/api/students/{s['id']}", json={"password": "changed-it"}, headers=auth)
    assert _slogin(client, "20260031", "changed-it").status_code == 200

    client.post(
        "/api/students/bulk", json={"ids": [s["id"]], "action": "reset_password"}, headers=auth
    )
    assert _slogin(client, "20260031", "20260031").status_code == 200


def test_bulk_delete_keeps_their_results(client, auth, exam):
    """删学生账号不能连带删掉成绩 —— 那是班级资料。"""
    from app.database import SessionLocal
    from app.models import ExamSubmission

    hdr = _stoken(client, auth, no="20260041")
    client.post(f"/api/student/exams/{exam['id']}/submit", json={"answers": {}}, headers=hdr)

    sid = client.get("/api/student/me", headers=hdr).json()["id"]
    client.post("/api/students/bulk", json={"ids": [sid], "action": "delete"}, headers=auth)

    db = SessionLocal()
    try:
        subs = db.query(ExamSubmission).filter(ExamSubmission.student_no == "20260041").all()
        assert len(subs) == 1, "成绩跟着账号一起没了"
        assert subs[0].student_id is None, "外键该被置空"
        assert subs[0].student_name == "张三", "姓名班级要留档"
    finally:
        db.close()


# ---------- 两种身份互不串门 ----------
def test_student_token_cannot_reach_teacher_apis(client, auth, exam):
    hdr = _stoken(client, auth, no="20260051")
    for method, url in [
        ("get", "/api/auth/me"),
        ("get", "/api/auth/users"),
        ("get", "/api/questions"),
        ("get", "/api/exams"),
        ("get", "/api/students"),
        ("get", f"/api/exams/{exam['id']}/submissions"),
        ("get", "/api/typing/records"),
    ]:
        res = getattr(client, method)(url, headers=hdr)
        assert res.status_code == 401, f"{url} 竟然放学生进去了（{res.status_code}）"


def test_teacher_token_cannot_reach_student_apis(client, auth):
    for url in ["/api/student/me", "/api/student/exams", "/api/student/home"]:
        assert client.get(url, headers=auth).status_code == 401, f"{url} 放教师令牌进去了"


def test_disabled_student_cannot_login(client, auth):
    s = _mk_student(client, auth, no="20260061")
    client.post("/api/students/bulk", json={"ids": [s["id"]], "action": "disable"}, headers=auth)
    res = _slogin(client, "20260061", "20260061")
    assert res.status_code == 403
    assert "停用" in res.json()["detail"]


# ---------- 考试 ----------
def test_student_paper_has_no_answers(client, auth, exam):
    """和公开答题页同一条底线：发给学生的卷子里不能出现答案。"""
    hdr = _stoken(client, auth, no="20260071")
    res = client.get(f"/api/student/exams/{exam['id']}/paper", headers=hdr)
    assert res.status_code == 200, res.text

    raw = res.text
    assert '"answer"' not in raw, "卷子里出现了 answer 字段"
    for g in res.json()["groups"]:
        for item in g["items"]:
            assert "answer" not in item


def test_exam_targeting_by_class(client, auth, exam):
    """老师指定了班级，别的班就不该在列表里看到这场考试。

    这里另发一场只给九(9)班的考试，**不动模块共用的那场** ——
    改共用对象再还原，一旦中途断言失败就还原不回去，后面的用例全被带崩。
    """
    paper_id = client.post(
        "/api/papers/generate",
        json={"title": "只给九九班的卷子", "counts": {"选择题": 2}, "save": True},
        headers=auth,
    ).json()["paper_id"]
    targeted = client.post(
        "/api/exams",
        json={"paper_id": paper_id, "target_class_ids": [_class_id(client, auth, "九年级", "9班")]},
        headers=auth,
    ).json()

    def sees(hdr):
        return {e["id"] for e in client.get("/api/student/exams", headers=hdr).json()}

    outsider = _stoken(client, auth, no="20260081", grade="七年级", cls="1班")
    assert targeted["id"] not in sees(outsider), "别班的学生不该看到这场考试"
    # 连取卷都进不去，不只是列表里看不到
    assert (
        client.get(f"/api/student/exams/{targeted['id']}/paper", headers=outsider).status_code
        == 404
    )

    insider = _stoken(client, auth, no="20260082", grade="九年级", cls="9班")
    assert targeted["id"] in sees(insider), "本班学生该看得到"
    assert client.get(f"/api/student/exams/{targeted['id']}/paper", headers=insider).status_code == 200


def test_submit_records_identity_from_account(client, auth, exam):
    """姓名班级学号从账号来，学生改不了，成绩不会张冠李戴。"""
    hdr = _stoken(client, auth, no="20260091", grade="七年级", cls="5班")
    res = client.post(
        f"/api/student/exams/{exam['id']}/submit",
        json={"answers": {}, "student_name": "我改成别人"},  # 多塞的字段应被忽略
        headers=hdr,
    )
    assert res.status_code == 200, res.text

    rows = client.get(f"/api/exams/{exam['id']}/submissions", headers=auth).json()
    mine = [r for r in rows if r["student_no"] == "20260091"]
    assert len(mine) == 1
    assert mine[0]["student_name"] == "张三"
    assert mine[0]["student_class"] == "七年级5班"


def test_cannot_submit_twice(client, auth, exam):
    hdr = _stoken(client, auth, no="20260101")
    first = client.post(f"/api/student/exams/{exam['id']}/submit", json={"answers": {}}, headers=hdr)
    assert first.status_code == 200
    again = client.post(f"/api/student/exams/{exam['id']}/submit", json={"answers": {}}, headers=hdr)
    assert again.status_code == 409
    assert "交过" in again.json()["detail"]


def test_home_counts(client, auth, exam):
    """交一份卷，首页的"已完成"要加一。

    用增量而不是绝对值：库里还有别的模块留下的考试，写死数字会互相牵连。
    """
    hdr = _stoken(client, auth, no="20260111")
    before = client.get("/api/student/home", headers=hdr).json()
    assert before["exam_done"] == 0
    assert before["exam_total"] >= 1

    client.post(f"/api/student/exams/{exam['id']}/submit", json={"answers": {}}, headers=hdr)
    after = client.get("/api/student/home", headers=hdr).json()
    assert after["exam_done"] == 1
    assert after["exam_total"] == before["exam_total"]


# ---------- 改密码 ----------
def test_change_own_password(client, auth):
    hdr = _stoken(client, auth, no="20260121")
    res = client.post(
        "/api/student/password",
        json={"old_password": "20260121", "new_password": "my-new-pw"},
        headers=hdr,
    )
    assert res.status_code == 200, res.text
    assert _slogin(client, "20260121", "my-new-pw").status_code == 200
    assert _slogin(client, "20260121", "20260121").status_code == 400


def test_cannot_set_password_to_student_no(client, auth):
    hdr = _stoken(client, auth, no="20260131")
    res = client.post(
        "/api/student/password",
        json={"old_password": "20260131", "new_password": "20260131"},
        headers=hdr,
    )
    assert res.status_code == 400
    # 同学之间互相猜得到，不许拿学号当密码
    assert "学号" in res.json()["detail"]


# ---------- 打字 ----------
def test_typing_record_links_to_account(client, auth):
    hdr = _stoken(client, auth, no="20260141", grade="七年级", cls="7班")
    res = client.post(
        "/api/typing/records",
        json={
            "student_name": "冒名顶替",      # 带令牌时这两个字段应被账号覆盖
            "student_class": "冒充的班",
            "module": "中文",
            "difficulty": "简单",
            "duration": 60,
            "typed_chars": 100,
            "correct_chars": 95,
        },
        headers=hdr,
    )
    assert res.status_code == 200, res.text

    mine = client.get("/api/student/typing/records", headers=hdr).json()
    assert len(mine) == 1 and mine[0]["accuracy"] == 95

    rows = client.get("/api/typing/records", headers=auth).json()
    rec = [r for r in rows if r["student_class"] == "七年级7班"]
    assert len(rec) == 1
    assert rec[0]["student_name"] == "张三", "带令牌时姓名该以账号为准"


def test_anonymous_typing_still_works(client):
    """公开的 /dazi 那条路不能被学生平台挤掉。"""
    res = client.post(
        "/api/typing/records",
        json={
            "student_name": "路人甲",
            "student_class": "六(1)班",
            "module": "英文",
            "difficulty": "简单",
            "duration": 60,
            "typed_chars": 80,
            "correct_chars": 80,
        },
    )
    assert res.status_code == 200
