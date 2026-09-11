"""教师账号管理：新增、改资料、重置密码、停用与重新启用。

重点在两类边界：
1. 非管理员碰不到这些接口；
2. 管理员不能把自己锁在外面（降自己的级、停用自己）。
"""

import pytest


@pytest.fixture(scope="module")
def teacher(client, auth):
    """建一个普通教师账号，后面的用例都拿它做操作对象。"""
    res = client.post(
        "/api/auth/users",
        json={"username": "wanglaoshi", "password": "init-pass-123", "name": "王老师"},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    return res.json()


def _login(client, username, password):
    return client.post("/api/auth/login", data={"username": username, "password": password})


# ---------- 新增 ----------
def test_create_teacher(teacher):
    assert teacher["username"] == "wanglaoshi"
    assert teacher["name"] == "王老师"
    assert teacher["role"] == "teacher"
    assert teacher["is_active"] is True


def test_new_teacher_can_log_in(client, teacher):
    assert _login(client, "wanglaoshi", "init-pass-123").status_code == 200


def test_duplicate_username_rejected(client, auth, teacher):
    res = client.post(
        "/api/auth/users",
        json={"username": "wanglaoshi", "password": "another-pass"},
        headers=auth,
    )
    assert res.status_code == 400


# ---------- 权限 ----------
def test_teacher_cannot_manage_accounts(client, teacher):
    tok = _login(client, "wanglaoshi", "init-pass-123").json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/api/auth/users", headers=h).status_code == 403
    assert client.patch(f"/api/auth/users/{teacher['id']}", json={"name": "x"}, headers=h).status_code == 403
    assert client.post(
        "/api/auth/users", json={"username": "x", "password": "123456"}, headers=h
    ).status_code == 403


def test_anonymous_cannot_manage_accounts(client):
    assert client.get("/api/auth/users").status_code == 401


# ---------- 重置密码 ----------
def test_admin_resets_password(client, auth, teacher):
    """老师忘密码的唯一出路：管理员重置。"""
    res = client.patch(
        f"/api/auth/users/{teacher['id']}", json={"password": "brand-new-pw-456"}, headers=auth
    )
    assert res.status_code == 200

    assert _login(client, "wanglaoshi", "brand-new-pw-456").status_code == 200
    assert _login(client, "wanglaoshi", "init-pass-123").status_code == 400  # 旧密码失效


def test_short_password_rejected(client, auth, teacher):
    """密码不合规要回 400 + 一句中文，不能是 422 的英文结构体。

    422 的 detail 是数组，界面上只能显示成"请求失败"，老师看了不知道改什么。
    """
    res = client.patch(f"/api/auth/users/{teacher['id']}", json={"password": "abc"}, headers=auth)
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert isinstance(detail, str) and "至少 6 位" in detail


@pytest.mark.parametrize(
    "payload, expect",
    [
        ({"username": "ab", "password": "goodpass1"}, "太短"),
        ({"username": "王老师", "password": "goodpass1"}, "字母"),
        ({"username": "has space", "password": "goodpass1"}, "字母"),
        ({"username": "okname", "password": "12345"}, "至少 6 位"),
        ({"username": "okname", "password": "12345678"}, "纯数字"),
        ({"username": "okname", "password": " padded123 "}, "空格"),
    ],
)
def test_bad_credentials_explain_why(client, auth, payload, expect):
    """每种不合规都要说清楚是哪不合规，而不是笼统地失败。"""
    res = client.post("/api/auth/users", json=payload, headers=auth)
    assert res.status_code == 400, res.text
    detail = res.json()["detail"]
    assert isinstance(detail, str), "detail 必须是一句话，不能是 422 那种数组"
    assert expect in detail, f"期望提到「{expect}」，实际是：{detail}"


def test_duplicate_username_is_case_insensitive(client, auth):
    client.post(
        "/api/auth/users", json={"username": "LiMing", "password": "goodpass1"}, headers=auth
    )
    res = client.post(
        "/api/auth/users", json={"username": "liming", "password": "goodpass1"}, headers=auth
    )
    assert res.status_code == 400
    assert "已存在" in res.json()["detail"]


# ---------- 改资料 ----------
def test_rename_and_change_role(client, auth, teacher):
    res = client.patch(
        f"/api/auth/users/{teacher['id']}", json={"name": "王小明", "role": "admin"}, headers=auth
    )
    assert res.status_code == 200
    assert res.json()["name"] == "王小明"
    assert res.json()["role"] == "admin"

    # 改回教师，不影响后面的用例
    client.patch(f"/api/auth/users/{teacher['id']}", json={"role": "teacher"}, headers=auth)


def test_invalid_role_rejected(client, auth, teacher):
    res = client.patch(f"/api/auth/users/{teacher['id']}", json={"role": "superuser"}, headers=auth)
    assert res.status_code == 400


def test_patch_unknown_user_is_404(client, auth):
    assert client.patch("/api/auth/users/999999", json={"name": "x"}, headers=auth).status_code == 404


# ---------- 管理员的自我保护 ----------
def test_admin_cannot_demote_self(client, auth):
    me = client.get("/api/auth/me", headers=auth).json()
    res = client.patch(f"/api/auth/users/{me['id']}", json={"role": "teacher"}, headers=auth)
    assert res.status_code == 400
    assert "自己" in res.json()["detail"]


def test_admin_cannot_deactivate_self(client, auth):
    me = client.get("/api/auth/me", headers=auth).json()
    assert client.delete(f"/api/auth/users/{me['id']}", headers=auth).status_code == 400
    res = client.patch(f"/api/auth/users/{me['id']}", json={"is_active": False}, headers=auth)
    assert res.status_code == 400


# ---------- 停用与重新启用 ----------
def test_deactivate_then_reactivate(client, auth, teacher):
    assert client.delete(f"/api/auth/users/{teacher['id']}", headers=auth).status_code == 200

    blocked = _login(client, "wanglaoshi", "brand-new-pw-456")
    assert blocked.status_code == 403
    assert "停用" in blocked.json()["detail"]

    # 重新启用——原来只能停用不能恢复，误停一个人就得重建账号
    res = client.patch(f"/api/auth/users/{teacher['id']}", json={"is_active": True}, headers=auth)
    assert res.status_code == 200
    assert res.json()["is_active"] is True
    assert _login(client, "wanglaoshi", "brand-new-pw-456").status_code == 200


# ---------- 批量操作与真删除 ----------
def _mk(client, auth, username, role="teacher"):
    res = client.post(
        "/api/auth/users",
        json={"username": username, "password": "goodpass1", "role": role},
        headers=auth,
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_bulk_disable_and_enable(client, auth):
    a, b = _mk(client, auth, "bulk.a"), _mk(client, auth, "bulk.b")
    ids = [a["id"], b["id"]]

    res = client.post(
        "/api/auth/users/bulk", json={"ids": ids, "action": "disable"}, headers=auth
    )
    assert res.status_code == 200 and res.json()["affected"] == 2
    assert _login(client, "bulk.a", "goodpass1").status_code == 403  # 停用了，登不上

    client.post("/api/auth/users/bulk", json={"ids": ids, "action": "enable"}, headers=auth)
    assert _login(client, "bulk.a", "goodpass1").status_code == 200


def test_bulk_delete_removes_accounts(client, auth):
    a = _mk(client, auth, "bulk.gone")
    res = client.post(
        "/api/auth/users/bulk", json={"ids": [a["id"]], "action": "delete"}, headers=auth
    )
    assert res.status_code == 200 and res.json()["affected"] == 1

    names = [u["username"] for u in client.get("/api/auth/users", headers=auth).json()]
    assert "bulk.gone" not in names
    assert _login(client, "bulk.gone", "goodpass1").status_code == 400


def test_cannot_delete_or_disable_self(client, auth):
    me = client.get("/api/auth/me", headers=auth).json()
    for action in ("delete", "disable"):
        res = client.post(
            "/api/auth/users/bulk", json={"ids": [me["id"]], "action": action}, headers=auth
        )
        assert res.status_code == 400
        assert "自己" in res.json()["detail"]


def test_cannot_delete_the_last_admin(client, auth):
    """把管理员删光会让谁都进不了账号管理页，只能去服务器上改库。"""
    me = client.get("/api/auth/me", headers=auth).json()
    other = _mk(client, auth, "adm.two", role="admin")

    # 删掉另一个管理员没问题，自己还在
    res = client.post(
        "/api/auth/users/bulk", json={"ids": [other["id"]], "action": "delete"}, headers=auth
    )
    assert res.status_code == 200

    # 但连自己一起删就该被拦住（这里先被「不能删自己」挡下）
    res = client.post(
        "/api/auth/users/bulk", json={"ids": [me["id"]], "action": "delete"}, headers=auth
    )
    assert res.status_code == 400


def test_delete_keeps_the_data_they_made(client, auth):
    """删账号不能连带删掉他建的题目——那是全校共用的资产。"""
    from app.database import SessionLocal
    from app.models import Question

    teacher = _mk(client, auth, "bulk.author")
    tok = _login(client, "bulk.author", "goodpass1").json()["access_token"]
    made = client.post(
        "/api/questions",
        json={"type": "选择题", "stem": "删账号后这道题要还在", "answer": "A", "scope": "信息基础与信息技术"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert made.status_code == 200, made.text
    qid = made.json()["id"]

    client.post(
        "/api/auth/users/bulk", json={"ids": [teacher["id"]], "action": "delete"}, headers=auth
    )

    db = SessionLocal()
    try:
        q = db.get(Question, qid)
        assert q is not None, "题目跟着账号一起没了"
        assert q.created_by is None, "外键该被置空"
    finally:
        db.close()


def test_bulk_needs_admin(client):
    res = client.post("/api/auth/users/bulk", json={"ids": [1], "action": "delete"})
    assert res.status_code == 401
