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
    res = client.patch(f"/api/auth/users/{teacher['id']}", json={"password": "abc"}, headers=auth)
    assert res.status_code == 422


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
