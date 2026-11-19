"""打字计分会话（2.23.1）：服务端出文本、记时间，练习中同步进度，一个会话只能交一次。

原来交成绩只报三个统计数，一个 POST 就能造出「8000 字/分」。这里测的是真的协议：
开练 → 同步进度 → 交成绩，时间都按服务端的钟。测试里不真的等，靠把会话的开始时间往前挪。
"""

import json
import uuid
from datetime import timedelta

import pytest

from app import clock
from app.database import SessionLocal
from app.models import TypingRecord, TypingSession
from app.siteconfig import site
from tests.typing_support import rig, start

TEXT = "a" * 600


@pytest.fixture(autouse=True)
def _rules(monkeypatch):
    monkeypatch.setattr(site.typing, "require_roster", False)
    monkeypatch.setattr(site.typing, "min_done_ratio", 0.5)
    monkeypatch.setattr(site.typing, "submit_interval_sec", 0)
    monkeypatch.setattr(site.typing, "max_speed_chinese", 200)
    monkeypatch.setattr(site.typing, "max_speed_english", 500)
    monkeypatch.setattr(site.typing, "burst_chars", 30)
    monkeypatch.setattr(site.typing, "submit_grace_sec", 10)


def _open(client, module="中文", time_limit=0, headers=None, length=300):
    res = start(client, {"module": module, "difficulty": "简单", "time_limit": time_limit,
                         "student_name": "会话测试", "student_class": "七(5)班"}, headers)
    assert res.status_code == 200, res.text
    sid = res.json()["session_id"]
    rig(sid, target="a" * length)
    return sid


def _shift(sid, seconds):
    """时间过去了 seconds 秒：开始时间、建会话时间、已有同步时间一起往前挪。"""
    with SessionLocal() as db:
        s = db.get(TypingSession, sid)
        d = timedelta(seconds=seconds)
        s.created_at -= d
        s.started_at -= d
        if s.last_progress_at:
            s.last_progress_at -= d
        if s.finished_at:
            s.finished_at -= d
        db.commit()


def _sync(client, sid, n, headers=None):
    return client.post("/api/typing/sessions/progress", headers=headers or {},
                       json={"session_id": sid, "answer": "a" * n})


def _submit(client, sid, n, headers=None, **extra):
    return client.post("/api/typing/records", headers=headers or {"X-Device-Id": uuid.uuid4().hex},
                       json={"session_id": sid, "answer": "a" * n, **extra})


def test_正常练习_同步几次再交_用时按服务端算(client):
    sid = _open(client)
    for n in (40, 80, 120, 160):           # 每 15 秒 40 字 = 160 字/分
        _shift(sid, 15)
        assert _sync(client, sid, n).json()["ok"] is True
    res = _submit(client, sid, 300)         # 最后一下冒出 140 字：时间窗里超速，作废
    assert res.status_code == 400 and "速度异常" in res.json()["detail"]

    sid = _open(client)
    for n in (40, 80, 120, 160):
        _shift(sid, 15)
        _sync(client, sid, n)
    _shift(sid, 15)
    res = _submit(client, sid, 200)
    assert res.status_code == 200, res.text
    got = res.json()
    # 不限时：从第一次同步往前倒推 3 秒算开始，3 + 45 + 15 = 63 秒
    assert 62 <= got["duration"] <= 64 and got["accuracy"] == 100
    assert got["speed"] == round(200 / (got["duration"] / 60))


def test_请求里报的数字一律不看(client):
    sid = _open(client)
    _shift(sid, 60)
    res = client.post("/api/typing/records", headers={"X-Device-Id": uuid.uuid4().hex}, json={
        "session_id": sid, "answer": "a" * 100 + "b" * 50,
        "typed_chars": 999, "correct_chars": 999, "duration": 1, "module": "英文",
        "student_name": "别人", "student_class": "别的班"})
    assert res.status_code == 200, res.text
    got = res.json()
    assert got["module"] == "中文" and got["accuracy"] == 67 and got["speed"] == 100
    with SessionLocal() as db:
        rec = db.query(TypingRecord).order_by(TypingRecord.id.desc()).first()
        assert (rec.student_name, rec.student_class) == ("会话测试", "七(5)班")


def test_一次粘贴一大段_同步时就作废(client):
    sid = _open(client)
    _shift(sid, 10)
    assert _sync(client, sid, 20).status_code == 200
    _shift(sid, 2)
    res = _sync(client, sid, 300)
    assert res.status_code == 400 and "速度异常" in res.json()["detail"]
    # 作废了：再同步、再交都不收
    assert _sync(client, sid, 20).status_code == 400
    _shift(sid, 600)
    res = _submit(client, sid, 300)
    assert res.status_code == 400 and "速度异常" in res.json()["detail"]


def test_同步全失败_最后一口气交上来的整段_也按时间窗卡住(client):
    """不同步、等够时间再整段交：总用时里的平均速度一样要在上限内。"""
    sid = _open(client)
    _shift(sid, 5)
    res = _submit(client, sid, 300)
    assert res.status_code == 400 and "速度异常" in res.json()["detail"]


def test_输入法整句上屏_一次冒出一截字照收(client):
    sid = _open(client)
    _shift(sid, 6)
    assert _sync(client, sid, 0).status_code == 200      # 前几秒在打拼音，框里还没字
    _shift(sid, 2)
    assert _sync(client, sid, 25).status_code == 200, "一整句 25 个字一下上屏"


def test_断网一会儿再补传_照收(client):
    sid = _open(client)
    _shift(sid, 10)
    _sync(client, sid, 20)
    _shift(sid, 40)                                     # 断网 40 秒，期间打了 100 字（150 字/分）
    assert _sync(client, sid, 120).status_code == 200
    _shift(sid, 10)
    assert _submit(client, sid, 150).status_code == 200


def test_一个会话只能交一次(client):
    sid = _open(client)
    _shift(sid, 120)
    assert _submit(client, sid, 300).status_code == 200
    res = _submit(client, sid, 300)
    assert res.status_code == 409 and "已经交过" in res.json()["detail"]
    assert _sync(client, sid, 300).status_code == 409


def test_被每分钟一次挡回来的_倒数完再交_用的是第一次交的内容和用时(client, monkeypatch):
    monkeypatch.setattr(site.typing, "submit_interval_sec", 60)
    dev = {"X-Device-Id": uuid.uuid4().hex}
    first = _open(client)
    _shift(first, 120)
    assert _submit(client, first, 300, headers=dev).status_code == 200
    sid = _open(client)
    _shift(sid, 90)
    assert _submit(client, sid, 150, headers=dev).status_code == 429
    _shift(sid, 60)                                     # 等了一分钟，等的时间不算用时
    with SessionLocal() as db:
        from app.models import RateHit
        db.query(RateHit).delete()
        db.commit()
    res = _submit(client, sid, 600, headers=dev)       # 再交时偷偷多塞字：不认，用第一次的
    assert res.status_code == 200, res.text
    assert res.json()["duration"] == 90 and res.json()["speed"] == 100


def test_限时练习_用时按时限加宽限封顶_晚太多只认到点前同步的(client):
    sid = _open(client, time_limit=1)
    _shift(sid, 30)
    _sync(client, sid, 60)
    _shift(sid, 28)
    _sync(client, sid, 110)
    _shift(sid, 300)                                    # 到点后五分钟才交（断网）
    late = _sync(client, sid, 500)
    assert late.status_code == 200 and late.json().get("late"), "到点后的同步不收"
    res = _submit(client, sid, 500)
    assert res.status_code == 200, res.text
    got = res.json()
    assert got["duration"] == 70, "1 分钟 + 10 秒宽限"
    assert got["speed"] == round(110 / (70 / 60)), "只认到点前最后一次同步的 110 字"


def test_限时练习_宽限内交上来的照常算(client):
    sid = _open(client, time_limit=1)
    _shift(sid, 30)
    _sync(client, sid, 60)
    _shift(sid, 33)
    res = _submit(client, sid, 120)
    assert res.status_code == 200 and res.json()["duration"] == 63


def test_不限时的exe_从开始敲才算时间(client):
    sid = _open(client)
    _shift(sid, 300)                                    # 对着文本看了五分钟
    assert _sync(client, sid, 3).status_code == 200      # 第一次同步：往前倒推 3 秒算开始
    _shift(sid, 57)
    res = _submit(client, sid, 150)
    assert res.status_code == 200 and res.json()["duration"] == 60


def test_没打完一半_会话留着可以接着练(client):
    sid = _open(client, length=400)
    _shift(sid, 60)
    res = _submit(client, sid, 100)
    assert res.status_code == 400 and "至少要 200 字" in res.json()["detail"]
    _shift(sid, 60)
    assert _submit(client, sid, 200).status_code == 200


def test_别的学生的令牌用不了这个会话(client, auth):
    from tests.test_typing import _student
    a = _student(client, auth, "26092201", "会话甲")
    b = _student(client, auth, "26092202", "会话乙")
    sid = _open(client, headers=a)
    _shift(sid, 60)
    assert _sync(client, sid, 50, headers=b).status_code == 403
    assert _submit(client, sid, 150, headers={**b, "X-Device-Id": uuid.uuid4().hex}).status_code == 403
    res = _submit(client, sid, 150, headers={**a, "X-Device-Id": uuid.uuid4().hex})
    assert res.status_code == 200
    with SessionLocal() as db:
        rec = db.query(TypingRecord).order_by(TypingRecord.id.desc()).first()
        assert rec.student_name == "会话甲"


def test_会话过期和乱填的id(client):
    assert _sync(client, "不存在", 10).status_code == 410
    assert _submit(client, "不存在", 10).status_code == 410
    sid = _open(client)
    _shift(sid, 2 * 3600 + 1)
    assert _submit(client, sid, 300).status_code == 410


def test_开练按出口IP限频(client, monkeypatch):
    monkeypatch.setattr(site.typing, "sessions_per_ip_per_minute", 2)
    ip = {"X-Real-IP": "10.250.1.1"}
    body = {"module": "键盘", "student_name": "限频", "student_class": "七(5)班"}
    for _ in range(2):
        h = {**ip, "X-Device-Id": uuid.uuid4().hex}
        assert client.post("/api/typing/sessions", headers=h, json=body).status_code == 200
    res = client.post("/api/typing/sessions", headers={**ip, "X-Device-Id": uuid.uuid4().hex}, json=body)
    assert res.status_code == 429, "换设备号也躲不过 IP 限频"


def test_旧会话随手清掉(client):
    sid = _open(client)
    _shift(sid, 4 * 3600)
    _open(client)
    with SessionLocal() as db:
        assert db.get(TypingSession, sid) is None


def test_键盘模块_交的是按键串(client):
    res = start(client, {"module": "键盘", "student_name": "键盘", "student_class": "七(5)班"})
    sid = res.json()["session_id"]
    text = res.json()["text"]
    assert text.startswith("`1234567890-=qwerty") and text.endswith(" ")
    _shift(sid, 60)
    answer = text[:10] + "\x01" + text[10:].upper()     # 中间按错一下；大写也算对
    r = client.post("/api/typing/records", headers={"X-Device-Id": uuid.uuid4().hex},
                    json={"session_id": sid, "answer": answer})
    assert r.status_code == 200, r.text
    assert r.json()["speed"] == 0 and r.json()["accuracy"] == round(len(text) / (len(text) + 1) * 100)


def test_同步打点有上限(client):
    sid = _open(client)
    for i in range(1, 120):
        _shift(sid, 2)
        _sync(client, sid, i)
    with SessionLocal() as db:
        checks = json.loads(db.get(TypingSession, sid).checks)
    assert len(checks) <= 80 and checks[0] == [0.0, 0]


def test_配置接口带出同步间隔(client):
    assert client.get("/api/typing/config").json()["sync_interval_sec"] == 1.5
