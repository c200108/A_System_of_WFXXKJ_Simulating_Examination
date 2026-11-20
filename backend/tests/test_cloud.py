"""个人云盘（2.25.0）：分配空间、免登录、密码同步、上传闸门、超额收权限。

OpenList 用一个假的顶替（FakeOpenList，接口和 services/cloud.py 的 OpenList 类一样），
真的 OpenList 联调见 services/cloud.py 开头的说明。
"""

import base64
import json

import pytest

from app.config import settings
from app.services import cloud


def _jwt(username: str) -> str:
    body = base64.urlsafe_b64encode(json.dumps({"username": username}).encode()).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiJ9.{body}.sig"


class FakeOpenList:
    def __init__(self, base):
        self.base = base
        self.password = "x"
        self.accounts = {1: {"id": 1, "username": "admin", "role": 2, "base_path": "/", "disabled": False,
                             "permission": 0x71FF, "password": ""},
                         2: {"id": 2, "username": "guest", "role": 1, "base_path": "/", "disabled": True,
                             "permission": 0, "password": ""}}
        self.pwds = {"admin": "x"}
        self.storage = []
        self.setting = {}
        self.saved = []
        self.next_id = 3
        self.down = False

    def _check(self):
        if self.down:
            raise cloud.CloudError("连不上云盘服务")

    def login(self, username, password):
        self._check()
        u = next((u for u in self.accounts.values() if u["username"] == username), None)
        if u and not u["disabled"] and self.pwds.get(username) == password:
            return _jwt(username)
        return None

    def admin_token(self, refresh=False):
        self._check()
        return "admintoken"

    def users(self):
        self._check()
        return [dict(u) for u in self.accounts.values()]

    def user(self, login):
        return next((u for u in self.users() if u["username"] == login), None)

    def create_user(self, body):
        self._check()
        uid = self.next_id
        self.next_id += 1
        self.accounts[uid] = {**{k: v for k, v in body.items() if k != "password"}, "id": uid, "password": ""}
        self.pwds[body["username"]] = body["password"]

    def update_user(self, body):
        self._check()
        old = self.accounts[body["id"]]
        if old["username"] != body["username"]:
            self.pwds[body["username"]] = self.pwds.pop(old["username"], None)
        if body.get("password"):
            self.pwds[body["username"]] = body["password"]
        self.accounts[body["id"]] = {**old, **{k: v for k, v in body.items() if k != "password"}}

    def delete_user(self, uid):
        u = self.accounts.pop(uid)
        self.pwds.pop(u["username"], None)

    def storages(self):
        self._check()
        return list(self.storage)

    def create_storage(self, body):
        self.storage.append(body)

    def settings(self):
        return [{"key": k, "value": v} for k, v in self.setting.items()]

    def save_settings(self, items):
        self.saved.append(items)
        for x in items:
            self.setting[x["key"]] = x["value"]


@pytest.fixture()
def fake(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "openlist_url", "http://openlist:5244/cloud")
    monkeypatch.setattr(settings, "cloud_storage_dir", str(tmp_path))
    f = FakeOpenList("http://openlist:5244/cloud")
    for k in ("site_title", "logo", "favicon", "main_color", "customize_head", "customize_body",
              "multipart_enabled", "announcement", "allow_indexed", "robots_txt", "home_icon", "audio_cover"):
        f.setting[k] = "old"
    monkeypatch.setattr(cloud, "_client", f)
    monkeypatch.setattr(cloud, "_setup_done", False)
    cloud._reserved.clear()
    yield f


def _teacher(client, auth, username):
    r = client.post("/api/auth/users", json={"username": username, "password": "teacher123",
                                              "name": username, "role": "teacher"}, headers=auth)
    assert r.status_code == 200, r.text
    uid = r.json()["id"]
    tok = client.post("/api/auth/login", data={"username": username, "password": "teacher123"}).json()
    return uid, {"Authorization": f"Bearer {tok['access_token']}"}


def test_没启用云盘时_接口说清楚(client, auth):
    assert client.get("/api/cloud/me", headers=auth).json()["enabled"] is False
    r = client.post("/api/cloud/open", headers=auth)
    assert r.status_code == 503
    assert client.get("/api/cloud/admin", headers=auth).json()["enabled"] is False


def test_分配空间_免登录_密码同步(client, auth, fake, tmp_path):
    uid, t = _teacher(client, auth, "cloud_t1")

    # 没设总容量不能分
    r = client.put(f"/api/cloud/admin/users/{uid}", json={"quota_gb": 1}, headers=auth)
    assert r.status_code == 400 and "总容量" in r.json()["detail"]
    # 没分配的老师点按钮：提示联系系统管理员
    r = client.post("/api/cloud/open", headers=t)
    assert r.status_code == 403 and "联系系统管理员" in r.json()["detail"]

    assert client.put("/api/cloud/admin/total", json={"total_gb": 3}, headers=auth).status_code == 200
    r = client.put(f"/api/cloud/admin/users/{uid}", json={"quota_gb": 5}, headers=auth)
    assert r.status_code == 400 and "最多还能给" in r.json()["detail"]
    r = client.put(f"/api/cloud/admin/users/{uid}", json={"quota_gb": 2}, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["login"] == "cloud_t1" and r.json()["quota_bytes"] == 2 * 1024 ** 3

    # 第一次接上：管理员改名、挂好存储、站点品牌化（分块上传关掉）
    assert fake.user("wfxx-admin") and not fake.user("admin")
    assert fake.storage[0]["mount_path"] == "/"
    assert json.loads(fake.storage[0]["addition"])["root_folder_path"] == str(tmp_path)
    assert fake.setting["multipart_enabled"] == "false"
    assert "wfxxcloud:" in fake.setting["customize_head"] and "个人云盘" in fake.setting["site_title"]
    ol = fake.user("cloud_t1")
    assert ol["base_path"] == "/cloud_t1" and not ol["disabled"] and ol["permission"] == cloud.PERM_FULL
    assert (tmp_path / "cloud_t1").is_dir()

    # 分配时还不知道教师端密码（随机的），登录一次教学平台就同步成一样的
    assert fake.login("cloud_t1", "teacher123") is None
    client.post("/api/auth/login", data={"username": "cloud_t1", "password": "teacher123"})
    assert fake.login("cloud_t1", "teacher123")

    # 免登录：换回 OpenList 的令牌和 localStorage 键名
    r = client.post("/api/cloud/open", headers=t)
    assert r.status_code == 200 and r.json()["storage_key"] == "wfxxcloud:token"
    assert cloud._jwt_username(r.json()["token"]) == "cloud_t1"

    # 改教学平台密码 → 云盘密码跟着改
    r = client.post("/api/auth/password", json={"old_password": "teacher123", "new_password": "newpass456"}, headers=t)
    assert r.status_code == 200
    assert fake.login("cloud_t1", "newpass456")

    # 单独设云盘密码以后，改教学平台密码不再影响云盘
    assert client.post("/api/cloud/password", json={"password": "123"}, headers=t).status_code == 400
    assert client.post("/api/cloud/password", json={"password": "cloudonly9"}, headers=t).json()["password_custom"]
    client.patch(f"/api/auth/users/{uid}", json={"password": "reset7788"}, headers=auth)
    assert fake.login("cloud_t1", "cloudonly9") and not fake.login("cloud_t1", "reset7788")
    # 改回一致要输教学平台的密码
    assert client.post("/api/cloud/password/sync", json={"current_password": "wrong"}, headers=t).status_code == 400
    assert client.post("/api/cloud/password/sync", json={"current_password": "reset7788"}, headers=t).json()["password_custom"] is False
    assert fake.login("cloud_t1", "reset7788")

    # 有人在 OpenList 后台把密码改了：免登录时按本系统的重设一遍
    fake.pwds["cloud_t1"] = "tampered"
    assert client.post("/api/cloud/open", headers=t).status_code == 200
    assert fake.login("cloud_t1", "reset7788")

    # 停用老师 → 云盘账号停用；启用回来
    client.delete(f"/api/auth/users/{uid}", headers=auth)
    assert fake.user("cloud_t1")["disabled"]
    client.patch(f"/api/auth/users/{uid}", json={"is_active": True}, headers=auth)
    assert not fake.user("cloud_t1")["disabled"]

    # 总容量不能改得比已分配的还小
    r = client.put("/api/cloud/admin/total", json={"total_gb": 1}, headers=auth)
    assert r.status_code == 400

    # 收回空间：账号停用，文件夹还在
    (tmp_path / "cloud_t1" / "a.txt").write_text("hi")
    assert client.put(f"/api/cloud/admin/users/{uid}", json={"quota_gb": 0}, headers=auth).status_code == 200
    assert fake.user("cloud_t1")["disabled"] and (tmp_path / "cloud_t1" / "a.txt").exists()
    assert client.post("/api/cloud/open", headers=t).status_code == 403

    ov = client.get("/api/cloud/admin", headers=auth).json()
    assert ov["service_ok"] and ov["openlist_admin"]["username"] == "wfxx-admin"


def test_上传闸门和超额收权限(client, auth, fake, tmp_path):
    uid, t = _teacher(client, auth, "cloud_t2")
    client.put("/api/cloud/admin/total", json={"total_gb": 10}, headers=auth)
    client.put(f"/api/cloud/admin/users/{uid}", json={"quota_gb": 0.001}, headers=auth)   # ≈ 1 MB
    tok = _jwt("cloud_t2")

    def gate(n=None, kind="put", token=tok):
        h = {"Authorization": token, "X-Upload-Kind": kind}
        if n is not None:
            h["X-Upload-Length"] = str(n)
        r = client.get("/api/cloud/gate", headers=h)
        return r.status_code, r.headers.get("x-cloud-reason")

    assert gate(300 * 1024) == (204, None)
    assert gate(2 * 1024 * 1024) == (403, "over")
    assert gate() == (403, "nolength")
    assert gate(kind="other") == (204, None)
    assert gate(10, token="garbage") == (403, "nologin")
    assert gate(10, token=_jwt("nobody")) == (403, "none")
    # 刚放行的 300 KB 先按已用算：再来 800 KB 就超了
    assert gate(800 * 1024) == (403, "over")

    # 后台扫描：实际用量超了 → 收回上传 / 复制 / 解压；删掉以后恢复
    big = tmp_path / "cloud_t2" / "big.bin"
    big.write_bytes(b"0" * (2 * 1024 * 1024))
    from app.database import SessionLocal

    with SessionLocal() as db:
        cloud.scan(db)
    assert fake.user("cloud_t2")["permission"] == cloud.PERM_OVER
    assert client.get("/api/cloud/me", headers=t).json()["over_quota"] is True
    big.unlink()
    with SessionLocal() as db:
        cloud.scan(db)
    assert fake.user("cloud_t2")["permission"] == cloud.PERM_FULL


def test_教学平台的admin和OpenList内置管理员不撞名(client, auth, fake):
    client.put("/api/cloud/admin/total", json={"total_gb": 10}, headers=auth)
    r = client.put("/api/cloud/admin/users/1", json={"quota_gb": 1}, headers=auth)
    assert r.status_code == 200 and r.json()["login"] == "admin"
    assert fake.user("admin")["role"] == 0 and fake.user("wfxx-admin")["role"] == 2
    assert cloud.login_for("guest") == "guest-t"
    client.put("/api/cloud/admin/users/1", json={"quota_gb": 0}, headers=auth)


def test_云盘服务挂了_登录照常(client, auth, fake):
    uid, _ = _teacher(client, auth, "cloud_t3")
    client.put("/api/cloud/admin/total", json={"total_gb": 10}, headers=auth)
    client.put(f"/api/cloud/admin/users/{uid}", json={"quota_gb": 1}, headers=auth)
    fake.down = True
    r = client.post("/api/auth/login", data={"username": "cloud_t3", "password": "teacher123"})
    assert r.status_code == 200
    ov = client.get("/api/cloud/admin", headers=auth).json()
    assert ov["enabled"] and ov["service_ok"] is False


def test_管理员密码和compose里的算法一致(monkeypatch):
    import hashlib

    monkeypatch.setattr(settings, "openlist_admin_password", "")
    want = hashlib.sha256(f"wfxx-openlist-admin:{settings.jwt_secret}".encode()).hexdigest()[:32]
    assert cloud.admin_password() == want
    from pathlib import Path

    compose = (Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text(encoding="utf-8")
    assert "printf 'wfxx-openlist-admin:%s'" in compose and "sha256sum | cut -c1-32" in compose


def test_密码加密能解开_换了密钥解不开():
    enc = cloud.encrypt("abc123x")
    assert cloud.decrypt(enc) == "abc123x"
    assert cloud.decrypt("not-a-token") is None
    assert cloud.decrypt("") is None
