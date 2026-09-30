"""阅卷按班：老师只批自己带的班，别的班的答卷看得到、批不了（2.12.1）。

甲老师带七年级1班，乙老师带七年级2班（conftest 里建的）；管理员不受限。
考试是管理员发的全校统考 —— 两位老师都看得到，这正是要按班分开批的场景。
"""

import json

import pytest
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Exam, ExamSubmission, Paper, PaperItem, Question, SimTask, Student, User
from app.services import drag

FLOW = next(e for e in drag.BANK if e["key"] == "Q322-话费")
# 只放对一个热区：部分通过，系统按比例预填，等老师复核 —— 正是要人来批的答卷
HALF = {"placed": {}}
for c in FLOW["checks"]:
    if c["assert"]["op"] == "slot":
        HALF["placed"][c["assert"]["slot"]] = [c["assert"]["is"][0]]
        break


@pytest.fixture(scope="module")
def exam(client, auth, teacher_auth, teacher2_auth):
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.role == "admin"))
        task = SimTask(kind="drag", title="话费流程图", env_json=json.dumps(FLOW["env"], ensure_ascii=False),
                       checks_json=json.dumps(FLOW["checks"], ensure_ascii=False))
        op = Question(type="操作题", stem="按班阅卷测试：补全话费流程图", stem_hash="grade-scope-op".ljust(64, "0"),
                      answer="", scope="Python编程基础", source="测试", sim_task=task)
        db.add(op)
        db.flush()
        paper = Paper(title="按班阅卷样卷", school="测试中学", duration="40", created_by=admin.id)
        paper.items = [PaperItem(question_id=op.id, order_no=0, section="操作题", score=20)]
        db.add(paper)
        db.flush()
        ex = Exam(paper_id=paper.id, title="按班阅卷考试", token="grade-scope-token", created_by=admin.id)
        db.add(ex)
        db.commit()
        exam_id, op_id = ex.id, op.id
    finally:
        db.close()

    subs = {}
    for name, cls, no in (("一班甲", "七年级1班", "G001"), ("二班乙", "七年级2班", "G002")):
        res = client.post("/api/take/grade-scope-token/submit", json={
            "student_name": name, "student_class": cls, "student_no": no,
            "answers": {str(op_id): json.dumps({"state": HALF})}})
        assert res.status_code == 200, res.text
    for row in client.get(f"/api/exams/{exam_id}/submissions", headers=auth).json():
        subs[row["student_class"]] = row["id"]
    return {"id": exam_id, "op": str(op_id), "subs": subs}


def _grade(client, headers, exam, cls, score=15):
    return client.patch(f"/api/exams/{exam['id']}/submissions/{exam['subs'][cls]}/manual",
                        json={"scores": {exam["op"]: score}}, headers=headers)


def test_成绩表标出批不批得了(client, teacher_auth, exam):
    rows = {r["student_class"]: r for r in
            client.get(f"/api/exams/{exam['id']}/submissions", headers=teacher_auth).json()}
    assert rows["七年级1班"]["can_grade"] is True
    assert rows["七年级2班"]["can_grade"] is False, "别的班的也列出来（能看），只是批不了"


def test_只能批自己班的(client, teacher_auth, teacher2_auth, exam):
    res = _grade(client, teacher_auth, exam, "七年级2班")
    assert res.status_code == 403 and "不是你带的班，只能查看" in res.json()["detail"]
    assert _grade(client, teacher_auth, exam, "七年级1班").status_code == 200
    assert _grade(client, teacher2_auth, exam, "七年级2班").status_code == 200
    assert _grade(client, teacher2_auth, exam, "七年级1班").status_code == 403


def test_别的班的答卷照样能看(client, teacher_auth, exam):
    res = client.get(f"/api/exams/{exam['id']}/submissions/{exam['subs']['七年级2班']}", headers=teacher_auth)
    assert res.status_code == 200 and res.json()["can_grade"] is False
    mine = client.get(f"/api/exams/{exam['id']}/submissions/{exam['subs']['七年级1班']}", headers=teacher_auth)
    assert mine.json()["can_grade"] is True


def test_管理员哪个班都能批(client, auth, exam):
    for cls in ("七年级1班", "七年级2班"):
        assert _grade(client, auth, exam, cls, 20).status_code == 200


def test_学生调了班_按他现在的班算(client, auth, teacher_auth, exam):
    """答卷上记的班级名是交卷时的；挂着账号的，学生现在在谁的班就归谁批。"""
    db = SessionLocal()
    try:
        cls_id = next(c["id"] for c in client.get("/api/classes", params={"mine": True},
                                                  headers=teacher_auth).json())
        st = Student(student_no="G099", name="转来的", class_id=cls_id, student_class="七年级1班",
                     password_hash="x")
        db.add(st)
        db.flush()
        sub = db.get(ExamSubmission, exam["subs"]["七年级2班"])
        sub.student_id = st.id
        db.commit()
    finally:
        db.close()
    assert _grade(client, teacher_auth, exam, "七年级2班").status_code == 200
