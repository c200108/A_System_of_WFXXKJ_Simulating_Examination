"""在线座次（2.20.0）：区域解析、男女交错、学困生区域、权限、学困生隐私。"""

import pytest

from app.services import seating
from app.services.seating import RangeError, adjacent_same_gender, cells_of, parse_ranges, plan


# ---------------- 区域解析 ----------------
def test_任意多段不连续区域_分隔符和大小写都认():
    got = parse_ranges("B2:B4, a4:c4；A1:b2  D9、E1")
    assert got == [(1, 1, 1, 3), (0, 3, 2, 3), (0, 0, 1, 1), (3, 8, 3, 8), (4, 0, 4, 0)]
    # 反着写也摆正；中文冒号也认
    assert parse_ranges("D5：A1") == [(0, 0, 3, 4)]


def test_座位顺序_按区域先后_区域里先行后列_重复只算一次():
    seats = cells_of(parse_ranges("A1:B2, B2:C2"))
    assert seats == ["A1", "B1", "A2", "B2", "C2"]


def test_合并单元格里的格子跳过():
    assert cells_of(parse_ranges("A1:C1"), skip=["b1"]) == ["A1", "C1"]


@pytest.mark.parametrize("bad", ["B", "12", "A0", "A1:B2:C3", "甲1", "ZZZZ1"])
def test_写错的区域说人话(bad):
    with pytest.raises(RangeError):
        parse_ranges(bad)


def test_区域太大不算():
    with pytest.raises(RangeError):
        cells_of(parse_ranges("A1:Z1000"))


def test_多列字母():
    assert seating.col_index("AA") == 26 and seating.col_letters(26) == "AA"
    assert seating.cell_name(27, 9) == "AB10"


# ---------------- 排座位 ----------------
def people(male=0, female=0, unknown=0, weak=()):
    out, n = [], 0
    for g, k in (("男", male), ("女", female), ("", unknown)):
        for _ in range(k):
            n += 1
            out.append({"id": n, "student_no": f"S{n:03d}", "name": f"学生{n}", "gender": g,
                        "struggling": n in weak})
    return out


def genders(ps):
    return {p["id"]: p["gender"] for p in ps}


def test_人数和座位数一样_每人一个座位():
    ps = people(male=6, female=6)
    got = plan(ps, "A1:D3", seed="x")
    assert got["seats"] == 12 and got["empty"] == 0 and not got["unplaced"]
    assert sorted(a["student_id"] for a in got["assignments"]) == list(range(1, 13))


def test_按学号顺序不打乱():
    got = plan(people(male=3), "A1:C1", shuffle=False)
    assert [a["text"] for a in got["assignments"]] == ["学生1", "学生2", "学生3"]


def test_学号加姓名():
    got = plan(people(male=1), "A1", shuffle=False, content="no_name")
    assert got["assignments"][0]["text"] == "S001 学生1"


def test_同一个种子排出来一样_不同种子不一样():
    ps = people(male=10, female=10)
    a = plan(ps, "A1:E4", seed="s1")["assignments"]
    assert a == plan(ps, "A1:E4", seed="s1")["assignments"]
    assert any(plan(ps, "A1:E4", seed=f"s{i}")["assignments"] != a for i in range(2, 6))


def test_男女交错_人数相等时相邻全是异性():
    ps = people(male=12, female=12)
    for i in range(10):
        got = plan(ps, "A1:F4", alternate=True, seed=f"g{i}")
        assert adjacent_same_gender(got["assignments"], genders(ps)) == 0


def test_男女交错_人数不均也尽量做到():
    ps = people(male=14, female=10)
    got = plan(ps, "A1:F4", alternate=True, seed="u")
    mixed = plan(ps, "A1:F4", alternate=False, seed="u")
    assert adjacent_same_gender(got["assignments"], genders(ps)) < \
        adjacent_same_gender(mixed["assignments"], genders(ps))
    assert len(got["assignments"]) == 24


def test_男女交错_性别没填的照样排上():
    got = plan(people(male=3, female=3, unknown=2), "A1:D2", alternate=True, seed="k")
    assert len(got["assignments"]) == 8


def test_学困生排进固定区域():
    ps = people(male=10, female=10, weak={1, 2, 3, 11})
    got = plan(ps, "A1:E4", zone="A1:B2", struggling_zone=True, seed="w")
    where = {a["student_id"]: a["cell"] for a in got["assignments"]}
    assert {where[i] for i in (1, 2, 3, 11)} == {"A1", "B1", "A2", "B2"}
    assert not got["warnings"]


def test_学困生区域放不下要提示():
    ps = people(male=10, weak={1, 2, 3})
    got = plan(ps, "A1:E2", zone="A1:B1", struggling_zone=True, seed="w")
    where = {a["student_id"]: a["cell"] for a in got["assignments"]}
    assert sum(1 for i in (1, 2, 3) if where[i] in ("A1", "B1")) == 2
    assert any("排到了区域外" in w for w in got["warnings"])
    assert len(got["assignments"]) == 10


def test_学困生区域加男女交错():
    ps = people(male=8, female=8, weak={1, 9})
    got = plan(ps, "A1:D4", zone="A1:B1", struggling_zone=True, alternate=True, seed="z")
    where = {a["student_id"]: a["cell"] for a in got["assignments"]}
    assert {where[1], where[9]} == {"A1", "B1"}


def test_座位多了留空_学生多了列出没排到的():
    got = plan(people(male=3), "A1:E1", seed="e")
    assert got["empty"] == 2 and any("留空" in w for w in got["warnings"])
    got = plan(people(male=6), "A1:D1", seed="e")
    assert len(got["unplaced"]) == 2 and any("没排到" in w for w in got["warnings"])


# ---------------- 接口：权限、隐私 ----------------
def _cid(client, auth, grade, name):
    for c in client.get("/api/classes", headers=auth).json():
        if c["grade"] == grade and c["name"] == name:
            return c["id"]
    return client.post("/api/classes", json={"grade": grade, "name": name}, headers=auth).json()["id"]


@pytest.fixture(scope="module")
def seat_class(client, auth, teacher_auth):
    """甲老师的七年级1班，放几个学生：两个学困生。"""
    cid = _cid(client, auth, "七年级", "1班")
    made = []
    for i, (g, weak) in enumerate([("男", True), ("女", False), ("男", False), ("女", True)]):
        res = client.post("/api/students", json={
            "student_no": f"SEAT{i:03d}", "name": f"座次{i}", "class_id": cid,
            "gender": g, "struggling": weak}, headers=auth)
        assert res.status_code == 200, res.text
        made.append(res.json())
    return {"cid": cid, "students": made}


def test_学困生标记老师看得到_学生自己看不到(client, auth, seat_class):
    rows = client.get("/api/students", params={"class_id": seat_class["cid"]}, headers=auth).json()
    mine = {r["student_no"]: r for r in rows}
    assert mine["SEAT000"]["struggling"] is True and mine["SEAT001"]["struggling"] is False
    tok = client.post("/api/student/login", params={"student_no": "SEAT000", "password": "123456"})
    assert tok.status_code == 200
    assert "struggling" not in tok.json()["student"]
    me = client.get("/api/student/me",
                    headers={"Authorization": f"Bearer {tok.json()['access_token']}"})
    assert "struggling" not in me.json()


def test_批量设学困生和性别(client, auth, seat_class):
    ids = [s["id"] for s in seat_class["students"][:2]]
    assert client.post("/api/students/bulk", json={"ids": ids, "action": "unmark_struggling"},
                       headers=auth).status_code == 200
    assert client.post("/api/students/bulk", json={"ids": ids, "action": "set_female"},
                       headers=auth).status_code == 200
    rows = {r["id"]: r for r in client.get(
        "/api/students", params={"class_id": seat_class["cid"]}, headers=auth).json()}
    assert all(not rows[i]["struggling"] and rows[i]["gender"] == "女" for i in ids)
    # 还原，别影响后面的用例
    client.post("/api/students/bulk", json={"ids": ids[:1], "action": "mark_struggling"}, headers=auth)
    client.post("/api/students/bulk", json={"ids": ids[:1], "action": "set_male"}, headers=auth)
    assert client.patch(f"/api/students/{ids[1]}", json={"struggling": False},
                        headers=auth).json()["struggling"] is False


def test_本班老师能排能存_别的老师只能看(client, teacher_auth, teacher2_auth, seat_class):
    cid = seat_class["cid"]
    got = client.post(f"/api/classes/{cid}/seat-plan", json={
        "ranges": "B2:C3", "zone": "B2:C2", "struggling_zone": True, "alternate_gender": True,
        "seed": "t"}, headers=teacher_auth)
    assert got.status_code == 200, got.text
    assert len(got.json()["assignments"]) >= 4

    sheet = {"data": [["讲台"], ["", "座次0"]], "mergeCells": {"A1": [3, 1]}}
    res = client.put(f"/api/classes/{cid}/seat-sheet", json={"sheet": sheet}, headers=teacher_auth)
    assert res.status_code == 200 and res.json()["has_seat_sheet"] is True

    mine = client.get(f"/api/classes/{cid}/seat-sheet", headers=teacher_auth).json()
    assert mine["can_edit"] and mine["sheet"] == sheet and mine["students"]

    other = client.get(f"/api/classes/{cid}/seat-sheet", headers=teacher2_auth).json()
    assert other["can_edit"] is False and other["sheet"] == sheet
    assert other["students"] == [], "别的班的老师拿不到名单（含学困生标记）"
    assert client.put(f"/api/classes/{cid}/seat-sheet", json={"sheet": {}},
                      headers=teacher2_auth).status_code == 403
    assert client.post(f"/api/classes/{cid}/seat-plan", json={"ranges": "A1"},
                       headers=teacher2_auth).status_code == 403


def test_区域写错返回400(client, teacher_auth, seat_class):
    res = client.post(f"/api/classes/{seat_class['cid']}/seat-plan", json={"ranges": "甲乙"},
                      headers=teacher_auth)
    assert res.status_code == 400 and "单元格" in res.json()["detail"]


def test_座次表太大不收(client, teacher_auth, seat_class):
    big = {"data": [["x" * 1000] * 100] * 30}
    res = client.put(f"/api/classes/{seat_class['cid']}/seat-sheet", json={"sheet": big},
                     headers=teacher_auth)
    assert res.status_code == 413


def test_清掉在线座次(client, teacher_auth, seat_class):
    res = client.delete(f"/api/classes/{seat_class['cid']}/seat-sheet", headers=teacher_auth)
    assert res.status_code == 200 and res.json()["has_seat_sheet"] is False


def test_导入名单第五列学困生(client, auth, seat_class):
    from app.services.roster import is_struggling
    assert is_struggling("是") and is_struggling(" √ ") and not is_struggling("") \
        and not is_struggling("否")
    cid = seat_class["cid"]
    res = client.post("/api/students/batch", json={
        "class_id": cid, "text": "SEAT900\t导入甲\t七年级1班\t男\t是\nSEAT901\t导入乙\t七年级1班\t女"},
        headers=auth)
    assert res.status_code == 200, res.text
    rows = {r["student_no"]: r for r in client.get(
        "/api/students", params={"class_id": cid}, headers=auth).json()}
    assert rows["SEAT900"]["struggling"] is True and rows["SEAT901"]["struggling"] is False
