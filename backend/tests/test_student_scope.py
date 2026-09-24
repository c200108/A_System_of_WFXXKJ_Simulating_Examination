"""教师端学生管理按班隔离（2.10.1）：老师只看得到、只管得着自己名下班级的学生。

甲老师带七年级1班，乙老师带七年级2班（conftest 里建的）；管理员不受限。
"""

import io

import pytest
from openpyxl import load_workbook


def _cid(client, auth, display):
    return next(c["id"] for c in client.get("/api/classes", headers=auth).json()
                if c["display"] == display)


@pytest.fixture(scope="module")
def roster(client, auth, teacher_auth, teacher2_auth):
    c1 = _cid(client, auth, "七年级1班")
    c2 = _cid(client, auth, "七年级2班")
    made = {}
    for no, name, cid in (("S1001", "甲班学生一", c1), ("S1002", "甲班学生二", c1),
                          ("S2001", "乙班学生一", c2), ("S9001", "未分班学生", None)):
        res = client.post("/api/students", json={"student_no": no, "name": name, "class_id": cid},
                          headers=auth)
        assert res.status_code == 200, res.text
        made[no] = res.json()["id"]
    return {"c1": c1, "c2": c2, "ids": made}


def _nos(client, headers, **params):
    return {s["student_no"] for s in client.get("/api/students", params=params, headers=headers).json()}


def test_老师只看得到自己班的学生(client, auth, teacher_auth, teacher2_auth, roster):
    mine = _nos(client, teacher_auth)
    assert {"S1001", "S1002"} <= mine and not mine & {"S2001", "S9001"}
    assert "S2001" in _nos(client, teacher2_auth) and "S1001" not in _nos(client, teacher2_auth)
    # 按别人的班筛也筛不出来
    assert not _nos(client, teacher_auth, class_id=roster["c2"])
    assert {"S1001", "S2001", "S9001"} <= _nos(client, auth), "管理员看全校"
    shown = set(client.get("/api/students/classes", headers=teacher_auth).json())
    assert "七年级1班" in shown and "七年级2班" not in shown


def test_导出也只有自己班(client, teacher_auth, roster):
    res = client.get("/api/students/export.xlsx", headers=teacher_auth)
    ws = load_workbook(io.BytesIO(res.content)).active
    nos = {r[0] for r in ws.iter_rows(min_row=2, values_only=True)}
    assert {"S1001", "S1002"} <= nos and "S2001" not in nos and "S9001" not in nos


def test_只能往自己的班里加学生(client, teacher_auth, roster):
    res = client.post("/api/students", json={"student_no": "S1003", "name": "新", "class_id": roster["c2"]},
                      headers=teacher_auth)
    assert res.status_code == 403 and "不是你带的班" in res.json()["detail"]
    res = client.post("/api/students", json={"student_no": "S1003", "name": "新"}, headers=teacher_auth)
    assert res.status_code == 400, "老师建的学生必须有班，不然建完自己就看不到了"
    res = client.post("/api/students", json={"student_no": "S1003", "name": "新", "class_id": roster["c1"]},
                      headers=teacher_auth)
    assert res.status_code == 200


def test_别的班的学生改不了_也看不出有这个人(client, auth, teacher_auth, roster):
    other = roster["ids"]["S2001"]
    res = client.patch(f"/api/students/{other}", json={"name": "改"}, headers=teacher_auth)
    assert res.status_code == 404
    mine = roster["ids"]["S1002"]
    res = client.patch(f"/api/students/{mine}", json={"class_id": roster["c2"]}, headers=teacher_auth)
    assert res.status_code == 403, "调到别人的班就管不着了，不让调"
    res = client.patch(f"/api/students/{mine}", json={"name": "甲班学生二号"}, headers=teacher_auth)
    assert res.status_code == 200 and res.json()["name"] == "甲班学生二号"
    res = client.patch(f"/api/students/{other}", json={"name": "乙班学生一"}, headers=auth)
    assert res.status_code == 200, "管理员照常能改"


def test_批量操作不认别的班的id(client, auth, teacher_auth, roster):
    ids = [roster["ids"]["S1001"], roster["ids"]["S2001"]]
    res = client.post("/api/students/bulk", json={"ids": ids, "action": "disable"}, headers=teacher_auth)
    assert res.json()["affected"] == 1
    states = {s["student_no"]: s["is_active"] for s in client.get("/api/students", headers=auth).json()}
    assert states["S1001"] is False and states["S2001"] is True
    res = client.post("/api/students/bulk", json={"ids": [roster["ids"]["S2001"]], "action": "delete"},
                      headers=teacher_auth)
    assert res.status_code == 404
    assert "S2001" in _nos(client, auth), "别的班的学生删不掉"


def test_粘贴名单_别人的班那几行导不进来(client, teacher_auth, roster):
    text = "S1101\t甲一\t七年级1班\nS2101\t乙一\t七年级2班\nS1102\t甲二\n"
    res = client.post("/api/students/batch", json={"text": text}, headers=teacher_auth).json()
    assert res["added"] == 1
    assert any("不是你带的班" in e for e in res["errors"]) and any("没写班级" in e for e in res["errors"])
    assert "只能往自己带的班里导" in res["hint"]
    # 选了默认班，没写班级的那一行就进这个班
    res = client.post("/api/students/batch", json={"text": "S1102\t甲二\n", "class_id": roster["c1"]},
                      headers=teacher_auth).json()
    assert res["added"] == 1
    res = client.post("/api/students/batch", json={"text": "S1103\t甲三\n", "class_id": roster["c2"]},
                      headers=teacher_auth)
    assert res.status_code == 403


def test_导入模板只列自己的班(client, teacher_auth):
    res = client.get("/api/students/template.xlsx", headers=teacher_auth)
    ws = load_workbook(io.BytesIO(res.content))["可用班级"]
    names = {r[0] for r in ws.iter_rows(min_row=2, values_only=True)}
    mine = {c["display"] for c in client.get("/api/classes", params={"mine": True}, headers=teacher_auth).json()}
    assert names == mine and "七年级1班" in names and "七年级2班" not in names


def test_名下没有班的老师一个学生都看不到(client, auth):
    client.post("/api/auth/users", json={"username": "teacher_noclass", "password": "teacher123",
                                         "name": "丙老师", "role": "teacher"}, headers=auth)
    token = client.post("/api/auth/login", data={"username": "teacher_noclass",
                                                 "password": "teacher123"}).json()["access_token"]
    h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/students", headers=h).json() == []
    res = client.post("/api/students", json={"student_no": "S7001", "name": "x"}, headers=h)
    assert res.status_code == 403 and "把班分给你" in res.json()["detail"]
