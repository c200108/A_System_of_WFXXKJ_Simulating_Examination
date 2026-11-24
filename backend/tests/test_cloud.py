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

    shares = []

    def admin(self, method, path, body=None, what=""):
        self._check()
        if path.startswith("/api/share/list"):
            return {"content": self.shares, "total": len(self.shares)}
        raise AssertionError(path)

    def _req(self, method, path, body=None, token="", **kw):
        if path == "/api/me":
            name = cloud._jwt_username(token)
            if name and any(u["username"] == name for u in self.accounts.values()):
                return {"code": 200, "data": {"username": name}}
            return {"code": 401, "message": "token is invalidated", "data": None}
        raise AssertionError(path)

    def login_raw(self, path, body, client_ip=""):
        self.last_ip = client_ip
        if path.endswith("/hash"):
            return {"code": 401, "message": "Invalid username or password", "data": None}
        tok = self.login(body["username"], body["password"])
        if tok:
            return {"code": 200, "message": "success", "data": {"token": tok}}
        return {"code": 401, "message": "Invalid username or password", "data": None}

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
    assert cloud.decrypt("中文密码9") is None and cloud.decrypt(cloud.encrypt("中文密码9")) == "中文密码9"
    # 改一个字节就解不开（有校验）
    import base64

    raw = bytearray(base64.urlsafe_b64decode(enc[3:]))
    raw[20] ^= 1                                     # 改密文里的一个字节（直接改 base64 末位可能只动到填充位）
    bad = "w1:" + base64.urlsafe_b64encode(bytes(raw)).decode()
    assert cloud.decrypt(bad) is None


def test_老的Fernet格式还能解开():
    """2.25.0～2.25.3 存的是 Fernet；在线版装着 cryptography，升级后照样解得开。"""
    import base64
    import hashlib

    import pytest

    Fernet = pytest.importorskip("cryptography.fernet").Fernet   # 机房版不装 cryptography，跳过

    key = hashlib.sha256(f"wfxx-cloud-password:{settings.jwt_secret}".encode()).digest()
    old = Fernet(base64.urlsafe_b64encode(key)).encrypt(b"oldpass1").decode()
    assert cloud.decrypt(old) == "oldpass1"


def test_云盘模块不依赖cryptography():
    """机房版 Win7 装不了 cryptography，云盘模块一 import 它整个后端就起不来（2.25.5）。"""
    import pathlib

    src = pathlib.Path(cloud.__file__).read_text(encoding="utf-8")
    top = src.split("def ", 1)[0]
    assert "cryptography" not in top


def test_OpenList登录页_刚分配空间就能用教学平台密码登录(client, auth, fake):
    """分配空间时平台不知道明文，云盘密码先是随机的；登录页把明文送到平台，对上了就同步过去再登。"""
    uid, _ = _teacher(client, auth, "cloud_t4")
    client.put("/api/cloud/admin/total", json={"total_gb": 10}, headers=auth)
    client.put(f"/api/cloud/admin/users/{uid}", json={"quota_gb": 1}, headers=auth)
    fake.pwds["cloud_t4"] = "random-unknown"
    r = client.post("/api/cloud/ol-login", json={"username": "cloud_t4", "password": "teacher123", "plain": True},
                    headers={"X-Real-IP": "198.51.100.7"})
    assert r.json()["code"] == 200 and fake.last_ip == "198.51.100.7"
    # 有人在云盘后台改了密码：平台记着的没变，也照样以平台为准修回来
    fake.pwds["cloud_t4"] = "tampered"
    assert client.post("/api/cloud/ol-login", json={"username": "cloud_t4", "password": "teacher123",
                                                    "plain": True}).json()["code"] == 200
    # 密码不对不同步，原样回 OpenList 的错误
    assert client.post("/api/cloud/ol-login", json={"username": "cloud_t4", "password": "wrong999",
                                                    "plain": True}).json()["code"] == 401
    assert fake.pwds["cloud_t4"] == "teacher123"
    # 拿不到明文就走 OpenList 的哈希登录
    assert client.post("/api/cloud/ol-login", json={"username": "cloud_t4", "password": "ab" * 32}).json()["code"] == 401
    client.put(f"/api/cloud/admin/users/{uid}", json={"quota_gb": 0}, headers=auth)


def test_OpenList页面头部脚本():
    head = cloud.HEAD_SCRIPT % {"prefix": cloud.TOKEN_KEY_PREFIX, "color": "#409eff"}
    assert "'/api/cloud/ol-login'" in head and r"/\/api\/auth\/login\/hash$/" in head
    assert "hope-breadcrumb__link" in head


def test_全校共享_列出别的老师的分享并标出共享者(client, auth, fake):
    a, ta = _teacher(client, auth, "share_a")
    b, tb = _teacher(client, auth, "share_b")
    client.patch(f"/api/auth/users/{a}", json={"name": "王老师"}, headers=auth)
    client.put("/api/cloud/admin/total", json={"total_gb": 10}, headers=auth)
    client.put(f"/api/cloud/admin/users/{a}", json={"quota_gb": 1}, headers=auth)
    client.put(f"/api/cloud/admin/users/{b}", json={"quota_gb": 1}, headers=auth)
    cloud._shared_cache["at"] = 0
    fake.shares = [
        {"id": "s1", "files": ["/share_a/七年级/课件.pptx"], "creator": "share_a", "pwd": "", "remark": "第5课",
         "disabled": False, "expires": None, "accessed": 3, "max_accessed": 0},
        {"id": "s2", "files": ["/share_a/素材"], "creator": "share_a", "pwd": "1234", "remark": "",
         "disabled": False, "expires": "0001-01-01T00:00:00Z", "accessed": 0, "max_accessed": 0},
        {"id": "s3", "files": ["/share_a/给学生.zip"], "creator": "share_a", "remark": "不共享，只发学生",
         "disabled": False, "expires": None},
        {"id": "s4", "files": ["/share_a/过期.doc"], "creator": "share_a", "remark": "", "disabled": False,
         "expires": "2020-01-01T00:00:00.123456789+08:00"},
        {"id": "s5", "files": ["/share_a/停用.doc"], "creator": "share_a", "disabled": True},
        {"id": "s6", "files": ["/share_b/b.txt", "/share_b/c.txt"], "creator": "share_b", "remark": ""},
        {"id": "s7", "files": ["/x/y.txt"], "creator": "stranger"},   # 不是平台分配的账号
        {"id": "s8", "files": ["/share_b"], "creator": "share_b", "remark": ""},   # 整个云盘
    ]
    items = client.get("/api/cloud/shared", headers=tb).json()["items"]
    by = {i["id"]: i for i in items}
    assert set(by) == {"s1", "s2", "s6", "s8"}
    assert by["s8"]["title"].endswith("的整个云盘") and by["s8"]["kind"] == "folder"
    assert by["s1"]["sharer"] == "王老师" and by["s1"]["kind"] == "file" and by["s1"]["url"] == "/cloud/@s/s1"
    assert by["s2"]["has_pwd"] and by["s2"]["kind"] == "folder"
    assert by["s6"]["mine"] and by["s6"]["more"] == 1
    # 云盘页面里的面板：拿 OpenList 令牌换
    r = client.get("/api/cloud/shared/ol", headers={"Authorization": _jwt("share_a")})
    assert r.status_code == 200 and {i["id"] for i in r.json()["items"] if i["mine"]} == {"s1", "s2"}
    assert client.get("/api/cloud/shared/ol", headers={"Authorization": _jwt("nobody")}).status_code == 401
    # 页面里有按钮和面板，分享页能在线预览
    assert "/api/cloud/shared/ol" in cloud.BODY_HTML
    from app.database import SessionLocal

    with SessionLocal() as db:
        assert cloud._brand_values(db)["share_preview"] == "true"
    client.put(f"/api/cloud/admin/users/{a}", json={"quota_gb": 0}, headers=auth)
    client.put(f"/api/cloud/admin/users/{b}", json={"quota_gb": 0}, headers=auth)
