"""课堂情况日志（在线座次右边那一栏）：增删改、权限、跟着班级进回收站。"""

import pytest


def _cid(client, auth, grade, name):
    for c in client.get("/api/classes", headers=auth).json():
        if c["grade"] == grade and c["name"] == name:
            return c["id"]
    return client.post("/api/classes", json={"grade": grade, "name": name}, headers=auth).json()["id"]


@pytest.fixture(scope="module")
def cid(client, auth):
    return _cid(client, auth, "七年级", "1班")      # conftest 里分给了甲老师（teacher_auth）


def test_新建修改删除_最新的在前(client, teacher_auth, cid):
    a = client.post(f"/api/classes/{cid}/logs", json={
        "lesson_date": "2026-11-03", "title": "第 1 次上机", "content": "请假：张三\n3 号机鼠标坏"},
        headers=teacher_auth)
    assert a.status_code == 200, a.text
    assert a.json()["author_name"] and a.json()["content"].endswith("鼠标坏")
    b = client.post(f"/api/classes/{cid}/logs", json={"lesson_date": "2026-11-05", "content": "全勤"},
                    headers=teacher_auth).json()
    rows = client.get(f"/api/classes/{cid}/logs", headers=teacher_auth).json()
    assert [r["id"] for r in rows[:2]] == [b["id"], a.json()["id"]]

    res = client.put(f"/api/classes/{cid}/logs/{b['id']}", json={
        "lesson_date": "2026-11-05", "title": "第 2 次", "content": "全勤，投影仪不亮"}, headers=teacher_auth)
    assert res.status_code == 200 and res.json()["title"] == "第 2 次"

    assert client.delete(f"/api/classes/{cid}/logs/{b['id']}", headers=teacher_auth).status_code == 200
    ids = [r["id"] for r in client.get(f"/api/classes/{cid}/logs", headers=teacher_auth).json()]
    assert b["id"] not in ids and a.json()["id"] in ids


def test_空的不收(client, teacher_auth, cid):
    res = client.post(f"/api/classes/{cid}/logs", json={"lesson_date": "2026-11-05", "title": " ",
                                                       "content": "  "}, headers=teacher_auth)
    assert res.status_code == 400


def test_别的老师只能看不能写(client, teacher_auth, teacher2_auth, cid):
    lid = client.post(f"/api/classes/{cid}/logs", json={"lesson_date": "2026-11-04", "content": "x"},
                      headers=teacher_auth).json()["id"]
    assert client.get(f"/api/classes/{cid}/logs", headers=teacher2_auth).status_code == 200
    assert client.post(f"/api/classes/{cid}/logs", json={"lesson_date": "2026-11-04", "content": "y"},
                       headers=teacher2_auth).status_code == 403
    assert client.put(f"/api/classes/{cid}/logs/{lid}", json={"lesson_date": "2026-11-04", "content": "y"},
                      headers=teacher2_auth).status_code == 403
    assert client.delete(f"/api/classes/{cid}/logs/{lid}", headers=teacher2_auth).status_code == 403


def test_日志不能跨班改(client, auth, cid):
    other = _cid(client, auth, "日志测试", "2班")
    lid = client.post(f"/api/classes/{cid}/logs", json={"lesson_date": "2026-11-04", "content": "z"},
                      headers=auth).json()["id"]
    assert client.delete(f"/api/classes/{other}/logs/{lid}", headers=auth).status_code == 404


def test_删班进回收站_还原后日志也回来(client, auth):
    c = _cid(client, auth, "日志测试", "9班")
    client.post(f"/api/classes/{c}/logs", json={"lesson_date": "2026-11-06", "content": "回收站测试"},
                headers=auth)
    assert client.delete(f"/api/classes/{c}", headers=auth).status_code == 200
    item = next(i for i in client.get("/api/recycle", headers=auth).json()["items"]
                if "日志测试9班" in i["title"])
    assert client.post("/api/recycle/restore", json={"ids": [item["id"]]}, headers=auth).status_code == 200
    rows = client.get(f"/api/classes/{c}/logs", headers=auth).json()
    assert [r["content"] for r in rows] == ["回收站测试"]
