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
