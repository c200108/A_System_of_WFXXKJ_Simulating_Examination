"""拼音登录、拼音列、班干部。

整个测试会话共用一个库，别的测试也建学生，所以这里的姓名都挑生僻字，拼音不和别人撞。
"""

from app.services import pinyin


# ---------------------------------------------------------------- 纯函数
def test_name_pinyin_rules():
    assert pinyin.name_pinyin("张三") == "zhangsan"
    assert pinyin.name_pinyin(" 吕布 ") == "lvbu"                 # ü 写成 v
    assert pinyin.name_pinyin("单雄信") == "shanxiongxin"          # 姓氏多音字
    assert pinyin.name_pinyin("曾乐") == "zengle"                  # 只改姓，名照常读
    assert pinyin.name_pinyin("尉迟恭") == "yuchigong"             # 复姓
    assert pinyin.name_pinyin("阿依古丽·买买提") == "ayigulimaimaiti"
    assert pinyin.name_pinyin("") == ""


def test_norm_pinyin():
    assert pinyin.norm_pinyin(" Zhang San ") == "zhangsan"
    assert pinyin.norm_pinyin("lüe") == "lve"
    assert pinyin.norm_pinyin("张三") == ""


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


def test_new_student_gets_pinyin_and_logs_in_with_it(client, auth):
    got = _mk(client, auth, "28010001", "犇骉")
    assert got["pinyin"] == "benbiao"
    res = _login(client, "benbiao")
    assert res.status_code == 200, res.text
    assert res.json()["student"]["student_no"] == "28010001"
    # 大小写、空格不讲究
    assert _login(client, " Ben Biao ").status_code == 200
    # 学号那条路照旧：学号 + 学号初始密码也行
    assert _login(client, "28010001", "28010001").status_code == 200
    assert _login(client, "benbiao", "28010001").status_code == 400


def test_login_classes_are_public(client, auth):
    cid = _class_id(client, auth, "八年级", "5班")
    _mk(client, auth, "28010101", "鹬鹭", "八年级", "5班")
    got = client.get("/api/student/classes").json()
    assert {"id": cid, "display": "八年级5班"} in got


def test_duplicate_pinyin_picks_by_class(client, auth):
    c1 = _class_id(client, auth, "八年级", "1班")
    c2 = _class_id(client, auth, "九年级", "2班")
    _mk(client, auth, "28010011", "鑫淼", "八年级", "1班")
    _mk(client, auth, "28010012", "鑫渺", "九年级", "2班")
    # 没选班级：分不出是谁，提示先选班级
    res = _login(client, "xinmiao")
    assert res.status_code == 409 and "选择班级" in res.json()["detail"]
    a = _login(client, "xinmiao", class_id=c1)
    b = _login(client, "xinmiao", class_id=c2)
    assert a.status_code == 200 and a.json()["student"]["student_no"] == "28010011"
    assert b.status_code == 200 and b.json()["student"]["student_no"] == "28010012"
    # 选错班
    other = _class_id(client, auth, "七年级", "3班")
    assert _login(client, "xinmiao", class_id=other).status_code == 400
    # 不再认「拼音 + 年级班级」
    assert _login(client, "xinmiao0801").status_code == 400
    # 学号不看班级
    assert _login(client, "28010012", "28010012", class_id=c1).status_code == 200


def test_disabled_duplicate_does_not_block(client, auth):
    a = _mk(client, auth, "28010021", "燚垚")
    b = _mk(client, auth, "28010022", "燚尧", "九年级", "2班")
    assert _login(client, "yiyao").status_code == 409
    res = client.post("/api/students/bulk", json={"ids": [b["id"]], "action": "disable"},
                      headers=auth)
    assert res.status_code == 200
    ok = _login(client, "yiyao")
    assert ok.status_code == 200 and ok.json()["student"]["id"] == a["id"]


def test_same_class_same_pinyin_falls_back_to_student_no(client, auth):
    cid = _class_id(client, auth, "八年级", "1班")
    _mk(client, auth, "28010031", "龘靐", "八年级", "1班")
    _mk(client, auth, "28010032", "龘靐", "八年级", "1班")
    res = _login(client, "dabing", class_id=cid)
    assert res.status_code == 409 and "学号" in res.json()["detail"]
    assert _login(client, "28010032").status_code == 200


def test_teacher_can_fix_pinyin(client, auth):
    row = _mk(client, auth, "28010041", "乐嫣嫣")        # 姓按 yue 读
    assert row["pinyin"] == "yueyanyan"
    res = client.patch(f"/api/students/{row['id']}", json={"pinyin": "Le Yanyan"}, headers=auth)
    assert res.status_code == 200 and res.json()["pinyin"] == "leyanyan"
    assert _login(client, "leyanyan").status_code == 200
    bad = client.patch(f"/api/students/{row['id']}", json={"pinyin": "乐"}, headers=auth)
    assert bad.status_code == 400
    # 改了名字，拼音跟着重算
    res = client.patch(f"/api/students/{row['id']}", json={"name": "毓嫣嫣"}, headers=auth)
    assert res.json()["pinyin"] == "yuyanyan"


def test_import_fills_pinyin(client, auth):
    cid = _class_id(client, auth)
    res = client.post("/api/students/batch",
                      json={"class_id": cid, "text": "28010051\t璟翊\n28010052\t玥瑶"},
                      headers=auth)
    assert res.status_code == 200 and res.json()["added"] == 2
    rows = client.get("/api/students", params={"keyword": "2801005"}, headers=auth).json()
    assert {r["pinyin"] for r in rows} == {"jingyi", "yueyao"}


def test_export_has_pinyin_columns(client, auth):
    from io import BytesIO
    from openpyxl import load_workbook
    _mk(client, auth, "28010061", "骁骐")
    res = client.get("/api/students/export.xlsx", params={"keyword": "28010061"}, headers=auth)
    ws = load_workbook(BytesIO(res.content)).active
    head = [c.value for c in ws[1]]
    assert head[:6] == ["学号", "姓名", "班级", "性别", "拼音", "班干部"]
    assert [c.value for c in ws[2]][4] == "xiaoqi"


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


def test_old_chinese_name_login_still_works(client, auth):
    """4.10.0 的姓名登录版 exe 还在机房里，填中文姓名照样能登。"""
    _mk(client, auth, "28010081", "翀翾")
    assert _login(client, "翀翾").status_code == 200


def test_desk_roster_carries_pinyin(client, auth):
    from app.database import SessionLocal
    from app.models import Exam
    from app.routers.desk import _roster
    _mk(client, auth, "28010091", "霂霖", "七年级", "9班")
    with SessionLocal() as db:
        exam = Exam(title="名单测试", token="pinyin-roster", paper_id=None,
                    target_classes="七年级9班")
        got = {r["no"]: r for r in _roster(db, exam)}
    assert got["28010091"]["py"] == "mulin" and got["28010091"]["cls"] == "七年级9班"
    assert "acct" not in got["28010091"]
