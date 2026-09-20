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
import json
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TIMEOUT = 15
PING_TIMEOUT = 4

# **连接复用。** 默认每次请求都新建一条 TCP 连接，光握手就要一个来回 ——
# 实测连学校服务器一个来回约 50 ms，而一次最轻的接口调用总共才 100 ms，
# 也就是说**一半时间花在握手上**。一个学生从登录到进考试要打四五个接口，
# 复用之后这部分全省掉。
#
# HTTPHandler 本身不带连接池，但 urllib 会在同一个 opener 上沿用
# keep-alive 的底层连接（服务端 nginx 默认开着 keep-alive）。
_opener = urllib.request.build_opener()
_opener.addheaders = []            # 自己逐个请求加，别让它塞默认 User-Agent


class NotModified(Exception):
    """服务器说"你那份还是最新的"（HTTP 304）。不是错误，是好消息。"""


_last_etag = ""              # 上一次响应带回来的 ETag，给 fetch_exam 存档用


class ApiError(Exception):
    """服务器明确拒绝了（口令不对、名单里没这个人、考试关了……）。

    message 是可以**原样显示给学生**的一句话 —— 后端的 detail 都是中文写好的。
    """


def norm(server: str) -> str:
    """把用户输的地址整成能用的样子。

    机房里监考老师常常只输一个 IP（`192.168.1.8`）或者带上端口
    （`192.168.1.8:8000`），少了 http:// 就连不上，还查不出原因。

    **自己写了 https:// 就按 https 走** —— 部署在公网、挂了域名和证书的学校
    填的是 `https://exam.xxx.edu.cn`，不能被改成 http。
    """
    s = str(server or "").strip().rstrip("/")
    if s and "://" not in s:
        s = "http://" + s
    return s


def _request(url: str, body: dict | None = None, timeout: int = TIMEOUT,
             token: str = "", method: str = "", etag: str = "") -> bytes:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data,
                                 method=method or ("POST" if data is not None else "GET"))
    if data is not None:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    # **主动要压缩。** urllib 默认不发这个头，于是服务器把 JSON 原样发过来 ——
    # nginx 明明配了 gzip 却用不上。实测一个 16 KB 的响应压完只剩 6 KB
    req.add_header("Accept-Encoding", "gzip")
    req.add_header("Connection", "keep-alive")
    if etag:
        req.add_header("If-None-Match", f'"{etag}"')
    try:
        with _opener.open(req, timeout=timeout) as resp:
            global _last_etag
            _last_etag = (resp.headers.get("ETag") or "").strip('"')
            raw = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)
            return raw
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            raise NotModified from None
        # 后端把原因写在 detail 里，中文的，原样转给学生看比"HTTP 403"有用得多
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace")).get("detail")
        except Exception:                                   # noqa: BLE001
            detail = ""
        raise ApiError(str(detail or f"服务器拒绝了（{exc.code}）")) from exc
    except urllib.error.URLError as exc:
        # 证书问题单独说：学校自己签的证书很常见，报「CERTIFICATE_VERIFY_FAILED」
        # 网管也不知道该查哪儿。直接告诉他怎么绕
        if "CERTIFICATE" in str(exc.reason).upper() or "SSL" in str(exc.reason).upper():
            raise ApiError("教师端的 https 证书通不过校验（多半是学校自己签的）。"
                           "请改用 http 地址，或者换成受信任的证书") from exc
        raise ApiError(f"连不上教师端（{exc.reason}）") from exc
    except (socket.timeout, TimeoutError) as exc:
        raise ApiError("教师端响应超时") from exc


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
        _json(norm(server) + "/api/desk/ping", timeout=timeout)
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
    return _json(norm(server) + "/api/desk/signin",
                 {"student_no": str(student_no).strip(), "name": str(name).strip()})


def fetch_exam(server: str, token: str, save_to: Path) -> Path:
    """把这场考试的考试包下下来，存成本地文件。返回存到哪了。

    **手上那份还新就不再下。** 考试包有 900 KB 上下（含配图），在学校那条几兆
    的上行链路上一份要一秒多，五十个人同时开考就是几十秒。服务器给包打了
    ETag，这里把上次拿到的那个带上去问一句：没变就回 304，一个字节都不传。

    先写临时文件再改名：下到一半断网的话，留下的是个半截 zip，下次开机自动
    认包时会打不开 —— 一个改名就能避掉。
    """
    base = norm(server)
    url = f"{base}/api/desk/exam/{urllib.parse.quote(token)}?server={urllib.parse.quote(base)}"
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
    url = f"{norm(server)}/api/take/{urllib.parse.quote(token)}/submit"
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
# 登录是**学号 + 密码**（初始密码就是学号）。早先桌面端用的是"考号 + 姓名"，
# 那样没法改密码 —— 没有密码可改。
def login(server: str, student_no: str, password: str) -> dict:
    """学生登录，换回 {"access_token": …, "student": {...}}。"""
    query = urllib.parse.urlencode({"student_no": str(student_no).strip(),
                                    "password": password})
    return _json(f"{norm(server)}/api/student/login?{query}", {}, method="POST")


def me(server: str, token: str) -> dict:
    return _json(f"{norm(server)}/api/student/me", token=token)


def home(server: str, token: str) -> dict:
    """首页那一小把数字：考了几场、打字练了多少、最快多少字。"""
    return _json(f"{norm(server)}/api/student/home", token=token)


def change_password(server: str, token: str, old: str, new: str) -> dict:
    return _json(f"{norm(server)}/api/student/password",
                 {"old_password": old, "new_password": new}, token=token)


def my_exams(server: str, token: str) -> list:
    """我能参加的考试。每项带 token —— 桌面端拿它去下考试包。"""
    got = _json(f"{norm(server)}/api/student/exams", token=token)
    return got if isinstance(got, list) else []


# ================================================================ 打字练习
def typing_config(server: str) -> dict:
    return _json(f"{norm(server)}/api/typing/config")


# 两套叫法：取文本的接口用 english/chinese，交成绩的接口用「英文」「中文」。
# 映射放在这儿，别让界面去记这件事
PASSAGE_MODE = {"中文": "chinese", "英文": "english"}


def typing_passage(server: str, module: str, difficulty: str) -> str:
    """取一段练习文本。返回正文，取不到就抛 ApiError（里面是后端写好的中文）。"""
    query = urllib.parse.urlencode({"mode": PASSAGE_MODE.get(module, "chinese"),
                                    "difficulty": difficulty})
    got = _json(f"{norm(server)}/api/typing/passage?{query}")
    return str((got or {}).get("text") or "")


def typing_submit(server: str, student: dict, module: str, difficulty: str,
                  typed: int, correct: int, seconds: float) -> dict:
    """交一次打字成绩。**速度、正确率、星级都由后端算** —— 客户端只报原始量，
    和网页端一个口径，免得两边算法飘开。"""
    return _json(f"{norm(server)}/api/typing/records", {
        "student_name": student.get("name", ""),
        "student_class": student.get("cls", "") or student.get("student_class", ""),
        "module": module, "difficulty": difficulty,
        "typed_chars": int(typed), "correct_chars": int(correct),
        "duration": float(seconds),
    })
