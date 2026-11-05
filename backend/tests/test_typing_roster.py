"""免登录打字页（/dazi）：手填的班级姓名要和学生名单对得上才能交成绩（2.12.0）。

对上了就挂到那个学生账号上，他自己的首页也看得到这次练习。
"""

import pytest

from app.siteconfig import site


@pytest.fixture(autouse=True)
def _roster_on(monkeypatch):
    monkeypatch.setattr(site.typing, "require_roster", True)


@pytest.fixture(scope="module")
def pupil(client, auth):
    cls = client.post("/api/classes", json={"grade": "九年级", "name": "7班"}, headers=auth).json()
    res = client.post("/api/students", json={"student_no": "R97001", "name": "名单甲",
                                             "class_id": cls["id"]}, headers=auth)
    assert res.status_code == 200, res.text
    return {"class": "九年级7班", "name": "名单甲", "id": res.json()["id"]}


def _submit(client, cls, name):
    return client.post("/api/typing/records", json={
        "student_name": name, "student_class": cls, "module": "键盘", "difficulty": "简单",
        "typed_chars": 50, "correct_chars": 48, "duration": 60})


def test_名单里没有的交不了(client, pupil):
    res = _submit(client, pupil["class"], "查无此人")
    assert res.status_code == 400
    assert "学生名单里没有「九年级7班 查无此人」" in res.json()["detail"]
    assert _submit(client, "九年级8班", pupil["name"]).status_code == 400, "班级不对也不行"


def test_对得上的能交_而且挂到学生账号上(client, auth, pupil):
    res = _submit(client, pupil["class"], pupil["name"])
    assert res.status_code == 200, res.text
    rows = client.get("/api/typing/records", params={"keyword": "名单甲"}, headers=auth).json()
    assert rows and rows[0]["student_class"] == "九年级7班"
    tok = client.post("/api/student/login", params={"student_no": "R97001", "password": "123456"})
    assert tok.status_code == 200, tok.text
    home = client.get("/api/student/home",
                      headers={"Authorization": "Bearer " + tok.json()["access_token"]}).json()
    assert home["typing_count"] == 1, "对上名单的成绩要算进学生自己的首页"


def test_空格和全角括号不算错(client, auth):
    cls = client.post("/api/classes", json={"grade": "九年级", "name": "(8)班"}, headers=auth).json()
    client.post("/api/students", json={"student_no": "R97002", "name": "名单乙",
                                       "class_id": cls["id"]}, headers=auth)
    assert _submit(client, " 九年级（8）班 ", " 名单乙 ").status_code == 200


def test_没填的还是提示填写(client):
    res = _submit(client, "", "")
    assert res.status_code == 400 and "请填写班级和姓名" in res.json()["detail"]


def test_开练之前先问一声(client, pupil):
    ok = client.get("/api/typing/check-student",
                    params={"student_class": pupil["class"], "student_name": pupil["name"]}).json()
    assert ok["ok"] is True
    no = client.get("/api/typing/check-student",
                    params={"student_class": pupil["class"], "student_name": "查无此人"}).json()
    assert no["ok"] is False and "学生名单里没有" in no["tip"]
    assert set(no) == {"ok", "tip"}, "只回对不对，不带任何学生信息"


def test_班级下拉只有班级名(client, pupil):
    got = client.get("/api/typing/roster-classes").json()
    assert "九年级7班" in got and all(isinstance(x, str) for x in got)


def test_关掉开关就照旧手填(client, monkeypatch):
    monkeypatch.setattr(site.typing, "require_roster", False)
    assert _submit(client, "校外班", "校外同学").status_code == 200
    assert client.get("/api/typing/check-student",
                      params={"student_class": "x", "student_name": "y"}).json()["ok"] is True
