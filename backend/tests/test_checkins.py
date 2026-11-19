"""课堂签到（2.24.0）：发起、学生签到、一台电脑一人、附加工作表实时填姓名、到点结束。"""

import uuid
from datetime import timedelta

import pytest

from app import clock
from tests.test_students import _class_id, _mk_student, _slogin

GRADE, CLS = "九年级", "签到班"


def _sheet():
    """座号 A1/A2/B1 一格，右边一格写姓名；B2 标成设备故障。"""
    return {"data": [["讲台", "", "", ""],
                     ["A1", "", "B1", ""],
                     ["A2", "", "B2", ""]],
            "broken": {"D3": "坏了"}}


@pytest.fixture(scope="module")
def room(client, auth):
    cid = _class_id(client, auth, GRADE, CLS)
    assert client.put(f"/api/classes/{cid}/seat-sheet", json={"sheet": _sheet()}, headers=auth).status_code == 200
    toks = {}
    for no, name in (("QD001", "签到甲"), ("QD002", "签到乙"), ("QD003", "签到丙")):
        _mk_student(client, auth, no=no, name=name, grade=GRADE, cls=CLS)
        toks[name] = {"Authorization": "Bearer " + _slogin(client, no, "123456").json()["access_token"]}
    return {"cid": cid, "toks": toks}


def _dev(tok, device=None, ip="203.0.113.9"):
    return {**tok, "X-Device-Id": device or uuid.uuid4().hex, "X-Real-IP": ip}


def _stop_all(client, auth, cid):
    cur = client.get(f"/api/classes/{cid}/checkins/current", headers=auth).json()["checkin"]
    if cur and cur["active"]:
        client.post(f"/api/classes/{cid}/checkins/{cur['id']}/stop", headers=auth)


def test_没签到时学生端问到的是没有(client, room):
    got = client.get("/api/student/checkin", headers=_dev(room["toks"]["签到甲"])).json()
    assert got["active"] is False and got["poll"] > 0


def test_发起_签到_填进新工作表(client, auth, teacher_auth, room):
    cid = room["cid"]
    _stop_all(client, auth, cid)
    assert client.post(f"/api/classes/{cid}/checkins", json={"minutes": 0}, headers=auth).status_code == 422
    assert client.post(f"/api/classes/{cid}/checkins", json={"minutes": 3},
                       headers=teacher_auth).status_code == 403, "不是本班老师不能发起"
    res = client.post(f"/api/classes/{cid}/checkins", json={"minutes": 3}, headers=auth)
    assert res.status_code == 200, res.text
    k = res.json()
    assert k["active"] and 170 <= k["remaining"] <= 180 and k["total"] == 3 and k["absent"] == 3
    assert "/" in k["tab_name"] and len(k["tab_name"]) == 14, "表名是 20261119/11:10 这种"
    assert client.post(f"/api/classes/{cid}/checkins", json={"minutes": 3},
                       headers=auth).status_code == 409, "同时只能有一个"

    jia = _dev(room["toks"]["签到甲"], device="dev-jia-0001")
    seen = client.get("/api/student/checkin", headers=jia).json()
    assert seen["active"] and seen["signed"] is None and seen["checkin_id"] == k["id"]
    assert [s["seat"] for s in seen["seats"]] == ["A1", "B1", "A2"], "B2 是故障座位不给选"

    assert client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "Z9"},
                       headers=jia).status_code == 400
    got = client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "b1"}, headers=jia).json()
    assert got == {"ok": True, "seat": "B1", "already": False}
    assert client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A1"},
                       headers=jia).json()["already"] is True, "签过了再签不改"

    yi = _dev(room["toks"]["签到乙"], device="dev-yi-0002")
    res = client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "B1"}, headers=yi)
    assert res.status_code == 409 and "已经有同学" in res.json()["detail"]
    # 同一台电脑换个账号签：不行
    res = client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A1"},
                      headers=_dev(room["toks"]["签到乙"], device="dev-jia-0001"))
    assert res.status_code == 409 and "签到甲" in res.json()["detail"]
    res = client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A1"}, headers=yi)
    assert res.status_code == 200, res.text

    view = client.get(f"/api/classes/{cid}/checkins/current", headers=teacher_auth).json()["checkin"]
    assert view["signed_count"] == 2 and view["absent"] == 1
    assert [(s["name"], s["seat"]) for s in view["signed"]] == [("签到甲", "B1"), ("签到乙", "A1")]
    assert [u["name"] for u in view["unsigned"]] == ["签到丙"]
    assert {o["name"] for o in view["online"]} == {"签到甲", "签到乙"}

    tabs = client.get(f"/api/classes/{cid}/seat-tabs", headers=auth).json()
    assert tabs[-1]["id"] == k["tab_id"]
    sheet = client.get(f"/api/classes/{cid}/seat-tabs/{k['tab_id']}", headers=auth).json()["sheet"]
    assert sheet["data"][1] == ["A1", "签到乙", "B1", "签到甲"]
    main = client.get(f"/api/classes/{cid}/seat-sheet", headers=auth).json()["sheet"]
    assert main["data"][1] == ["A1", "", "B1", ""], "sheet1 不动"


def test_机房版同一个内网IP只能签一人(client, auth, room):
    cid = room["cid"]
    _stop_all(client, auth, cid)
    k = client.post(f"/api/classes/{cid}/checkins", json={"minutes": 1}, headers=auth).json()
    a = _dev(room["toks"]["签到甲"], ip="192.168.5.20")
    b = _dev(room["toks"]["签到乙"], ip="192.168.5.20")    # 设备号不同、内网 IP 相同
    assert client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A1"}, headers=a).status_code == 200
    assert client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A2"}, headers=b).status_code == 409
    # 线上（公网出口 IP，整个机房一个）不按 IP 拦
    c = _dev(room["toks"]["签到丙"], ip="203.0.113.9")
    assert client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A2"}, headers=c).status_code == 200


def test_到点或提前结束后不能签_中途登录拿剩余时间(client, auth, room, monkeypatch):
    cid = room["cid"]
    _stop_all(client, auth, cid)
    k = client.post(f"/api/classes/{cid}/checkins", json={"minutes": 2}, headers=auth).json()
    real = clock.now
    monkeypatch.setattr(clock, "now", lambda: real() + timedelta(seconds=70))
    late = client.get("/api/student/checkin", headers=_dev(room["toks"]["签到丙"])).json()
    assert late["active"] and 40 <= late["remaining"] <= 50, "中途登录的看到的是剩余时间"
    monkeypatch.setattr(clock, "now", lambda: real() + timedelta(seconds=121))
    assert client.get("/api/student/checkin", headers=_dev(room["toks"]["签到丙"])).json()["active"] is False
    res = client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A1"},
                      headers=_dev(room["toks"]["签到丙"]))
    assert res.status_code == 410
    view = client.get(f"/api/classes/{cid}/checkins/current", headers=auth).json()["checkin"]
    assert view["active"] is False and view["remaining"] == 0


def test_别的班的学生签不了(client, auth, room):
    cid = room["cid"]
    _stop_all(client, auth, cid)
    k = client.post(f"/api/classes/{cid}/checkins", json={"minutes": 1}, headers=auth).json()
    _mk_student(client, auth, no="QD900", name="外班", grade=GRADE, cls="别的班")
    other = {"Authorization": "Bearer " + _slogin(client, "QD900", "123456").json()["access_token"]}
    assert client.get("/api/student/checkin", headers=_dev(other)).json()["active"] is False
    assert client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A1"},
                       headers=_dev(other)).status_code == 404
    client.post(f"/api/classes/{cid}/checkins/{k['id']}/stop", headers=auth)


def test_工作表能改能删_签到中的不能删(client, auth, room):
    cid = room["cid"]
    _stop_all(client, auth, cid)
    k = client.post(f"/api/classes/{cid}/checkins", json={"minutes": 1}, headers=auth).json()
    assert client.delete(f"/api/classes/{cid}/seat-tabs/{k['tab_id']}", headers=auth).status_code == 409
    client.post(f"/api/classes/{cid}/checkins/{k['id']}/stop", headers=auth)
    assert client.put(f"/api/classes/{cid}/seat-tabs/{k['tab_id']}", json={"sheet": {"data": [["x"]]}},
                      headers=auth).status_code == 200
    assert client.delete(f"/api/classes/{cid}/seat-tabs/{k['tab_id']}", headers=auth).status_code == 200
    assert client.get(f"/api/classes/{cid}/seat-tabs/{k['tab_id']}", headers=auth).status_code == 404


def test_sheet1没有座号不能发起(client, auth):
    cid = _class_id(client, auth, GRADE, "没座号班")
    client.put(f"/api/classes/{cid}/seat-sheet", json={"sheet": {"data": [["讲台"]]}}, headers=auth)
    res = client.post(f"/api/classes/{cid}/checkins", json={"minutes": 1}, headers=auth)
    assert res.status_code == 400 and "座号" in res.json()["detail"]


def test_默认空表能认出座号():
    from app.services import checkin
    got = [s["seat"] for s in checkin.seats(checkin.default_sheet())]
    assert "A1" in got and "D14" in got and len(got) > 50
