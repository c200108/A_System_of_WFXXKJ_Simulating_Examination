"""课堂加减分（在线座次右键学生）：加、减、撤销、总分、权限、不能给别的班的学生加。"""

import pytest


def _cid(client, auth, grade, name):
    for c in client.get("/api/classes", headers=auth).json():
        if c["grade"] == grade and c["name"] == name:
            return c["id"]
    return client.post("/api/classes", json={"grade": grade, "name": name}, headers=auth).json()["id"]


@pytest.fixture(scope="module")
def two(client, auth):
    cid = _cid(client, auth, "七年级", "1班")              # 甲老师的班（conftest）
    other = _cid(client, auth, "积分测试", "1班")
    a = client.post("/api/students", json={"student_no": "PT001", "name": "积分甲", "class_id": cid},
                    headers=auth).json()
    b = client.post("/api/students", json={"student_no": "PT002", "name": "积分乙", "class_id": other},
                    headers=auth).json()
    return {"cid": cid, "other": other, "a": a["id"], "b": b["id"]}


def test_加减撤销_总分跟着变(client, teacher_auth, two):
    cid, a = two["cid"], two["a"]
    r1 = client.post(f"/api/classes/{cid}/points", json={"student_id": a, "delta": 2, "reason": "回答问题"},
                     headers=teacher_auth)
    assert r1.status_code == 200 and r1.json()["total"] == 2
    r2 = client.post(f"/api/classes/{cid}/points", json={"student_id": a, "delta": -1}, headers=teacher_auth)
    assert r2.json()["total"] == 1
    got = client.get(f"/api/classes/{cid}/points", headers=teacher_auth).json()
    assert got["totals"][str(a)] == 1 and got["recent"][0]["delta"] == -1
    u = client.delete(f"/api/classes/{cid}/points/{r2.json()['entry']['id']}", headers=teacher_auth)
    assert u.json()["total"] == 2


def test_不能是0_不能超范围(client, teacher_auth, two):
    url = f"/api/classes/{two['cid']}/points"
    assert client.post(url, json={"student_id": two["a"], "delta": 0}, headers=teacher_auth).status_code == 400
    assert client.post(url, json={"student_id": two["a"], "delta": 101}, headers=teacher_auth).status_code == 422


def test_别的班的学生不收_别的老师不能加也看不到(client, auth, teacher_auth, teacher2_auth, two):
    url = f"/api/classes/{two['cid']}/points"
    assert client.post(url, json={"student_id": two["b"], "delta": 1}, headers=auth).status_code == 400
    assert client.post(url, json={"student_id": two["a"], "delta": 1}, headers=teacher2_auth).status_code == 403
    assert client.get(url, headers=teacher2_auth).status_code == 403


def test_座次表接口带班干部(client, teacher_auth, two):
    got = client.get(f"/api/classes/{two['cid']}/seat-sheet", headers=teacher_auth).json()
    assert all("class_role" in s for s in got["students"])
