"""历史试卷多选：批量删除（进回收站，连考试一起）、批量导出 zip。"""

import io
import zipfile

import pytest


@pytest.fixture(scope="module", autouse=True)
def _questions(client, auth):
    """单独跑这个文件时题库是空的：自己放几道选择题，组卷才抽得到（已有的跳过）。"""
    for i in range(3):
        client.post("/api/questions", headers=auth, json={
            "type": "选择题", "stem": f"批量操作测试题 {i}：下列哪个是输入设备？", "answer": "A",
            "scope": "计算机硬件",
            "options": [{"label": "A", "content": "键盘"}, {"label": "B", "content": "显示器"}]})


def _paper(client, auth, title):
    res = client.post("/api/papers/generate", headers=auth, json={
        "title": title, "by_sections": False, "counts": {"选择题": 2}, "save": True})
    assert res.status_code == 200, res.text
    return res.json()["paper_id"]


def _ids(client, auth):
    return {p["id"]: p for p in client.get("/api/papers", headers=auth).json()}


def test_列表带考试场数(client, auth):
    pid = _paper(client, auth, "带考试的卷")
    assert _ids(client, auth)[pid]["exam_count"] == 0
    res = client.post("/api/exams", json={"paper_id": pid}, headers=auth)
    assert res.status_code == 200, res.text
    assert _ids(client, auth)[pid]["exam_count"] == 1


def test_批量删除_连考试一起进回收站_每份能单独还原(client, auth):
    a, b = _paper(client, auth, "批量删甲"), _paper(client, auth, "批量删乙")
    exam = client.post("/api/exams", json={"paper_id": a}, headers=auth).json()
    res = client.post("/api/papers/bulk-delete", json={"ids": [a, b, 999999, a]}, headers=auth)
    assert res.status_code == 200, res.text
    got = res.json()
    assert got["deleted"] == [a, b] and got["exams"] == 1
    assert got["failed"] == [{"id": 999999, "reason": "试卷不存在（可能已经被删了）"}]
    left = _ids(client, auth)
    assert a not in left and b not in left
    assert client.get(f"/api/exams/{exam['id']}", headers=auth).status_code == 404

    items = client.get("/api/recycle", params={"kind": "paper"}, headers=auth).json()["items"]
    mine = [i for i in items if "批量删甲" in i["title"] or "批量删乙" in i["title"]]
    assert len(mine) == 2, "每份卷各占回收站一条"
    one = next(i for i in mine if "批量删甲" in i["title"])
    assert "连同 1 场考试" in one["detail"]
    assert client.post("/api/recycle/restore", json={"ids": [one["id"]]},
                       headers=auth).json()["restored"] == 1
    assert a in _ids(client, auth) and b not in _ids(client, auth)


def test_批量删除_没选东西和没登录(client, auth):
    assert client.post("/api/papers/bulk-delete", json={"ids": []}, headers=auth).status_code == 400
    assert client.post("/api/papers/bulk-delete", json={"ids": [1]}).status_code == 401


def test_批量导出_zip里每份一个文件_同名不覆盖(client, auth):
    a, b = _paper(client, auth, "同名卷"), _paper(client, auth, "同名卷")
    for fmt, per in (("xlsx", 1), ("html", 1), ("both", 2)):
        res = client.post("/api/papers/bulk-export", json={"ids": [a, b, 999999], "fmt": fmt},
                          headers=auth)
        assert res.status_code == 200, res.text
        assert res.headers["content-type"] == "application/zip"
        names = zipfile.ZipFile(io.BytesIO(res.content)).namelist()
        papers = [n for n in names if n != "说明.txt"]
        assert len(papers) == 2 * per and len(set(papers)) == len(papers), names
        assert "说明.txt" in names                       # 找不到的那份写进说明
        if fmt != "html":
            assert any(n.endswith(".xlsx") for n in names)
        if fmt != "xlsx":
            html = next(n for n in names if n.endswith("_学生答题.html"))
            assert "同名卷" in zipfile.ZipFile(io.BytesIO(res.content)).read(html).decode("utf-8")


def test_批量导出_都不存在是404_格式不对是422(client, auth):
    assert client.post("/api/papers/bulk-export", json={"ids": [999998]},
                       headers=auth).status_code == 404
    assert client.post("/api/papers/bulk-export", json={"ids": [1], "fmt": "pdf"},
                       headers=auth).status_code == 422
