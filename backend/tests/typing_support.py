"""打字测试的帮手：把老写法的「统计数」换成真的会话流程走一遍（2.23.1）。

老测试写的是 {typed_chars, correct_chars, duration, target_chars, time_limit, keystrokes}。
这里照真客户端那样：先 POST /sessions 开练（走真的名单校验、模块难度校验），
再在测试库里把原文换成一段可控的、把开始时间往前挪 duration 秒（测试里不真的等），
最后 POST /records 交「敲出来的内容」。速度、正确率、用时都还是服务端自己算的。
"""

import uuid
from datetime import timedelta

from app.database import SessionLocal
from app.models import TypingSession


def start(client, body: dict, headers: dict | None = None):
    """开练。设备号、IP 每次现生成：「每分钟最多换三次文本」按设备算，别让它挡住测试。"""
    h = {k: v for k, v in (headers or {}).items() if k.lower() == "authorization"}
    h["X-Device-Id"] = uuid.uuid4().hex
    # 开练按出口 IP 限频（每分钟 120 次）：整套测试共用一个库，每次换个 IP
    h["X-Real-IP"] = f"10.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}.{uuid.uuid4().int % 250}"
    return client.post("/api/typing/sessions", headers=h, json={
        "module": body.get("module", "中文"),
        "difficulty": body.get("difficulty", "简单"),
        "time_limit": body.get("time_limit", 0),
        "student_name": body.get("student_name", ""),
        "student_class": body.get("student_class", ""),
    })


def rig(session_id: str, *, target: str | None = None, seconds: float = 0) -> None:
    """改测试库里的会话：换原文、把开始时间往前挪 seconds 秒。"""
    with SessionLocal() as db:
        s = db.get(TypingSession, session_id)
        if target is not None:
            s.target = target
        if seconds:
            s.created_at -= timedelta(seconds=seconds)
            s.started_at -= timedelta(seconds=seconds)
        db.commit()


def legacy_submit(client, body: dict, headers: dict | None = None):
    """老写法的一次交成绩，换成会话流程。开练就被挡（名单、模块）的直接返回那个响应。"""
    res = start(client, body, headers)
    if res.status_code != 200:
        return res
    sid = res.json()["session_id"]
    typed = int(body.get("typed_chars", 0))
    correct = min(typed, int(body.get("correct_chars", 0)))
    length = max(int(body.get("target_chars", 0) or 0), typed, 1)
    if body.get("module") == "键盘":
        answer = "a" * correct + "\x01" * (typed - correct)
    else:
        answer = "a" * correct + "b" * (typed - correct)
    seconds = float(body.get("duration", 60))
    rig(sid, target="a" * length, seconds=seconds)
    payload = {"session_id": sid, "answer": answer}
    if body.get("keystrokes") is not None:
        payload["keystrokes"] = body["keystrokes"]
    # 交成绩这一刻的钟定死在「开始 + duration」：请求本身花的那点时间不算进去，
    # 慢一点的机器（3.8 的机房版环境）也不会多算 1 秒
    from app import clock

    with SessionLocal() as db:
        at = db.get(TypingSession, sid).started_at + timedelta(seconds=seconds)
    real = clock.now
    clock.now = lambda: at
    try:
        return client.post("/api/typing/records", headers=headers or {}, json=payload)
    finally:
        clock.now = real
