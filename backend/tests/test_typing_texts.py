"""打字文本库：界面增删改 + txt 批量导入 + 取文本走数据库。"""

import io


def test_seeded_from_config(client, auth):
    """首次建库时 config.yaml 里的内置文本应该已经灌进来了。"""
    stats = client.get("/api/typing/texts/stats", headers=auth).json()
    assert stats["english"] and stats["chinese"]
    assert all(n > 0 for n in stats["english"].values())


def test_passage_comes_from_db(client):
    res = client.get("/api/typing/passage", params={"mode": "chinese", "difficulty": "简单"})
    assert res.status_code == 200
    assert len(res.json()["text"]) > 30


def test_passage_404_when_no_text(client):
    res = client.get("/api/typing/passage", params={"mode": "english", "difficulty": "地狱"})
    assert res.status_code == 404
    assert "还没有" in res.json()["detail"]


def test_text_management_needs_login(client):
    assert client.get("/api/typing/texts").status_code == 401
    assert client.post(
        "/api/typing/texts",
        json={"mode": "chinese", "difficulty": "简单", "content": "偷偷加一段"},
    ).status_code == 401


def test_create_and_use(client, auth):
    content = "这是一段专门为测试添加的中文练习文本，长度足够用来打字。"
    res = client.post(
        "/api/typing/texts",
        json={"mode": "chinese", "difficulty": "中等", "content": content},
        headers=auth,
    )
    assert res.status_code == 200
    assert res.json()["source"] == "自定义"

    rows = client.get(
        "/api/typing/texts", params={"keyword": "专门为测试"}, headers=auth
    ).json()
    assert len(rows) == 1


def test_too_short_rejected(client, auth):
    res = client.post(
        "/api/typing/texts",
        json={"mode": "chinese", "difficulty": "简单", "content": "太短"},
        headers=auth,
    )
    assert res.status_code == 400


def test_duplicate_rejected(client, auth):
    body = {"mode": "english", "difficulty": "简单", "content": "a duplicated sentence for testing."}
    assert client.post("/api/typing/texts", json=body, headers=auth).status_code == 200
    assert client.post("/api/typing/texts", json=body, headers=auth).status_code == 409


def test_duplicate_ignores_whitespace(client, auth):
    """只差空格的两段算同一段，不该重复入库。"""
    a = {"mode": "english", "difficulty": "中等", "content": "spacing does not make it new."}
    b = {"mode": "english", "difficulty": "中等", "content": "spacing   does not  make it new."}
    assert client.post("/api/typing/texts", json=a, headers=auth).status_code == 200
    assert client.post("/api/typing/texts", json=b, headers=auth).status_code == 409


def test_update_and_deactivate(client, auth):
    rows = client.get("/api/typing/texts", params={"keyword": "专门为测试"}, headers=auth).json()
    tid = rows[0]["id"]

    res = client.put(
        f"/api/typing/texts/{tid}",
        json={"content": "改过之后的中文练习文本，同样足够长可以用来打字练习。"},
        headers=auth,
    )
    assert res.status_code == 200
    assert "改过之后" in res.json()["content"]

    res = client.put(f"/api/typing/texts/{tid}", json={"is_active": False}, headers=auth)
    assert res.json()["is_active"] is False


def test_delete(client, auth):
    rows = client.get("/api/typing/texts", params={"keyword": "改过之后"}, headers=auth).json()
    tid = rows[0]["id"]
    assert client.delete(f"/api/typing/texts/{tid}", headers=auth).status_code == 200
    assert client.delete(f"/api/typing/texts/{tid}", headers=auth).status_code == 404


# ---------------------------------------------------------------- txt 导入
def _upload(client, auth, text, mode="chinese", difficulty="困难", name="t.txt",
            encoding="utf-8", split="line"):
    return client.post(
        "/api/typing/texts/import",
        params={"mode": mode, "difficulty": difficulty, "split": split},
        files={"file": (name, io.BytesIO(text.encode(encoding)), "text/plain")},
        headers=auth,
    )


def test_import_line_per_passage(client, auth):
    """默认一行一段。文件里夹杂空行是常事，不能因此改变分段方式。"""
    txt = "\n".join([
        "导入测试第一段，内容足够长可以拿来练习打字。",
        "导入测试第二段，内容同样足够长可以拿来练习。",
        "短",                       # 太短，应被跳过
        "",                         # 空行
        "导入测试第三段，内容也足够长可以拿来练习打字。",
    ])
    res = _upload(client, auth, txt)
    assert res.status_code == 200
    body = res.json()
    assert body["added"] == 3
    assert body["too_short"] == 1


def test_import_blank_line_separated(client, auth):
    """显式选 blank 才按空行分段，段内换行折成空格 —— 贴整篇文章时用。"""
    txt = "第一段开头\n第一段接着写，这样拼起来足够长。\n\n第二段独立成段，长度也够用来练习。"
    res = _upload(client, auth, txt, difficulty="中等", split="blank")
    body = res.json()
    assert body["added"] == 2

    rows = client.get("/api/typing/texts", params={"keyword": "第一段接着写"}, headers=auth).json()
    assert "\n" not in rows[0]["content"]  # 段内换行已折成空格


def test_import_skips_duplicates(client, auth):
    txt = "重复导入检测用的这一段文字，长度足够。"
    first = _upload(client, auth, txt, difficulty="简单").json()
    second = _upload(client, auth, txt, difficulty="简单").json()
    assert first["added"] == 1
    assert second["added"] == 0 and second["skipped"] == 1


def test_import_gbk_encoding(client, auth):
    """老师从记事本另存的 txt 常常是 GBK，不能因为编码就报错。"""
    res = _upload(client, auth, "用国标编码保存的一段中文练习文本，长度足够。", encoding="gbk")
    assert res.status_code == 200
    assert res.json()["added"] == 1


def test_import_rejects_non_txt(client, auth):
    res = _upload(client, auth, "内容", name="x.docx")
    assert res.status_code == 400


def test_import_empty_file(client, auth):
    res = _upload(client, auth, "   \n\n  ")
    assert res.status_code == 400
