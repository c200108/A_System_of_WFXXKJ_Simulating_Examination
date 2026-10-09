"""教师端安卓 APP 的两个接口：认服务器、心跳保持登录（5.0.0）。"""

from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings
from app.security import TOKEN_STUDENT, TOKEN_TEACHER


def _token(user_id: int, role: str, age_minutes: float, typ: str = TOKEN_TEACHER) -> str:
    """造一张已经签发了 age_minutes 分钟的令牌，模拟 APP 开了很久。"""
    issued = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    payload = {
        "sub": str(user_id),
        "role": role,
        "typ": typ,
        "iat": issued,
        "exp": issued + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _admin_id(client, auth) -> int:
    return client.get("/api/auth/me", headers=auth).json()["id"]


def test_info_is_public_and_identifies_the_server(client):
    res = client.get("/api/app/info")
    assert res.status_code == 200
    body = res.json()
    # APP 靠这个字段认出是本系统，填错地址（比如别的网站）就对不上
    assert body["app"] == "wfxxkj-exam"
    assert body["protocol"] >= 1
    assert body["heartbeat_seconds"] > 0
    assert body["title"]


def test_session_requires_teacher_login(client):
    assert client.post("/api/app/session").status_code == 401
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.post("/api/app/session", headers=bad).status_code == 401


def test_session_rejects_student_token(client, auth):
    uid = _admin_id(client, auth)
    stu = {"Authorization": f"Bearer {_token(uid, 'student', 1, TOKEN_STUDENT)}"}
    assert client.post("/api/app/session", headers=stu).status_code == 401


def test_fresh_token_is_kept(client, auth):
    """刚登录不久：不换令牌，APP 继续用手上那张。"""
    res = client.post("/api/app/session", headers=auth)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["token"] is None
    assert body["user"]["username"] == "admin"
    assert 0 < body["expires_in"] <= settings.jwt_expire_minutes * 60


def test_old_token_gets_replaced_and_new_one_works(client, auth):
    """用掉四分之一寿命以后，心跳发一张新令牌；新令牌能正常调教师接口。"""
    uid = _admin_id(client, auth)
    old = _token(uid, "admin", settings.jwt_expire_minutes / 4 + 1)
    res = client.post("/api/app/session", headers={"Authorization": f"Bearer {old}"})
    assert res.status_code == 200, res.text
    fresh = res.json()["token"]
    assert fresh and fresh != old
    assert res.json()["expires_in"] == settings.jwt_expire_minutes * 60

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh}"})
    assert me.status_code == 200
    assert me.json()["id"] == uid


def test_expired_token_cannot_be_refreshed(client, auth):
    """过期了就是过期了：心跳不能把死令牌救活，APP 得用保存的账密重新登录。"""
    uid = _admin_id(client, auth)
    dead = _token(uid, "admin", settings.jwt_expire_minutes + 5)
    res = client.post("/api/app/session", headers={"Authorization": f"Bearer {dead}"})
    assert res.status_code == 401
