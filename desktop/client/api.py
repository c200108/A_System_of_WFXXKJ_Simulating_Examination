# -*- coding: utf-8 -*-
"""和教师端网站说话。学生端所有的数据都从这里来。

这里只管**说话**，不管说什么。"学生在真机上做出来的东西怎么变成一份作答"
在 `states.py` —— 三类操作题各有各的终态，那是另一件事。

## 四个调用，对应后端 desk.py 的四个接口

    ping(server)                    通不通
    signin(server, no, name)        我是谁、我今天考什么          → /api/desk/signin
    fetch_exam(server, token, to)   把这场考试的考试包下下来      → /api/desk/exam/{token}
    submit(server, token, ...)      交卷                          → /api/take/{token}/submit

**学生、班级、试卷、考试全部来自教师端的数据库**，客户端一份都不存。老师在网页上
加个转学生、改个班级、发一场新考试，考场这边下一次开机就看得见，不用重新发包。

## 为什么用 urllib 不用 requests

标准库里就有，打包进 exe 不多一个依赖、不多几 MB，也不用在机房机器上装东西。

## 交卷为什么走 /api/take 而不是 /api/desk

因为那个接口**本来就在**：免登录、服务端判分、答卷直接进成绩页。桌面端和网页端
交上来的东西形状一样，后端不需要知道是谁交的 —— 判分、成绩页、阅卷界面一行都
不用改。桌面端不是另一套系统，是这场考试的另一个客户端。

## 传不上去怎么办

**本地那份 .ans 永远先写**，上传只是顺便。断网、服务器没开、网线被踢掉，学生该交
的卷已经在硬盘上了，网通了补传就行。考场里最怕的不是慢，是丢卷。
"""

from __future__ import annotations

import gzip
import hashlib
import http.client
import json
import platform
import socket
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

TIMEOUT = 15
PING_TIMEOUT = 4

# ================================================================ 连接复用
#
# **一半的等待花在握手上。** 实测连学校那台服务器（111.170.33.3:3315）：
#
#     TCP 建连                  约 35 ms
#     一次最轻的接口调用        60 ~ 95 ms      ← 新连接，握手 + 一个来回
#     同一条连接上再发一次      **33 ms**       ← 只剩一个来回
#
# 也就是说复用连接能让每次调用**直接减半**。学生从登录到进考试要打四五个接口，
# 每换一页又是一次，省下来的是能感觉到的。
#
# 早先这里给请求加了个 `Connection: keep-alive` 头就以为完事了 —— **没用**：
# urllib 每次 urlopen 都新建一个 HTTPConnection，头写得再好也照样重新握手。
# 上面那组数就是这么量出来的（加了头的 urllib 仍然 61~93 ms）。要真复用，
# 就得自己攥着连接。
#
# 规矩：**GET 才进池子，POST 一律用新连接。**
# 池子里的连接可能已经被服务器按 keep-alive 超时悄悄关掉了，发出去才发现，
# 这时重发一次是安全的 —— 对 GET 而言。POST 不行：交卷那一下要是服务器已经
# 收到、只是回程断了，重发就成了交两次卷。多花一次握手，换交卷这件事不出岔子。
_pool_lock = threading.Lock()
_pool: dict = {}                   # {(scheme, host, port): 闲着的那条连接}


def _take(scheme: str, host: str, port: int, timeout: int, reuse: bool):
    """借一条连接。返回 (连接, 是不是从池子里拿的)。"""
    if reuse:
        with _pool_lock:
            conn = _pool.pop((scheme, host, port), None)
        if conn is not None:
            conn.timeout = timeout
            return conn, True
    cls = http.client.HTTPSConnection if scheme == "https" else http.client.HTTPConnection
    return cls(host, port or (443 if scheme == "https" else 80), timeout=timeout), False


def _keep(scheme: str, host: str, port: int, conn) -> None:
    """用完还回池子。同一个 (协议, 主机, 端口) 只留一条 —— 学生端是单人使用，
    多留没意义，还会在换服务器之后攒下一堆没用的连接。"""
    with _pool_lock:
        old = _pool.get((scheme, host, port))
        _pool[(scheme, host, port)] = conn
    if old is not None and old is not conn:
        _close(old)


def _close(conn) -> None:
    try:
        conn.close()
    except Exception:                                       # noqa: BLE001
        pass


def drop_connections() -> None:
    """把攒着的连接全关掉。换服务器、退出登录时叫一声，别留着连旧地址的连接。"""
    with _pool_lock:
        conns = list(_pool.values())
        _pool.clear()
    for c in conns:
        _close(c)


class NotModified(Exception):
    """服务器说"你那份还是最新的"（HTTP 304）。不是错误，是好消息。"""


_last_etag = ""              # 上一次响应带回来的 ETag，给 fetch_exam 存档用


class ApiError(Exception):
    """服务器明确拒绝了（口令不对、名单里没这个人、考试关了……）。

    message 是可以**原样显示给学生**的一句话 —— 后端的 detail 都是中文写好的。
    retry_after：服务器说「过几秒再来」（429，打字交得太快、换文本太勤）时的秒数，别的是 0。
    """

    def __init__(self, message: str = "", retry_after: int = 0):
        super().__init__(message)
        self.retry_after = retry_after


def _device_id() -> str:
    """这台电脑的设备号，放在 X-Device-Id 里：打字「同一台电脑每分钟只能交一次、
    最多换三次文本」服务端按它认电脑。

    按机器名 + 网卡地址算，**不存文件** —— 机房的还原卡一重启文件就没了，换一版 exe
    也还是同一个号。不用 IP：线上服务器那边整个机房一个出口 IP，认 IP 就成了全机房一起限。
    """
    raw = f"{platform.node()}|{uuid.getnode():012x}"
    return "pc-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


DEVICE_ID = _device_id()


def norm(server: str) -> str:
    """把用户输的地址整理干净：去掉首尾空格和末尾的斜杠。**不加协议**。

    界面上的「教师端地址」只填 `192.168.1.8:8000`、`exam.xxx.edu.cn` 这样的，
    不带 http://（4.14.1）。用的时候再由 base() 选协议：

      · IP（含 localhost、带端口的）—— 直接 http；
      · 域名 —— 先试 https，连不上再退 http，试出来的记住，下次直接用；
      · 自己写了 http:// 或 https:// 的，照写的走，不猜。
    """
    return str(server or "").strip().rstrip("/")


def bare(server: str) -> str:
    """显示在输入框里的样子：去掉 http:// / https:// 前缀。"""
    s = norm(server)
    low = s.lower()
    for head in ("http://", "https://"):
        if low.startswith(head):
            return s[len(head):]
    return s


_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def _hostport(s: str) -> str:
    return s.split("/", 1)[0]


def is_ip_address(server: str) -> bool:
    """地址里的主机是不是 IP：IPv4、localhost、[IPv6]（可以带端口）。"""
    hp = _hostport(bare(server)).lower()
    if hp.startswith("["):                                 # [::1]:8000
        return True
    host = hp.rsplit(":", 1)[0] if hp.count(":") == 1 else hp
    if hp.count(":") > 1:                                  # 不带方括号的 IPv6
        return True
    return host == "localhost" or bool(_IPV4.match(host))


# 试出来的协议：{"exam.xxx.edu.cn": "https"}。内存里一份，配置文件里存一份，
# 重开程序不用再试一遍
_schemes_lock = threading.Lock()
_schemes: dict = {}
_schemes_loaded = False
# 两个协议都没试通的域名：{主机: 什么时候试的}。三十秒里不再重试，
# 不然断网时每个请求都要先白等两轮超时
_dead: dict = {}
DEAD_FOR = 30


def _load_schemes() -> None:
    global _schemes_loaded
    if _schemes_loaded:
        return
    _schemes_loaded = True
    try:
        from . import store
        got = store.load_config().get("server_schemes") or {}
        _schemes.update({str(k): str(v) for k, v in got.items() if v in ("http", "https")})
    except Exception:                                       # noqa: BLE001
        pass


def _remember(host: str, scheme: str | None) -> None:
    with _schemes_lock:
        if scheme:
            _schemes[host] = scheme
        else:
            _schemes.pop(host, None)
        snapshot = dict(_schemes)
    try:
        from . import store
        store.save_config(server_schemes=snapshot)
    except Exception:                                       # noqa: BLE001
        pass


def _probe(s: str) -> str:
    """域名先试 https、再试 http。服务器回了话（哪怕是 404）就算通。"""
    for scheme in ("https", "http"):
        try:
            _request(f"{scheme}://{s}/api/desk/ping", timeout=PING_TIMEOUT)
            return scheme
        except NetError:
            continue
        except (ApiError, NotModified):
            return scheme
    return ""


def base(server: str) -> str:
    """带协议的完整地址。所有请求都走它：登录、取卷、下载考试包、交卷、打字……

    域名第一次用的时候要试一下（最多两轮 PING_TIMEOUT），所以**别在界面线程里叫**；
    试出来之后记住，之后都是直接返回。
    """
    s = norm(server)
    if not s or "://" in s:
        return s
    if is_ip_address(s):
        return "http://" + s
    host = _hostport(s).lower()
    with _schemes_lock:
        _load_schemes()
        known = _schemes.get(host)
    if known:
        return f"{known}://{s}"
    if time.time() - _dead.get(host, 0) < DEAD_FOR:
        return "https://" + s                              # 刚试过都不通，别再等一遍
    scheme = _probe(s)
    if scheme:
        _dead.pop(host, None)
        _remember(host, scheme)
        return f"{scheme}://{s}"
    _dead[host] = time.time()
    return "https://" + s


def forget(server: str) -> None:
    """记住的协议不灵了（证书过期、服务器换了配置）：忘掉，下次重新试。"""
    s = norm(server)
    if s and "://" not in s and not is_ip_address(s):
        host = _hostport(s).lower()
        with _schemes_lock:
            _load_schemes()
            had = host in _schemes
        if had:
            _remember(host, None)


class NetError(ApiError):
    """根本没连上（断网、地址不对、超时、证书不过）。和「服务器拒绝了」分开，
    试协议的时候靠它分：连不上才换 http，服务器回了 4xx 说明这个协议是通的。"""


def _fail(exc: Exception) -> ApiError:
    """把底层异常翻成一句学生和网管看得懂的话。"""
    text = str(getattr(exc, "reason", exc) or exc)
    # 证书问题单独说：学校自己签的证书很常见，报「CERTIFICATE_VERIFY_FAILED」
    # 网管也不知道该查哪儿。直接告诉他怎么绕
    if "CERTIFICATE" in text.upper() or "SSL" in text.upper():
        return NetError("教师端的 https 证书通不过校验（多半是学校自己签的）。"
                        "请改用 http 地址，或者换成受信任的证书")
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return NetError("教师端响应超时")
    return NetError(f"连不上教师端（{text}）")


def _request(url: str, body: dict | None = None, timeout: int = TIMEOUT,
             token: str = "", method: str = "", etag: str = "") -> bytes:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    verb = method or ("POST" if data is not None else "GET")
    bits = urllib.parse.urlsplit(url)
    path = bits.path + (f"?{bits.query}" if bits.query else "")

    headers = {"Accept": "application/json",
               # **主动要压缩。** 不发这个头，服务器就把 JSON 原样发过来 ——
               # nginx 明明配了 gzip 却用不上。实测 16 KB 的响应压完只剩 6 KB
               "Accept-Encoding": "gzip",
               "Connection": "keep-alive",
               "X-Device-Id": DEVICE_ID}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = "Bearer " + token
    if etag:
        headers["If-None-Match"] = f'"{etag}"'

    # GET 才复用连接（见上面那段）。重发也只给 GET，而且只在"这条连接是从池子里
    # 拿的"时候 —— 那种失败十有八九是服务器早把它关了，请求根本没出去。
    reuse = verb == "GET"
    for attempt in (1, 2):
        conn, pooled = _take(bits.scheme, bits.hostname, bits.port, timeout, reuse)
        try:
            conn.request(verb, path, body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
        except Exception as exc:                            # noqa: BLE001
            _close(conn)
            if attempt == 1 and pooled:
                continue                                    # 换条新连接再来一次
            # 试出来记住的协议连不上了：忘掉，下一次重新试（证书过期、改了配置）
            forget(f"{bits.hostname}:{bits.port}" if bits.port else str(bits.hostname))
            raise _fail(exc) from exc
        if reuse and not resp.will_close:
            _keep(bits.scheme, bits.hostname, bits.port, conn)
        else:
            _close(conn)
        break

    if resp.status == 304:
        raise NotModified
    if resp.status >= 400:
        # 后端把原因写在 detail 里，中文的，原样转给学生看比"HTTP 403"有用得多
        try:
            detail = json.loads(raw.decode("utf-8", "replace")).get("detail")
        except Exception:                                   # noqa: BLE001
            detail = ""
        try:
            wait = int(resp.headers.get("Retry-After") or 0) if resp.status == 429 else 0
        except ValueError:
            wait = 0
        raise ApiError(str(detail or f"服务器拒绝了（{resp.status}）"), retry_after=wait)

    global _last_etag
    _last_etag = (resp.headers.get("ETag") or "").strip('"')
    if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
        raw = gzip.decompress(raw)
    return raw


def _json(url: str, body: dict | None = None, timeout: int = TIMEOUT,
          token: str = "", method: str = ""):
    raw = _request(url, body, timeout, token, method)
    try:
        return json.loads(raw.decode("utf-8", "replace") or "{}")
    except ValueError as exc:
        raise ApiError("教师端返回的内容看不懂，地址是不是填成别的网站了？") from exc


# ================================================================ 探活
def ping(server: str, timeout: int = PING_TIMEOUT) -> bool:
    """开考前探一下，好早点提示监考老师 —— 别等到交卷才发现网不通。"""
    if not server:
        return False
    try:
        _json(base(server) + "/api/desk/ping", timeout=timeout)
        return True
    except ApiError:
        return False


# ================================================================ 认人 + 取卷
def signin(server: str, student_no: str, name: str = "") -> dict:
    """报考号姓名，换回 {"student": {...}, "exams": [...]}。

    exams 里每一项：id / title / token / duration_min / submitted / can_take。
    **只包含面向这个学生班级的考试** —— 准入在服务器那边判，客户端不做过滤，
    也就没法被绕过。
    """
    return _json(base(server) + "/api/desk/signin",
                 {"student_no": str(student_no).strip(), "name": str(name).strip()})


def exam_live(server: str, token: str) -> dict:
    """考试中途老师改了的设置：{"early_submit": 允许提前交卷, "is_open": 考试还开着}。

    考试包里那份是开考那一刻的；老师考到一半打开「允许提前交卷」，靠这个跟上。
    超时给短一点：它在后台问，问不到就按原来的设置走，不耽误考试。
    """
    return _json(base(server) + f"/api/take/{token}/live", timeout=5)


def fetch_exam(server: str, token: str, save_to: Path) -> Path:
    """把这场考试的考试包下下来，存成本地文件。返回存到哪了。

    **手上那份还新就不再下。** 考试包有 900 KB 上下（含配图），在学校那条几兆
    的上行链路上一份要一秒多，五十个人同时开考就是几十秒。服务器给包打了
    ETag，这里把上次拿到的那个带上去问一句：没变就回 304，一个字节都不传。

    先写临时文件再改名：下到一半断网的话，留下的是个半截 zip，下次开机自动
    认包时会打不开 —— 一个改名就能避掉。
    """
    base_url = base(server)
    url = f"{base_url}/api/desk/exam/{urllib.parse.quote(token)}?server={urllib.parse.quote(base_url)}"
    save_to = Path(save_to)
    stamp = save_to.with_suffix(save_to.suffix + ".etag")

    old = ""
    if save_to.exists():
        try:
            old = stamp.read_text(encoding="utf-8").strip()
        except OSError:
            old = ""

    try:
        raw = _request(url, timeout=120, etag=old)
    except NotModified:
        return save_to                   # 本地那份就是最新的

    if not raw.startswith(b"PK"):
        raise ApiError("下下来的不是考试包，请让老师确认这场考试还开着")
    save_to.parent.mkdir(parents=True, exist_ok=True)
    tmp = save_to.with_suffix(save_to.suffix + ".part")
    tmp.write_bytes(raw)
    tmp.replace(save_to)
    if _last_etag:
        try:
            stamp.write_text(_last_etag, encoding="utf-8")
        except OSError:
            pass
    return save_to


# ================================================================ 交卷
def submit(server: str, token: str, student: dict, answers: dict,
           timeout: int = TIMEOUT) -> tuple[bool, str, dict]:
    """交卷。返回 (成不成, 给学生看的一句话, 服务器返回的内容)。

    这里**不抛异常**：交卷这一步失败不能把界面打断，学生要看到"卷子存本机了、
    可以补传"，而不是一个报错框。
    """
    if not server or not token:
        return False, "没有教师端地址，只能交到本地", {}
    url = f"{base(server)}/api/take/{urllib.parse.quote(token)}/submit"
    try:
        got = _json(url, {
            "student_name": student.get("name", ""),
            "student_class": student.get("cls", ""),
            "student_no": student.get("no", ""),
            "answers": answers,
        }, timeout)
        return True, str(got.get("message") or "交卷成功"), got
    except ApiError as exc:
        return False, str(exc), {}


# ================================================================ 学生账号
# 下面这一组走的是**学生网页端本来就有的那套接口**（/api/student/*）。
# 桌面端因此不用另起一套：首页数字、改密码、考试列表、打字练习，网页上有的
# 这边都有，而且两边看到的永远是同一份数据。
#
# 登录是**学号 + 密码**（初始密码 123456；老账号是学号）。早先桌面端用的是"考号 + 姓名"，
# 那样没法改密码 —— 没有密码可改。
def login(server: str, student_no: str, password: str) -> dict:
    """学生登录，换回 {"access_token": …, "student": {...}}。"""
    query = urllib.parse.urlencode({"student_no": str(student_no).strip(),
                                    "password": password})
    return _json(f"{base(server)}/api/student/login?{query}", {}, method="POST")


def login_classes(server: str) -> list:
    """姓名登录版登录页的班级下拉：[{"id": 3, "display": "八年级1班"}, …]。不用登录。"""
    got = _json(f"{base(server)}/api/student/classes")
    return got if isinstance(got, list) else []


def login_by_name(server: str, name: str, password: str, class_id=None) -> dict:
    """「姓名登录版」的登录：班级 + 中文姓名 + 密码（初始 123456）。同一个班里重名的
    改填学号 —— 这一栏也认学号。"""
    params = {"name": str(name).strip(), "password": password}
    if class_id is not None:
        params["class_id"] = class_id
    query = urllib.parse.urlencode(params)
    return _json(f"{base(server)}/api/student/login-by-name?{query}", {}, method="POST")


def me(server: str, token: str) -> dict:
    return _json(f"{base(server)}/api/student/me", token=token)


def home(server: str, token: str) -> dict:
    """首页那一小把数字：考了几场、打字练了多少、最快多少字。"""
    return _json(f"{base(server)}/api/student/home", token=token)


def change_password(server: str, token: str, old: str, new: str) -> dict:
    return _json(f"{base(server)}/api/student/password",
                 {"old_password": old, "new_password": new}, token=token)


def my_exams(server: str, token: str) -> list:
    """我能参加的考试。每项带 token —— 桌面端拿它去下考试包。"""
    got = _json(f"{base(server)}/api/student/exams", token=token)
    return got if isinstance(got, list) else []


def review(server: str, token: str, exam_id) -> dict:
    """回看自己交的那份卷。

    **对错和每题得分要看老师放没放**（服务器按 show_answer 决定给不给），
    客户端只管显示收到的东西 —— 判"能不能看"的活儿放在服务端，exe 被反编译
    也套不出答案来。

    分数是**当场读的**，不是交卷那一刻的快照：老师批完操作题，学生点一下
    刷新就能看到新分。
    """
    return _json(f"{base(server)}/api/student/exams/{exam_id}/review", token=token)


# ================================================================ 打字练习
def typing_config(server: str) -> dict:
    return _json(f"{base(server)}/api/typing/config")


# 两套叫法：取文本的接口用 english/chinese，交成绩的接口用「英文」「中文」。
# 映射放在这儿，别让界面去记这件事
PASSAGE_MODE = {"中文": "chinese", "英文": "english"}


def typing_passage(server: str, module: str, difficulty: str) -> str:
    """取一段练习文本。返回正文，取不到就抛 ApiError（里面是后端写好的中文）。"""
    query = urllib.parse.urlencode({"mode": PASSAGE_MODE.get(module, "chinese"),
                                    "difficulty": difficulty})
    got = _json(f"{base(server)}/api/typing/passage?{query}")
    return str((got or {}).get("text") or "")


def typing_submit(server: str, student: dict, module: str, difficulty: str,
                  typed: int, correct: int, seconds: float, token: str = "",
                  target: int = 0) -> dict:
    """交一次打字成绩。**速度、正确率、星级都由后端算** —— 客户端只报原始量，
    和网页端一个口径，免得两边算法飘开。

    **令牌和学号一定要带上**：这条成绩要挂到学生账号上，首页那三个数字
    （练习次数、最快速度、平均正确率）只统计挂上了账号的记录。不带的话成绩
    照样入库、老师在成绩页也看得见，但学生自己的首页永远是 0 —— 这个坑
    交卷那条路踩过一次（4.4.0 修的），打字这条当时漏了。

    两样都带是有意的：令牌是正经凭据，但它会过期（默认 12 小时）；练了一下午
    再交的时候令牌可能已经失效，这时服务端按学号认领，和交卷那条路一个写法。

    target 是这段文本有多长：服务端要打完一半（min_done_ratio）才收，靠它判。
    exe 不限时，time_limit 固定报 0。
    """
    return _json(f"{base(server)}/api/typing/records", {
        "student_name": student.get("name", ""),
        "student_class": student.get("cls", "") or student.get("student_class", ""),
        "student_no": str(student.get("no", "") or student.get("student_no", "")),
        "module": module, "difficulty": difficulty,
        "typed_chars": int(typed), "correct_chars": int(correct),
        "duration": float(seconds),
        "target_chars": int(target), "time_limit": 0,
    }, token=token)
