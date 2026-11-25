"""人工智能通识教育测评题（2.27.0）：多选、填空判分；组卷互斥规则；网页交卷按名单核对；题库批量操作。"""

import json

import pytest

from app.database import SessionLocal
from app.models import Question
from app.services import answers
from app.services.literacy import EXAM_SCOPES, SCOPE_G7, SCOPE_G8, bank, seed_literacy


# ---------------- 判分规则 ----------------
def test_多选题比字母集合_全对才算对():
    q = {"type": "选择题", "answer": "ABD"}
    assert answers.is_multi(q)
    assert answers.judge(q, "DBA", "ABD") == (True, 1.0)
    assert answers.judge(q, "A,B,D", "ABD")[0]
    assert answers.judge(q, "AB", "ABD") == (False, 0.0)       # 漏选
    assert answers.judge(q, "ABCD", "ABD") == (False, 0.0)     # 多选
    assert not answers.judge(q, "", "ABD")[0]
    assert answers.judge({"type": "选择题", "answer": "B"}, "B", "B") == (True, 1.0)


def test_填空题按空给分_括号里的说法也算对():
    ans = "第一空：数据（特征数据）；第二空：特征库"
    assert answers.blank_keys(ans) == [["数据", "特征数据"], ["特征库"]]
    assert answers.check_blanks(json.dumps(["特征数据", " 特征库 "]), ans) == (2, 2)
    assert answers.check_blanks(json.dumps(["数据", "特征"]), ans) == (1, 2)
    assert answers.judge({"type": "填空题"}, json.dumps(["数据", ""]), ans) == (False, 0.5)
    assert answers.check_blanks("领域专属", "专业（或“领域专属”）") == (1, 1)
    assert answers.check_blanks("姿态", "姿态；关键") == (1, 2)    # 老客户端只交一个框
    assert answers.blank_count({"answer": "姿态；关键"}) == 2
    assert answers.blank_count({"answer": "", "stem": "填____和____"}) == 2


def test_题目数据完整():
    data = bank()
    assert len(data) == 334
    assert {d["scope"] for d in data} == set(EXAM_SCOPES)
    multi = [d for d in data if d["type"] == "选择题" and len(d["answer"]) > 1]
    assert len(multi) == 33
    assert sum(1 for d in data if d["type"] == "填空题") == 4
    for d in data:
        if d["type"] == "选择题":
            labels = {o["label"] for o in d["options"]}
            assert set(d["answer"]) <= labels, d["stem"][:30]
        assert "（　B　）" not in d["stem"] and "（　√　）" not in d["stem"], "题干里不能留答案"


def test_入库按题干查重_判断题带两个选项(client):
    with SessionLocal() as db:
        first = seed_literacy(db)
        db.commit()
        again = seed_literacy(db)
        db.commit()
        assert first in (0, 334) and again == 0
        judge = db.query(Question).filter(Question.scope == SCOPE_G7, Question.type == "判断题").first()
        assert [o.content for o in judge.options] == ["正确", "错误"]


# ---------------- 组卷规则 ----------------
def _gen(client, auth, **kw):
    body = {"by_sections": False, "counts": {"选择题": 30, "判断题": 10}, **kw}
    return client.post("/api/papers/generate", json=body, headers=auth)


def test_测评题只能单独按题型组卷(client, auth):
    with SessionLocal() as db:
        seed_literacy(db)
        db.commit()
    res = _gen(client, auth, scopes=[SCOPE_G8], counts={"选择题": 32, "判断题": 8, "操作题": 5})
    assert res.status_code == 200, res.text
    got = res.json()
    assert {q["scope"] for q in got["questions"]} == {SCOPE_G8}
    assert not [q for q in got["questions"] if q["type"] == "操作题"], "操作题固定 0 道"
    assert _gen(client, auth, scopes=[SCOPE_G7, "物联网"]).status_code == 400
    assert _gen(client, auth, scopes=[SCOPE_G7, SCOPE_G8]).status_code == 400
    assert _gen(client, auth, scopes=[SCOPE_G7], counts={"选择题": 30, "判断题": 9}).status_code == 400
    assert _gen(client, auth, scopes=[SCOPE_G7], counts={"选择题": 20, "判断题": 20}).status_code == 400
    six = client.post("/api/papers/preview-plan", json={"by_sections": True, "scopes": [SCOPE_G7]},
                      headers=auth)
    assert six.status_code == 400


def test_平常组卷和六大题都抽不到测评题(client, auth):
    with SessionLocal() as db:
        seed_literacy(db)
        db.commit()
    res = _gen(client, auth, counts={"选择题": 999, "判断题": 999})
    if res.status_code == 200:
        assert not [q for q in res.json()["questions"] if q["scope"] in EXAM_SCOPES]
    six = client.post("/api/papers/generate", json={"by_sections": True}, headers=auth)
    if six.status_code == 200:
        assert not [q for q in six.json()["questions"] if q["scope"] in EXAM_SCOPES]


# ---------------- 网页交卷按名单核对 ----------------
@pytest.fixture(scope="module")
def roster_exam(client, auth):
    with SessionLocal() as db:
        seed_literacy(db)
        db.commit()
    client.post("/api/classes/batch", json={"grade": "名单测试", "start": 1, "end": 2, "suffix": "班"},
                headers=auth)
    cls = {c["name"]: c["id"] for c in client.get("/api/classes", headers=auth).json()
           if c["grade"] == "名单测试"}
    client.post("/api/students", json={"student_no": "MD001", "name": "核对甲", "class_id": cls["1班"]},
                headers=auth)
    paper = _gen(client, auth, scopes=[SCOPE_G7], counts={"选择题": 30, "判断题": 10, "填空题": 2},
                 save=True).json()
    exam = client.post("/api/exams", json={"paper_id": paper["paper_id"], "early_submit": True,
                                           "target_class_ids": [cls["1班"], cls["2班"]]},
                       headers=auth).json()
    return {"exam": exam, "cls": cls, "paper": paper}


def test_班级下拉只列有学生的班(client, roster_exam):
    got = client.get(f"/api/take/{roster_exam['exam']['token']}/classes").json()
    assert [c["display"] for c in got] == ["名单测试1班"]


def test_姓名不在名单里交不上(client, roster_exam):
    tok, c1 = roster_exam["exam"]["token"], roster_exam["cls"]["1班"]
    url = f"/api/take/{tok}/submit"
    assert client.post(url, json={"student_name": "核对甲", "answers": {}}).status_code == 400   # 没选班
    res = client.post(url, json={"student_name": "乱写的", "class_id": c1, "answers": {}})
    assert res.status_code == 400 and "名单里没有" in res.json()["detail"]
    ok = client.post(url, json={"student_name": " 核对甲 ", "class_id": c1, "answers": {}})
    assert ok.status_code == 200, ok.text
    again = client.post(url, json={"student_name": "核对甲", "class_id": c1, "answers": {}})
    assert again.status_code == 409, "同一个人默认只能交一次"


def test_取卷带多选和空数_交卷按新规则判分(client, auth, roster_exam):
    tok = roster_exam["exam"]["token"]
    body = client.get(f"/api/take/{tok}").json()
    items = [q for g in body["groups"] for q in g["items"]]
    assert any(q["multi"] for q in items if q["type"] == "选择题")
    assert all(q["blanks"] >= 1 for q in items if q["type"] == "填空题")
    full = {q["id"]: q for q in roster_exam["paper"]["questions"]}
    mine = {}
    for q in items:
        right = full[q["id"]]["answer"]
        if q["type"] == "选择题":
            mine[str(q["id"])] = right[::-1]          # 多选倒着交也对
        elif q["type"] == "判断题":
            mine[str(q["id"])] = "A" if right == "正确" else "B"
        else:
            keys = answers.blank_keys(right)
            mine[str(q["id"])] = json.dumps([k[-1] for k in keys], ensure_ascii=False)
    client.post("/api/students", json={"student_no": "MD002", "name": "核对乙",
                                       "class_id": roster_exam["cls"]["1班"]}, headers=auth)
    res = client.post(f"/api/take/{tok}/submit", json={
        "student_name": "核对乙", "class_id": roster_exam["cls"]["1班"], "answers": mine}).json()
    assert res["right_count"] == res["objective_count"] == len(items)


# ---------------- 题库批量操作 ----------------
def test_批量停用启用删除(client, auth):
    with SessionLocal() as db:
        seed_literacy(db)
        db.commit()
    rows = client.get("/api/questions", params={"scope": SCOPE_G8, "page_size": 3}, headers=auth).json()["items"]
    ids = [r["id"] for r in rows]
    assert client.post("/api/questions/bulk", json={"ids": ids, "action": "disable"}, headers=auth).json()["done"] == 3
    got = client.get("/api/questions", params={"status": "disabled", "scope": SCOPE_G8}, headers=auth).json()
    assert {r["id"] for r in got["items"]} >= set(ids) and all(r["is_disabled"] for r in got["items"])
    assert client.get("/api/questions/stats", headers=auth).json()["disabled"] >= 3
    # 停用的题组卷抽不到
    paper = _gen(client, auth, scopes=[SCOPE_G8], counts={"选择题": 120, "判断题": 0})
    assert paper.status_code == 400   # 判断题 0 凑不满 40 的规矩先拦住
    assert client.post("/api/questions/bulk", json={"ids": ids, "action": "enable"}, headers=auth).status_code == 200
    assert client.post("/api/questions/bulk", json={"ids": ids, "action": "difficulty", "value": 9},
                       headers=auth).status_code == 400
    assert client.post("/api/questions/bulk", json={"ids": ids, "action": "scope", "value": "不存在"},
                       headers=auth).status_code == 400
    assert client.post("/api/questions/bulk", json={"ids": ids, "action": "delete"}, headers=auth).json()["done"] == 3
    left = client.get("/api/questions", params={"scope": SCOPE_G8, "page_size": 200}, headers=auth).json()
    assert not set(ids) & {r["id"] for r in left["items"]}


def test_停用的题组卷抽不到(client, auth):
    with SessionLocal() as db:
        seed_literacy(db)
        db.query(Question).filter(Question.scope == SCOPE_G7, Question.type == "判断题").update(
            {Question.is_disabled: True})
        db.commit()
    try:
        res = _gen(client, auth, scopes=[SCOPE_G7], counts={"选择题": 30, "判断题": 10})
        assert res.status_code == 200
        assert not [q for q in res.json()["questions"] if q["type"] == "判断题"]
        assert res.json()["warnings"], "判断题一道都抽不到要提示"
    finally:
        with SessionLocal() as db:
            db.query(Question).filter(Question.scope == SCOPE_G7).update({Question.is_disabled: False})
            db.commit()
