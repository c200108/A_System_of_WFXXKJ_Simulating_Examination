"""班级 + 汉字姓名登录、班干部。

整个测试会话共用一个库，别的测试也建学生，所以这里的姓名都挑生僻字，不和别人撞。
"""


# ---------------------------------------------------------------- 接口
def _class_id(client, auth, grade="八年级", name="1班"):
    for c in client.get("/api/classes", headers=auth).json():
        if c["grade"] == grade and c["name"] == name:
            return c["id"]
    res = client.post("/api/classes", json={"grade": grade, "name": name}, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()["id"]


def _mk(client, auth, no, name, grade="八年级", cls="1班"):
    res = client.post("/api/students", json={
        "student_no": no, "name": name, "class_id": _class_id(client, auth, grade, cls)},
        headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _login(client, account, pwd="123456", class_id=None):
    params = {"name": account, "password": pwd}
    if class_id is not None:
        params["class_id"] = class_id
    return client.post("/api/student/login-by-name", params=params)


def test_class_name_login(client, auth):
    cid = _class_id(client, auth, "八年级", "1班")
    row = _mk(client, auth, "28010001", "犇骉")
    assert "pinyin" not in row
    res = _login(client, "犇骉", class_id=cid)
    assert res.status_code == 200, res.text
    assert res.json()["student"]["student_no"] == "28010001"
    # 学号那条路照旧：学号 + 学号初始密码也行
    assert _login(client, "28010001", "28010001").status_code == 200
    assert _login(client, "犇骉", "28010001", class_id=cid).status_code == 400
    # 选错班
    other = _class_id(client, auth, "七年级", "3班")
    assert _login(client, "犇骉", class_id=other).status_code == 400
    # 拼音不再能登
    assert _login(client, "benbiao", class_id=cid).status_code == 400


def test_login_classes_are_public(client, auth):
    cid = _class_id(client, auth, "八年级", "5班")
    _mk(client, auth, "28010101", "鹬鹭", "八年级", "5班")
    got = client.get("/api/student/classes").json()
    assert {"id": cid, "display": "八年级5班"} in got


def test_same_name_in_different_classes(client, auth):
    c1 = _class_id(client, auth, "八年级", "1班")
    c2 = _class_id(client, auth, "九年级", "2班")
    _mk(client, auth, "28010011", "鑫淼", "八年级", "1班")
    _mk(client, auth, "28010012", "鑫淼", "九年级", "2班")
    a = _login(client, "鑫淼", class_id=c1)
    b = _login(client, "鑫淼", class_id=c2)
    assert a.status_code == 200 and a.json()["student"]["student_no"] == "28010011"
    assert b.status_code == 200 and b.json()["student"]["student_no"] == "28010012"
    # 老客户端不选班：全校两位同名，分不出
    assert _login(client, "鑫淼").status_code == 409


def test_same_class_same_name_needs_student_no(client, auth):
    cid = _class_id(client, auth, "八年级", "1班")
    _mk(client, auth, "28010031", "龘靐", "八年级", "1班")
    _mk(client, auth, "28010032", "龘靐", "八年级", "1班")
    res = _login(client, "龘靐", class_id=cid)
    assert res.status_code == 409 and "学号" in res.json()["detail"]
    assert _login(client, "28010032").status_code == 200


def test_disabled_same_name_does_not_block(client, auth):
    cid = _class_id(client, auth, "八年级", "1班")
    a = _mk(client, auth, "28010021", "燚垚")
    b = _mk(client, auth, "28010022", "燚垚")
    client.post("/api/students/bulk", json={"ids": [b["id"]], "action": "disable"}, headers=auth)
    ok = _login(client, "燚垚", class_id=cid)
    assert ok.status_code == 200 and ok.json()["student"]["id"] == a["id"]


def test_export_columns(client, auth):
    from io import BytesIO
    from openpyxl import load_workbook
    _mk(client, auth, "28010061", "骁骐")
    res = client.get("/api/students/export.xlsx", params={"keyword": "28010061"}, headers=auth)
    head = [c.value for c in load_workbook(BytesIO(res.content)).active[1]]
    assert head[:5] == ["学号", "姓名", "班级", "性别", "班干部"]


def test_desk_roster_has_class_and_name(client, auth):
    from app.database import SessionLocal
    from app.models import Exam
    from app.routers.desk import _roster
    _mk(client, auth, "28010091", "霂霖", "七年级", "9班")
    with SessionLocal() as db:
        exam = Exam(title="名单测试", token="class-roster", paper_id=None,
                    target_classes="七年级9班")
        got = {r["no"]: r for r in _roster(db, exam)}
    assert got["28010091"]["name"] == "霂霖" and got["28010091"]["cls"] == "七年级9班"


def test_class_roles(client, auth):
    cid = _class_id(client, auth, "七年级", "9班")
    a = _mk(client, auth, "28010071", "芃芃", "七年级", "9班")
    b = _mk(client, auth, "28010072", "蓁蓁", "七年级", "9班")
    c = _mk(client, auth, "28010073", "葳蕤", "七年级", "9班")

    def role(sid, r):
        return client.patch(f"/api/students/{sid}", json={"class_role": r}, headers=auth)

    assert role(a["id"], "班长").json()["class_role"] == "班长"
    assert role(b["id"], "组长").status_code == 200
    assert role(c["id"], "组长").status_code == 200
    # 一个班一位班长：换人时原来那位卸任
    assert role(b["id"], "班长").status_code == 200
    rows = {r["id"]: r["class_role"]
            for r in client.get("/api/students", params={"class_id": cid}, headers=auth).json()}
    assert rows[a["id"]] == "" and rows[b["id"]] == "班长" and rows[c["id"]] == "组长"
    assert role(a["id"], "学委").status_code == 400
    # 调到别的班，班干部不跟着走
    other = _class_id(client, auth, "七年级", "8班")
    res = client.patch(f"/api/students/{c['id']}", json={"class_id": other}, headers=auth)
    assert res.json()["class_role"] == ""
