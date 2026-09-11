"""需求反馈与更新日志。

反馈是公开提交、公开展示的，所以重点测两件事：
联系方式不能出现在公开接口里；下架后公开列表要看不到。
"""


def _post(client, **kw):
    body = {"author": "张同学", "content": "希望打字练习能增加古诗文段落", "category": "建议"}
    body.update(kw)
    return client.post("/api/feedback", json=body)


# ---------------------------------------------------------------- 反馈
def test_submit_without_login(client):
    res = _post(client)
    assert res.status_code == 200
    body = res.json()
    assert body["author"] == "张同学"
    assert body["category"] == "建议"


def test_contact_never_exposed_publicly(client):
    """联系方式只给管理端看，公开接口里一个字都不能有。"""
    res = _post(client, author="李老师", contact="13800138000", content="建议增加错题本功能")
    assert res.status_code == 200
    assert "contact" not in res.json()

    raw = client.get("/api/feedback").text
    assert "13800138000" not in raw


def test_author_and_content_required(client):
    assert _post(client, author="  ").status_code == 400
    assert _post(client, content="短").status_code == 400


def test_unknown_category_rejected(client):
    assert _post(client, category="灌水").status_code == 400


def test_duplicate_submit_is_idempotent(client):
    """手抖点两次不该刷屏。"""
    a = _post(client, author="王同学", content="希望能在手机上也能练打字")
    b = _post(client, author="王同学", content="希望能在手机上也能练打字")
    assert a.json()["id"] == b.json()["id"]


def test_public_list_is_open(client):
    res = client.get("/api/feedback")
    assert res.status_code == 200
    assert len(res.json()) >= 1


def test_teacher_endpoints_need_login(client):
    assert client.get("/api/feedback/all").status_code == 401
    assert client.post("/api/feedback/1/reply", json={"reply": "好"}).status_code == 401


def test_teacher_sees_contact(client, auth):
    rows = client.get("/api/feedback/all", headers=auth).json()
    assert any(r.get("contact") == "13800138000" for r in rows)


def test_reply_shows_up_publicly(client, auth):
    fid = client.get("/api/feedback").json()[0]["id"]
    res = client.post(f"/api/feedback/{fid}/reply", json={"reply": "已排入下个版本"}, headers=auth)
    assert res.status_code == 200
    assert [r["content"] for r in res.json()["replies"]] == ["已排入下个版本"]

    shown = next(r for r in client.get("/api/feedback").json() if r["id"] == fid)
    assert shown["replies"][0]["content"] == "已排入下个版本"
    assert shown["replies"][0]["is_admin"] is True


def test_hidden_feedback_disappears_from_public_list(client, auth):
    fid = _post(client, author="临时", content="这条待会儿会被下架掉").json()["id"]
    assert any(r["id"] == fid for r in client.get("/api/feedback").json())

    res = client.patch(f"/api/feedback/{fid}/visibility", params={"is_public": False}, headers=auth)
    assert res.status_code == 200
    assert not any(r["id"] == fid for r in client.get("/api/feedback").json())

    # 下架不是删除，管理端还能看到
    assert any(r["id"] == fid for r in client.get("/api/feedback/all", headers=auth).json())

    client.delete(f"/api/feedback/{fid}", headers=auth)
    assert not any(r["id"] == fid for r in client.get("/api/feedback/all", headers=auth).json())


# ---------------------------------------------------------------- 更新日志
def test_changelog_is_public_and_grouped(client):
    versions = client.get("/api/changelog").json()
    assert versions, "初始化时应该已经灌进了历史版本"

    v = versions[0]
    assert {"version", "released_on", "groups"} <= set(v)
    assert v["groups"], "每个版本至少有一组变动"
    g = v["groups"][0]
    assert {"type", "label", "items"} <= set(g)
    assert g["items"][0]["content"]


def test_newest_version_first(client):
    dates = [v["released_on"] for v in client.get("/api/changelog").json()]
    assert dates == sorted(dates, reverse=True)


def test_groups_follow_spec_order(client):
    """组内顺序固定成 Added→Changed→…→Security，读起来才整齐。"""
    order = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]
    for v in client.get("/api/changelog").json():
        idx = [order.index(g["type"]) for g in v["groups"]]
        assert idx == sorted(idx), v["version"]


def test_change_types_endpoint(client):
    types = client.get("/api/changelog/types").json()
    assert [t["value"] for t in types] == [
        "Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"
    ]
    assert types[0]["label"] == "新增"


def test_latest_version(client):
    res = client.get("/api/changelog/latest").json()
    assert res["version"]
    assert res["released_on"]


def test_add_entry_needs_login(client):
    res = client.post(
        "/api/changelog",
        json={"version": "9.9.9", "change_type": "Added", "content": "偷偷加一条"},
    )
    assert res.status_code == 401


def test_plain_teacher_cannot_delete_entry(client, auth, teacher_auth):
    """更新日志是公共内容，普通教师加得了、删不了。"""
    eid = client.post(
        "/api/changelog",
        json={"version": "9.9.8", "change_type": "Fixed", "content": "普通教师建的条目"},
        headers=teacher_auth,
    ).json()["id"]

    res = client.delete(f"/api/changelog/{eid}", headers=teacher_auth)
    assert res.status_code == 403
    assert "删除权" in res.json()["detail"]

    # 管理员照样删得掉，收拾干净
    assert client.delete(f"/api/changelog/{eid}", headers=auth).status_code == 200


def test_teacher_adds_and_deletes_entry(client, auth):
    res = client.post(
        "/api/changelog",
        json={
            "version": "9.9.9",
            "released_on": "2026-12-31",
            "change_type": "Fixed",
            "content": "测试用条目",
        },
        headers=auth,
    )
    assert res.status_code == 200
    eid = res.json()["id"]

    top = client.get("/api/changelog").json()[0]
    assert top["version"] == "9.9.9"  # 日期最新，排在最前

    assert client.delete(f"/api/changelog/{eid}", headers=auth).status_code == 200
    assert client.get("/api/changelog").json()[0]["version"] != "9.9.9"


def test_invalid_change_type_rejected(client, auth):
    res = client.post(
        "/api/changelog",
        json={"version": "9.9.9", "change_type": "Improved", "content": "x"},
        headers=auth,
    )
    assert res.status_code == 400
