"""打字防作弊（2.22.1）：复制粘贴刷出来的成绩不收。

学生成绩里出现过「8340 字/分、用时 1 秒」：整段粘贴进去的。服务端两道关：
速度上限（config.yaml 的 typing.max_speed_*），和网页端报上来的按键数核对字数。
"""

import uuid


def _post(client, **kw):
    body = {"student_name": "防作弊", "student_class": "七(9)班", "module": "中文",
            "difficulty": "简单", "typed_chars": 60, "correct_chars": 55, "duration": 60,
            "target_chars": 100, "time_limit": 0}
    body.update(kw)
    return client.post("/api/typing/records", json=body, headers={"X-Device-Id": uuid.uuid4().hex})


def test_正常速度照收(client):
    assert _post(client).status_code == 200
    assert _post(client, module="英文", typed_chars=300, correct_chars=290, duration=60).status_code == 200
    assert _post(client, module="键盘", typed_chars=60, correct_chars=58, duration=30).status_code == 200


def test_截图里那种一秒打完的不收(client):
    res = _post(client, typed_chars=140, correct_chars=139, duration=1)
    assert res.status_code == 400
    assert "速度异常" in res.json()["detail"]
    rows = client.post("/api/typing/records", json={}).status_code  # 不影响别的
    assert rows == 422


def test_速度上限按模块(client):
    # 中文 200 字/分：201 不收、200 收
    assert _post(client, typed_chars=201, correct_chars=201, target_chars=300).status_code == 400
    assert _post(client, typed_chars=200, correct_chars=200, target_chars=300).status_code == 200
    # 英文 500 字母/分
    assert _post(client, module="英文", typed_chars=520, correct_chars=510, target_chars=600).status_code == 400
    # 认识键盘 400 键/分
    assert _post(client, module="键盘", typed_chars=250, correct_chars=250, duration=30).status_code == 400


def test_上限填0不限(client, monkeypatch):
    from app.siteconfig import site
    monkeypatch.setattr(site.typing, "max_speed_chinese", 0)
    assert _post(client, typed_chars=140, correct_chars=139, duration=1).status_code == 200


def test_字比按键多出一大截是粘贴的(client):
    # 中文：60 个字只按了 5 次键
    res = _post(client, keystrokes=5)
    assert res.status_code == 400 and "只按了 5 次键" in res.json()["detail"]
    # 拼音打字：每个字好几个键，正常
    assert _post(client, keystrokes=200).status_code == 200
    # 五笔词组之类：键数比字数少一些也照收（0.6 倍以上）
    assert _post(client, keystrokes=40).status_code == 200
    # 英文：每个字母都要按一次键
    assert _post(client, module="英文", typed_chars=100, correct_chars=98, keystrokes=60).status_code == 400
    assert _post(client, module="英文", typed_chars=100, correct_chars=98, keystrokes=105).status_code == 200


def test_不报按键数的exe和旧网页不查这一条(client):
    assert _post(client).status_code == 200
