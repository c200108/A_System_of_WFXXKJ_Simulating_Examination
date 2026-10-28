"""数据回收站（2.14.1）：删掉的先进回收站，7 天内能原样还原，过期才彻底删除。
顺带：打字成绩「删除筛选出的全部」不能再用 MySQL 不认的子查询删除写法；班级座次表。"""

from datetime import timedelta

from app import clock
from app.database import SessionLocal
from app.models import Exam, ExamSubmission, Question, RecycleItem, Student, TypingRecord


def _items(client, hdr, kind=""):
    return client.get("/api/recycle", params={"kind": kind}, headers=hdr).json()["items"]


def _restore(client, hdr, ids):
    res = client.post("/api/recycle/restore", json={"ids": ids}, headers=hdr)
    assert res.status_code == 200, res.text
    return res.json()


import pytest


@pytest.fixture(autouse=True, scope="module")
def _bank(client, auth):
    """本模块自己造几道题，单独跑也不依赖别的测试先导题。"""
    for i in range(4):
        client.post("/api/questions", json={
            "type": "选择题", "stem": f"回收站测试用题 {i}：下面哪个对？", "answer": "A",
            "scope": "信息基础与信息技术",
            "options": [{"label": "A", "content": "甲"}, {"label": "B", "content": "乙"}]},
            headers=auth)


def _paper(client, auth, title):
    res = client.post("/api/papers/generate", json={
        "title": title, "by_sections": False, "counts": {"选择题": 2}, "save": True}, headers=auth)
    assert res.status_code == 200, res.text
    return res.json()["paper_id"]


def test_exam_with_submissions_restores_in_full(client, auth):
    pid = _paper(client, auth, "回收站考试卷")
    exam = client.post("/api/exams", json={"paper_id": pid}, headers=auth).json()
    for name in ("甲", "乙"):
        res = client.post(f"/api/take/{exam['token']}/submit", json={
            "student_name": name, "student_class": "七年级1班", "student_no": "", "answers": {}})
        assert res.status_code == 200, res.text
    assert client.delete(f"/api/exams/{exam['id']}", headers=auth).status_code == 200
    with SessionLocal() as db:
        assert db.get(Exam, exam["id"]) is None
        left = db.query(ExamSubmission).filter(ExamSubmission.exam_id == exam["id"]).count()
        assert left == 0, f"答卷没跟着删：{left}"

    item = next(i for i in _items(client, auth, "exam") if "回收站考试卷" in i["title"])
    assert item["kind_name"] == "考试" and "2 份答卷" in item["detail"]
    assert item["days_left"] == 7
    assert _restore(client, auth, [item["id"]]) == {"restored": 1, "failed": []}
    with SessionLocal() as db:
        back = db.get(Exam, exam["id"])
        assert back and back.token == exam["token"], "id、口令原样回来，学生链接照样能用"
        assert len(back.submissions) == 2
    assert all(i["id"] != item["id"] for i in _items(client, auth))


def test_paper_takes_its_exams_and_comes_back(client, auth):
    pid = _paper(client, auth, "连考试一起删的卷")
    exam = client.post("/api/exams", json={"paper_id": pid}, headers=auth).json()
    assert client.delete(f"/api/papers/{pid}", headers=auth).status_code == 200
    with SessionLocal() as db:
        assert db.get(Exam, exam["id"]) is None
    item = next(i for i in _items(client, auth, "paper") if "连考试一起删的卷" in i["title"])
    _restore(client, auth, [item["id"]])
    with SessionLocal() as db:
        assert db.get(Exam, exam["id"]) is not None
    assert client.get(f"/api/papers/{pid}", headers=auth).status_code == 200


def test_question_soft_delete_goes_through_bin(client, auth):
    qid = client.get("/api/questions", params={"keyword": "回收站测试用题"},
                     headers=auth).json()["items"][0]["id"]
    assert client.delete(f"/api/questions/{qid}", headers=auth).status_code == 200
    item = next(i for i in _items(client, auth, "question"))
    _restore(client, auth, [item["id"]])
    with SessionLocal() as db:
        assert db.get(Question, qid).is_deleted is False


def test_students_and_their_links_come_back(client, auth):
    cid = next((c["id"] for c in client.get("/api/classes", headers=auth).json()
                if c["display"] == "九年级31班"), None) or client.post(
        "/api/classes", json={"grade": "九年级", "name": "31班"}, headers=auth).json()["id"]
    sid = client.post("/api/students", json={"student_no": "20269931", "name": "回收生",
                                             "class_id": cid}, headers=auth).json()["id"]
    with SessionLocal() as db:
        db.add(TypingRecord(student_id=sid, student_name="回收生", student_class="九年级31班",
                            module="中文", difficulty="简单", typed_chars=10, duration=60, speed=10, accuracy=100))
        db.commit()
    res = client.post("/api/students/bulk", json={"ids": [sid], "action": "delete"}, headers=auth)
    assert res.status_code == 200, res.text
    item = next(i for i in _items(client, auth, "student") if "回收生" in i["detail"])
    _restore(client, auth, [item["id"]])
    with SessionLocal() as db:
        st = db.get(Student, sid)
        assert st and st.class_id == cid
        assert db.query(TypingRecord).filter(TypingRecord.student_id == sid).count() == 1, \
            "打字成绩重新挂回这个学生名下"


def test_class_restore_reattaches_students(client, auth):
    cid = client.post("/api/classes", json={"grade": "九年级", "name": "32班"}, headers=auth).json()["id"]
    sid = client.post("/api/students", json={"student_no": "20269932", "name": "班里人",
                                             "class_id": cid}, headers=auth).json()["id"]
    assert client.delete(f"/api/classes/{cid}", params={"force": True}, headers=auth).status_code == 200
    with SessionLocal() as db:
        assert db.get(Student, sid).class_id is None
    item = next(i for i in _items(client, auth, "class") if "九年级32班" in i["title"])
    _restore(client, auth, [item["id"]])
    with SessionLocal() as db:
        assert db.get(Student, sid).class_id == cid


def _typing(db, n, cls, name="打字生"):
    for i in range(n):
        db.add(TypingRecord(student_name=f"{name}{i}", student_class=cls, module="中文",
                            difficulty="简单", typed_chars=10, duration=60, speed=10, accuracy=100))
    db.commit()


def test_filtered_typing_delete_then_restore(client, auth):
    """「删除筛选出的全部」：只删这个班的；先查 id 再按 id 删（MySQL 不认同表子查询删除）。"""
    with SessionLocal() as db:
        _typing(db, 3, "7，9")
        _typing(db, 2, "别的班")
    res = client.delete("/api/typing/records", params={"student_class": "7，9"}, headers=auth)
    assert res.status_code == 200, res.text
    assert res.json()["deleted"] == 3
    with SessionLocal() as db:
        assert db.query(TypingRecord).filter(TypingRecord.student_class == "别的班").count() == 2
        assert db.query(TypingRecord).filter(TypingRecord.student_class == "7，9").count() == 0
    item = next(i for i in _items(client, auth, "typing_record") if "7，9" in i["detail"])
    _restore(client, auth, [item["id"]])
    with SessionLocal() as db:
        assert db.query(TypingRecord).filter(TypingRecord.student_class == "7，9").count() == 3


def test_typing_clear_sql_has_no_self_subquery():
    """服务器上是 MySQL：生成的删除语句里不能有「同一张表的子查询」。"""
    from sqlalchemy.dialects import mysql
    from app.services import recycle

    class Fake:
        sqls = []

        def execute(self, stmt):
            self.sqls.append(str(stmt.compile(dialect=mysql.dialect())))

            class R:
                rowcount = 1
            return R()

    db = Fake()
    recycle.delete_ids(db, TypingRecord, [1, 2, 3])
    assert db.sqls and all("SELECT" not in s.upper() for s in db.sqls)


def test_teacher_only_sees_own_deletions(client, auth, teacher_auth):
    with SessionLocal() as db:
        _typing(db, 1, "仅管理员删的")
    client.delete("/api/typing/records", params={"student_class": "仅管理员删的"}, headers=auth)
    mine = _items(client, teacher_auth)
    assert all("仅管理员删的" not in i["detail"] and "仅管理员删的" not in i["title"] for i in mine)
    admin_item = next(i for i in _items(client, auth, "typing_record") if "仅管理员删的" in i["title"] + i["detail"])
    res = client.post("/api/recycle/restore", json={"ids": [admin_item["id"]]}, headers=teacher_auth)
    assert res.status_code == 404, "别人删的，老师看不到也还原不了"


def test_expired_items_are_purged(client, auth):
    with SessionLocal() as db:
        _typing(db, 1, "过期班")
    client.delete("/api/typing/records", params={"student_class": "过期班"}, headers=auth)
    with SessionLocal() as db:
        item = db.query(RecycleItem).filter(RecycleItem.detail.like("%过期班%")).one()
        item.expires_at = clock.now() - timedelta(minutes=1)
        db.commit()
        iid = item.id
    _items(client, auth)                      # 打开回收站顺手清理
    with SessionLocal() as db:
        assert db.get(RecycleItem, iid) is None


def test_destroy_now(client, auth):
    with SessionLocal() as db:
        _typing(db, 1, "马上彻底删")
    client.delete("/api/typing/records", params={"student_class": "马上彻底删"}, headers=auth)
    item = next(i for i in _items(client, auth, "typing_record") if "马上彻底删" in i["detail"])
    assert client.post("/api/recycle/destroy", json={"ids": [item["id"]]}, headers=auth).status_code == 200
    assert all(i["id"] != item["id"] for i in _items(client, auth))


# ---------------------------------------------------------------- 座次表
def test_seat_chart_upload_view_download(client, auth, teacher_auth):
    cid = client.post("/api/classes", json={"grade": "九年级", "name": "33班"}, headers=auth).json()["id"]
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    res = client.post(f"/api/classes/{cid}/seat", files={"file": ("机房座位.png", png, "image/png")},
                      headers=auth)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["seat_kind"] == "image" and body["seat_url"].startswith("/uploads/seats/")
    assert client.get(body["seat_url"]).content == png, "图片地址能直接打开"

    xlsx = b"PK\x03\x04" + b"x" * 30
    res = client.post(f"/api/classes/{cid}/seat",
                      files={"file": ("九33座次.xlsx", xlsx, "application/octet-stream")}, headers=auth)
    assert res.json()["seat_kind"] == "sheet" and res.json()["seat_name"] == "九33座次.xlsx"
    got = client.get(f"/api/classes/{cid}/seat/file", headers=auth)
    assert got.status_code == 200 and got.content == xlsx
    assert "filename*=UTF-8''" in got.headers["content-disposition"]

    bad = client.post(f"/api/classes/{cid}/seat", files={"file": ("a.exe", b"MZ", "x")}, headers=auth)
    assert bad.status_code == 400
    other = client.post(f"/api/classes/{cid}/seat", files={"file": ("a.png", png, "image/png")},
                        headers=teacher_auth)
    assert other.status_code == 403, "不是自己带的班，不能改座次表"
    assert client.delete(f"/api/classes/{cid}/seat", headers=auth).json()["seat_kind"] == ""
