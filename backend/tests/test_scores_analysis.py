"""2.10.0：操作题自动定分、成绩页（删答卷、样卷）、成绩分析、系统时钟校正。

考试直接在库里搭（两道选择题 + 一道挂了仿真任务的流程图拖拽题），交卷走真的
/api/take/{口令}/submit —— 判分、落库、成绩页、分析页都是真的那条路。
"""

import json
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import clock
from app.database import SessionLocal
from app.models import (AppMeta, Base, ChangelogEntry, Exam, ExamSubmission, Option, Paper,
                        PaperItem, Question, SchoolClass, SimTask, User)
from app.services import drag
from app.services.analysis import analyze
from app.services.exam import apply_manual, settle_auto, settle_submission
from app.siteconfig import site

FLOW = next(e for e in drag.BANK if e["key"] == "Q322-话费")    # 两个热区：A、B


def _perfect(checks):
    placed = {}
    for c in checks:
        a = c["assert"]
        if a["op"] == "slot":
            placed[a["slot"]] = [a["is"][0]]
    return {"placed": placed}


RIGHT = _perfect(FLOW["checks"])
WRONG = {"placed": {s: ["i9"] for s in RIGHT["placed"]}}          # 两个热区都放错
HALF = {"placed": dict(list(RIGHT["placed"].items())[:1])}        # 只放对了一个


@pytest.fixture(scope="module")
def scored_exam(client, auth):
    """管理员发的一场考试，四个人交卷：全对 / 操作题全错 / 操作题对一半 / 白卷。"""
    db = SessionLocal()
    try:
        admin = db.scalar(select(User).where(User.role == "admin"))
        qs = []
        for i, ans in enumerate(("A", "B")):
            q = Question(type="选择题", stem=f"成绩分析测试选择题{i}", stem_hash=f"analysis-choice-{i}".ljust(64, "0"),
                         answer=ans, scope="信息技术基础", source="测试")
            q.options = [Option(label=l, content=f"选项{l}") for l in "ABCD"]
            qs.append(q)
        task = SimTask(kind="drag", title="话费流程图", env_json=json.dumps(FLOW["env"], ensure_ascii=False),
                       checks_json=json.dumps(FLOW["checks"], ensure_ascii=False))
        op = Question(type="操作题", stem="成绩分析测试：补全话费流程图", stem_hash="analysis-op".ljust(64, "0"),
                      answer="", scope="Python编程基础", source="测试", sim_task=task)
        qs.append(op)
        db.add_all(qs)
        db.flush()
        paper = Paper(title="成绩分析样卷", school="测试中学", duration="40", created_by=admin.id)
        paper.items = [PaperItem(question_id=q.id, order_no=i, section=q.type, score=(10 if q.type == "选择题" else 20))
                       for i, q in enumerate(qs)]
        db.add(paper)
        db.flush()
        exam = Exam(paper_id=paper.id, title="成绩分析考试", token="analysis-token-001", created_by=admin.id)
        db.add(exam)
        db.commit()
        exam_id, token = exam.id, exam.token
        choice_ids = [qs[0].id, qs[1].id]
        op_id = op.id
    finally:
        db.close()

    def submit(name, cls, no, choices, state):
        answers = {str(choice_ids[0]): choices[0], str(choice_ids[1]): choices[1]}
        answers[str(op_id)] = json.dumps({"state": state}) if state is not None else ""
        res = client.post(f"/api/take/{token}/submit", json={
            "student_name": name, "student_class": cls, "student_no": no, "answers": answers})
        assert res.status_code == 200, res.text

    submit("全对", "七年级1班", "A001", ("A", "B"), RIGHT)       # 40
    submit("操作错", "七年级1班", "A002", ("A", "C"), WRONG)     # 10
    submit("对一半", "七年级2班", "B001", ("A", "B"), HALF)      # 20 + 10 = 30，操作题待复核
    submit("白卷", "七年级2班", "B002", ("", ""), None)         # 0
    subs = {s["student_no"]: s for s in client.get(f"/api/exams/{exam_id}/submissions", headers=auth).json()}
    return {"id": exam_id, "token": token, "subs": subs, "op_id": op_id}


# ================================================================ 自动定分
def test_检查点全过给满分全没过给0分_都不用老师再点(scored_exam, client, auth):
    subs = scored_exam["subs"]
    assert subs["A001"]["score"] == 40 and subs["A001"]["pending_manual"] == 0
    assert subs["A002"]["score"] == 10 and subs["A002"]["pending_manual"] == 0
    assert subs["B002"]["score"] == 0 and subs["B002"]["pending_manual"] == 0, "白卷：检查点全没过，0 分定了"
    # 部分通过：按比例预填 10 分，但要老师复核
    assert subs["B001"]["score"] == 30 and subs["B001"]["pending_manual"] == 1

    exam = client.get(f"/api/exams/{scored_exam['id']}", headers=auth).json()
    assert exam["ungraded_count"] == 1, "考试列表上的「待阅」只剩对一半的那一份"

    d = client.get(f"/api/exams/{scored_exam['id']}/submissions/{subs['A001']['id']}", headers=auth).json()
    op = next(x for x in d["detail"] if x["id"] == scored_exam["op_id"])
    assert op["graded"] and op["auto_graded"] and op["earned"] == 20
    assert "全部通过" in op["reason"]


def test_老师给过的分_系统不再动():
    d = {"id": 1, "manual": True, "auto": True, "score": 20, "earned": 10,
         "check_passed": 1, "check_total": 2}
    assert settle_auto(d) is False and not d.get("graded"), "部分通过留给老师"
    got = apply_manual([d], {"1": 15})
    assert d["earned"] == 15 and d["graded"] and d["auto_graded"] is False
    d["check_passed"] = 2                   # 就算后来"全过"了
    assert settle_auto(d) is False and d["earned"] == 15, "老师的判断优先"
    assert got["pending"] == 0


def test_老师保存时没带自动定好的分_不会被清零():
    auto = {"id": 1, "manual": True, "auto": True, "score": 20, "earned": 20,
            "check_passed": 2, "check_total": 2}
    settle_auto(auto)
    other = {"id": 2, "manual": True, "score": 10, "earned": 0}
    got = apply_manual([auto, other], {"2": 7})
    assert auto["earned"] == 20 and auto["graded"]
    assert got["subjective_score"] == 27 and got["pending"] == 0


def test_老答卷补一遍_只标评完_分数不变():
    detail = [{"id": 1, "manual": True, "auto": True, "score": 20, "earned": 20,
               "check_passed": 3, "check_total": 3, "reason": "仿真题自动判分，老师可复核"},
              {"id": 2, "manual": True, "auto": True, "score": 10, "earned": 0,
               "check_passed": 0, "check_total": 2}]
    sub = ExamSubmission(detail_json=json.dumps(detail), manual_json="{}", score=20,
                         subjective_score=20, subjective_total=30, graded_at=None)
    assert settle_submission(sub) is True
    assert sub.score == 20 and sub.graded_at is not None
    assert json.loads(sub.manual_json) == {"1": 20, "2": 0}
    assert settle_submission(sub) is False, "只补一次"


# ================================================================ 成绩页
def test_样卷带答案_按大题分组(scored_exam, client, auth):
    p = client.get(f"/api/exams/{scored_exam['id']}/paper", headers=auth).json()
    assert p["full_score"] == 40 and [g["name"] for g in p["groups"]] == ["选择题", "操作题"]
    first = p["groups"][0]["items"][0]
    assert first["answer"] == "A" and len(first["options"]) == 4 and first["no"] == 1
    op = p["groups"][1]["items"][0]
    assert op["sim_kind"] == "drag" and op["checks"], "操作题列出检查点，老师知道判的是什么"


def test_样卷只给老师(scored_exam, client):
    assert client.get(f"/api/exams/{scored_exam['id']}/paper").status_code == 401


# ================================================================ 成绩分析
def test_全体_各项指标(scored_exam, client, auth):
    r = client.get(f"/api/exams/{scored_exam['id']}/analysis", headers=auth).json()
    s = r["summary"]
    assert s["count"] == 4 and s["full"] == 40 and s["avg"] == 20.0 and s["median"] == 20.0
    assert s["max"] == 40 and s["min"] == 0 and s["pass_rate"] == 50.0 and s["pending"] == 1
    assert [c["name"] for c in r["classes"]] == ["七年级1班", "七年级2班"]
    assert [x["no"] for x in r["ranking"]] == ["A001", "B001", "A002", "B002"]
    assert r["ranking"][0]["rank"] == 1
    op = r["operations"][0]
    assert len(op["checks"]) == 2 and all(0 <= c["pass_rate"] <= 100 for c in op["checks"])
    assert sum(b["count"] for b in r["bands"]) == 4
    assert r["options"]["classes"] == ["七年级1班", "七年级2班"] and len(r["options"]["students"]) == 4
    text = "".join(r["conclusions"])
    assert "平均分 20.0/40" in text and "等老师复核" in text


def test_按班看(scored_exam, client, auth):
    r = client.get(f"/api/exams/{scored_exam['id']}/analysis", params={"classes": "七年级2班"},
                   headers=auth).json()
    assert r["scope"]["kind"] == "classes" and r["summary"]["count"] == 2
    assert {x["no"] for x in r["ranking"]} == {"B001", "B002"}
    assert r["ranking"][0]["rank"] == 2, "名次是在全场里排的"


def test_学生之间比(scored_exam, client, auth):
    ids = f"{scored_exam['subs']['A001']['id']},{scored_exam['subs']['B001']['id']}"
    r = client.get(f"/api/exams/{scored_exam['id']}/analysis", params={"students": ids},
                   headers=auth).json()
    assert r["scope"]["kind"] == "students" and len(r["compare"]) == 2
    assert {c["rank"] for c in r["compare"]} == {1, 2}
    assert any("两人差距最大" in x for x in r["conclusions"])


def test_分析的数跟着阅卷变(scored_exam, client, auth):
    sid = scored_exam["subs"]["B001"]["id"]
    client.patch(f"/api/exams/{scored_exam['id']}/submissions/{sid}/manual",
                 json={"scores": {str(scored_exam["op_id"]): 20}}, headers=auth)
    r = client.get(f"/api/exams/{scored_exam['id']}/analysis", headers=auth).json()
    assert r["summary"]["pending"] == 0 and r["summary"]["avg"] == 22.5


def test_没人交卷也不出错():
    r = analyze([{"id": 1, "type": "选择题", "score": 10, "stem": "x"}], [], 60)
    assert r["summary"]["count"] == 0 and r["conclusions"]


# ================================================================ 删答卷（放在最后：会删数据）
def test_删答卷要改得动这场考试(scored_exam, client, teacher_auth):
    sid = scored_exam["subs"]["B002"]["id"]
    res = client.delete(f"/api/exams/{scored_exam['id']}/submissions/{sid}", headers=teacher_auth)
    assert res.status_code == 403, "管理员发的考试，任课老师能看能批，不能删"


def test_删一份_批量删(scored_exam, client, auth):
    subs = scored_exam["subs"]
    res = client.delete(f"/api/exams/{scored_exam['id']}/submissions/{subs['B002']['id']}", headers=auth)
    assert res.status_code == 200
    res = client.post(f"/api/exams/{scored_exam['id']}/submissions/delete",
                      json={"ids": [subs["A002"]["id"], subs["B001"]["id"], 999999]}, headers=auth)
    assert res.json()["deleted"] == 2, "不是这场考试的 id 不认"
    left = client.get(f"/api/exams/{scored_exam['id']}/submissions", headers=auth).json()
    assert [s["student_no"] for s in left] == ["A001"]
    # 删掉的学生能重新交卷
    res = client.post(f"/api/take/{scored_exam['token']}/submit", json={
        "student_name": "白卷", "student_class": "七年级2班", "student_no": "B002", "answers": {}})
    assert res.status_code == 200


# ================================================================ 系统时钟
def test_时钟校正(monkeypatch):
    monkeypatch.setattr(site.time, "offset_hours", -8)
    got = clock.now()
    assert abs((got - (datetime.now() - timedelta(hours=8))).total_seconds()) < 5
    assert got.microsecond == 0


def test_校正值改了_已有记录的时间一起挪_只挪一次(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + (tmp_path / "c.db").as_posix())
    Base.metadata.create_all(engine)
    t0 = datetime(2026, 9, 24, 18, 0, 0)
    with Session(engine) as db:
        db.add(SchoolClass(grade="七年级", name="1班", created_at=t0))
        db.add(ChangelogEntry(version="9.9.9", released_on=date(2026, 9, 24), change_type="Fixed",
                              content="x", created_at=t0))
        db.commit()
        monkeypatch.setattr(site.time, "offset_hours", 0)
        assert clock.rebase(db) == 0, "第一次、校正值是 0：只记一笔，不挪"
        monkeypatch.setattr(site.time, "offset_hours", -8)
        assert clock.rebase(db) == -8
        assert db.scalar(select(SchoolClass.created_at)) == t0 - timedelta(hours=8)
        assert db.scalar(select(ChangelogEntry.released_on)) == date(2026, 9, 24), "日期列不动"
        assert clock.rebase(db) == 0, "没改就不再挪"
        monkeypatch.setattr(site.time, "offset_hours", -7)
        assert clock.rebase(db) == 1
        assert db.scalar(select(SchoolClass.created_at)) == t0 - timedelta(hours=7)
        assert db.get(AppMeta, clock.KEY).value == "-7.0"
    engine.dispose()


def test_时钟状态不跟着数据导出导入():
    from tools import export_data, import_data
    assert "app_meta" in export_data.SKIP_TABLES and "app_meta" in import_data.SKIP_TABLES
