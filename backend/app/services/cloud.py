"""个人云盘（2.25.0）：每位老师一块独立的网盘空间，界面用开源的 OpenList。

整体是这样搭的（docker-compose.yml 里多了一个 openlist 服务）：

    宿主机 /home/WFXXKJ_ExamSystem_CloudStorage/      ← 云盘根目录，openlist 和后端两个容器都挂在 /cloud-storage
        zhangsan/  lisi/  ...                          ← 每位老师一个文件夹（文件夹名 = 用户名）

    OpenList 里只有一个「本机存储」挂在 / ，指向上面的根目录；
    每位老师在 OpenList 里有一个同名账号，根目录（base_path）锁在 /<自己的文件夹>，互相看不到。

    网页上 /cloud/ 由前端容器的 nginx 转给 openlist（frontend/nginx/cloud.conf）。

**配额由本系统管**，OpenList 自己没有配额：
    1. 上传前 nginx 先问后端 GET /api/cloud/gate（auth_request），带着这次要传多少字节。
       个人用量 + 这次 > 分到的空间，或者全部云盘用量 + 这次 > 管理员设的总容量，就拒绝；
    2. 后台每 5 分钟量一次每位老师的实际用量（复制、解压这些绕过第 1 步的也算进去），
       超了就收回上传 / 复制 / 解压的权限（还能删、能下载），删到额度以内自动恢复。

**账号密码**默认和教师端一致：老师登录教学平台、改密码、管理员重置密码时，后端拿到明文顺手同步过去；
也可以在「我的账号」里单独设一个云盘密码。密码加密存在 cloud_accounts.password_enc 里 ——
教师主页上点「个人云盘」是免登录的，后端要拿它去 OpenList 换令牌。为了这一点，
OpenList 自己的「修改密码」被 nginx 挡掉了（改了的话后端就换不到令牌），只能在教学平台里改。

和教学平台同一个域名，浏览器的 localStorage 是共用的，而 OpenList 也把登录令牌存在 token 这个键里，
会把教师端的登录挤掉。所以塞进 OpenList 页面头部的那段脚本（HEAD_SCRIPT）把它存的键统一加上 wfxxcloud: 前缀。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import shutil
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AppMeta, CloudAccount, User

log = logging.getLogger("cloud")

MB = 1024 * 1024
GB_MB = 1024

# OpenList 自带的管理员叫 admin，和教学平台的系统管理员（ADMIN_USERNAME 默认也是 admin）撞名，
# 第一次接上时改成这个名字，把 admin 让给老师用
ADMIN_LOGIN = "wfxx-admin"
# OpenList 里另有一个内置的 guest；这两个名字教学平台的账号用不了，云盘登录名后面加 -t
RESERVED_LOGINS = {ADMIN_LOGIN, "guest"}

# OpenList 的权限位（internal/model/user.go）
P_NO_PASSWORD = 1 << 1    # 进带访问密码的文件夹不用输密码
P_WRITE = 1 << 3          # 新建文件夹、上传
P_RENAME = 1 << 4
P_MOVE = 1 << 5
P_COPY = 1 << 6
P_REMOVE = 1 << 7
P_READ_ARCHIVE = 1 << 12  # 在线看压缩包里有什么
P_DECOMPRESS = 1 << 13
P_SHARE = 1 << 14         # 生成分享链接（发给学生下载）
PERM_FULL = (P_NO_PASSWORD | P_WRITE | P_RENAME | P_MOVE | P_COPY | P_REMOVE
             | P_READ_ARCHIVE | P_DECOMPRESS | P_SHARE)
# 超了额度：会让空间变大的几样收回，删、改名、移动、下载、分享照旧 —— 老师得能删东西腾地方
PERM_OVER = PERM_FULL & ~(P_WRITE | P_COPY | P_DECOMPRESS)

# 教学平台的界面主题 → 主色（和 frontend/src/theme.js 里各主题的 primary 一致）
THEME_COLORS = {
    "default": "#409eff", "ant": "#1677ff", "primer": "#0969da", "naive": "#18a058",
    "indigo": "#4f46e5", "warm": "#e8590c", "contrast": "#0040c1",
}

TOKEN_KEY_PREFIX = "wfxxcloud:"

# 塞进 OpenList 每个页面 <head> 最前面（customize_head 设置项），比它自己的脚本先跑
HEAD_SCRIPT = r"""<script>
/* 教学平台：OpenList 和教学平台同一个域名、共用 localStorage，它的 token 会把教师端的登录挤掉。
   这里把它存取的键都加上 wfxxcloud: 前缀，两边互不干扰；没选过语言时默认中文。 */
(function () {
  var P = '%(prefix)s', S = Storage.prototype, g = S.getItem, s = S.setItem, r = S.removeItem, c = S.clear;
  function mine(o) { try { return o === window.localStorage } catch (e) { return false } }
  S.getItem = function (k) {
    if (!mine(this)) return g.call(this, k);
    var v = g.call(this, P + k);
    return v === null && k === 'lang' ? 'zh-CN' : v;
  };
  S.setItem = function (k, v) { return mine(this) ? s.call(this, P + k, v) : s.call(this, k, v) };
  S.removeItem = function (k) { return mine(this) ? r.call(this, P + k) : r.call(this, k) };
  /* 登录页：把 /auth/login/hash 改送到教学平台后端，带上登录框里的明文。
     这样刚分配空间、还没同步过密码的老师，用教学平台的密码也能直接登上（见 services/cloud.py 的 login_page）。 */
  var X = XMLHttpRequest.prototype, xo = X.open, xs = X.send;
  X.open = function (m, u) {
    this.__wfxxLogin = /\/api\/auth\/login\/hash$/.test(String(u || ''));
    if (this.__wfxxLogin) arguments[1] = '/api/cloud/ol-login';
    return xo.apply(this, arguments);
  };
  X.send = function (b) {
    if (this.__wfxxLogin) {
      try {
        var d = JSON.parse(b), el = document.querySelector('input[type=password]');
        d.plain = !!(el && el.value);
        if (d.plain) d.password = el.value;
        b = JSON.stringify(d);
      } catch (e) {}
    }
    return xs.call(this, b);
  };
  /* 面包屑兜底（2.25.1）：有老师在预览课件（PPT 预览器）时点上级目录没反应。点了 0.8 秒地址还没变，
     就整页跳过去，不管是哪个预览器卡住了路由。 */
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest && e.target.closest('a.hope-breadcrumb__link');
    if (!a || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    var want = a.getAttribute('href') || '', before = location.pathname;
    if (!want || want.charAt(0) !== '/') return;
    setTimeout(function () {
      var dec = function (x) { try { return decodeURI(x) } catch (_) { return x } };
      if (location.pathname === before && dec(before) !== dec(want)) location.href = want;
    }, 800);
  }, true);
  S.clear = function () {
    if (!mine(this)) return c.call(this);
    for (var i = this.length - 1; i >= 0; i--) { var k = this.key(i); if (k && k.indexOf(P) === 0) r.call(this, k) }
  };
})();
</script>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif; }
  .wfxx-back { position: fixed; left: 16px; bottom: 16px; z-index: 1000; padding: 6px 14px; border-radius: 999px;
    font-size: 13px; text-decoration: none; color: #fff; background: %(color)s; box-shadow: 0 2px 8px rgba(0,0,0,.18); opacity: .92; }
  .wfxx-back:hover { opacity: 1; }
</style>"""

BODY_HTML = '<a class="wfxx-back" href="/js/paper" title="回到教学平台的教师后台">← 返回教学平台</a>'


class CloudError(Exception):
    """说给人听的错误：接口层直接把 str(e) 当 detail 返回。"""


# ---------------------------------------------------------------- 开关、密钥
def enabled() -> bool:
    return bool(settings.openlist_url.strip())


def admin_password() -> str:
    """OpenList 管理员密码。docker-compose.yml 里 openlist 容器启动时用同一个算法算出来再设进去。"""
    if settings.openlist_admin_password:
        return settings.openlist_admin_password
    return hashlib.sha256(f"wfxx-openlist-admin:{settings.jwt_secret}".encode()).hexdigest()[:32]


# 云盘密码要能还原（免登录时拿它去 OpenList 换令牌），所以是加密存、不是哈希存。
# **只用标准库**（2.25.5）：原来用 cryptography 的 Fernet，可机房版 Win7 装不了 cryptography
# （Rust 编的，Win7 上 import 就崩），机房版一导入这个模块整个后端都起不来。
# 做法：HMAC-SHA256 当计数器模式的密钥流做异或加密，再用另一把钥匙 HMAC 整段（先加密后认证），
# 两把钥匙都由 JWT_SECRET 推出来。格式 "w1:" + base64url(16 字节随机数 + 密文 + 32 字节校验)。
def _keys() -> tuple:
    base = hashlib.sha256(f"wfxx-cloud-password:{settings.jwt_secret}".encode()).digest()
    return hashlib.sha256(base + b"enc").digest(), hashlib.sha256(base + b"mac").digest()


def _stream(key: bytes, nonce: bytes, n: int) -> bytes:
    out = b""
    i = 0
    while len(out) < n:
        out += hmac.new(key, nonce + i.to_bytes(4, "big"), hashlib.sha256).digest()
        i += 1
    return out[:n]


def encrypt(plain: str) -> str:
    k_enc, k_mac = _keys()
    nonce = secrets.token_bytes(16)
    data = plain.encode()
    ct = bytes(a ^ b for a, b in zip(data, _stream(k_enc, nonce, len(data))))
    tag = hmac.new(k_mac, nonce + ct, hashlib.sha256).digest()
    return "w1:" + base64.urlsafe_b64encode(nonce + ct + tag).decode()


def _decrypt_fernet(token: str):
    """2.25.0～2.25.3 存的是 Fernet 格式。装着 cryptography（在线版）就照样解开，下次写入换成新格式。"""
    try:
        from cryptography.fernet import Fernet, InvalidToken
    except Exception:                         # noqa: BLE001  机房版没装
        return None
    key = hashlib.sha256(f"wfxx-cloud-password:{settings.jwt_secret}".encode()).digest()
    try:
        return Fernet(base64.urlsafe_b64encode(key)).decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def decrypt(token: str):
    """解不开（换过 JWT_SECRET、从别的服务器导过来的数据）返回 None，调用方会重新设一个。"""
    if not token:
        return None
    if not token.startswith("w1:"):
        return _decrypt_fernet(token)
    try:
        raw = base64.urlsafe_b64decode(token[3:].encode())
    except (ValueError, TypeError):
        return None
    if len(raw) < 48:
        return None
    nonce, ct, tag = raw[:16], raw[16:-32], raw[-32:]
    k_enc, k_mac = _keys()
    if not hmac.compare_digest(tag, hmac.new(k_mac, nonce + ct, hashlib.sha256).digest()):
        return None
    try:
        return bytes(a ^ b for a, b in zip(ct, _stream(k_enc, nonce, len(ct)))).decode()
    except UnicodeDecodeError:
        return None


def random_password() -> str:
    return secrets.token_urlsafe(18)


def login_for(username: str) -> str:
    return f"{username}-t" if username.lower() in RESERVED_LOGINS else username


# ---------------------------------------------------------------- OpenList 接口
class OpenList:
    """OpenList 的 HTTP 接口，只用到管理员的用户、存储、设置几样，外加普通用户登录。"""

    def __init__(self, base: str, password: str):
        self.base = base.rstrip("/")
        self.password = password
        self._token = ""
        self._lock = threading.Lock()
        # 连不上之后 30 秒内不再去连，直接报错：OpenList 挂了的时候，老师登录、改密码不能每次都卡 8 秒
        self._down_until = 0.0

    def _req(self, method: str, path: str, body=None, token: str = "", timeout: float = 8,
             headers: dict | None = None):
        if time.time() < self._down_until:
            raise CloudError("连不上云盘服务（OpenList 没启动或还在启动），过一会儿再试")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", token)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                out = json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise CloudError(f"云盘服务出错（HTTP {e.code}）") from e
        except (urllib.error.URLError, OSError, ValueError) as e:
            self._down_until = time.time() + 30
            raise CloudError("连不上云盘服务（OpenList 没启动或还在启动），过一会儿再试") from e
        return out

    def _ok(self, out: dict, what: str):
        if out.get("code") != 200:
            raise CloudError(f"{what}失败：{out.get('message') or out}")
        return out.get("data")

    def login(self, username: str, password: str) -> str | None:
        """普通用户登录，成功返回令牌，用户名密码不对返回 None。"""
        out = self._req("POST", "/api/auth/login", {"username": username, "password": password})
        if out.get("code") == 200:
            return (out.get("data") or {}).get("token")
        return None

    def login_raw(self, path: str, body: dict, client_ip: str = "") -> dict:
        """原样转发 OpenList 登录页的登录请求，返回它的 JSON（成功、密码错、要两步验证都原样给前端）。

        带上 X-Forwarded-For：OpenList 按 IP 记输错次数，不带的话所有人都算成后端这一个 IP，
        一个人连输错几次就把全校的云盘登录锁住 5 分钟。
        """
        return self._req("POST", path, body, headers={"X-Forwarded-For": client_ip} if client_ip else None)

    def admin_token(self, refresh: bool = False) -> str:
        with self._lock:
            if self._token and not refresh:
                return self._token
            for name in (ADMIN_LOGIN, "admin"):
                tok = self.login(name, self.password)
                if tok:
                    self._token = tok
                    return tok
        raise CloudError("云盘服务的管理员密码对不上（看 docker compose logs openlist）")

    def admin(self, method: str, path: str, body=None, what: str = "云盘操作"):
        out = self._req(method, path, body, token=self.admin_token())
        if out.get("code") in (401, 403):     # 令牌过期、OpenList 重启后改过管理员密码
            out = self._req(method, path, body, token=self.admin_token(refresh=True))
        return self._ok(out, what)

    # 用户
    def users(self) -> list[dict]:
        data = self.admin("GET", "/api/admin/user/list?page=1&per_page=100000", what="读云盘账号")
        return list((data or {}).get("content") or [])

    def user(self, login: str) -> dict | None:
        for u in self.users():
            if u.get("username") == login:
                return u
        return None

    def create_user(self, body: dict) -> None:
        self.admin("POST", "/api/admin/user/create", body, what="建云盘账号")

    def update_user(self, body: dict) -> None:
        self.admin("POST", "/api/admin/user/update", body, what="改云盘账号")

    def delete_user(self, uid: int) -> None:
        self.admin("POST", f"/api/admin/user/delete?id={uid}", what="删云盘账号")

    # 存储、设置
    def storages(self) -> list[dict]:
        data = self.admin("GET", "/api/admin/storage/list?page=1&per_page=1000", what="读云盘存储")
        return list((data or {}).get("content") or [])

    def create_storage(self, body: dict) -> None:
        self.admin("POST", "/api/admin/storage/create", body, what="挂载云盘目录")

    def settings(self) -> list[dict]:
        return list(self.admin("GET", "/api/admin/setting/list", what="读云盘设置") or [])

    def save_settings(self, items: list[dict]) -> None:
        self.admin("POST", "/api/admin/setting/save", items, what="改云盘设置")


_client: OpenList | None = None


def client() -> OpenList:
    global _client
    if not enabled():
        raise CloudError("这台服务器没有启用个人云盘（docker-compose.yml 里没有 openlist 服务）")
    if _client is None or _client.base != settings.openlist_url.rstrip("/"):
        _client = OpenList(settings.openlist_url, admin_password())
    return _client


# ---------------------------------------------------------------- 第一次接上：改管理员名、挂目录、品牌
_setup_done = False
_setup_lock = threading.Lock()


def _brand_values(db: Session) -> dict[str, str]:
    from ..siteconfig import site

    theme = db.get(AppMeta, "ui_theme")
    color = THEME_COLORS.get(theme.value if theme else "default", THEME_COLORS["default"])
    logo = site.site.favicon or "/favicon.svg"
    brand = site.site.brand or site.site.title or "信息科技教学平台"
    return {
        "site_title": f"{brand} · 个人云盘",
        "announcement": "",
        "logo": logo,
        "favicon": logo,
        "audio_cover": logo,
        "main_color": color,
        "home_icon": "📁",
        "allow_indexed": "false",
        "robots_txt": "User-agent: *\nDisallow: /",
        # 分块上传走 /api/fs/multipart/，那条路 nginx 不放行（配额管不住）；关了网页就走普通上传
        "multipart_enabled": "false",
        "customize_head": HEAD_SCRIPT % {"prefix": TOKEN_KEY_PREFIX, "color": color},
        "customize_body": BODY_HTML,
    }


def apply_branding(db: Session) -> None:
    ol = client()
    want = _brand_values(db)
    changed = [dict(x, value=want[x["key"]]) for x in ol.settings()
               if x.get("key") in want and x.get("value") != want[x["key"]]]
    if changed:
        ol.save_settings(changed)


def ensure_setup(db: Session, force: bool = False) -> None:
    """改管理员名、把云盘根目录挂成 OpenList 的 /、设站点名和配色。做过一次就不再做（除非 force）。"""
    global _setup_done
    if _setup_done and not force:
        return
    with _setup_lock:
        if _setup_done and not force:
            return
        ol = client()
        ol.admin_token()
        for u in ol.users():
            if u.get("role") == 2 and u.get("username") == "admin":
                ol.update_user({**u, "username": ADMIN_LOGIN, "password": ""})
                ol.admin_token(refresh=True)
        if not any(s.get("mount_path") == "/" for s in ol.storages()):
            ol.create_storage({
                "mount_path": "/", "driver": "Local", "order": 0, "remark": "教学平台个人云盘（自动创建，勿删）",
                "cache_expiration": 0, "webdav_policy": "native_proxy", "down_proxy_url": "",
                "addition": json.dumps({
                    "root_folder_path": settings.cloud_storage_dir, "thumbnail": False,
                    "show_hidden": False, "mkdir_perm": "755",
                }),
            })
        apply_branding(db)
        _setup_done = True


# ---------------------------------------------------------------- 容量
def total_mb(db: Session) -> int:
    row = db.get(AppMeta, "cloud_total_mb")
    try:
        return max(0, int(row.value)) if row else 0
    except ValueError:
        return 0


def set_total_mb(db: Session, value: int) -> None:
    row = db.get(AppMeta, "cloud_total_mb")
    if row:
        row.value = str(value)
    else:
        db.add(AppMeta(key="cloud_total_mb", value=str(value)))


def disk() -> dict | None:
    """云盘根目录所在那块盘（宿主机 /home 所在分区）的总量、已用、剩余，字节。目录不在返回 None。"""
    root = settings.cloud_storage_dir
    if not os.path.isdir(root):
        return None
    du = shutil.disk_usage(root)
    return {"total": du.total, "used": du.used, "free": du.free}


def folder_path(acc: CloudAccount) -> str:
    return os.path.join(settings.cloud_storage_dir, acc.folder)


def measure(path: str) -> int:
    """文件夹里所有文件加起来多大（不跟符号链接）。"""
    total = 0
    stack = [path]
    while stack:
        d = stack.pop()
        try:
            with os.scandir(d) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.is_file(follow_symlinks=False):
                            total += e.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def allocated_mb(db: Session, exclude_user: int | None = None) -> int:
    q = select(CloudAccount)
    return sum(a.quota_mb for a in db.scalars(q) if a.user_id != exclude_user)


# ---------------------------------------------------------------- 账号同步
def _ensure_folder(acc: CloudAccount) -> None:
    root = settings.cloud_storage_dir
    if os.path.isdir(root):
        os.makedirs(folder_path(acc), exist_ok=True)


def _password_of(acc: CloudAccount) -> tuple[str, bool]:
    """(密码, 是不是刚换的新密码)。存的解不开就换一个随机的，调用方要把它设到 OpenList。"""
    pwd = decrypt(acc.password_enc)
    if pwd is None:
        pwd = random_password()
        acc.password_enc = encrypt(pwd)
        return pwd, True
    return pwd, False


def sync(db: Session, user: User, acc: CloudAccount | None = None, *, password: str | None = None,
         users: list[dict] | None = None) -> None:
    """让 OpenList 里这位老师的账号和本系统一致：在不在、停没停用、根目录、权限，需要时连密码一起设。

    password 给了就把云盘密码设成它（并加密存下）。只改了 acc、不提交，调用方 commit。
    """
    acc = acc or db.get(CloudAccount, user.id)
    if acc is None:
        return
    ol = client()
    ensure_setup(db)
    if password is not None:
        acc.password_enc = encrypt(password)
    else:
        password, fresh = _password_of(acc)
        if not fresh:
            password = None   # 没变就不碰 OpenList 里的密码（改密码会让已登录的云盘页掉线）

    want_disabled = acc.quota_mb <= 0 or not user.is_active
    want = {
        "username": acc.login,
        "base_path": "/" + acc.folder,
        "role": 0,
        "disabled": want_disabled,
        "permission": PERM_OVER if acc.over_quota else PERM_FULL,
    }
    if not want_disabled:
        _ensure_folder(acc)
    found = next((u for u in users if u.get("username") == acc.login), None) if users is not None \
        else ol.user(acc.login)
    if found is None:
        if want_disabled:
            return                         # 没分空间也就不用建
        if password is None:
            password, _ = _password_of(acc)
        ol.create_user({**want, "password": password})
        return
    same = all(found.get(k) == v for k, v in want.items())
    if same and password is None:
        return
    ol.update_user({**found, **want, "password": password or ""})


def sync_quietly(db: Session, user: User, **kw) -> None:
    """改了账号状态（停用、启用、改密码）顺手同步一下；云盘服务不在也不影响原来的操作，后台扫描会补上。"""
    if not enabled():
        return
    try:
        sync(db, user, **kw)
        db.commit()
    except Exception as e:                    # noqa: BLE001
        db.rollback()
        log.warning("同步云盘账号 %s 没成功：%s", user.username, e)


def on_password_known(db: Session, user: User, plain: str) -> None:
    """登录、改密码、管理员重置密码时调：云盘密码跟教师端一致的，换成新的明文。

    只有和存着的不一样才去碰 OpenList，平常登录不多一次网络请求。
    """
    if not enabled():
        return
    acc = db.get(CloudAccount, user.id)
    if acc is None or acc.password_custom or decrypt(acc.password_enc) == plain:
        return
    sync_quietly(db, user, acc=acc, password=plain)


def remove(db: Session, user: User) -> None:
    """删账号前调：删掉 OpenList 里的账号。文件夹留着不删（文件找管理员还能拷出来）。"""
    acc = db.get(CloudAccount, user.id)
    if acc is None or not enabled():
        return
    try:
        found = client().user(acc.login)
        if found:
            client().delete_user(found["id"])
    except Exception as e:                    # noqa: BLE001
        log.warning("删云盘账号 %s 没成功：%s", acc.login, e)


def set_quota(db: Session, user: User, quota_mb: int) -> CloudAccount:
    """分配 / 调整 / 收回（0）一位老师的空间。校验总量，建账号，同步到 OpenList，提交。"""
    if quota_mb < 0:
        raise CloudError("空间不能是负数")
    acc = db.get(CloudAccount, user.id)
    if quota_mb > 0:
        total = total_mb(db)
        if total <= 0:
            raise CloudError("还没有设置云盘总容量，先在上面设好总容量再分配")
        others = allocated_mb(db, exclude_user=user.id)
        if others + quota_mb > total:
            left = max(0, total - others)
            raise CloudError(f"超出云盘总容量：其他老师已分走 {fmt_mb(others)}，最多还能给 {fmt_mb(left)}")
    if acc is None:
        if quota_mb == 0:
            raise CloudError("这位老师还没有分配过空间")
        acc = CloudAccount(
            user_id=user.id, quota_mb=0, folder=user.username, login=login_for(user.username),
            password_enc=encrypt(random_password()), password_custom=False,
        )
        db.add(acc)
    acc.quota_mb = quota_mb
    if quota_mb > 0:
        acc.used_bytes = measure(folder_path(acc)) if os.path.isdir(folder_path(acc)) else 0
        acc.over_quota = acc.used_bytes > quota_mb * MB
        acc.checked_at = datetime.now()
    sync(db, user, acc)
    db.commit()
    return acc


def fmt_mb(mb: int) -> str:
    return f"{mb / GB_MB:.1f} GB".replace(".0 GB", " GB") if mb >= GB_MB else f"{mb} MB"


# ---------------------------------------------------------------- OpenList 登录页
def login_page(db: Session, body: dict, plain: bool, client_ip: str = "") -> dict:
    """直接打开 /cloud/ 在 OpenList 登录页登录时走这里（页面头上的脚本把登录请求改送到 /api/cloud/ol-login）。

    为什么要绕一道：分配空间时平台只有教师端密码的哈希，不知道明文，云盘账号的密码先是随机的，
    要等老师下次登录教学平台才同步过去 —— 分完空间马上用教学平台的密码登云盘就会「用户名或密码错误」。
    这里拿到的是登录框里的明文：和教学平台密码对得上（且云盘密码没单独设）就先同步过去，再交给 OpenList 登录。
    plain=False（没找到密码框、拿不到明文）就原样走 OpenList 的哈希登录。
    """
    from ..security import verify_password

    ol = client()
    username = str(body.get("username") or "")
    password = str(body.get("password") or "")
    fwd = {"username": username, "password": password, "otp_code": str(body.get("otp_code") or "")}
    if not plain:
        return ol.login_raw("/api/auth/login/hash", fwd, client_ip)
    acc = db.scalar(select(CloudAccount).where(CloudAccount.login == username)) if username else None
    user = db.get(User, acc.user_id) if acc is not None else None
    # 和教学平台的登录密码对得上、云盘密码又没单独设：这就是这位老师的云盘密码
    eligible = (acc is not None and user is not None and acc.quota_mb > 0 and user.is_active
                and not acc.password_custom and bool(password) and verify_password(password, user.password_hash))

    def push() -> None:
        try:
            sync(db, user, acc, password=password)
            db.commit()
        except CloudError as e:
            db.rollback()
            log.warning("登录页同步云盘密码 %s 没成功：%s", username, e)

    if eligible and decrypt(acc.password_enc) != password:
        push()
    out = ol.login_raw("/api/auth/login", fwd, client_ip)
    if eligible and out.get("code") in (400, 401) and "password" in str(out.get("message") or "").lower():
        # 平台记着的和 OpenList 里的对不上（有人在云盘后台改过）：以平台为准再设一次
        push()
        out = ol.login_raw("/api/auth/login", fwd, client_ip)
    return out


# ---------------------------------------------------------------- 免登录跳转
def open_token(db: Session, user: User) -> str:
    """教师主页「个人云盘」：拿存着的云盘密码去 OpenList 换一个令牌。对不上就重设一次再换。"""
    acc = db.get(CloudAccount, user.id)
    if acc is None or acc.quota_mb <= 0:
        raise PermissionError("你还没有分配个人云盘空间，无法访问，请联系系统管理员")
    ol = client()
    ensure_setup(db)
    pwd, fresh = _password_of(acc)
    tok = None if fresh else ol.login(acc.login, pwd)
    if not tok:
        # 账号还没建、被人在 OpenList 后台改过、换过服务器……按本系统的重新设一遍
        sync(db, user, acc, password=pwd)
        db.commit()
        tok = ol.login(acc.login, pwd)
    if not tok:
        raise CloudError("云盘账号登录不上，请联系系统管理员看看 OpenList 的日志")
    return tok


# ---------------------------------------------------------------- 上传闸门（nginx auth_request）
_reserved: dict[str, list[tuple[float, int]]] = {}
_reserved_lock = threading.Lock()
RESERVE_SECONDS = 120     # 刚放行的上传在这么久里按「已用」算，防止几个文件同时传、一起把额度挤爆
FRESH_SECONDS = 30        # 用量隔这么久没量就当场再量一次


def _jwt_username(token: str) -> str:
    """从 OpenList 的令牌里读出用户名。**不验签**：令牌是假的 OpenList 自己会拒，这里只是借用户名查额度。"""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return str(json.loads(base64.urlsafe_b64decode(part)).get("username") or "")
    except Exception:                        # noqa: BLE001
        return ""


def gate(db: Session, token: str, length: int | None, writes: bool = True) -> str:
    """能不能放行这次上传。放行返回 ""，否则返回原因：nologin / none / over / total / nolength。

    writes=False 是复制、解压这类：事先不知道多大，只看现在是不是已经超了。
    """
    login = _jwt_username(token)
    if not login:
        return "nologin"
    if login == ADMIN_LOGIN:
        return ""
    acc = db.scalar(select(CloudAccount).where(CloudAccount.login == login))
    if acc is None or acc.quota_mb <= 0:
        return "none"
    if writes and length is None:
        return "nolength"
    now = time.time()
    if acc.checked_at is None or (datetime.now() - acc.checked_at).total_seconds() > FRESH_SECONDS:
        acc.used_bytes = measure(folder_path(acc))
        acc.checked_at = datetime.now()
        db.commit()
    with _reserved_lock:
        mine = [(t, n) for t, n in _reserved.get(login, []) if now - t < RESERVE_SECONDS]
        pending = sum(n for _, n in mine)
        need = length or 0
        if acc.used_bytes + pending + need > acc.quota_mb * MB:
            return "over"
        total = total_mb(db)
        everyone = sum(a.used_bytes for a in db.scalars(select(CloudAccount)))
        all_pending = sum(n for k, v in _reserved.items() for t, n in v if now - t < RESERVE_SECONDS)
        if total and everyone + all_pending + need > total * MB:
            return "total"
        if need:
            mine.append((now, need))
        _reserved[login] = mine
    return ""


# ---------------------------------------------------------------- 后台：量用量、超额收权限、对账
SCAN_EVERY = 300


def scan(db: Session) -> None:
    """量每位老师的实际用量，超没超额变了就改 OpenList 里的权限；顺带把账号状态对一遍账。"""
    ol = client()
    ensure_setup(db)
    users = ol.users()
    for acc in db.scalars(select(CloudAccount)):
        user = db.get(User, acc.user_id)
        if user is None:
            continue
        if acc.quota_mb > 0 and os.path.isdir(folder_path(acc)):
            acc.used_bytes = measure(folder_path(acc))
            acc.over_quota = acc.used_bytes > acc.quota_mb * MB
            acc.checked_at = datetime.now()
        try:
            sync(db, user, acc, users=users)
        except CloudError as e:
            log.warning("云盘对账 %s：%s", acc.login, e)
    db.commit()


def start_background() -> None:
    if not enabled():
        return
    from ..database import SessionLocal

    def loop():
        time.sleep(15)                      # 等 openlist 容器起来
        while True:
            try:
                with SessionLocal() as db:
                    # 几个工作进程各有一个线程，靠 app_meta 里的时间戳错开，免得一起量
                    row = db.get(AppMeta, "cloud_scan_at")
                    last = float(row.value) if row and row.value.replace(".", "", 1).isdigit() else 0
                    if time.time() - last >= SCAN_EVERY - 30:
                        if row:
                            row.value = str(time.time())
                        else:
                            db.add(AppMeta(key="cloud_scan_at", value=str(time.time())))
                        db.commit()
                        scan(db)
            except Exception as e:            # noqa: BLE001
                log.warning("云盘后台扫描没成功：%s", e)
            time.sleep(SCAN_EVERY)

    threading.Thread(target=loop, name="cloud-scan", daemon=True).start()
