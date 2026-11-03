"""教师端「API」板块（2.16.0）：建 API、第三方送数据的各种格式、教师隔离、统计、学情汇总。

甲老师带七年级1班，乙老师带七年级2班（conftest 里建的）。
"""

import io
import json

import pytest
from openpyxl import load_workbook


def _cid(client, auth, display):
    return next(c["id"] for c in client.get("/api/classes", headers=auth).json() if c["display"] == display)


@pytest.fixture(scope="module")
def kids(client, auth, teacher_auth, teacher2_auth):
    c1 = _cid(client, auth, "七年级1班")
    ids = {}
    for no, name in (("D1001", "数据学生一"), ("D1002", "数据学生二"), ("D1003", "数据学生三")):
        res = client.post("/api/students", json={"student_no": no, "name": name, "class_id": c1}, headers=auth)
        assert res.status_code == 200, res.text
        ids[no] = res.json()["id"]
    return {"c1": c1, "ids": ids}


def _new(client, headers, name="第3课 课堂练习", template="answer"):
    res = client.post("/api/data-apis", json={"name": name, "description": "测试", "template": template},
                      headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _send(client, api, body, **kw):
    headers = {"X-Api-Key": api["write_token"], **kw.pop("headers", {})}
    return client.post(f"/api/hook/{api['key']}", json=body, headers=headers, **kw)


# ---------------------------------------------------------------- 建、隔离
def test_老师之间互相看不到_管理员看全部(client, auth, teacher_auth, teacher2_auth):
    a = _new(client, teacher_auth, "甲的API")
    b = _new(client, teacher2_auth, "乙的API")
    adm = _new(client, auth, "管理员的API")
    mine = {x["id"] for x in client.get("/api/data-apis", headers=teacher_auth).json()["items"]}
    assert a["id"] in mine and b["id"] not in mine and adm["id"] not in mine, "管理员建的老师也看不到"
    for path in ("", "/records", "/stats", "/sources", "/export"):
        assert client.get(f"/api/data-apis/{b['id']}{path}", headers=teacher_auth).status_code == 404
    assert client.put(f"/api/data-apis/{b['id']}", json={"name": "x"}, headers=teacher_auth).status_code == 404
    assert client.delete(f"/api/data-apis/{b['id']}", headers=teacher_auth).status_code == 404
    every = client.get("/api/data-apis", headers=auth).json()
    got = {x["id"] for x in every["items"]}
    assert {a["id"], b["id"], adm["id"]} <= got
    assert "teachers" in every
    only_b = {x["id"] for x in client.get("/api/data-apis", params={"owner_id": b["owner_id"]},
                                          headers=auth).json()["items"]}
    assert b["id"] in only_b and a["id"] not in only_b


def test_写入密钥只能写自己那个API(client, teacher_auth, teacher2_auth):
    a = _new(client, teacher_auth)
    b = _new(client, teacher2_auth)
    res = client.post(f"/api/hook/{b['key']}", json={"x": 1}, headers={"X-Api-Key": a["write_token"]})
    assert res.status_code == 401 and res.json()["code"] == "TOKEN_INVALID"
    assert client.post(f"/api/hook/{a['key']}", json={"x": 1}).json()["code"] == "TOKEN_MISSING"
    assert client.post("/api/hook/nosuchkey000", json={"x": 1},
                       headers={"X-Api-Key": a["write_token"]}).status_code == 404
    # 写入密钥拿去读记录不行
    r = client.get(f"/api/hook/{a['key']}/records", headers={"X-Api-Key": a["write_token"]})
    assert r.status_code in (401, 403)


def test_转给另一位老师只有管理员能做(client, auth, teacher_auth, teacher2_auth):
    a = _new(client, teacher_auth)
    b_owner = _new(client, teacher2_auth)["owner_id"]
    assert client.post(f"/api/data-apis/{a['id']}/transfer", json={"owner_id": b_owner},
                       headers=teacher_auth).status_code == 403
    assert client.post(f"/api/data-apis/{a['id']}/transfer", json={"owner_id": b_owner},
                       headers=auth).status_code == 200
    assert client.get(f"/api/data-apis/{a['id']}", headers=teacher_auth).status_code == 404
    assert client.get(f"/api/data-apis/{a['id']}", headers=teacher2_auth).status_code == 200


# ---------------------------------------------------------------- 各种格式
def test_标准信封_学号对上名单(client, teacher_auth, kids):
    api = _new(client, teacher_auth)
    res = _send(client, api, {
        "client_id": "c-1", "type": "answer", "activity": {"id": "L3", "name": "第3课"},
        "student": {"no": "D1001", "name": "数据学生一"}, "score": 8, "max_score": 10,
        "answers": [{"q": "1", "answer": "B", "correct": True, "score": 5, "max": 5},
                    {"q": "2", "answer": "A", "correct": False, "score": 3, "max": 5}],
        "page": "https://teach.example.com/l3/index.html?from=qq",
    })
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["ok"] and body["student_matched"] and not body["duplicate"]
    again = _send(client, api, {"client_id": "c-1", "score": 1})
    assert again.status_code == 200 and again.json()["duplicate"] and again.json()["id"] == body["id"]

    rows = client.get(f"/api/data-apis/{api['id']}/records", headers=teacher_auth).json()
    assert rows["total"] == 1
    r = rows["items"][0]
    assert r["student"]["class"] == "七年级1班", "对上名单后班级从名单补"
    assert r["page"] == "https://teach.example.com/l3/index.html", "来源网页去掉 ? 后面"
    assert r["score"] == 8 and r["student_matched"]


def test_随便什么JSON都收_认别名(client, teacher_auth, kids):
    api = _new(client, teacher_auth, template="custom")
    res = _send(client, api, {"学号": "D1002", "姓名": "数据学生二", "得分": "9分", "我的作品": "小车",
                              "detail": {"step": 3, "clicks": 12}})
    assert res.status_code == 201 and res.json()["student_matched"]
    rows = client.get(f"/api/data-apis/{api['id']}/records", headers=teacher_auth).json()
    r = rows["items"][0]
    assert r["score"] == 9 and r["type"] == "data"
    assert r["fields"]["我的作品"] == "小车" and r["fields"]["detail.step"] == 3
    assert any(c["key"] == "我的作品" for c in rows["columns"])


def test_名单里没有的学生只在API里显示(client, teacher_auth):
    api = _new(client, teacher_auth)
    res = _send(client, api, {"student": {"no": "X999", "name": "外校学生"}, "score": 5})
    assert res.status_code == 201 and res.json()["student_matched"] is False


def test_批量数组_sendBeacon_表单_GET(client, teacher_auth):
    api = _new(client, teacher_auth, template="survey")
    res = _send(client, api, [{"name": "甲", "q1": "A"}, {"name": "乙", "q1": "B"}, {"name": "丙"}])
    assert res.status_code == 200 and res.json()["accepted"] == 3

    beacon = json.dumps({"name": "丁", "_token": api["write_token"]})
    res = client.post(f"/api/hook/{api['key']}", content=beacon, headers={"Content-Type": "text/plain"})
    assert res.status_code == 201, res.text

    res = client.post(f"/api/hook/{api['key']}", data={"姓名": "戊", "班级": "七年级1班", "_token": api["write_token"],
                                                       "_redirect": "https://teach.example.com/done.html"},
                      follow_redirects=False)
    assert res.status_code == 303 and res.headers["location"].endswith("?wfxx=ok")
    res = client.post(f"/api/hook/{api['key']}?token={api['write_token']}", data={"姓名": "己"},
                      headers={"Accept": "text/html"})
    assert res.status_code == 200 and "提交成功" in res.text

    assert client.get(f"/api/hook/{api['key']}?token={api['write_token']}&name=x").status_code == 405
    client.put(f"/api/data-apis/{api['id']}", json={"allow_get": True}, headers=teacher_auth)
    assert client.get(f"/api/hook/{api['key']}?token={api['write_token']}&name=x").status_code == 201

    rows = client.get(f"/api/data-apis/{api['id']}/records", headers=teacher_auth).json()
    assert rows["total"] == 7
    stored = [json.dumps(i["payload"], ensure_ascii=False) for i in rows["items"]]
    assert not any(api["write_token"] in s for s in stored), "密钥不能存进数据里"


def test_格式错误和超限(client, teacher_auth, monkeypatch):
    api = _new(client, teacher_auth)
    h = {"X-Api-Key": api["write_token"], "Content-Type": "application/json"}
    assert client.post(f"/api/hook/{api['key']}", content="{bad", headers=h).json()["code"] == "BAD_JSON"
    assert client.post(f"/api/hook/{api['key']}", content="", headers=h).json()["code"] == "EMPTY"
    big = {"x": "字" * 100_000}
    assert _send(client, api, big).json()["code"] == "PAYLOAD_TOO_LARGE"
    from app.services import dataapi
    monkeypatch.setattr(dataapi, "MAX_RECORDS", 1)
    assert _send(client, api, {"a": 1}).status_code == 201
    r = _send(client, api, {"a": 2})
    assert r.status_code == 507 and r.json()["code"] == "QUOTA_FULL"


def test_暂停_时间段_来源白名单(client, teacher_auth):
    api = _new(client, teacher_auth)
    url = f"/api/data-apis/{api['id']}"
    client.put(url, json={"status": "paused"}, headers=teacher_auth)
    assert _send(client, api, {"a": 1}).json()["code"] == "PAUSED"
    client.put(url, json={"status": "active", "accept_until": "2000-01-01T00:00:00"}, headers=teacher_auth)
    assert _send(client, api, {"a": 1}).json()["code"] == "OUT_OF_WINDOW"
    client.put(url, json={"clear_window": True, "allowed_origins": "https://teach.example.com/"},
               headers=teacher_auth)
    assert _send(client, api, {"a": 1}, headers={"Origin": "https://evil.example.com"}).status_code == 403
    assert _send(client, api, {"a": 1}, headers={"Origin": "https://teach.example.com"}).status_code == 201
    assert _send(client, api, {"a": 1}).status_code == 201, "服务器端程序不带 Origin，只认密钥"
    bad = client.put(url, json={"allowed_origins": "teach.example.com"}, headers=teacher_auth)
    assert bad.status_code == 400


def test_跨域预检和响应头(client, teacher_auth):
    api = _new(client, teacher_auth)
    pre = client.options(f"/api/hook/{api['key']}", headers={
        "Origin": "https://teach.example.com", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-api-key"})
    assert pre.status_code == 204
    assert pre.headers["access-control-allow-origin"] == "https://teach.example.com"
    assert "X-Api-Key" in pre.headers["access-control-allow-headers"]
    res = _send(client, api, {"a": 1}, headers={"Origin": "https://teach.example.com"})
    assert res.headers["access-control-allow-origin"] == "https://teach.example.com"
    assert "access-control-allow-credentials" not in res.headers
    # 别的接口不受影响：仍然只认全站白名单
    other = client.options("/api/data-apis", headers={"Origin": "https://teach.example.com",
                                                      "Access-Control-Request-Method": "GET"})
    assert other.headers.get("access-control-allow-origin") != "https://teach.example.com"


def test_sdk能下载(client):
    res = client.get("/api/hook/sdk.js")
    assert res.status_code == 200 and "WFXX" in res.text and "javascript" in res.headers["content-type"]


def test_只算最新一条(client, teacher_auth):
    api = _new(client, teacher_auth)
    for s in (3, 6, 9):
        _send(client, api, {"student": {"no": "Z1", "name": "张"}, "activity": "任务1", "score": s, "max_score": 10})
    st = client.get(f"/api/data-apis/{api['id']}/stats", headers=teacher_auth).json()
    assert st["records"] == 3
    client.put(f"/api/data-apis/{api['id']}", json={"dedupe": "latest"}, headers=teacher_auth)
    st = client.get(f"/api/data-apis/{api['id']}/stats", headers=teacher_auth).json()
    assert st["records"] == 1 and st["avg_score"] == 9
    _send(client, api, {"student": {"no": "Z1"}, "activity": "任务1", "score": 10, "max_score": 10})
    st = client.get(f"/api/data-apis/{api['id']}/stats", headers=teacher_auth).json()
    assert st["records"] == 1 and st["avg_score"] == 10


# ---------------------------------------------------------------- 统计、读取、导出、删除
def test_大图统计_自评互评(client, teacher_auth, kids):
    api = _new(client, teacher_auth, template="peer_eval")
    client.put(f"/api/data-apis/{api['id']}", json={"class_ids": [kids["c1"]]}, headers=teacher_auth)
    _send(client, api, {"type": "self_eval", "student": {"no": "D1001"},
                        "ratings": [{"item": "合作", "score": 5, "max": 5}, {"item": "表达", "score": 3, "max": 5}],
                        "comment": "我觉得这次合作很顺利"})
    _send(client, api, {"type": "peer_eval", "student": {"no": "D1002"}, "target": {"no": "D1001", "name": "数据学生一"},
                        "ratings": {"合作": 4, "表达": 4}, "comment": "合作很好"})
    _send(client, api, {"type": "answer", "student": {"no": "D1003"}, "score": 6, "max_score": 10,
                        "answers": [{"q": "1", "correct": True}, {"q": "2", "correct": False, "answer": "C"}]})
    st = client.get(f"/api/data-apis/{api['id']}/stats", headers=teacher_auth).json()
    assert st["records"] == 3 and st["expected"] >= 3 and st["submitted_roster"] == 3
    radar = {d["item"]: d for d in st["radar"]}
    assert radar["合作"]["self"] == 100 and radar["合作"]["peer"] == 4
    assert st["peer_matrix"]["cells"]
    q = {x["q"]: x for x in st["questions"]}
    assert q["1"]["rate"] == 100 and q["2"]["rate"] == 0 and q["2"]["wrong"]
    assert any(w == "合作" for w, _ in st["keywords"])
    src = client.get(f"/api/data-apis/{api['id']}/sources", headers=teacher_auth).json()
    assert sum(s["records"] for s in src["items"]) == 3


def test_读取接口和网页汇总(client, teacher_auth):
    api = _new(client, teacher_auth)
    _send(client, api, {"student": {"name": "甲"}, "score": 8, "max_score": 10})
    base = f"/api/hook/{api['key']}"
    assert client.get(f"{base}/records", headers={"X-Api-Key": "x"}).json()["code"] == "READ_DISABLED"
    on = client.post(f"/api/data-apis/{api['id']}/rotate-token", json={"which": "read"}, headers=teacher_auth).json()
    rec = client.get(f"{base}/records", headers={"Authorization": f"Bearer {on['read_token']}"}).json()
    assert rec["ok"] and rec["records"][0]["student"]["name"] == "甲"
    assert client.get(f"{base}/summary", headers={"X-Api-Key": api["write_token"]}).status_code == 401
    client.put(f"/api/data-apis/{api['id']}", json={"public_summary": True}, headers=teacher_auth)
    sm = client.get(f"{base}/summary", headers={"X-Api-Key": api["write_token"]}).json()
    assert sm["ok"] and sm["avg_rate"] == 80 and "甲" not in json.dumps(sm, ensure_ascii=False)


def test_导出_标记无效_删除进回收站(client, teacher_auth):
    api = _new(client, teacher_auth, "导出测试")
    ids = [_send(client, api, {"student": {"name": n}, "score": 5, "备注": "x"}).json()["id"] for n in "甲乙丙"]
    res = client.get(f"/api/data-apis/{api['id']}/export", headers=teacher_auth)
    ws = load_workbook(io.BytesIO(res.content)).active
    assert ws.max_row == 4 and "备注" in [c.value for c in ws[1]]
    csv_ = client.get(f"/api/data-apis/{api['id']}/export", params={"format": "csv"}, headers=teacher_auth)
    assert csv_.content.startswith("﻿".encode())

    client.patch(f"/api/data-apis/{api['id']}/records", json={"ids": ids[:1], "flag": "invalid"}, headers=teacher_auth)
    assert client.get(f"/api/data-apis/{api['id']}/stats", headers=teacher_auth).json()["records"] == 2
    d = client.post(f"/api/data-apis/{api['id']}/records/delete", json={"ids": ids[1:2]}, headers=teacher_auth)
    assert d.json()["count"] == 1
    assert client.get(f"/api/data-apis/{api['id']}", headers=teacher_auth).json()["record_count"] == 2

    assert client.delete(f"/api/data-apis/{api['id']}", headers=teacher_auth).status_code == 200
    bin_ = client.get("/api/recycle", headers=teacher_auth).json()["items"]
    item = next(i for i in bin_ if i["kind"] == "data_api" and "导出测试" in i["title"])
    r = client.post("/api/recycle/restore", json={"ids": [item["id"]]}, headers=teacher_auth).json()
    assert r["restored"] == 1, r
    back = client.get(f"/api/data-apis/{api['id']}/records", headers=teacher_auth).json()
    assert back["total"] == 2


def test_测试数据按钮(client, teacher_auth):
    api = _new(client, teacher_auth)
    assert client.post(f"/api/data-apis/{api['id']}/test", headers=teacher_auth).json()["ok"]
    assert client.get(f"/api/data-apis/{api['id']}/records", headers=teacher_auth).json()["total"] == 1


# ---------------------------------------------------------------- 学情
def test_学情汇总第三方数据_只算自己的API(client, auth, teacher_auth, teacher2_auth, kids):
    sid = kids["ids"]["D1001"]
    mine = _new(client, teacher_auth, "甲老师的学情API", template="self_eval")
    _send(client, mine, {"type": "self_eval", "student": {"no": "D1001"},
                         "ratings": [{"item": "专注", "score": 4, "max": 5}]})
    other = _new(client, teacher2_auth, "乙老师的API")
    _send(client, other, {"student": {"no": "D1001"}, "score": 1})

    got = client.get(f"/api/students/{sid}/insight", headers=teacher_auth).json()
    names = {a["name"] for a in got["web"]["apis"]}
    assert "甲老师的学情API" in names and "乙老师的API" not in names
    assert any(d["item"] == "专注" and d["self"] == 80 for d in got["web"]["dimensions"])
    assert {"exams", "typing", "student"} <= set(got)

    every = client.get(f"/api/students/{sid}/insight", headers=auth).json()
    assert "乙老师的API" in {a["name"] for a in every["web"]["apis"]}, "管理员看全部"
    assert client.get(f"/api/students/{sid}/insight", headers=teacher2_auth).status_code == 404, \
        "别的班的学生看不到学情"


def test_学情里的考试和排名(client, auth, teacher_auth, kids):
    """借用学生平台交卷，看学情里的名次。"""
    from app.database import SessionLocal
    from app.models import Exam, ExamSubmission, Paper

    with SessionLocal() as db:
        me_id = next(u["id"] for u in client.get("/api/auth/users", headers=auth).json() if u["username"] == "teacher_a")
        p = Paper(title="学情卷", config_json="{}", created_by=me_id)
        db.add(p)
        db.flush()
        e = Exam(paper_id=p.id, title="学情小测", token="insight-tok-1", created_by=me_id)
        db.add(e)
        db.flush()
        for no, sc in (("D1001", 80), ("D1002", 90), ("D1003", 70)):
            db.add(ExamSubmission(exam_id=e.id, student_id=kids["ids"][no], student_no=no, student_name=no,
                                  student_class="七年级1班", score=sc, objective_total=100))
        db.commit()
    got = client.get(f"/api/students/{kids['ids']['D1001']}/insight", headers=teacher_auth).json()["exams"]
    item = next(i for i in got["items"] if i["title"] == "学情小测")
    assert item["rank"] == 2 and item["takers"] == 3 and item["class_rank"] == 2 and item["rate"] == 80
    assert got["class_rank"] is not None


# ---------------------------------------------------------------- AI 专用提示词（2.16.1）
def _prompt(client, headers, api, **params):
    res = client.get(f"/api/data-apis/{api['id']}/ai-prompt", params=params, headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


def _example(prompt):
    """提示词第四节那份完整 JSON 例子。"""
    return json.loads(prompt.split("```json\n", 1)[1].split("\n```", 1)[0])


def test_AI提示词_只给自己的_不含读取密钥(client, teacher_auth, teacher2_auth):
    api = _new(client, teacher_auth, "提示词-隔离")
    assert client.get(f"/api/data-apis/{api['id']}/ai-prompt", headers=teacher2_auth).status_code == 404
    on = client.post(f"/api/data-apis/{api['id']}/rotate-token", json={"which": "read"}, headers=teacher_auth).json()
    got = _prompt(client, teacher_auth, api)
    assert on["read_token"] and on["read_token"] not in got["prompt"], "读取密钥不能进提示词"
    assert api["write_token"] in got["prompt"]
    assert f"/api/hook/{api['key']}" in got["endpoint"] and got["endpoint"] in got["prompt"]
    assert "wfxxSend" in got["prompt"] and "老师的要求" in got["prompt"]


def test_AI提示词_按前端给的对外地址拼(client, teacher_auth):
    api = _new(client, teacher_auth, "提示词-地址")
    got = _prompt(client, teacher_auth, api, base="https://exam.example.cn:3315/")
    assert got["endpoint"] == f"https://exam.example.cn:3315/api/hook/{api['key']}"
    assert f"ENDPOINT: '{got['endpoint']}'" in got["prompt"]
    bad = _prompt(client, teacher_auth, api, base="javascript:alert(1)")
    assert bad["endpoint"].startswith("http://testserver/"), "不像网址的 base 不用"


@pytest.mark.parametrize("template,typ,field", [
    ("answer", "answer", "answers"), ("self_eval", "self_eval", "ratings"),
    ("peer_eval", "peer_eval", "target"), ("survey", "survey", "answers"), ("custom", "experiment", "data"),
])
def test_AI提示词_各用途的例子能被平台认出来(client, teacher_auth, kids, template, typ, field):
    api = _new(client, teacher_auth, f"提示词-{template}", template)
    ex = _example(_prompt(client, teacher_auth, api)["prompt"])
    assert ex["type"] == typ and field in ex
    ex["student"] = {"no": "D1001", "name": "数据学生一", "class": "七年级1班"}
    res = _send(client, api, ex)
    assert res.status_code == 201 and res.json()["student_matched"], res.text
    rec = client.get(f"/api/data-apis/{api['id']}/records", headers=teacher_auth).json()["items"][0]
    assert rec["type"] == typ and rec["activity"]["name"] == ex["activity"]["name"]
    if template == "peer_eval":
        assert rec["target"]["name"] == "李四"
    st = client.get(f"/api/data-apis/{api['id']}/stats", headers=teacher_auth).json()
    if template in ("answer", "survey"):
        assert {q["q"] for q in st["questions"]} == {a["q"] for a in ex["answers"]}
    if template in ("self_eval", "peer_eval"):
        assert {d["item"] for d in st["radar"]} == {r["item"] for r in ex["ratings"]}


def test_AI提示词_跟着设置变(client, teacher_auth, kids):
    api = _new(client, teacher_auth, "提示词-设置")
    plain = _prompt(client, teacher_auth, api)["prompt"]
    assert "wfxxSummary" not in plain and "下拉框" not in plain and "ORIGIN_DENIED）" not in plain
    client.put(f"/api/data-apis/{api['id']}", headers=teacher_auth, json={
        "public_summary": True, "class_ids": [kids["c1"]], "dedupe": "latest",
        "allowed_origins": "https://teach.example.com"})
    p = _prompt(client, teacher_auth, api)["prompt"]
    assert "wfxxSummary" in p, "开了网页可读汇总才给汇总函数"
    assert "「七年级1班」" in p and "下拉框" in p, "关联了班级就让学生从下拉里选"
    assert "只算最新一条" in p
    assert "https://teach.example.com" in p and "file://" in p
