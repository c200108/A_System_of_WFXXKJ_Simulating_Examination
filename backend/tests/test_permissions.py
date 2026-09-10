"""权限隔离：考试按人隔离、反馈的下架删除只有管理员能做、老师能改自己的资料。

这一组测的都是"谁能看到什么、谁能动什么"，出问题就是越权，
所以断言写得比别处死一些：不光看状态码，还看列表里到底有没有那一条。
"""


def _ensure_bank(client, headers):
    """保证题库里有足够题目可抽。单独跑这个文件时题库是空的，先垫几道进去。

    题干重复会被接口按哈希挡掉，所以这里可以反复调用。
    """
    from app.constants import DICT_SCOPE, DICT_TYPE

    rows = client.get("/api/dicts", headers=headers).json()
    scope = next(r["name"] for r in rows if r["category"] == DICT_SCOPE)
    qtype = next(r["name"] for r in rows if r["category"] == DICT_TYPE)
    for i in range(4):
        client.post(
            "/api/questions",
            json={
                "type": qtype,
                "stem": f"权限测试专用题 {i}：下面哪一项说法是正确的？",
                "answer": "A",
                "scope": scope,
                "options": [
                    {"label": "A", "content": "正确的那一项"},
                    {"label": "B", "content": "不对的那一项"},
                    {"label": "C", "content": "也不对"},
                    {"label": "D", "content": "还是不对"},
                ],
            },
            headers=headers,
        )
    return qtype


def _publish(client, headers, title):
    """组一份卷、存档、发布成考试，返回考试 id。发布人就是 headers 对应的老师。"""
    qtype = _ensure_bank(client, headers)
    paper = client.post(
        "/api/papers/generate",
        json={"title": title, "counts": {qtype: 2}, "save": True},
        headers=headers,
    ).json()
    assert paper.get("paper_id"), f"组卷要先存档才能发布考试：{paper}"

    res = client.post(
        "/api/exams", json={"paper_id": paper["paper_id"], "title": title}, headers=headers
    )
    assert res.status_code == 200, res.text
    return res.json()["id"]


# ---------------------------------------------------------------- 考试隔离
def test_teacher_only_sees_own_exams(client, teacher_auth, teacher2_auth):
    a = _publish(client, teacher_auth, "甲老师的期中卷")
    b = _publish(client, teacher2_auth, "乙老师的期中卷")

    mine = [e["id"] for e in client.get("/api/exams", headers=teacher_auth).json()]
    assert a in mine
    assert b not in mine, "甲老师不该看见乙老师发布的考试"

    theirs = [e["id"] for e in client.get("/api/exams", headers=teacher2_auth).json()]
    assert b in theirs and a not in theirs


def test_admin_sees_every_exam_with_owner_name(client, auth, teacher_auth):
    a = _publish(client, teacher_auth, "甲老师的单元测")
    rows = client.get("/api/exams", headers=auth).json()
    ids = [e["id"] for e in rows]
    assert a in ids, "管理员应该看得到所有老师的考试"

    row = next(e for e in rows if e["id"] == a)
    assert row["owner_name"] == "甲老师", "管理员看列表要能分清是谁发的"


def test_owner_name_is_blank_for_teachers(client, teacher_auth):
    """老师看到的都是自己的，不用再标一遍是谁发的。"""
    _publish(client, teacher_auth, "甲老师的随堂练")
    rows = client.get("/api/exams", headers=teacher_auth).json()
    assert all(e["owner_name"] == "" for e in rows)


def test_other_teacher_cannot_touch_your_exam(client, teacher_auth, teacher2_auth):
    """看不见还不够，直接拿 id 打接口也得挡住。"""
    eid = _publish(client, teacher_auth, "甲老师的保密卷")

    for method, url in [
        ("get", f"/api/exams/{eid}"),
        ("get", f"/api/exams/{eid}/submissions"),
        ("get", f"/api/exams/{eid}/stats"),
        ("get", f"/api/exams/{eid}/export.xlsx"),
    ]:
        res = getattr(client, method)(url, headers=teacher2_auth)
        assert res.status_code == 404, f"{url} 越权了：{res.status_code}"

    assert client.patch(
        f"/api/exams/{eid}", json={"is_open": False}, headers=teacher2_auth
    ).status_code == 404
    assert client.delete(f"/api/exams/{eid}", headers=teacher2_auth).status_code == 404

    # 本人当然还动得了
    assert client.get(f"/api/exams/{eid}", headers=teacher_auth).status_code == 200


def test_admin_can_touch_any_exam(client, auth, teacher_auth):
    eid = _publish(client, teacher_auth, "甲老师的月考卷")
    assert client.get(f"/api/exams/{eid}", headers=auth).status_code == 200
    assert client.patch(
        f"/api/exams/{eid}", json={"is_open": False}, headers=auth
    ).status_code == 200


def test_student_link_still_works_for_anyone(client, teacher_auth):
    """隔离只针对教师端。学生凭链接答题是公开的，不能被这次改动挡住。"""
    eid = _publish(client, teacher_auth, "甲老师的公开考试")
    token = client.get(f"/api/exams/{eid}", headers=teacher_auth).json()["token"]
    res = client.get(f"/api/take/{token}")  # 不带任何令牌
    assert res.status_code == 200


# ---------------------------------------------------------------- 个人资料
def test_teacher_updates_own_profile(client, teacher_auth):
    res = client.patch(
        "/api/auth/me",
        json={"name": "甲老师", "grade_class": "七年级 1-4 班", "contact": "13900000001"},
        headers=teacher_auth,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["grade_class"] == "七年级 1-4 班"
    assert body["contact"] == "13900000001"

    # 再取一次确认真的落库了
    assert client.get("/api/auth/me", headers=teacher_auth).json()["grade_class"] == "七年级 1-4 班"


def test_profile_cannot_change_role_or_username(client, teacher_auth):
    """改自己资料的接口不接受 role/username/is_active，防止自我提权。"""
    client.patch(
        "/api/auth/me",
        json={"role": "admin", "username": "hacker", "is_active": False},
        headers=teacher_auth,
    )
    me = client.get("/api/auth/me", headers=teacher_auth).json()
    assert me["role"] == "teacher"
    assert me["username"] == "teacher_a"
    assert me["is_active"] is True


def test_profile_needs_login(client):
    assert client.patch("/api/auth/me", json={"name": "无名"}).status_code == 401


# ---------------------------------------------------------------- 反馈权限
def _new_feedback(client, content):
    return client.post(
        "/api/feedback",
        json={"author": "权限测试", "category": "建议", "content": content},
    ).json()["id"]


def test_only_admin_can_hide_feedback(client, teacher_auth, auth):
    fid = _new_feedback(client, "这条用来测下架权限，普通老师不该能下架它")

    res = client.patch(
        f"/api/feedback/{fid}/visibility", params={"is_public": False}, headers=teacher_auth
    )
    assert res.status_code == 403
    assert any(r["id"] == fid for r in client.get("/api/feedback").json()), "老师下架不该生效"

    assert client.patch(
        f"/api/feedback/{fid}/visibility", params={"is_public": False}, headers=auth
    ).status_code == 200
    assert not any(r["id"] == fid for r in client.get("/api/feedback").json())


def test_only_admin_can_delete_feedback(client, teacher_auth, auth):
    fid = _new_feedback(client, "这条用来测删除权限，普通老师不该能删掉它")
    assert client.delete(f"/api/feedback/{fid}", headers=teacher_auth).status_code == 403
    assert any(r["id"] == fid for r in client.get("/api/feedback").json())
    assert client.delete(f"/api/feedback/{fid}", headers=auth).status_code == 200


def test_only_admin_sees_contacts(client, teacher_auth, auth):
    """联系方式是管理端专属，普通老师连这个接口都进不去。"""
    assert client.get("/api/feedback/all", headers=teacher_auth).status_code == 403
    assert client.get("/api/feedback/all", headers=auth).status_code == 200


def test_teachers_replies_do_not_overwrite_each_other(client, teacher_auth, teacher2_auth):
    fid = _new_feedback(client, "这条会有两位老师分别回复，谁也不该盖掉谁")

    client.post(f"/api/feedback/{fid}/reply", json={"reply": "甲老师：收到了"}, headers=teacher_auth)
    res = client.post(
        f"/api/feedback/{fid}/reply", json={"reply": "乙老师：我补充一句"}, headers=teacher2_auth
    )
    assert res.status_code == 200

    replies = res.json()["replies"]
    assert [r["content"] for r in replies] == ["甲老师：收到了", "乙老师：我补充一句"]
    assert [r["author"] for r in replies] == ["甲老师", "乙老师"]
    assert all(r["is_admin"] is False for r in replies)


def test_empty_reply_is_rejected(client, teacher_auth):
    fid = _new_feedback(client, "空回复应该被挡下来，不该留一条白板")
    res = client.post(f"/api/feedback/{fid}/reply", json={"reply": "   "}, headers=teacher_auth)
    assert res.status_code == 400


def test_reply_can_only_be_withdrawn_by_author_or_admin(client, teacher_auth, teacher2_auth, auth):
    fid = _new_feedback(client, "这条用来测回复能不能被别人撤回")
    res = client.post(f"/api/feedback/{fid}/reply", json={"reply": "甲老师的回复"}, headers=teacher_auth)
    rid = res.json()["replies"][0]["id"]

    assert client.delete(f"/api/feedback/replies/{rid}", headers=teacher2_auth).status_code == 403
    assert client.delete(f"/api/feedback/replies/{rid}", headers=teacher_auth).status_code == 200

    # 管理员撤别人的可以
    res = client.post(f"/api/feedback/{fid}/reply", json={"reply": "再来一条"}, headers=teacher_auth)
    rid2 = res.json()["replies"][0]["id"]
    assert client.delete(f"/api/feedback/replies/{rid2}", headers=auth).status_code == 200


def test_like_toggles_and_counts_once_per_person(client, teacher_auth, teacher2_auth):
    fid = _new_feedback(client, "这条用来测点赞，点两次应该变成取消")

    res = client.post(f"/api/feedback/{fid}/like", headers=teacher_auth)
    assert res.json()["like_count"] == 1
    assert res.json()["liked_by_me"] is True

    # 同一个人再点就是取消
    res = client.post(f"/api/feedback/{fid}/like", headers=teacher_auth)
    assert res.json()["like_count"] == 0
    assert res.json()["liked_by_me"] is False

    # 两个人各点一次是 2
    client.post(f"/api/feedback/{fid}/like", headers=teacher_auth)
    res = client.post(f"/api/feedback/{fid}/like", headers=teacher2_auth)
    assert res.json()["like_count"] == 2


def test_like_needs_login(client):
    fid = _new_feedback(client, "没登录的人不该能点赞，这条用来验证")
    assert client.post(f"/api/feedback/{fid}/like").status_code == 401


def test_public_list_marks_my_likes(client, teacher_auth):
    """带令牌看列表要能认出自己点过的赞；不带令牌照样能看，只是都显示没点过。"""
    fid = _new_feedback(client, "这条用来验证列表里的点赞标记对不对")
    client.post(f"/api/feedback/{fid}/like", headers=teacher_auth)

    row = next(r for r in client.get("/api/feedback", headers=teacher_auth).json() if r["id"] == fid)
    assert row["liked_by_me"] is True and row["like_count"] == 1

    anon = next(r for r in client.get("/api/feedback").json() if r["id"] == fid)
    assert anon["liked_by_me"] is False and anon["like_count"] == 1


def test_emoji_survives_a_round_trip(client, teacher_auth):
    """评论和回复都要能存表情。数据库是 utf8mb4，4 字节字符不能被截断。"""
    text = "希望能加个夜间模式 🌙✨，晚上做题眼睛疼 😣"
    fid = client.post(
        "/api/feedback", json={"author": "小明 🙂", "category": "建议", "content": text}
    ).json()["id"]

    row = next(r for r in client.get("/api/feedback").json() if r["id"] == fid)
    assert row["content"] == text
    assert row["author"] == "小明 🙂"

    res = client.post(f"/api/feedback/{fid}/reply", json={"reply": "好主意 👍🏻，记下了"}, headers=teacher_auth)
    assert res.json()["replies"][0]["content"] == "好主意 👍🏻，记下了"
