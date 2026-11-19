"""需求反馈与更新日志。

反馈是公开提交的，但**要管理员审核过才公开展示**。重点测三件事：
新提交的不能直接出现在公开区；联系方式不能出现在公开接口里；
审核状态的流转（通过 / 拒绝 / 退回）。
"""


def _post(client, **kw):
    body = {"author": "张同学", "content": "希望打字练习能增加古诗文段落", "category": "建议"}
    body.update(kw)
    return client.post("/api/feedback", json=body)


def _approve(client, auth, fid):
    """审过一条，让它进公开区。"""
    res = client.patch(
        f"/api/feedback/{fid}/review", json={"status": "approved"}, headers=auth
    )
    assert res.status_code == 200, res.text
    return res.json()


def _post_approved(client, auth, **kw):
    fid = _post(client, **kw).json()["id"]
    _approve(client, auth, fid)
    return fid


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


def test_new_feedback_is_not_public_until_reviewed(client, auth):
    """先审后发：刚提交的不该出现在公开区。"""
    fid = _post(client, author="待审同学", content="这条提交完应该处于待审核状态").json()["id"]
    assert not any(r["id"] == fid for r in client.get("/api/feedback").json())

    # 但管理端看得到，状态是 pending
    mine = next(r for r in client.get("/api/feedback/all", headers=auth).json() if r["id"] == fid)
    assert mine["status"] == "pending"

    _approve(client, auth, fid)
    assert any(r["id"] == fid for r in client.get("/api/feedback").json())


def test_public_list_is_open(client, auth):
    _post_approved(client, auth, author="公开列表", content="这条用来保证公开列表至少有一条")
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
    fid = _post_approved(client, auth, author="回复对象", content="这条会被老师回复，回复要公开显示")
    res = client.post(f"/api/feedback/{fid}/reply", json={"reply": "已排入下个版本"}, headers=auth)
    assert res.status_code == 200
    assert [r["content"] for r in res.json()["replies"]] == ["已排入下个版本"]

    shown = next(r for r in client.get("/api/feedback").json() if r["id"] == fid)
    assert shown["replies"][0]["content"] == "已排入下个版本"
    assert shown["replies"][0]["is_admin"] is True


def test_rejected_feedback_disappears_from_public_list(client, auth):
    fid = _post_approved(client, auth, author="临时", content="这条待会儿会被拒掉")
    assert any(r["id"] == fid for r in client.get("/api/feedback").json())

    res = client.patch(
        f"/api/feedback/{fid}/review",
        json={"status": "rejected", "note": "内容不合适"},
        headers=auth,
    )
    assert res.status_code == 200
    assert not any(r["id"] == fid for r in client.get("/api/feedback").json())

    # 拒绝不是删除，管理端还能看到，而且留着拒绝原因
    row = next(r for r in client.get("/api/feedback/all", headers=auth).json() if r["id"] == fid)
    assert row["status"] == "rejected"
    assert row["review_note"] == "内容不合适"

    client.delete(f"/api/feedback/{fid}", headers=auth)
    assert not any(r["id"] == fid for r in client.get("/api/feedback/all", headers=auth).json())


def test_cannot_reply_or_like_before_approval(client, auth, teacher_auth):
    """待审的内容还没公开，回复和点赞都没有意义，应该被挡下来。"""
    fid = _post(client, author="待审", content="这条在审核通过前不该能回复或点赞").json()["id"]

    assert client.post(
        f"/api/feedback/{fid}/reply", json={"reply": "抢先回一句"}, headers=teacher_auth
    ).status_code == 409
    assert client.post(f"/api/feedback/{fid}/like", headers=teacher_auth).status_code == 409

    _approve(client, auth, fid)
    assert client.post(
        f"/api/feedback/{fid}/reply", json={"reply": "现在可以了"}, headers=teacher_auth
    ).status_code == 200


def test_bulk_review(client, auth):
    ids = [
        _post(client, author=f"批量{i}", content=f"批量审核测试第 {i} 条内容").json()["id"]
        for i in range(3)
    ]
    res = client.post(
        "/api/feedback/review-bulk", json={"ids": ids, "status": "approved"}, headers=auth
    )
    assert res.json()["affected"] == 3

    public = {r["id"] for r in client.get("/api/feedback").json()}
    assert set(ids) <= public


def test_pending_count_visible_to_teachers(client, auth, teacher_auth):
    before = client.get("/api/feedback/pending-count", headers=teacher_auth).json()["pending"]
    _post(client, author="计数", content="这条提交后待审数应该加一")
    after = client.get("/api/feedback/pending-count", headers=teacher_auth).json()["pending"]
    assert after == before + 1


# ---------------------------------------------------------------- 更新日志
def test_changelog_is_admin_only(client, teacher_auth):
    """更新日志整个模块收归管理员，普通教师连看都看不到。"""
    for url in ["/api/changelog", "/api/changelog/types"]:
        assert client.get(url).status_code == 401, f"{url} 竟然免登录就能看"
        res = client.get(url, headers=teacher_auth)
        assert res.status_code == 403, f"{url} 放普通教师进去了"
        assert "管理员" in res.json()["detail"]

    # 页脚那个版本号是例外：谁都要显示，但它只回一个版本号，不含内容
    res = client.get("/api/changelog/latest")
    assert res.status_code == 200
    assert set(res.json()) <= {"version", "released_on"}


def test_changelog_is_grouped(client, auth):
    versions = client.get("/api/changelog", headers=auth).json()
    assert versions, "初始化时应该已经灌进了历史版本"

    v = versions[0]
    assert {"version", "released_on", "groups"} <= set(v)
    assert v["groups"], "每个版本至少有一组变动"
    g = v["groups"][0]
    assert {"type", "label", "items"} <= set(g)
    assert g["items"][0]["content"]


def test_newest_version_first(client, auth):
    dates = [v["released_on"] for v in client.get("/api/changelog", headers=auth).json()]
    assert dates == sorted(dates, reverse=True)


def test_groups_follow_spec_order(client, auth):
    """组内顺序固定成 Added→Changed→…→Security，读起来才整齐。"""
    order = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]
    for v in client.get("/api/changelog", headers=auth).json():
        idx = [order.index(g["type"]) for g in v["groups"]]
        assert idx == sorted(idx), v["version"]


def test_change_types_endpoint(client, auth):
    types = client.get("/api/changelog/types", headers=auth).json()
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


def test_plain_teacher_cannot_write_entries(client, auth, teacher_auth):
    """普通教师既加不了也删不了 —— 整个模块都不归他管。"""
    res = client.post(
        "/api/changelog",
        json={"version": "9.9.8", "change_type": "Fixed", "content": "普通教师建的条目"},
        headers=teacher_auth,
    )
    assert res.status_code == 403 and "管理员" in res.json()["detail"]

    eid = client.post(
        "/api/changelog",
        json={"version": "9.9.8", "change_type": "Fixed", "content": "管理员建的条目"},
        headers=auth,
    ).json()["id"]
    assert client.delete(f"/api/changelog/{eid}", headers=teacher_auth).status_code == 403
    # 管理员照样删得掉，收拾干净
    assert client.delete(f"/api/changelog/{eid}", headers=auth).status_code == 200


def test_admin_adds_and_deletes_entry(client, auth):
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

    top = client.get("/api/changelog", headers=auth).json()[0]
    assert top["version"] == "9.9.9"  # 日期最新，排在最前

    assert client.delete(f"/api/changelog/{eid}", headers=auth).status_code == 200
    assert client.get("/api/changelog", headers=auth).json()[0]["version"] != "9.9.9"


def test_invalid_change_type_rejected(client, auth):
    res = client.post(
        "/api/changelog",
        json={"version": "9.9.9", "change_type": "Improved", "content": "x"},
        headers=auth,
    )
    assert res.status_code == 400


# ---------------------------------------------------------------- 反馈配图
PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


def test_upload_image_and_attach(client, auth):
    res = client.post(
        "/api/feedback/images", files={"file": ("shot.png", PNG_1PX, "image/png")}
    )
    assert res.status_code == 200, res.text
    url = res.json()["image_url"]
    assert url.startswith("/uploads/feedback/") and url.endswith(".png")

    fid = client.post(
        "/api/feedback",
        json={"author": "带图同学", "category": "问题", "content": "这里显示不正常，见图", "images": [url]},
    ).json()["id"]
    _approve(client, auth, fid)

    row = next(r for r in client.get("/api/feedback").json() if r["id"] == fid)
    assert row["images"] == [url]


def test_upload_rejects_non_image(client):
    """光看扩展名不够：改个名字就能往服务器上放任意文件。"""
    res = client.post(
        "/api/feedback/images",
        files={"file": ("fake.png", b"#!/bin/sh\nrm -rf /\n", "image/png")},
    )
    assert res.status_code == 400
    assert "不是图片" in res.json()["detail"]


def test_upload_rejects_other_extensions(client):
    res = client.post(
        "/api/feedback/images", files={"file": ("a.exe", PNG_1PX, "application/octet-stream")}
    )
    assert res.status_code == 400
    assert "png/jpg" in res.json()["detail"]


def test_network_image_url_accepted(client, auth):
    url = "https://example.com/pic.png"
    fid = client.post(
        "/api/feedback",
        json={"author": "外链同学", "category": "建议", "content": "配一张网络图片试试", "images": [url]},
    ).json()["id"]
    _approve(client, auth, fid)
    row = next(r for r in client.get("/api/feedback").json() if r["id"] == fid)
    assert row["images"] == [url]


def test_bad_image_url_rejected(client):
    res = client.post(
        "/api/feedback",
        json={
            "author": "乱填同学",
            "category": "建议",
            "content": "这条的图片地址是乱填的，应该被挡住",
            "images": ["javascript:alert(1)"],
        },
    )
    assert res.status_code == 400
    assert "http" in res.json()["detail"]


def test_too_many_images_rejected(client):
    res = client.post(
        "/api/feedback",
        json={
            "author": "图多同学",
            "category": "建议",
            "content": "一条配四张图应该被挡住，最多三张",
            "images": [f"https://example.com/{i}.png" for i in range(4)],
        },
    )
    assert res.status_code == 400
    assert "最多" in res.json()["detail"]


def test_footer_version_matches_the_newest_entry(client, auth):
    """页脚的版本号必须和更新日志第一条一致。

    真出过：页脚落后两三个版本。两个原因叠在一起 ——
    /changelog/latest 按 id 取（而 seed 是从新到旧插的，同一天里最旧的 id 最大），
    列表按字符串排（2.4.10 会被排到 2.4.9 下面）。一天只发一版时日期能兜住，
    一天发好几版就露馅了。
    """
    versions = client.get("/api/changelog", headers=auth).json()
    latest = client.get("/api/changelog/latest").json()
    assert versions[0]["version"] == latest["version"], (
        f"页脚显示 {latest['version']}，列表第一条却是 {versions[0]['version']}"
    )


def test_version_order_is_numeric_not_alphabetical(client, auth):
    """2.4.10 要排在 2.4.9 前面 —— 按字符串比就会反过来。"""
    from app.routers.community import version_key

    assert version_key("2.4.10") > version_key("2.4.9")
    assert version_key("2.5.0") > version_key("2.4.10")
    assert version_key("0.0.9-permtest") == (0, 0, 9), "认不出的段按 0 算，不能抛异常"

    # 真实数据里也要成立：同一天发的版本按数值从大到小排
    versions = client.get("/api/changelog", headers=auth).json()
    by_date: dict[str, list] = {}
    for v in versions:
        by_date.setdefault(v["released_on"], []).append(version_key(v["version"]))
    for day, keys in by_date.items():
        assert keys == sorted(keys, reverse=True), f"{day} 这天的版本顺序乱了：{keys}"


# ---------------------------------------------------------------- 置顶黄条（2.23.2）
def _clear_pins():
    from app.database import SessionLocal
    from app.models import Feedback

    with SessionLocal() as db:
        for f in db.query(Feedback).filter(Feedback.pinned_at.is_not(None)):
            f.pinned_at = f.pinned_until = None
        db.commit()


def _news(client, headers):
    res = client.get("/api/feedback/news", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()["items"]


def test_黄条只显示置顶的(client, auth, teacher_auth):
    _clear_pins()
    assert client.get("/api/feedback/news").status_code == 401
    fid = _post_approved(client, auth, content="黄条只显示置顶的" + "啊" * 100)
    assert _news(client, teacher_auth) == [], "最新消息不再自动上黄条"

    res = client.put(f"/api/feedback/{fid}/pin", json={"days": 0}, headers=auth)
    assert res.status_code == 200 and res.json()["pinned"] is True and res.json()["pinned_until"] is None
    client.post(f"/api/feedback/{fid}/reply", json={"reply": "已经安排上了"}, headers=auth)
    items = _news(client, teacher_auth)
    assert len(items) == 1 and items[0]["feedback_id"] == fid
    assert items[0]["text"].endswith("…") and items[0]["reply_count"] == 1
    assert items[0]["last_reply"]["text"] == "已经安排上了" and items[0]["pinned_until"] is None
    # 公开列表里置顶的排最前
    assert client.get("/api/feedback").json()[0]["id"] == fid

    assert client.delete(f"/api/feedback/{fid}/pin", headers=auth).json()["pinned"] is False
    assert _news(client, teacher_auth) == []


def test_置顶只给管理员_只能置顶公开的(client, auth, teacher_auth):
    _clear_pins()
    fid = _post_approved(client, auth, content="只有管理员能置顶")
    assert client.put(f"/api/feedback/{fid}/pin", json={"days": 3}, headers=teacher_auth).status_code == 403
    pending = _post(client, content="还没审的不能置顶").json()["id"]
    assert client.put(f"/api/feedback/{pending}/pin", json={"days": 3}, headers=auth).status_code == 409
    assert client.put(f"/api/feedback/{fid}/pin", json={"days": 31}, headers=auth).status_code == 422
    # 撤下（拒绝）后黄条上就没有了
    client.put(f"/api/feedback/{fid}/pin", json={"days": 3}, headers=auth)
    _approve(client, auth, fid)
    client.patch(f"/api/feedback/{fid}/review", json={"status": "rejected"}, headers=auth)
    assert _news(client, teacher_auth) == []


def test_最多置顶5条(client, auth, teacher_auth):
    _clear_pins()
    ids = [_post_approved(client, auth, content=f"置顶第 {i} 条") for i in range(6)]
    for fid in ids[:5]:
        assert client.put(f"/api/feedback/{fid}/pin", json={"days": 0}, headers=auth).status_code == 200
    res = client.put(f"/api/feedback/{ids[5]}/pin", json={"days": 0}, headers=auth)
    assert res.status_code == 409 and "最多同时置顶 5 条" in res.json()["detail"]
    # 已经置顶的改期限不受限
    assert client.put(f"/api/feedback/{ids[0]}/pin", json={"days": 7}, headers=auth).status_code == 200
    assert len(_news(client, teacher_auth)) == 5
    client.delete(f"/api/feedback/{ids[1]}/pin", headers=auth)
    assert client.put(f"/api/feedback/{ids[5]}/pin", json={"days": 0}, headers=auth).status_code == 200
    _clear_pins()


def test_置顶到期自动不显示(client, auth, teacher_auth, monkeypatch):
    from datetime import timedelta

    from app import clock

    _clear_pins()
    fid = _post_approved(client, auth, content="置顶 2 天")
    got = client.put(f"/api/feedback/{fid}/pin", json={"days": 2}, headers=auth).json()
    assert got["pinned_until"]
    assert len(_news(client, teacher_auth)) == 1
    real = clock.now
    monkeypatch.setattr(clock, "now", lambda: real() + timedelta(days=2, minutes=1))
    assert _news(client, teacher_auth) == []
    assert client.get("/api/feedback").json()[0].get("pinned") is not True or         client.get("/api/feedback").json()[0]["id"] != fid
