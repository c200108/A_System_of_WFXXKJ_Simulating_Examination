"""2.28.0：网页取卷重抽、临时保存的同一套、重考次数、交卷频率、排名、考试时长、交卷人数。"""

import pytest

from app.database import SessionLocal
from app.services.literacy import SCOPE_G8, seed_literacy


@pytest.fixture(scope="module")
def setup(client, auth):
    with SessionLocal() as db:
        seed_literacy(db)
        db.commit()
    client.post("/api/classes/batch", json={"grade": "规则测试", "start": 1, "end": 1, "suffix": "班"},
                headers=auth)
    cid = next(c["id"] for c in client.get("/api/classes", headers=auth).json() if c["grade"] == "规则测试")
    for i, n in enumerate(["规则甲", "规则乙", "规则丙"]):
        client.post("/api/students", json={"student_no": f"GZ{i}", "name": n, "class_id": cid}, headers=auth)

    def exam(**kw):
        paper = client.post("/api/papers/generate", json={
            "by_sections": False, "scopes": [SCOPE_G8], "counts": {"选择题": 30, "判断题": 10},
            "save": True, "shuffle_objective": kw.pop("shuffle", True)}, headers=auth).json()
        return client.post("/api/exams", json={"paper_id": paper["paper_id"], "early_submit": True, **kw},
                           headers=auth).json()

    return {"cid": cid, "exam": exam}


def _ids(body):
    return [q["id"] for g in body["groups"] for q in g["items"]]


def test_开了乱序每次取卷重抽_带draw取回同一套(client, setup):
    tok = setup["exam"]()["token"]
    a, b = client.get(f"/api/take/{tok}").json(), client.get(f"/api/take/{tok}").json()
    assert a["draw"] and b["draw"] and a["draw"] != b["draw"]
    assert set(_ids(a)) != set(_ids(b)), "八年级测评题有一百多道，两次抽到的题应该不一样"
    assert a["total"] == b["total"] == 40
    again = client.get(f"/api/take/{tok}", params={"draw": a["draw"]}).json()
    assert again["draw"] == a["draw"] and _ids(again) == _ids(a), "临时保存后刷新还是这一套"


def test_没开乱序不重抽(client, setup):
    tok = setup["exam"](shuffle=False)["token"]
    a, b = client.get(f"/api/take/{tok}").json(), client.get(f"/api/take/{tok}").json()
    assert a["draw"] == b["draw"] == "" and _ids(a) == _ids(b)


def test_重考次数和交卷频率(client, auth, setup):
    ex = setup["exam"](allow_retake=True, max_attempts=3, rate_window=5, rate_max=2)
    url = f"/api/take/{ex['token']}/submit"
    body = {"student_name": "规则甲", "class_id": setup["cid"], "answers": {}}
    assert client.post(url, json=body).status_code == 200
    assert client.post(url, json=body).status_code == 200
    third = client.post(url, json=body)
    assert third.status_code == 429 and "提交次数过多" in third.json()["detail"] and "后再交卷" in third.json()["detail"]
    # 放宽频率后，第 3 次能交，第 4 次超出次数
    client.patch(f"/api/exams/{ex['id']}", json={"rate_window": 0}, headers=auth)
    assert client.post(url, json=body).status_code == 200
    fourth = client.post(url, json=body)
    assert fourth.status_code == 409 and "最多交 3 次" in fourth.json()["detail"]


def test_排名每人取最高分_交卷人数和份数分开(client, auth, setup):
    ex = setup["exam"](allow_retake=True, shuffle=False)
    url = f"/api/take/{ex['token']}/submit"
    key = {}
    paper = client.get(f"/api/exams/{ex['id']}/paper", headers=auth).json()
    for g in paper["groups"]:
        for q in g["items"]:
            key[str(q["id"])] = "A" if q["answer"] == "正确" else "B" if q["answer"] == "错误" else q["answer"]
    good = client.post(url, json={"student_name": "规则乙", "class_id": setup["cid"], "answers": key}).json()
    assert good["rank"] == 1
    client.post(url, json={"student_name": "规则乙", "class_id": setup["cid"], "answers": {}})
    low = client.post(url, json={"student_name": "规则丙", "class_id": setup["cid"], "answers": {}}).json()
    assert (low["rank"], low["rank_total"]) == (2, 2), "规则乙交了两次只算一个人、取最高分"
    st = client.get(f"/api/exams/{ex['id']}/stats", headers=auth).json()
    assert (st["submission_count"], st["student_count"]) == (3, 2)


def test_考试时长能单独改(client, auth, setup):
    ex = setup["exam"]()
    assert client.patch(f"/api/exams/{ex['id']}", json={"duration": "25"}, headers=auth).status_code == 200
    assert client.get(f"/api/take/{ex['token']}").json()["duration"] == "25"
    assert client.get(f"/api/exams/{ex['id']}/paper", headers=auth).json()["duration"] == "25"
    assert client.patch(f"/api/exams/{ex['id']}", json={"duration": "abc"}, headers=auth).status_code == 400
    client.patch(f"/api/exams/{ex['id']}", json={"duration": ""}, headers=auth)
    out = client.get(f"/api/exams/{ex['id']}", headers=auth).json()
    assert client.get(f"/api/take/{ex['token']}").json()["duration"] == out["paper_duration"]


def test_姓名乱试次数多了被限(client, setup):
    from app.routers import take

    ex = setup["exam"]()
    url = f"/api/take/{ex['token']}/submit"
    for _ in range(take.ROSTER_FAILS):
        assert client.post(url, json={"student_name": "瞎猜", "class_id": setup["cid"], "answers": {}}).status_code == 400
    assert client.post(url, json={"student_name": "瞎猜", "class_id": setup["cid"], "answers": {}}).status_code == 429


# ---------------------------------------------------------------- 2.29.0 每题平均分、抽卷的成绩分析
def test_测评卷每题平均分_40题每题2点5分(client, auth, setup):
    ex = setup["exam"]()
    body = client.get(f"/api/take/{ex['token']}").json()
    pts = {q["score"] for g in body["groups"] for q in g["items"]}
    assert pts == {2.5} and body["full_score"] == 100
    paper = client.get(f"/api/exams/{ex['id']}/paper", headers=auth).json()
    assert {q["score"] for g in paper["groups"] for q in g["items"]} == {2.5}
    assert [g["score"] for g in paper["groups"]] == [75, 25]
    # 答对 3 题 = 7.5 分
    ids = [q["id"] for g in body["groups"] for q in g["items"]][:3]
    ans = {}
    for qid in ids:
        a = client.get(f"/api/questions/{qid}", headers=auth).json()["answer"]
        ans[str(qid)] = "A" if a == "正确" else "B" if a == "错误" else a
    res = client.post(f"/api/take/{ex['token']}/submit", json={
        "student_name": "平均分", "student_class": "规则测试1班", "student_no": "AVG1",
        "answers": ans, "draw": body["draw"]}).json()
    assert res["score"] == 7.5 and res["full_score"] == 100


def test_抽卷考试的成绩分析按每人自己那套算(client, auth, setup):
    import random

    ex = setup["exam"]()
    tok = ex["token"]
    cache = {}
    rnd = random.Random(7)
    for i in range(24):
        body = client.get(f"/api/take/{tok}").json()
        skill = (i + 1) / 25             # 每人水平不一样，分数拉开
        ans = {}
        for g in body["groups"]:
            for q in g["items"]:
                if q["id"] not in cache:
                    a = client.get(f"/api/questions/{q['id']}", headers=auth).json()["answer"]
                    cache[q["id"]] = "A" if a == "正确" else "B" if a == "错误" else a
                ans[str(q["id"])] = cache[q["id"]] if rnd.random() < skill else "Z"
        r = client.post(f"/api/take/{tok}/submit", json={
            "student_name": f"抽卷{i}", "student_class": f"规则测试{1 + i % 2}班", "student_no": f"CJ{i:02d}",
            "answers": ans, "draw": body["draw"]})
        assert r.status_code == 200, r.text
    a = client.get(f"/api/exams/{ex['id']}/analysis", headers=auth).json()
    s = a["summary"]
    assert s["full"] == 100, "每人那一套都是 100 分，不是全场抽到过的题加起来"
    assert s["count"] == 24 and sum(b["count"] for b in a["bands"]) == 24
    assert a["bands"][-1]["label"] == "90–100"
    assert s["avg_rate"] == s["avg"] or abs(s["avg_rate"] - s["avg"]) < 0.11
    for r in a["ranking"]:
        assert abs(r["rate"] - r["score"]) < 0.11, "满分 100：得分率就是分数"
    for g in a["sections"] + a["scopes"] + a["types"]:
        assert g["rate"] is not None and 0 <= g["rate"] <= 100, g
    sec = {g["name"]: g for g in a["sections"]}
    assert (sec["选择题"]["questions"], sec["选择题"]["full"]) == (30, 75)
    assert (sec["判断题"]["questions"], sec["判断题"]["full"]) == (10, 25)
    assert sec["选择题"]["pool"] > 30, "全场抽到过的选择题比一套卷子多"
    # 大题得分率 = 各人这部分得分之和 / 各人这部分满分之和
    subs = client.get(f"/api/exams/{ex['id']}/submissions", headers=auth).json()
    total = sum(x["score"] for x in subs)
    sum_sec = sum(g["avg"] * 24 for g in a["sections"])
    assert abs(sum_sec - total) < 24 * 0.1 * 2
    qs = [q for q in a["questions"] if q["rate"] is not None]
    assert qs and all(0 <= q["rate"] <= 100 for q in qs)
    assert all(q["answered"] <= 24 for q in qs)
    assert any(q["discrimination"] is not None for q in qs)


def test_学生端考试包带多选和填空空数_每题平均分(client, auth, setup):
    """2.29.0：/api/desk/exam 的包以前漏了 multi，exe 上多选题全成了单选。"""
    import io
    import json
    import zipfile

    from app.database import SessionLocal
    from app.models import Question
    from app.services.literacy import SCOPE_G8 as G8

    with SessionLocal() as db:
        multi_ids = [q.id for q in db.query(Question).filter(Question.scope == G8, Question.type == "选择题")
                     if len((q.answer or "").strip()) >= 2]
    assert multi_ids, "八年级测评题里有多选题"
    # 按题型组卷是随机抽的：多组几张，总有一张抽到多选题
    for _ in range(8):
        ex = setup["exam"](shuffle=False)
        raw = client.get(f"/api/desk/exam/{ex['token']}").content
        z = zipfile.ZipFile(io.BytesIO(raw))
        paper = json.loads(z.read("paper.json"))
        assert {q["score"] for q in paper} == {2.5}
        got = [q for q in paper if int(q["id"]) in multi_ids]
        if got:
            assert all(q.get("multi") is True for q in got)
            assert not any(q.get("multi") for q in paper if int(q["id"]) not in multi_ids)
            assert "answer" not in json.dumps(paper)
            return
    raise AssertionError("组了 8 张卷子都没抽到多选题")


def test_错得最多的题导出完整题干和选项(client, auth, setup):
    import io

    from openpyxl import load_workbook

    ex = setup["exam"](shuffle=False)
    body = client.get(f"/api/take/{ex['token']}").json()
    first = body["groups"][0]["items"][0]
    for i in range(3):
        client.post(f"/api/take/{ex['token']}/submit", json={
            "student_name": f"导出{i}", "student_class": "规则测试1班", "student_no": f"DC{i}",
            "answers": {str(first["id"]): "Z"}})
    res = client.get(f"/api/exams/{ex['id']}/hardest.xlsx", headers=auth)
    assert res.status_code == 200
    ws = load_workbook(io.BytesIO(res.content)).active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0][:5] == ("序号", "题型", "知识范围", "题干", "选项A")
    assert len(rows) == 41, "40 道题都有人作答（没答的算未作答）"
    q = client.get(f"/api/questions/{first['id']}", headers=auth).json()
    row = next(r for r in rows[1:] if r[3] == q["stem"])
    assert row[3] == q["stem"], "题干完整，不截断"
    if q["type"] == "选择题":
        assert row[4] == next(o["content"] for o in q["options"] if o["label"] == "A")
    assert row[16] == "Z（3 人）", "答错的人最多选了什么"
    assert client.get(f"/api/exams/{ex['id']}/hardest.xlsx", params={"limit": 5}, headers=auth) \
        .status_code == 200
