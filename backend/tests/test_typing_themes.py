"""打字练习文本的主题（2.15.0）：归类、只取启用主题、不跨主题、多主题随机。

各用例用自己独有的「难度」名放文本（如「主题·不跨」），学生取文本的接口按难度 + 语言筛，
这样和别的打字用例、和内置文本互不干扰。
"""

import sqlalchemy as sa
from sqlalchemy import create_engine

from test_migrations import _alembic_config, blank_db  # noqa: F401  （fixture）

API = "/api/typing"


def _theme(client, auth, name):
    res = client.post(f"{API}/themes", json={"name": name}, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()


def _text(client, auth, content, theme_id, difficulty, mode="chinese"):
    res = client.post(f"{API}/texts", headers=auth, json={
        "mode": mode, "difficulty": difficulty, "content": content, "theme_id": theme_id})
    assert res.status_code == 200, res.text
    return res.json()


def _builtin(client, auth):
    themes = client.get(f"{API}/themes", headers=auth).json()
    return next(t for t in themes if t["is_builtin"])


def _passage(client, difficulty, mode="chinese"):
    res = client.get(f"{API}/passage", params={"mode": mode, "difficulty": difficulty})
    assert res.status_code == 200, res.text
    return res.json()["text"]


# ---------------------------------------------------------------- 归类
def test_内置主题信息生活_现有文本都归它(client, auth):
    b = _builtin(client, auth)
    assert b["name"] == "信息生活" and b["is_enabled"] and b["total"] > 0
    texts = client.get(f"{API}/texts", headers=auth).json()
    assert texts and all(t["theme_id"] == b["id"] for t in texts)
    # 不给主题新增的也归它
    got = client.post(f"{API}/texts", headers=auth, json={
        "mode": "chinese", "difficulty": "主题·默认", "content": "不选主题新增的这段文本归信息生活。"}).json()
    assert got["theme_id"] == b["id"]


def test_迁移把升级前的文本都归到信息生活(blank_db):  # noqa: F811
    from alembic import command

    cfg = _alembic_config(blank_db)
    command.upgrade(cfg, "0020")
    engine = create_engine(blank_db)
    try:
        with engine.begin() as conn:
            for i, src in enumerate(("内置", "自定义", "导入"), 1):
                conn.execute(sa.text(
                    "INSERT INTO typing_texts (id, mode, difficulty, content, content_hash, source,"
                    " is_active) VALUES (:i, 'chinese', '简单', :c, :h, :s, 1)"),
                    {"i": i, "c": f"升级前的第{i}段文本内容", "h": f"hash-{i}", "s": src})
        command.upgrade(cfg, "0021")
        with engine.begin() as conn:
            themes = conn.execute(sa.text(
                "SELECT id, name, is_enabled, is_builtin FROM typing_themes")).fetchall()
            got = {r[0] for r in conn.execute(sa.text("SELECT theme_id FROM typing_texts"))}
    finally:
        engine.dispose()
    assert len(themes) == 1 and themes[0][1] == "信息生活" and themes[0][2] and themes[0][3]
    assert got == {themes[0][0]}


# ---------------------------------------------------------------- 学生取文本
def test_一篇只来自一个主题_绝不跨主题(client, auth):
    a = _theme(client, auth, "主题甲")
    b = _theme(client, auth, "主题乙")
    for i in range(6):
        _text(client, auth, f"甲甲甲第{i}段内容。", a["id"], "主题·不跨")
        _text(client, auth, f"乙乙乙第{i}段内容。", b["id"], "主题·不跨")
    seen = {"甲": 0, "乙": 0}
    for _ in range(120):
        text = _passage(client, "主题·不跨")
        assert ("甲" in text) != ("乙" in text), f"跨主题拼了：{text}"
        seen["甲" if "甲" in text else "乙"] += 1
    # 两个主题等概率：120 次里各占 50% 左右（给足余量，不让偶然失败）
    assert 35 <= seen["甲"] <= 85, seen


def test_段多的主题不会更容易被抽到(client, auth):
    """先挑主题再挑段：主题之间等概率，不按段数加权。"""
    a = _theme(client, auth, "多段主题")
    b = _theme(client, auth, "少段主题")
    for i in range(20):
        _text(client, auth, f"多多多第{i}段内容文本。", a["id"], "主题·加权")
    _text(client, auth, "少少少只有这一段内容。", b["id"], "主题·加权")
    few = sum("少" in _passage(client, "主题·加权") for _ in range(120))
    assert 35 <= few <= 85, few


def test_只从启用的主题里取(client, auth):
    a = _theme(client, auth, "启用主题")
    b = _theme(client, auth, "停用主题")
    _text(client, auth, "启启启这段来自启用主题。", a["id"], "主题·启停")
    _text(client, auth, "停停停这段来自停用主题。", b["id"], "主题·启停")
    assert client.put(f"{API}/themes/{b['id']}", headers=auth,
                      json={"is_enabled": False}).status_code == 200
    for _ in range(30):
        assert "停" not in _passage(client, "主题·启停")
    # 只剩停用主题有文本的难度：学生取不到，说清楚
    _text(client, auth, "只有停用主题有这一段。", b["id"], "主题·全停")
    res = client.get(f"{API}/passage", params={"mode": "chinese", "difficulty": "主题·全停"})
    assert res.status_code == 404 and "启用的主题" in res.json()["detail"]


def test_主题段数不够时不拿别的主题凑(client, auth):
    a = _theme(client, auth, "两段主题")
    _text(client, auth, "两两两第一段内容。", a["id"], "主题·不够")
    _text(client, auth, "两两两第二段内容。", a["id"], "主题·不够")
    b = _theme(client, auth, "十段主题")
    for i in range(10):
        _text(client, auth, f"十十十第{i}段内容。", b["id"], "主题·不够")
    for _ in range(40):
        text = _passage(client, "主题·不够")
        if "两" in text:
            assert "十" not in text and text.count("两两两") <= 2


def test_至少保留一个启用的主题(client, auth):
    themes = client.get(f"{API}/themes", headers=auth).json()
    was = {t["id"]: t["is_enabled"] for t in themes}
    try:
        on = [t["id"] for t in themes if t["is_enabled"]]
        for tid in on[:-1]:
            assert client.put(f"{API}/themes/{tid}", headers=auth,
                              json={"is_enabled": False}).status_code == 200
        res = client.put(f"{API}/themes/{on[-1]}", headers=auth, json={"is_enabled": False})
        assert res.status_code == 400 and "至少要保留一个" in res.json()["detail"]
    finally:
        for tid, en in was.items():
            client.put(f"{API}/themes/{tid}", headers=auth, json={"is_enabled": en})


# ---------------------------------------------------------------- 老师管理主题
def test_新增改名重名(client, auth):
    t = _theme(client, auth, "人工智能")
    assert client.post(f"{API}/themes", json={"name": "人工智能"}, headers=auth).status_code == 409
    res = client.put(f"{API}/themes/{t['id']}", json={"name": "AI 与生活"}, headers=auth)
    assert res.status_code == 200 and res.json()["name"] == "AI 与生活"
    assert client.put(f"{API}/themes/{t['id']}", json={"name": "信息生活"},
                      headers=auth).status_code == 409
    assert client.get(f"{API}/themes").status_code == 401


def test_内置主题不能删(client, auth):
    b = _builtin(client, auth)
    res = client.delete(f"{API}/themes/{b['id']}", headers=auth)
    assert res.status_code == 400 and "不能删除" in res.json()["detail"]


def test_删主题_文本归回信息生活_回收站还原接回去(client, auth):
    b = _builtin(client, auth)
    c = _theme(client, auth, "要删的主题")
    t1 = _text(client, auth, "删删删这段原来属于要删的主题。", c["id"], "主题·删除")
    res = client.delete(f"{API}/themes/{c['id']}", headers=auth)
    assert res.status_code == 200 and res.json()["moved"] == 1
    # 归回信息生活：按信息生活筛得到它，学生也照样取得到
    ids = [t["id"] for t in client.get(f"{API}/texts", params={"theme_id": b["id"]},
                                       headers=auth).json()]
    assert t1["id"] in ids
    assert "删删删" in _passage(client, "主题·删除")

    item = next(i for i in client.get("/api/recycle", params={"kind": "typing_theme"},
                                      headers=auth).json()["items"] if "要删的主题" in i["title"])
    assert client.post("/api/recycle/restore", json={"ids": [item["id"]]},
                       headers=auth).json()["restored"] == 1
    got = next(t for t in client.get(f"{API}/texts", headers=auth).json() if t["id"] == t1["id"])
    assert got["theme_id"] == c["id"]


def test_删主题要删除权(client, teacher_auth, auth):
    c = _theme(client, auth, "普通老师删不了")
    assert client.delete(f"{API}/themes/{c['id']}", headers=teacher_auth).status_code == 403


# ---------------------------------------------------------------- 文本归类
def test_导入编辑筛选批量改主题(client, auth):
    d = _theme(client, auth, "导入主题")
    e = _theme(client, auth, "批量目标")
    res = client.post(f"{API}/texts/import", headers=auth,
                      params={"mode": "chinese", "difficulty": "主题·导入", "theme_id": d["id"]},
                      files={"file": ("t.txt", "导入的第一段内容。\n导入的第二段内容。".encode("utf-8"),
                                      "text/plain")})
    assert res.status_code == 200 and res.json()["added"] == 2
    mine = client.get(f"{API}/texts", params={"theme_id": d["id"]}, headers=auth).json()
    assert len(mine) == 2 and all(t["theme_id"] == d["id"] for t in mine)

    one = mine[0]["id"]
    assert client.put(f"{API}/texts/{one}", json={"theme_id": e["id"]},
                      headers=auth).json()["theme_id"] == e["id"]
    res = client.post(f"{API}/texts/bulk", headers=auth,
                      json={"ids": [t["id"] for t in mine], "action": "theme", "theme_id": e["id"]})
    assert res.status_code == 200 and res.json()["affected"] == 2
    assert client.get(f"{API}/texts", params={"theme_id": d["id"]}, headers=auth).json() == []
    themes = {t["id"]: t for t in client.get(f"{API}/themes", headers=auth).json()}
    assert themes[e["id"]]["counts"]["chinese"]["主题·导入"] == 2


def test_不存在的主题拒收(client, auth):
    res = client.post(f"{API}/texts", headers=auth, json={
        "mode": "chinese", "difficulty": "主题·坏", "content": "主题不存在的这段文本。", "theme_id": 999999})
    assert res.status_code == 400
    res = client.post(f"{API}/texts/bulk", headers=auth,
                      json={"ids": [1], "action": "theme", "theme_id": 999999})
    assert res.status_code == 400
