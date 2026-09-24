"""打字防刷（2.11.0）：中文英文打完一半才能交；同一台电脑每分钟只能交一次、最多换三次文本。

「同一台电脑」认 X-Device-Id（网页存在浏览器里、exe 按本机网卡算），没带才认 IP ——
线上服务器那种整个机房一个出口 IP 的，只认 IP 就成了全机房每分钟只能交一次。
"""

import uuid
from datetime import timedelta

import pytest
from sqlalchemy import update

from app.database import SessionLocal
from app.models import RateHit
from app.siteconfig import site


@pytest.fixture(autouse=True)
def _limits_on(monkeypatch):
    monkeypatch.setattr(site.typing, "min_done_ratio", 0.5)
    monkeypatch.setattr(site.typing, "submit_interval_sec", 60)
    monkeypatch.setattr(site.typing, "passage_per_minute", 3)


def _dev():
    return {"X-Device-Id": uuid.uuid4().hex}


def _body(**kw):
    body = {"student_name": "防刷", "student_class": "七(9)班", "module": "中文",
            "difficulty": "简单", "typed_chars": 60, "correct_chars": 55, "duration": 90,
            "target_chars": 100, "time_limit": 0}
    body.update(kw)
    return body


def _post(client, headers, **kw):
    return client.post("/api/typing/records", json=_body(**kw), headers=headers)


def _age(seconds):
    """把已有的计数往前挪，等于时间过去了这么久 —— 测试里不真的睡一分钟。"""
    with SessionLocal() as db:
        db.execute(update(RateHit).values(at=RateHit.at - timedelta(seconds=seconds)))
        db.commit()


def test_配置接口带出规则_客户端拿来提前提示(client):
    got = client.get("/api/typing/config").json()
    assert (got["min_done_ratio"], got["submit_interval_sec"], got["passage_per_minute"]) == (0.5, 60, 3)


def test_没打完一半交不了(client):
    res = _post(client, _dev(), typed_chars=49, correct_chars=49)
    assert res.status_code == 400
    assert "至少要 50 字" in res.json()["detail"] and "你敲了 49 字" in res.json()["detail"]
    assert _post(client, _dev(), typed_chars=50).status_code == 200
    assert _post(client, _dev(), module="英文", typed_chars=10, target_chars=21).status_code == 400


def test_限时练习练满一半时间也算(client):
    """英文一篇四五百个字母，1 分钟谁也敲不完一半 —— 只认字数的话限时练习永远交不上。"""
    long = dict(module="英文", typed_chars=40, correct_chars=38, target_chars=480)
    assert _post(client, _dev(), time_limit=1, duration=30, **long).status_code == 200
    res = _post(client, _dev(), time_limit=1, duration=29, **long)
    assert res.status_code == 400 and "练满 0.5 分钟" in res.json()["detail"]
    # 配置里没有的限时档位不认，免得随便报一个很短的限时
    assert _post(client, _dev(), time_limit=7, duration=300, **long).status_code == 400
    assert _post(client, _dev(), time_limit=0, duration=600, **long).status_code == 400, "exe 不限时，只认字数"


def test_旧版学生端没报文本长度_中文英文交不上_键盘照常(client):
    res = _post(client, _dev(), target_chars=0)
    assert res.status_code == 400 and "版本太旧" in res.json()["detail"]
    assert _post(client, _dev(), module="键盘", target_chars=0, typed_chars=5).status_code == 200


def test_同一台电脑每分钟只能交一次(client):
    me, other = _dev(), _dev()
    assert _post(client, me).status_code == 200
    res = _post(client, me)
    assert res.status_code == 429
    assert "每分钟只能交一次" in res.json()["detail"]
    assert 55 <= int(res.headers["Retry-After"]) <= 60
    assert _post(client, other).status_code == 200, "别的电脑不受影响"
    _age(61)
    assert _post(client, me).status_code == 200, "过了一分钟又能交"


def test_没交上的不占这一分钟的名额(client):
    me = _dev()
    assert _post(client, me, typed_chars=10).status_code == 400
    assert _post(client, me).status_code == 200


def test_没带设备号的按IP认(client):
    a, b = {"X-Real-IP": "10.9.9.1"}, {"X-Real-IP": "10.9.9.2"}
    assert _post(client, a).status_code == 200
    assert _post(client, a).status_code == 429
    assert _post(client, b).status_code == 200
    # 设备号格式不对（太短、带怪字符）的当没带
    assert _post(client, {"X-Device-Id": "x", "X-Real-IP": "10.9.9.1"}).status_code == 429


def _passage(client, headers, difficulty="简单"):
    return client.get("/api/typing/passage", params={"mode": "chinese", "difficulty": difficulty},
                      headers=headers)


def test_每分钟最多换三次文本(client):
    me = _dev()
    for _ in range(3):
        assert _passage(client, me).status_code == 200
    res = _passage(client, me)
    assert res.status_code == 429 and "每分钟最多换 3 次" in res.json()["detail"]
    assert res.headers["Retry-After"]
    assert _passage(client, _dev()).status_code == 200, "别的电脑不受影响"
    _age(61)
    assert _passage(client, me).status_code == 200


def test_没取到文本的不算一次(client):
    me = _dev()
    for _ in range(4):
        assert _passage(client, me, "地狱").status_code == 404
    assert _passage(client, me).status_code == 200


def test_填0就是不限(client, monkeypatch):
    monkeypatch.setattr(site.typing, "submit_interval_sec", 0)
    monkeypatch.setattr(site.typing, "passage_per_minute", 0)
    monkeypatch.setattr(site.typing, "min_done_ratio", 0)
    me = _dev()
    for _ in range(5):
        assert _passage(client, me).status_code == 200
        assert _post(client, me, typed_chars=1, target_chars=0).status_code == 200


def test_限频计数不跟着数据导出导入():
    from tools import export_data, import_data

    assert "rate_hits" in export_data.SKIP_TABLES and "rate_hits" in import_data.SKIP_TABLES
