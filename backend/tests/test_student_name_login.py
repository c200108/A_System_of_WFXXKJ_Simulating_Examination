"""姓名登录版学生端：账号是中文姓名，初始密码 123456。

学号登录那条路一点不变（初始密码仍是学号），两条路认的是同一个账号。
"""


def _class_id(client, auth):
    for c in client.get("/api/classes", headers=auth).json():
        if c["grade"] == "八年级" and c["name"] == "姓名班":
            return c["id"]
    res = client.post("/api/classes", json={"grade": "八年级", "name": "姓名班"}, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()["id"]


def _mk(client, auth, no, name):
    res = client.post("/api/students", json={
        "student_no": no, "name": name, "class_id": _class_id(client, auth)}, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _by_name(client, name, pwd="123456"):
    return client.post("/api/student/login-by-name", params={"name": name, "password": pwd})


def test_name_and_123456_logs_in(client, auth):
    _mk(client, auth, "27010001", "姓名甲")
    res = _by_name(client, "姓名甲")
    assert res.status_code == 200, res.text
    assert res.json()["student"]["student_no"] == "27010001"
    # 名单里常有多打的空格
    assert _by_name(client, "  姓名甲 ").status_code == 200


def test_student_no_login_is_unchanged(client, auth):
    _mk(client, auth, "27010002", "姓名乙")
    # 2.19.2 起新账号初始密码是 123456：学号登录也用 123456，学号本身不再是密码
    ok = client.post("/api/student/login", params={"student_no": "27010002", "password": "123456"})
    assert ok.status_code == 200
    bad = client.post("/api/student/login", params={"student_no": "27010002", "password": "27010002"})
    assert bad.status_code == 400


def test_wrong_password_or_unknown_name(client, auth):
    _mk(client, auth, "27010003", "姓名丙")
    assert _by_name(client, "姓名丙", "654321").status_code == 400
    assert _by_name(client, "查无此人").status_code == 400
    assert _by_name(client, "  ").status_code == 400


def test_after_changing_the_password_123456_stops_working(client, auth):
    _mk(client, auth, "27010004", "姓名丁")
    token = _by_name(client, "姓名丁").json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    # 姓名登录的学生只知道 123456，改密码时它就是原密码
    res = client.post("/api/student/password",
                      json={"old_password": "123456", "new_password": "xinmima88"}, headers=h)
    assert res.status_code == 200, res.text
    assert _by_name(client, "姓名丁").status_code == 400
    assert _by_name(client, "姓名丁", "xinmima88").status_code == 200
    # 学号登录也跟着换成新密码
    assert client.post("/api/student/login", params={
        "student_no": "27010004", "password": "xinmima88"}).status_code == 200


def test_cannot_change_password_to_123456(client, auth):
    _mk(client, auth, "27010005", "姓名戊")
    token = _by_name(client, "姓名戊").json()["access_token"]
    res = client.post("/api/student/password",
                      json={"old_password": "123456", "new_password": "123456"},
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 400
    assert "初始密码" in res.json()["detail"]


def test_reset_by_teacher_brings_123456_back(client, auth):
    s = _mk(client, auth, "27010006", "姓名己")
    client.patch(f"/api/students/{s['id']}", json={"password": "changed-it"}, headers=auth)
    assert _by_name(client, "姓名己").status_code == 400
    client.post("/api/students/bulk", json={"ids": [s["id"]], "action": "reset_password"},
                headers=auth)
    assert _by_name(client, "姓名己").status_code == 200


def test_same_name_asks_for_student_no(client, auth):
    _mk(client, auth, "27010007", "重名")
    _mk(client, auth, "27010008", "重名")
    res = _by_name(client, "重名")
    assert res.status_code == 409
    assert "学号" in res.json()["detail"]
    # 框里改填学号就能进
    got = _by_name(client, "27010008")
    assert got.status_code == 200
    assert got.json()["student"]["student_no"] == "27010008"


def test_same_name_but_different_password_finds_the_right_one(client, auth):
    _mk(client, auth, "27010009", "同名")
    b = _mk(client, auth, "27010010", "同名")
    client.patch(f"/api/students/{b['id']}", json={"password": "only-mine-1"}, headers=auth)
    assert _by_name(client, "同名").json()["student"]["student_no"] == "27010009"
    assert _by_name(client, "同名", "only-mine-1").json()["student"]["student_no"] == "27010010"


def test_disabled_student_cannot_login_by_name(client, auth):
    s = _mk(client, auth, "27010011", "姓名庚")
    client.patch(f"/api/students/{s['id']}", json={"is_active": False}, headers=auth)
    assert _by_name(client, "姓名庚").status_code == 403


def test_name_login_does_not_take_the_student_no_password(client, auth):
    """姓名登录版的初始密码只有 123456 —— 学号同学之间都知道，不能拿来登。"""
    _mk(client, auth, "27010012", "姓名辛")
    assert _by_name(client, "姓名辛", "27010012").status_code == 400


def test_old_client_can_still_change_password_with_student_no(client, auth):
    """2.19.2 以前建的老账号初始密码是学号（库里不改），学号版老客户端照样能登、能改密码。"""
    s = _mk(client, auth, "27010013", "姓名壬")
    client.patch(f"/api/students/{s['id']}", json={"password": "27010013"}, headers=auth)  # 模拟老账号
    token = client.post("/api/student/login", params={
        "student_no": "27010013", "password": "27010013"}).json()["access_token"]
    res = client.post("/api/student/password",
                      json={"old_password": "27010013", "new_password": "xinmima99"},
                      headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200, res.text
    assert _by_name(client, "姓名壬", "xinmima99").status_code == 200
