"""操作题在**数据库里没有仿真任务**时，照样铺文件、照样自动判分。

## 为什么这条最重要

老师从 2.8.0 导出数据、导进新版本的库 —— `sim_task_id` 全是空。要是只认库里
配好的那份仿真任务，所有操作题一夜之间变成"不能自动判分"，而且**表面上看不出
毛病**：题目照出、考试照发，学生打开一看是个空壳，考完才发现全是 0 分。

题干是跟着题目走的，导库不会丢。所以逻辑以题干为准 —— 这组测试就是钉住
"换个库、换个版本，操作题的行为不变"。

## 题干照抄自题库

这三道就是学生截图里报上来的那三道（Windows / WPS 文字 / AI 工具）。
"""

import io
import json
import zipfile

import pytest

WIN = """本题工作目录:D:\\EXAM\\windows操作
请打开本题工作目录下的系统基本操作文件夹，按要求完成以下操作:
①在"IT"文件夹下创建"计算机技术.docx"文件。
②将"IT"文件夹下的文件"遥感.txt"和"红外.txt"移动到"传感技术"文件夹中。"""

WPS = """本题工作目录:D:\\EXAM\\WPS文字
请打开本题工作目录中的"A工具知多少.docx"，请完成以下操作:
①将文档中所有的"Deepsek"替换成"DeepSeek"。
②将文档中的标题设置为黑体、小二号、居中对齐。
③在文章最后输入一段新的文字:"即时AI：即时AI是即时下的AI设计工具。"。"""

AI = """本题工作目录:D:\\EXAM\\生成式人工智能
请使用给定的AI工具完成以下操作:
①请对"半壕春水一城花"这句诗，生成一段鉴赏文本
②请为"超然台"，生成一幅宣传画。
③请为苏轼的《望江南·超然台作》，生成一幅国风图片。"""


@pytest.fixture(scope="module")
def bare_exam(client, auth):
    """一场考试，三道操作题**都不挂仿真任务** —— 就像刚从旧库导进来那样。"""
    # **必出题是全局状态**：同一个知识范围只有一个槽位，别的测试文件留下的必出题
    # 会把这三道挤掉（症状是「没进卷子」）。开跑前先清干净。
    for old in client.get("/api/questions?pinned=true&page_size=200",
                          headers=auth).json()["items"]:
        client.put(f"/api/questions/{old['id']}", json={"is_pinned": False},
                   headers=auth)

    made = {}
    for scope, text in (("Windows系统操作", WIN), ("WPS文字操作", WPS),
                        ("人工智能", AI)):
        q = client.post("/api/questions", json={
            "type": "操作题", "stem": text, "answer": "略", "scope": scope,
            "is_pinned": True, "options": []}, headers=auth).json()
        assert not q.get("sim_task_id"), "这组测试的前提就是没有仿真任务"
        made[scope] = q

    paper = client.post("/api/papers/generate", json={
        "title": "导库之后的测验", "by_sections": True, "use_pinned": True,
        "save": True}, headers=auth)
    assert paper.status_code == 200, paper.text
    paper = paper.json()
    for scope, q in made.items():
        assert any(x["id"] == q["id"] for x in paper["questions"]), f"{scope} 没进卷子"
        client.put(f"/api/questions/{q['id']}", json={"is_pinned": False}, headers=auth)

    exam = client.post("/api/exams", json={"paper_id": paper["paper_id"],
                                           "show_score": True}, headers=auth).json()
    yield {"exam": exam, "qid": {k: v["id"] for k, v in made.items()}}
    for q in made.values():
        client.delete(f"/api/questions/{q['id']}", headers=auth)


def paper_of(client, auth, bare_exam) -> list:
    raw = client.get(f"/api/desk/export/{bare_exam['exam']['id']}", headers=auth).content
    z = zipfile.ZipFile(io.BytesIO(raw))
    return json.loads(z.read("paper.json")), z


# ================================================================ 出包
def test_questions_get_a_simulation_even_without_a_sim_task(client, auth, bare_exam):
    """**核心**：库里没配，照样认得出是哪一类，学生端才不会显示成"不能作答"。"""
    paper, _z = paper_of(client, auth, bare_exam)
    by_id = {str(q["id"]): q for q in paper}
    kinds = {}
    for scope, qid in bare_exam["qid"].items():
        row = by_id[str(qid)]
        assert row.get("sim"), f"{scope} 没有 sim，学生端只能显示「由老师评阅」"
        assert not row["sim"].get("manual"), f"{scope} 还挂着人工评阅"
        kinds[scope] = row["sim"]["kind"]
    assert kinds == {"Windows系统操作": "win", "WPS文字操作": "wps", "人工智能": "ai"}


def test_the_windows_question_ships_its_files(client, auth, bare_exam):
    """考场里得真有文件可操作，不能是个空文件夹。"""
    paper, z = paper_of(client, auth, bare_exam)
    names = [n for n in z.namelist() if n.startswith("files/")]
    assert any("遥感.txt" in n for n in names), names
    assert any("红外.txt" in n for n in names), names
    assert any(n.rstrip("/").endswith("传感技术") for n in names), "目标文件夹没铺出来"


def test_the_wps_question_ships_a_real_docx(client, auth, bare_exam):
    """WPS 题要有一个真文档，而且**要替换的词得在正文里**，否则没法做。"""
    paper, z = paper_of(client, auth, bare_exam)
    docs = [n for n in z.namelist() if n.endswith(".docx")]
    assert docs, "没铺出 .docx，学生打开是空的"
    blob = z.read(docs[0])
    assert blob[:2] == b"PK", "不是真的 docx"

    # docx 本身是个压缩包，正文要解出来看 —— 直接在裸字节里搜是搜不到的
    inner = zipfile.ZipFile(io.BytesIO(blob))
    body = inner.read("word/document.xml").decode("utf-8")
    assert "Deepsek" in body, "文档里没有要替换的词，这一问没法做"


def test_the_package_still_has_no_answers(client, auth, bare_exam):
    """兜底出来的检查点**一样不能发给学生**。"""
    raw = client.get(f"/api/desk/export/{bare_exam['exam']['id']}", headers=auth).content
    text = raw.decode("utf-8", "ignore")
    for bad in ('"checks"', '"assert"', '"sim_checks"'):
        assert bad not in text, f"考试包里出现了 {bad}"


# ================================================================ 判分
def submit(client, bare_exam, no, answers):
    return client.post(f"/api/take/{bare_exam['exam']['token']}/submit",
                       json={"student_name": "导库同学", "student_class": "九年级1班",
                             "student_no": no, "answers": answers})


def detail_of(client, auth, bare_exam, no) -> dict:
    eid = bare_exam["exam"]["id"]
    subs = client.get(f"/api/exams/{eid}/submissions", headers=auth).json()
    sub = next(s for s in subs if s["student_no"] == no)
    got = client.get(f"/api/exams/{eid}/submissions/{sub['id']}", headers=auth).json()
    by_id = {d["id"]: d for d in got["detail"]}
    return {scope: by_id[qid] for scope, qid in bare_exam["qid"].items()}


def test_a_correct_run_is_auto_graded(client, auth, bare_exam):
    """**交卷即出分** —— 三道题都不用老师动手。"""
    root = "C:/EXAM/系统基本操作"
    fs = {f"{root}/IT": {"type": "dir"},
          f"{root}/IT/计算机技术.docx": {"type": "file"},
          f"{root}/传感技术": {"type": "dir"},
          f"{root}/传感技术/遥感.txt": {"type": "file"},
          f"{root}/传感技术/红外.txt": {"type": "file"}}
    answers = {
        str(bare_exam["qid"]["Windows系统操作"]):
            json.dumps({"state": {"fs": fs, "recycle": {}}}, ensure_ascii=False),
        str(bare_exam["qid"]["人工智能"]): json.dumps({"state": {"messages": [
            {"role": "user", "text": "请对半壕春水一城花这句诗生成一段鉴赏文本，"
                                     "再为超然台生成一幅宣传画，"
                                     "为望江南超然台作生成一幅国风图片"}]}},
            ensure_ascii=False),
    }
    res = submit(client, bare_exam, "26991101", answers)
    assert res.status_code == 200, res.text

    got = detail_of(client, auth, bare_exam, "26991101")
    win = got["Windows系统操作"]
    assert win["auto"] is True and win["check_passed"] == win["check_total"], win["checks"]
    ai = got["人工智能"]
    assert ai["auto"] is True and ai["earned"] > 0, ai["checks"]


def test_a_wrong_run_says_which_step_failed(client, auth, bare_exam):
    """判错了要指出是哪一问 —— 老师阅卷页和学生申诉都靠这个。"""
    root = "C:/EXAM/系统基本操作"
    answers = {str(bare_exam["qid"]["Windows系统操作"]): json.dumps(
        {"state": {"fs": {f"{root}/IT": {"type": "dir"}}, "recycle": {}}})}
    submit(client, bare_exam, "26991102", answers)

    win = detail_of(client, auth, bare_exam, "26991102")["Windows系统操作"]
    assert win["check_passed"] < win["check_total"]
    bad = [c for c in win["checks"] if not c["ok"]]
    assert bad and all(c["desc"] and c["why"] for c in bad)


def test_a_hand_made_sim_task_still_wins(client, auth):
    """老师手工配过的仍然优先 —— 他调过的比机器按题干推的准。

    兜底只在"库里什么都没有"时才接管，不能反过来把老师的配置盖掉。
    """
    task = client.post("/api/sims", json={
        "kind": "win", "title": "老师手配的",
        "env": {"fs": {"C:/EXAM/手配": {"type": "dir"}}, "recycle": {}},
        "checks": [{"desc": "只有这一条", "score": 9,
                    "assert": {"op": "exists", "path": "C:/EXAM/手配/答案"}}],
    }, headers=auth).json()
    # 题干要和上面那道不一样，否则会被题库的查重拦下来
    q = client.post("/api/questions", json={
        "type": "操作题", "stem": WIN.replace("IT", "IT部门"), "answer": "略",
        "scope": "Windows系统操作", "sim_task_id": task["id"], "options": []},
        headers=auth)
    assert q.status_code == 200, q.text
    q = q.json()

    from app.database import SessionLocal
    from app.models import PaperItem, Question
    from app.services.exam import _item_from_row

    db = SessionLocal()
    row = db.get(Question, q["id"])
    item = _item_from_row(PaperItem(snapshot_json=None, section="", score=9), row)
    assert [c["desc"] for c in item["sim_checks"]] == ["只有这一条"]
    assert "C:/EXAM/手配" in json.dumps(item["sim"], ensure_ascii=False)
    client.delete(f"/api/questions/{q['id']}", headers=auth)
