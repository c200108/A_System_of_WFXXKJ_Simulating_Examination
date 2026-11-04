"""打字交成绩后显示的全校排名（2.17.2）。

排行按「模块 + 难度」分开排，**每个学生只算最好的一次** —— 练得再多也只占一个
名次，名次不会超过总人数；但每一次练习照样入库，学情和成绩页里一条不少。
"""

import pytest

from tests.test_typing import _student, _submit


@pytest.fixture(autouse=True)
def _empty_board(client):
    """每条用例从空榜开始（库是整场测试共用的）。"""
    from sqlalchemy import delete

    from app.database import SessionLocal
    from app.models import TypingRecord

    with SessionLocal() as db:
        db.execute(delete(TypingRecord))
        db.commit()


def _go(client, name, correct, cls="七(3)班", **kw):
    """correct 个字、60 秒，速度就是 correct 字/分。"""
    res = _submit(client, student_name=name, student_class=cls,
                  typed_chars=correct, correct_chars=correct, **kw)
    assert res.status_code == 200, res.text
    return res.json()


def test_first_one_is_first_of_one(client):
    r = _go(client, "甲", 50)
    assert (r["rank"], r["rank_total"], r["best_speed"], r["best_rank"]) == (1, 1, 50, 1)


def test_each_student_counts_once_by_best(client, auth):
    for s in (60, 70, 80):                 # 乙练了三次，只算最好的 80
        _go(client, "乙", s)
    _go(client, "丙", 75)
    r = _go(client, "丁", 72)
    assert r["rank_total"] == 3            # 乙、丙、丁三个人，不是五条记录
    assert r["rank"] == 3                  # 比 80、75 慢

    # 乙这次只打了 65：这次速度排第 3（75、72 都比它快），自己最好的 80 仍是第 1
    r = _go(client, "乙", 65)
    assert (r["rank"], r["rank_total"], r["best_speed"], r["best_rank"]) == (3, 3, 80, 1)

    # 原始记录一条不少：乙交了 4 次，成绩页里就有 4 条
    rows = client.get("/api/typing/records", headers=auth, params={"keyword": "乙"}).json()
    assert len([x for x in rows if x["student_name"] == "乙"]) == 4


def test_ties_share_rank(client):
    _go(client, "甲", 90)
    _go(client, "乙", 70)
    r = _go(client, "丙", 70)
    assert (r["rank"], r["rank_total"]) == (2, 3)


def test_module_and_difficulty_are_separate_boards(client):
    _go(client, "甲", 200, module="英文", difficulty="简单")
    _go(client, "乙", 100, module="英文", difficulty="中等")
    _go(client, "丙", 150, module="中文", difficulty="简单")
    r = _go(client, "丁", 10, module="中文", difficulty="中等")
    assert (r["rank"], r["rank_total"]) == (1, 1)
    r = _go(client, "戊", 120, module="英文", difficulty="简单")
    assert (r["rank"], r["rank_total"]) == (2, 2)


def test_same_name_in_two_classes_are_two_people(client):
    _go(client, "张三", 80, cls="七(1)班")
    r = _go(client, "张三", 60, cls="七(2)班")
    assert (r["rank"], r["rank_total"]) == (2, 2)


def test_account_merges_old_unlinked_records(client, auth):
    """同一个班级姓名，既有挂了账号的、又有没挂上的老记录：算一个人。"""
    me = _student(client, auth, "26091101", "排名甲")
    # 学号写错了没认上：以账号的班级姓名留了一条不挂账号的
    _go(client, "排名甲", 90, cls="八年级2班")
    res = client.post("/api/typing/records", headers=me, json={
        "student_name": "x", "student_class": "x", "module": "英文", "difficulty": "简单",
        "typed_chars": 50, "correct_chars": 50, "duration": 60})
    r = res.json()
    assert (r["rank_total"], r["best_speed"], r["best_rank"]) == (1, 90, 1)


def test_keyboard_has_no_rank(client):
    r = _submit(client, module="键盘", typed_chars=60, correct_chars=54).json()
    assert r["rank"] is None and r["rank_total"] is None
