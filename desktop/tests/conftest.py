# -*- coding: utf-8 -*-
"""桌面端的测试跑在**真后端**上。

不用 TestClient：客户端是拿 urllib 连真 HTTP 的，用 TestClient 就把要验的那一段
（网络、超时、下载、断线）全绕过去了。所以这里在后台线程里起一个真的 uvicorn，
用一个临时 SQLite 库，端口让系统随便挑。

跑法（用后端那个 venv，它有 fastapi 和 uvicorn）：

    backend\\.venv\\Scripts\\python.exe -m pytest desktop/tests -q
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest
import tkinter as tk

HERE = Path(__file__).resolve().parent
DESKTOP = HERE.parent
ROOT = DESKTOP.parent
sys.path.insert(0, str(DESKTOP))            # client 包
sys.path.insert(0, str(ROOT / "backend"))   # app 包


EXAM_ROOT = "C:/EXAM"
ADMIN = "admin"
ADMIN_PWD = "desk-test-pwd"      # 只在这套测试的临时库里存在

# **环境变量必须在 import app.* 之前设好。**
# `app/config.py` 在导入的那一刻就把配置读死了（Settings 只建一次）。测试模块
# 在顶上 `from app.services import …` 就会把它带进来 —— 那时候如果还没设
# DATABASE_URL，整套测试会悄悄连到开发库 data/app.db 上，报错却是
# 「no such table: users」这种看不出根因的。撞过一次，所以放在模块级。
WORK = Path(tempfile.mkdtemp(prefix="deskserver-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(WORK / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(WORK / "uploads")
os.environ["JWT_SECRET"] = "desktop-tests-only"
os.environ["ADMIN_USERNAME"] = ADMIN
os.environ["ADMIN_PASSWORD"] = ADMIN_PWD


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def typing_limits_off(monkeypatch):
    """打字防刷（2.11.0）自检里默认关掉：整套自检都是**同一台电脑**（同一个设备号），
    一分钟里要交好几次、取好几次文本；很多用例也只敲几个字就交。
    专门测这几条的用例自己用 `typing_limits_on` 打开。"""
    from app.siteconfig import site

    for key in ("min_done_ratio", "submit_interval_sec", "passage_per_minute"):
        monkeypatch.setattr(site.typing, key, 0)


@pytest.fixture
def typing_limits_on(monkeypatch):
    """按 config.yaml 的默认值打开防刷，并清掉前面用例留下的计数。"""
    from sqlalchemy import delete

    from app.database import SessionLocal
    from app.models import RateHit
    from app.siteconfig import site

    monkeypatch.setattr(site.typing, "min_done_ratio", 0.5)
    monkeypatch.setattr(site.typing, "submit_interval_sec", 60)
    monkeypatch.setattr(site.typing, "passage_per_minute", 3)
    with SessionLocal() as db:
        db.execute(delete(RateHit))
        db.commit()


def age_rate_hits(seconds: int) -> None:
    """把限频计数往前挪，等于时间过去了这么久 —— 自检里不真的等一分钟。"""
    from datetime import timedelta

    from sqlalchemy import update

    from app.database import SessionLocal
    from app.models import RateHit

    with SessionLocal() as db:
        db.execute(update(RateHit).values(at=RateHit.at - timedelta(seconds=seconds)))
        db.commit()


@pytest.fixture(scope="session")
def server():
    """一个真的后端，跑在 127.0.0.1 的随机端口上，库是临时的。"""
    import uvicorn
    from alembic import command
    from alembic.config import Config

    # 建表走 alembic：真实部署就是这么建的，测试也照走，免得两边的表结构飘开
    cfg = Config(str(ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])
    command.upgrade(cfg, "head")

    from app.seed import seed
    seed(supplement=False)  # 补充题会挤进组卷，测试从空题库起步（补充题另有 test_supplement）

    from app.main import app
    port = free_port()
    cfg_u = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(cfg_u)
    threading.Thread(target=srv.run, daemon=True).start()

    base = f"http://127.0.0.1:{port}"
    for _ in range(100):                       # 起来之前别往下走
        try:
            urllib.request.urlopen(base + "/api/desk/ping", timeout=1)
            break
        except Exception:                      # noqa: BLE001
            time.sleep(0.1)
    else:
        raise RuntimeError("后端没起来")

    yield base
    srv.should_exit = True


# ================================================================ 老师那一半
def teacher_token(server: str) -> str:
    from conftest import ADMIN, ADMIN_PWD
    body = urllib.parse.urlencode({"username": ADMIN, "password": ADMIN_PWD}).encode()
    req = urllib.request.Request(server + "/api/auth/login", data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())["access_token"]
    except urllib.error.HTTPError as exc:
        raise AssertionError("老师登录不上：" + exc.read().decode("utf-8", "replace")) from None


def call(server, method, path, body=None, token=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(server + path, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as exc:          # 让失败说人话，别只剩个 400
        raise AssertionError(f"{method} {path} → {exc.code} "
                             f"{exc.read().decode('utf-8', 'replace')}") from None


@pytest.fixture(scope="session")
def exam(server):
    """老师在网页后台走一遍：建仿真任务 → 出题 → 组卷 → 发布给一个班。"""
    tk = teacher_token(server)

    cid = call(server, "POST", "/api/classes", {"grade": "九年级", "name": "1班"}, tk)["id"]
    # 一个班二十个人。每个用例都用**名单里真有的**考号，免得测出来的是
    # "名单里没这个人"而不是想验的东西。
    #
    # **每个用例用自己的学号**：同一学号只能交一次卷，两个用例共用一个，
    # 后跑的那个会撞上 409，而且报错看着像是别的毛病。
    #   26090101-07  test_flow 用
    #   26090111-20  test_ui 用
    for i, name in enumerate(["桌面甲", "桌面丙", "桌面丁", "桌面戊", "桌面己",
                              "桌面庚", "桌面辛"], start=1):
        call(server, "POST", "/api/students",
             {"student_no": f"260901{i:02d}", "name": name, "class_id": cid}, tk)
    for i in range(11, 21):
        call(server, "POST", "/api/students",
             {"student_no": f"260901{i}", "name": f"机房{i}", "class_id": cid}, tk)
    other = call(server, "POST", "/api/classes", {"grade": "九年级", "name": "2班"}, tk)["id"]
    call(server, "POST", "/api/students",
         {"student_no": "26090201", "name": "外班乙", "class_id": other}, tk)

    task = call(server, "POST", "/api/sims", {
        "kind": "win", "title": "文件与文件夹操作",
        "env": {"fs": {f"{EXAM_ROOT}/win02": {"type": "dir"},
                       f"{EXAM_ROOT}/win02/会徽": {"type": "dir"},
                       f"{EXAM_ROOT}/win02/素材": {"type": "dir"},
                       f"{EXAM_ROOT}/win02/素材/冬奥介绍.txt": {
                           "type": "file", "content": "北京冬奥会"},
                       f"{EXAM_ROOT}/win02/待删除.tmp": {"type": "file", "content": "要删掉"}},
                "recycle": {}},
        "checks": [
            {"desc": "在「会徽」里新建「冬梦.txt」", "score": 4,
             "assert": {"op": "exists", "path": f"{EXAM_ROOT}/win02/会徽/冬梦.txt",
                        "is": "file"}},
            {"desc": "「冬梦.txt」里写上「一起向未来」", "score": 3,
             "assert": {"op": "content", "path": f"{EXAM_ROOT}/win02/会徽/冬梦.txt",
                        "has": "一起向未来"}},
            {"desc": "把「冬奥介绍.txt」复制到「会徽」", "score": 3,
             "assert": {"op": "exists", "path": f"{EXAM_ROOT}/win02/会徽/冬奥介绍.txt"}},
            {"desc": "删除「待删除.tmp」", "score": 2,
             "assert": {"op": "missing", "path": f"{EXAM_ROOT}/win02/待删除.tmp"}},
        ],
    }, tk)

    q = call(server, "POST", "/api/questions", {
        "type": "操作题",
        "stem": "打开 win02：(1) 在「会徽」里新建「冬梦.txt」并写上「一起向未来」；"
                "(2) 把「素材」里的「冬奥介绍.txt」复制到「会徽」；(3) 删除「待删除.tmp」。",
        "answer": "略", "scope": "Windows系统操作", "sim_task_id": task["id"],
        "is_pinned": True, "options": [],
    }, tk)

    paper = call(server, "POST", "/api/papers/generate", {
        "title": "桌面端测验", "by_sections": True, "use_pinned": True, "save": True}, tk)
    picked = next(x for x in paper["questions"] if x["id"] == q["id"])
    # 必出是全局状态，卷子存完立刻摘掉
    call(server, "PUT", f"/api/questions/{q['id']}", {"is_pinned": False}, tk)

    ex = call(server, "POST", "/api/exams",
              {"paper_id": paper["paper_id"], "target_class_ids": [cid],
               "show_score": True}, tk)
    return {"token": tk, "exam": ex, "qid": q["id"], "score": picked.get("score") or 0}


@pytest.fixture
def lab(tmp_path):
    """一台"考场机器"：考试文件夹 + 答案包目录。"""
    return {"root": tmp_path / "EXAM", "out": tmp_path / "答案包"}


@pytest.fixture(scope="session")
def exam_with_picture(server, exam):
    """一场带配图题的考试。

    图直接写进服务器的上传目录（测试里服务器就跑在同一个进程），再把
    `image_url` 挂到题上 —— 和老师在网页后台上传图片的效果一样。
    """
    from app.config import settings
    tk = teacher_token(server)
    cid = next(c["id"] for c in call(server, "GET", "/api/classes", token=tk)
               if c["grade"] == "九年级" and c["name"] == "1班")

    PIL = pytest.importorskip("PIL.Image", reason="服务端要靠 Pillow 解 JPEG")
    box = Path(settings.upload_dir) / "images"
    box.mkdir(parents=True, exist_ok=True)
    im = PIL.new("RGB", (1000, 800), (30, 120, 200))
    im.save(box / "读图题.jpg", format="JPEG")

    q = call(server, "POST", "/api/questions", {
        "type": "选择题", "stem": "请仔细读图，下列说法正确的是（ ）",
        "answer": "A", "scope": "计算机网络基础",
        "image_url": "/uploads/images/读图题.jpg", "is_pinned": True,
        "options": [{"label": "A", "content": "对"}, {"label": "B", "content": "错"}],
    }, tk)
    paper = call(server, "POST", "/api/papers/generate", {
        "title": "带图题测验", "by_sections": False,
        "counts": {"选择题": 1}, "use_pinned": True, "save": True}, tk)
    assert any(x["id"] == q["id"] for x in paper["questions"]), "必出的带图题没进卷子"
    call(server, "PUT", f"/api/questions/{q['id']}", {"is_pinned": False}, tk)

    ex = call(server, "POST", "/api/exams",
              {"paper_id": paper["paper_id"], "target_class_ids": [cid]}, tk)
    yield {"exam": ex, "qid": q["id"]}
    call(server, "DELETE", f"/api/questions/{q['id']}", token=tk)


# 放在这里而不是 test_ui.py：拖拽作答区的测试也要用同一个根窗口
@pytest.fixture(scope="session")
def tk_root():
    """**整场自检就这一个根窗口。**

    一个进程里反复 `Tk()` / `destroy()`，同时后台还跑着 uvicorn 线程，Tcl 会被
    踩坏 —— 症状是 "couldn't read file scrlbar.tcl" 这种莫名其妙的报错。
    """
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()
