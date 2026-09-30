"""打字学情（2.12.0）：分析页的统计和结论、成绩页的筛选排序分页、批量删除。"""

from datetime import datetime, timedelta
from types import SimpleNamespace

import io

import pytest
from openpyxl import load_workbook

from app.services import typing_analysis as TA

T0 = datetime(2026, 9, 1, 8, 0)


def rec(cls, name, speed, acc, stars=2, module="中文", diff="简单", day=0, i=[0]):
    i[0] += 1
    return SimpleNamespace(id=i[0], student_class=cls, student_name=name, module=module,
                           difficulty=diff, speed=speed, accuracy=acc, duration=60,
                           typed_chars=speed, stars=stars, created_at=T0 + timedelta(days=day, minutes=i[0]))


# ================================================================ 纯计算
def test_汇总数字():
    rows = [rec("一班", "甲", 30, 90), rec("一班", "甲", 40, 96, 3), rec("二班", "乙", 20, 70, 1)]
    r = TA.analyze(rows, "中文")
    s = r["summary"]
    assert (s["count"], s["students"], s["per_student"]) == (3, 2, 1.5)
    assert (s["avg_speed"], s["median_speed"], s["max_speed"]) == (30.0, 30.0, 40)
    assert s["reach_rate"] == 66.7 and s["three_star_rate"] == 33.3
    assert [b["count"] for b in r["accuracy_bands"]] == [1, 1, 0, 1, 0, 0]


def test_班级先按学生平均_练得多的拽不走全班():
    rows = [rec("一班", "勤", 60, 95) for _ in range(9)] + [rec("一班", "懒", 20, 95)]
    c = TA.analyze(rows, "中文")["classes"][0]
    assert c["avg_speed"] == 40.0, "两个学生各算一票：(60+20)/2"
    assert (c["students"], c["count"], c["per_student"]) == (2, 10, 5.0)


def test_参与率要有名单():
    r = TA.analyze([rec("一班", "甲", 30, 90)], "中文", roster={"一班": 40})
    assert r["classes"][0]["participation"] == 2.5
    assert any("参与率最低的是 一班" in t and "还有 39 人没练过" in t for t in r["conclusions"])


def test_进步_最后三次减最初三次():
    rows = [rec("一班", "甲", v, 90, day=d) for d, v in enumerate((20, 22, 24, 40, 42, 44))]
    st = TA.analyze(rows, "中文")["ranking"][0]
    assert st["progress"] == 20.0 and st["best_speed"] == 44
    assert TA.analyze(rows[:3], "中文")["ranking"][0]["progress"] is None, "不满 4 次不算"


def test_键盘和全部模块不谈速度():
    rows = [rec("一班", "甲", 0, 90, module="键盘"), rec("一班", "甲", 30, 90)]
    for module in ("键盘", ""):
        r = TA.analyze(rows, module)
        assert r["speedy"] is False and r["summary"]["avg_speed"] is None and not r["speed_bands"]
    assert any("请在上方选「中文」或「英文」" in t for t in TA.analyze(rows, "")["conclusions"])


def test_结论_求快不求准():
    rows = [rec("一班", f"快{i}", 60, 60, 0) for i in range(5)] + \
           [rec("一班", f"稳{i}", 30, 95) for i in range(5)]
    assert any("先准后快" in t for t in TA.analyze(rows, "中文")["conclusions"])


def test_结论_走势():
    rows = [rec("一班", "甲", 20 + d * 5, 90, day=d) for d in range(6)]
    assert any("后半段平均速度比前半段提高" in t for t in TA.analyze(rows, "中文")["conclusions"])


def test_走势没人练的日子也列出来():
    rows = [rec("一班", "甲", 30, 90, day=0), rec("一班", "甲", 30, 90, day=4)]
    pts = TA.analyze(rows, "中文")["trend"]["points"]
    assert [p["count"] for p in pts] == [1, 0, 0, 0, 1]


def test_学生对比带每次的点():
    rows = [rec("一班", "甲", 30, 90), rec("一班", "甲", 35, 92), rec("二班", "乙", 25, 80)]
    r = TA.analyze(rows, "中文", {"kind": "students"})
    assert [len(c["points"]) for c in r["compare"]] == [2, 1]
    assert any(t.startswith("甲（一班）：练了 2 次") for t in r["conclusions"])


def test_没有记录():
    assert "还没有打字练习记录" in TA.analyze([], "中文")["conclusions"][0]


# ================================================================ 接口
def _submit(client, cls, name, typed, correct, module="中文", diff="简单"):
    res = client.post("/api/typing/records", json={
        "student_name": name, "student_class": cls, "module": module, "difficulty": diff,
        "typed_chars": typed, "correct_chars": correct, "duration": 60})
    assert res.status_code == 200, res.text


@pytest.fixture(scope="module")
def seeded(client):
    # 模块级的夹具比每个用例的开关先跑：名单比对、一分钟一次这些得自己关
    from app.siteconfig import site
    with pytest.MonkeyPatch.context() as mp:
        for key in ("require_roster", "min_done_ratio", "submit_interval_sec"):
            mp.setattr(site.typing, key, 0)
        _seed(client)


def _seed(client):
    for cls, name, typed, correct in (("析一班", "赵", 40, 38), ("析一班", "赵", 50, 49),
                                      ("析一班", "钱", 30, 20), ("析二班", "孙", 60, 57)):
        _submit(client, cls, name, typed, correct)
    _submit(client, "析二班", "孙", 80, 80, module="键盘")


def _search(client, auth, **params):
    res = client.get("/api/typing/records/search", params=params, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def test_筛选_排序_分页(client, auth, seeded):
    got = _search(client, auth, student_class="析一班", sort="speed", order="desc")
    assert got["total"] == 3 and [x["speed"] for x in got["items"]] == [49, 38, 20]
    got = _search(client, auth, student_class="析一班", sort="speed", order="asc", page=2, page_size=2)
    assert got["total"] == 3 and [x["speed"] for x in got["items"]] == [49]
    assert _search(client, auth, keyword="孙", module="键盘")["total"] == 1
    today = datetime.now().date().isoformat()
    assert _search(client, auth, student_class="析二班", date_from=today, date_to=today)["total"] == 2
    assert _search(client, auth, student_class="析二班", date_to="2000-01-01")["total"] == 0


def test_分析接口_按班级和学生对比(client, auth, seeded):
    res = client.get("/api/typing/analysis", params={"module": "中文", "classes": ["析一班"]}, headers=auth)
    assert res.status_code == 200, res.text
    r = res.json()
    assert r["scope"]["kind"] == "classes" and r["summary"]["count"] == 3 and r["summary"]["students"] == 2
    assert "析一班" in r["options"]["classes"] and r["conclusions"]
    r = client.get("/api/typing/analysis", params={"module": "中文", "students": ["析一班|赵", "析二班|孙"]},
                   headers=auth).json()
    assert [c["name"] for c in r["compare"]] == ["赵", "孙"]
    assert client.get("/api/typing/analysis").status_code == 401


def test_导出按筛选(client, auth, seeded):
    raw = client.get("/api/typing/export.xlsx", params={"student_class": "析二班"}, headers=auth).content
    names = {r[0] for r in load_workbook(io.BytesIO(raw)).active.iter_rows(min_row=2, values_only=True)}
    assert names == {"孙"}


def test_批量删除要删除权(client, auth, teacher_auth, seeded):
    ids = [x["id"] for x in _search(client, auth, student_class="析一班", keyword="钱")["items"]]
    assert client.post("/api/typing/records/delete", json={"ids": ids}, headers=teacher_auth).status_code == 403
    res = client.post("/api/typing/records/delete", json={"ids": ids}, headers=auth)
    assert res.json()["deleted"] == 1
    assert _search(client, auth, student_class="析一班")["total"] == 2


def test_按筛选删除_只删看到的(client, auth, seeded):
    res = client.delete("/api/typing/records", params={"student_class": "析二班", "module": "键盘"}, headers=auth)
    assert res.json()["deleted"] == 1
    assert _search(client, auth, student_class="析二班")["total"] == 1, "中文那条还在"
