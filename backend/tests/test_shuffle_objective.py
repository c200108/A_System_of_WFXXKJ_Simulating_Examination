"""选择判断题乱序（2.19.0）和题库「有无答案」筛选。

乱序本身在答题端做（每个学生按「考试 + 学生」各自打乱，见 frontend/src/shuffle.js、
desktop/client/shuffle.py），服务端只负责三件事：

  · 组卷时记下「这份卷子要乱序」，卷子里的题序和选项**按原样**存；
  · 取卷（网页 / 学生平台 / 学生端考试包）时把这个开关带下去；
  · 老配置、老 APP 传的 shuffle_options 照样认。
"""

import io
import json
import zipfile

import pytest

from app.siteconfig import PaperConf


def _paper(client, auth, **extra):
    body = {"by_sections": False, "counts": {"选择题": 4, "判断题": 2}, "save": True}
    body.update(extra)
    res = client.post("/api/papers/generate", json=body, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _exam(client, auth, paper_id):
    res = client.post("/api/exams", json={"paper_id": paper_id}, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def test_老配置的shuffle_options读成新开关():
    assert PaperConf(shuffle_options=False).shuffle_objective is False
    assert PaperConf(shuffle_options=True).shuffle_objective is True
    assert PaperConf().shuffle_objective is True
    # 两个都写了，以新键为准
    assert PaperConf(shuffle_options=True, shuffle_objective=False).shuffle_objective is False


def test_开了乱序_卷子里选项按原样存_取卷带上开关(client, auth):
    paper = _paper(client, auth, shuffle_objective=True)
    assert paper["shuffle"] is True
    # 组卷这一步不再打乱选项：和题库里的一模一样，答案也是原答案
    for q in paper["questions"]:
        if q["type"] != "选择题":
            continue
        raw = client.get("/api/questions", params={"keyword": q["stem"][:20]}, headers=auth).json()
        src = next(x for x in raw["items"] if x["id"] == q["id"])
        assert [o["content"] for o in q["options"]] == [o["content"] for o in src["options"]]
        assert q["answer"] == src["answer"]

    again = client.get(f"/api/papers/{paper['paper_id']}", headers=auth).json()
    assert again["shuffle"] is True

    exam = _exam(client, auth, paper["paper_id"])
    took = client.get(f"/api/take/{exam['token']}").json()
    assert took["shuffle"] is True


def test_关了乱序_取卷说不乱(client, auth):
    paper = _paper(client, auth, shuffle_objective=False)
    exam = _exam(client, auth, paper["paper_id"])
    assert paper["shuffle"] is False
    assert client.get(f"/api/take/{exam['token']}").json()["shuffle"] is False


@pytest.mark.parametrize("old", [True, False])
def test_老APP传的shuffle_options照样认(client, auth, old):
    assert _paper(client, auth, shuffle_options=old)["shuffle"] is old


def test_学生端考试包里带乱序开关(client, auth):
    paper = _paper(client, auth, shuffle_objective=True)
    exam = _exam(client, auth, paper["paper_id"])
    res = client.get(f"/api/desk/exam/{exam['token']}")
    assert res.status_code == 200, res.text
    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
    assert manifest["shuffle"] is True


def test_乱序不影响判分_交的是原选项字母(client, auth):
    """答题端只是把选项换了位置显示，交上来的还是原字母 —— 照原答案判就对。"""
    paper = _paper(client, auth, shuffle_objective=True)
    exam = _exam(client, auth, paper["paper_id"])
    key = {str(q["id"]): q["answer"] if q["type"] == "选择题"
           else ("A" if q["answer"] == "正确" else "B") for q in paper["questions"]
           if q["answer"]}
    res = client.post(f"/api/take/{exam['token']}/submit",
                      json={"student_name": "乱序甲", "student_no": "SHUF01", "answers": key})
    assert res.status_code == 200, res.text
    got = res.json()
    assert got["right_count"] == got["objective_count"] == len(key)


def test_题库按有无答案筛选(client, auth):
    for stem, ans in (("有无答案筛选·有答案", "A"), ("有无答案筛选·没答案", ""),
                      ("有无答案筛选·全是空格", "   ")):
        res = client.post("/api/questions", json={
            "type": "选择题", "stem": stem, "answer": ans, "scope": "计算机网络基础",
            "options": [{"label": "A", "content": "甲"}, {"label": "B", "content": "乙"}]},
            headers=auth)
        assert res.status_code == 200, res.text

    def stems(**kw):
        got = client.get("/api/questions", params={"keyword": "有无答案筛选", **kw},
                         headers=auth).json()
        return {q["stem"] for q in got["items"]}

    assert stems() == {"有无答案筛选·有答案", "有无答案筛选·没答案", "有无答案筛选·全是空格"}
    assert stems(has_answer="true") == {"有无答案筛选·有答案"}
    assert stems(has_answer="false") == {"有无答案筛选·没答案", "有无答案筛选·全是空格"}
    # 导出走同一套筛选
    res = client.get("/api/questions/export.xlsx",
                     params={"keyword": "有无答案筛选", "has_answer": "true"}, headers=auth)
    assert res.status_code == 200
