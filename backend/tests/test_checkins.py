"""课堂签到（2.24.0）：发起、学生签到、一台电脑一人、附加工作表实时填姓名、到点结束。
2.26.0：按电脑名 / IP 自动认座、绑座模式、座号认主人、老师撤销。"""

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
    assert got == {"ok": True, "seat": "B1", "already": False, "how": "pick"}
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


# ================================================================ 按机器号自动认座（2.26.0）
@pytest.fixture()
def rule(client, auth):
    def set_(mode, offset=0):
        res = client.put("/api/checkin-seat/rule", json={"mode": mode, "offset": offset}, headers=auth)
        assert res.status_code == 200, res.text
        return res.json()
    yield set_
    set_("pick")
    client.post("/api/checkin-seat/bind-mode", json={"minutes": 0}, headers=auth)
    client.delete("/api/checkin-seat/bindings/all", headers=auth)


def _q(tok, host="", lan_ip="", device=None, ip="203.0.113.9"):
    return {"headers": _dev(tok, device=device, ip=ip), "params": {"host": host, "lan_ip": lan_ip}}


def test_认座规则只有管理员能改_谁都能看(client, auth, teacher_auth, rule):
    assert client.get("/api/checkin-seat/rule", headers=teacher_auth).json()["mode"] == "pick"
    assert client.put("/api/checkin-seat/rule", json={"mode": "host_tail"}, headers=teacher_auth).status_code == 403
    assert client.put("/api/checkin-seat/rule", json={"mode": "乱写"}, headers=auth).status_code == 400
    got = rule("ip_num", 100)
    assert got["mode"] == "ip_num" and got["offset"] == 100 and "host_tail" in got["modes"]


def test_电脑名末段就是座号_登录就自动签上_不弹选择框(client, auth, room, rule):
    cid = room["cid"]
    _stop_all(client, auth, cid)
    rule("host_tail")
    k = client.post(f"/api/classes/{cid}/checkins", json={"minutes": 3}, headers=auth).json()
    got = client.get("/api/student/checkin", **_q(room["toks"]["签到甲"], host="C09-COMPUTE-b1",
                                                     device="pc-auto-0001")).json()
    assert got["signed"] == {"seat": "B1", "how": "auto"}, got
    # 认不出来的电脑名（末段不是座号 / 不在表里）：照旧下拉框选
    got = client.get("/api/student/checkin", **_q(room["toks"]["签到乙"], host="WIN-7F3K2",
                                                     device="pc-auto-0002")).json()
    assert got["signed"] is None and got["auto"] is None
    # 认得出来的电脑不许借下拉框签别的座号
    res = client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A1", "host": "C09-COMPUTE-A2"},
                      headers=_dev(room["toks"]["签到乙"], device="pc-auto-0002"))
    assert res.status_code == 409 and "A2" in res.json()["detail"]
    sheet = client.get(f"/api/classes/{cid}/seat-tabs/{k['tab_id']}", headers=auth).json()["sheet"]
    assert sheet["data"][1] == ["A1", "", "B1", "签到甲"]
    view = client.get(f"/api/classes/{cid}/checkins/current", headers=auth).json()["checkin"]
    assert view["signed"][0]["how"] == "auto" and view["signed"][0]["host"] == "C09-COMPUTE-b1"


def test_座号认主人_自选占了别人座号的被挤走(client, auth, room, rule):
    cid = room["cid"]
    _stop_all(client, auth, cid)
    rule("host_tail")
    k = client.post(f"/api/classes/{cid}/checkins", json={"minutes": 3}, headers=auth).json()
    # 乙在一台认不出来的电脑上自己选了 A1
    yi = _dev(room["toks"]["签到乙"], device="pc-own-0002")
    assert client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A1", "host": "WIN-XYZ"},
                       headers=yi).status_code == 200
    # A1 那台电脑的主人丙登录：A1 归丙，乙被挤掉
    got = client.get("/api/student/checkin", **_q(room["toks"]["签到丙"], host="C09-COMPUTE-A1",
                                                     device="pc-own-0003")).json()
    assert got["signed"] == {"seat": "A1", "how": "auto"}
    again = client.get("/api/student/checkin", headers=yi).json()
    assert again["signed"] is None and "A1" not in [s["seat"] for s in again["seats"] if not s["taken"]]
    sheet = client.get(f"/api/classes/{cid}/seat-tabs/{k['tab_id']}", headers=auth).json()["sheet"]
    assert sheet["data"][1] == ["A1", "签到丙", "B1", ""]
    # 两台电脑认出同一个座号（重名）：后来的签不上，告诉他找老师
    got = client.get("/api/student/checkin", **_q(room["toks"]["签到甲"], host="C10-COMPUTE-A1",
                                                     device="pc-own-0001")).json()
    assert got["signed"] is None and got["auto"]["seat"] == "A1" and "找老师" in got["auto"]["error"]


def test_老师撤销一条签到_表里姓名清掉_学生重新签(client, auth, teacher_auth, room, rule):
    cid = room["cid"]
    _stop_all(client, auth, cid)
    k = client.post(f"/api/classes/{cid}/checkins", json={"minutes": 3}, headers=auth).json()
    jia = _dev(room["toks"]["签到甲"], device="pc-rv-0001")
    client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A2"}, headers=jia)
    eid = client.get(f"/api/classes/{cid}/checkins/current", headers=auth).json()["checkin"]["signed"][0]["id"]
    url = f"/api/classes/{cid}/checkins/{k['id']}/entries/{eid}"
    assert client.delete(url, headers=teacher_auth).status_code == 403, "不是本班老师不能撤销"
    view = client.delete(url, headers=auth).json()
    assert view["signed_count"] == 0
    sheet = client.get(f"/api/classes/{cid}/seat-tabs/{k['tab_id']}", headers=auth).json()["sheet"]
    assert sheet["data"][2][1] == ""
    assert client.get("/api/student/checkin", headers=jia).json()["signed"] is None


def test_数字规则_电脑名末尾数字和IP末段按座号顺序数(client, auth, room, rule):
    from app.services import checkin as ck
    labels = ["B1", "A2", "A10", "A1"]
    assert ck.seat_order(labels) == ["A1", "A2", "A10", "B1"]
    assert ck.rule_seat({"mode": "host_num", "offset": 0}, "PC-003", "", labels) == "A10"
    assert ck.rule_seat({"mode": "host_num", "offset": 0}, "PC-009", "", labels) == ""
    assert ck.rule_seat({"mode": "ip_num", "offset": 100}, "", "10.9.82.104", labels) == "B1"
    assert ck.rule_seat({"mode": "host_tail", "offset": 0}, "C09_COMPUTE_a10", "", labels) == "A10"
    assert ck.clean_ip("10.9.82.105") == "10.9.82.105" and ck.clean_ip("x") == ""
    assert ck.clean_host("C09-COMPUTE-C14") == "C09-COMPUTE-C14" and ck.clean_host("<b>") == ""

    cid = room["cid"]
    _stop_all(client, auth, cid)
    rule("ip_num", 100)
    client.post(f"/api/classes/{cid}/checkins", json={"minutes": 3}, headers=auth)
    # 本班表的座号顺序：A1 A2 B1（B2 故障）→ .102 是 A2
    got = client.get("/api/student/checkin", **_q(room["toks"]["签到甲"], lan_ip="10.9.82.102",
                                                     device="pc-ip-0001")).json()
    assert got["signed"] == {"seat": "A2", "how": "auto"}


def test_预览哪台电脑对哪个座号_重名标出来(client, auth, room, rule):
    for name, host, dev in (("签到甲", "C09-COMPUTE-A1", "pc-pv-0001"), ("签到乙", "C09-COMPUTE-B1", "pc-pv-0002"),
                            ("签到丙", "LAB-PC", "pc-pv-0003")):
        client.get("/api/student/checkin", **_q(room["toks"][name], host=host, device=dev))
    got = client.get("/api/checkin-seat/preview", params={"mode": "host_tail", "class_id": room["cid"]},
                     headers=auth).json()
    by = {m["host"]: m for m in got["machines"]}
    assert by["C09-COMPUTE-A1"]["seat"] == "A1" and by["C09-COMPUTE-B1"]["student"] == "签到乙"
    assert by["LAB-PC"]["seat"] == "" and got["clash"] == []
    assert client.get("/api/checkin-seat/rule", headers=auth).json()["mode"] == "pick", "预览不改规则"


def test_绑座模式_每台电脑选一次_签到时按绑定自动签(client, auth, room, rule):
    cid = room["cid"]
    _stop_all(client, auth, cid)
    jia = _dev(room["toks"]["签到甲"], device="pc-bind-0001")
    yi = _dev(room["toks"]["签到乙"], device="pc-bind-0002")
    assert "bind" not in client.get("/api/student/checkin", headers=jia).json()
    assert client.post("/api/student/seat-bind", json={"seat": "A1"}, headers=jia).status_code == 410
    assert client.post("/api/checkin-seat/bind-mode", json={"minutes": 5},
                       headers=auth).json()["bind_remaining"] > 200
    b = client.get("/api/student/checkin", headers=jia).json()["bind"]
    assert b["mine"] == "" and {"seat": "A2", "taken": False} in b["seats"]
    assert client.post("/api/student/seat-bind", json={"seat": "a2", "host": "LAB-PC"}, headers=jia).json()["seat"] == "A2"
    assert "bind" not in client.get("/api/student/checkin", headers=jia).json(), "绑过了不再弹"
    res = client.post("/api/student/seat-bind", json={"seat": "A2"}, headers=yi)
    assert res.status_code == 409 and "LAB-PC" in res.json()["detail"]
    assert [x["seat"] for x in client.get("/api/checkin-seat/bindings", headers=auth).json()] == ["A2"]
    client.post("/api/checkin-seat/bind-mode", json={"minutes": 0}, headers=auth)

    # 认座规则还是 pick，绑定照样生效（绑定优先）
    client.post(f"/api/classes/{cid}/checkins", json={"minutes": 3}, headers=auth)
    got = client.get("/api/student/checkin", headers=_dev(room["toks"]["签到丙"], device="pc-bind-0001")).json()
    assert got["signed"] == {"seat": "A2", "how": "bind"}
    assert client.delete("/api/checkin-seat/bindings/pc-bind-0001", headers=auth).status_code == 200
    assert client.get("/api/checkin-seat/bindings", headers=auth).json() == []


def test_一个同学最多签两台电脑_电脑坏了换一台再签(client, auth, room, rule):
    cid = room["cid"]
    _stop_all(client, auth, cid)
    k = client.post(f"/api/classes/{cid}/checkins", json={"minutes": 3}, headers=auth).json()
    tok = room["toks"]["签到甲"]
    pc1, pc2, pc3 = (_dev(tok, device=f"pc-two-000{i}") for i in (1, 2, 3))
    assert client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A1"}, headers=pc1).status_code == 200
    # 换到第二台：这台还没签，签到框照样弹，并说明在别处签过
    got = client.get("/api/student/checkin", headers=pc2).json()
    assert got["signed"] is None and got["elsewhere"] == ["A1"]
    assert client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "B1"}, headers=pc2).status_code == 200
    assert client.get("/api/student/checkin", headers=pc1).json()["signed"]["seat"] == "A1", "回第一台也算签过"
    # 第三台：签不了，也不锁住
    got = client.get("/api/student/checkin", headers=pc3).json()
    assert got["signed"]["limit"] is True
    res = client.post("/api/student/checkin", json={"checkin_id": k["id"], "seat": "A2"}, headers=pc3)
    assert res.status_code == 409 and "两台" in res.json()["detail"]
    view = client.get(f"/api/classes/{cid}/checkins/current", headers=auth).json()["checkin"]
    assert view["signed_count"] == 1 and view["absent"] == 2, "两台电脑也只算一个人"
    assert [(s["seat"], s["second"]) for s in view["signed"]] == [("A1", False), ("B1", True)]
    sheet = client.get(f"/api/classes/{cid}/seat-tabs/{k['tab_id']}", headers=auth).json()["sheet"]
    assert sheet["data"][1] == ["A1", "签到甲", "B1", "签到甲"]


def test_已登录没签的带电脑名_快结束提醒的秒数(client, auth, room, rule):
    cid = room["cid"]
    _stop_all(client, auth, cid)
    client.post(f"/api/classes/{cid}/checkins", json={"minutes": 3}, headers=auth)
    got = client.get("/api/student/checkin", **_q(room["toks"]["签到乙"], host="LAB-PC-07", device="pc-rmd-0001")).json()
    assert got["signed"] is None and got["remind"] == 60
    view = client.get(f"/api/classes/{cid}/checkins/current", headers=auth).json()["checkin"]
    yi = next(u for u in view["unsigned"] if u["name"] == "签到乙")
    assert yi["online"] and yi["host"] == "LAB-PC-07" and view["remind"] == 60
