# -*- coding: utf-8 -*-
"""整条链路：老师在网页后台发考试 → 学生开 exe → 真机操作 → 交卷 → 老师看成绩。

用的是真后端、真 HTTP、真文件操作，客户端这边调的就是 exe 里跑的那几个函数。
这条链路一旦坏掉，症状通常是**操作题全班 0 分**，而且不报错 —— 所以值得把每一
段都钉住。

最要紧的三条：
  · 学生只输考号就能找到自己的考试（`test_student_sees_only_own_exam`）
  · 真机操作能被服务器判出分（`test_full_run_is_graded_on_the_server`）
  · 补传只靠那个 .ans 就能完成（`test_retry_upload_needs_nothing_but_the_ans`）
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from client import api, package, snapshot, states, store
from conftest import EXAM_ROOT, call


# ================================================================ 学生那一半
def do_the_work(root: Path):
    """学生在真实文件系统里做题：新建、写内容、复制、删除。"""
    base = root / "win02"
    (base / "会徽" / "冬梦.txt").write_bytes("一起向未来".encode("gbk"))
    shutil.copy2(base / "素材" / "冬奥介绍.txt", base / "会徽" / "冬奥介绍.txt")
    (base / "待删除.tmp").unlink()


# ================================================================ 认人
def test_student_signs_in_with_just_a_number(server, exam):
    got = api.signin(server, "26090101", "桌面甲")
    assert got["student"]["name"] == "桌面甲"
    assert got["student"]["cls"], "班级要从教师端的库里带出来，考生不用自己填"


def test_student_sees_only_own_exam(server, exam):
    """**准入**：考试发给九年级1班，九年级2班的学生连口令都拿不到。"""
    mine = api.signin(server, "26090101")["exams"]
    assert any(e["id"] == exam["exam"]["id"] for e in mine)
    other = api.signin(server, "26090201")["exams"]
    assert all(e["id"] != exam["exam"]["id"] for e in other)


def test_wrong_name_is_refused(server, exam):
    with pytest.raises(api.ApiError) as err:
        api.signin(server, "26090101", "冒名顶替")
    assert "26090101" in str(err.value)


def test_unknown_number_says_so_in_chinese(server):
    """报错要能原样贴到学生屏幕上 —— 「HTTP 404」对考场没有任何帮助。"""
    with pytest.raises(api.ApiError) as err:
        api.signin(server, "00000000")
    assert "考号" in str(err.value)


def test_bad_address_does_not_hang(server):
    assert api.ping("http://127.0.0.1:9") is False
    assert api.ping("") is False


def test_address_without_scheme_still_works(server, exam):
    """监考老师多半只会输一个 IP 和端口。"""
    bare = server.replace("http://", "")
    assert api.ping(bare) is True


def test_an_https_address_is_left_alone(server):
    """部署到公网、挂了域名和证书的学校填的是 https://… —— **不能被改成 http**，
    否则永远连不上，而提示还是「连不上教师端」。"""
    assert api.norm("https://exam.xxx.edu.cn") == "https://exam.xxx.edu.cn"
    assert api.base("https://exam.xxx.edu.cn") == "https://exam.xxx.edu.cn"
    assert api.base("http://exam.xxx.edu.cn/") == "http://exam.xxx.edu.cn"
    # 不写协议的 IP 直接 http（4.14.1 起 norm 只整理、不加协议，协议由 base 选）
    assert api.norm("192.168.1.8:8080/") == "192.168.1.8:8080"
    assert api.base("192.168.1.8:8080/") == "http://192.168.1.8:8080"


# ================================================================ 取卷 + 开考
def test_fetched_package_carries_what_the_client_needs(server, exam, lab):
    e = next(x for x in api.signin(server, "26090101")["exams"]
             if x["id"] == exam["exam"]["id"])
    pack = package.ExamPackage(api.fetch_exam(server, e["token"], lab["out"] / "卷.ekb"))
    assert pack.token == e["token"]
    assert pack.server == server
    assert pack.logical_root == EXAM_ROOT, "少了前缀，操作题会全班判 0 分"
    assert pack.duration_min > 0 and len(pack.paper) > 0


def test_fetched_package_has_no_answers(server, exam, lab):
    raw = (api.fetch_exam(server, exam["exam"]["token"],
                          lab["out"] / "卷.ekb")).read_bytes()
    text = raw.decode("utf-8", "ignore")
    for bad in ('"answer"', '"checks"', '"assert"'):
        assert bad not in text, f"考试包里出现了 {bad}，检查点漏到学生机上了"


def test_deploy_lays_out_the_exam_folder(server, exam, lab):
    pack = package.ExamPackage(api.fetch_exam(server, exam["exam"]["token"],
                                              lab["out"] / "卷.ekb"))
    snapshot.clear_root(lab["root"], force=True)
    snapshot.mark_root(lab["root"])
    pack.deploy_files(lab["root"])
    assert (lab["root"] / "win02" / "素材" / "冬奥介绍.txt").exists()
    assert (lab["root"] / "win02" / "会徽").is_dir(), "空文件夹也得铺出来，否则学生没处新建"


# ================================================================ 交卷
def run_exam(server, exam, lab, student_no, student_name, work=do_the_work):
    """把一个考生从取卷跑到交卷，返回 (答案包路径, 上传结果)。"""
    pack = package.ExamPackage(api.fetch_exam(server, exam["exam"]["token"],
                                              lab["out"] / "卷.ekb"))
    snapshot.clear_root(lab["root"], force=True)
    snapshot.mark_root(lab["root"])
    pack.deploy_files(lab["root"])
    if work:
        work(lab["root"])

    shot = snapshot.snapshot(lab["root"])
    answers = {str(q["id"]): "A" for q in pack.paper if q["type"] == "选择题"}
    got = states.collect(pack.paper, lab["root"], pack.logical_root)
    student = {"no": student_no, "name": student_name, "cls": "九年级1班"}
    path = package.write_answer(lab["out"] / f"{student_no}-{student_name}", pack,
                                student, answers, shot, "2026-09-18 09:00:00",
                                "测试", got)
    return path, api.submit(server, pack.token, student,
                            states.payload(answers, got))


def test_full_run_is_graded_on_the_server(server, exam, lab):
    """**核心断言**：真机上做的操作，服务器按检查点判出满分，老师看得到每一问。"""
    _, (ok, msg, got) = run_exam(server, exam, lab, "26090101", "桌面甲")
    assert ok, msg
    assert got.get("score", 0) > 0

    subs = call(server, "GET", f"/api/exams/{exam['exam']['id']}/submissions",
                token=exam["token"])
    sub = next(s for s in subs if s["student_no"] == "26090101")
    detail = call(server, "GET",
                  f"/api/exams/{exam['exam']['id']}/submissions/{sub['id']}",
                  token=exam["token"])
    item = next(d for d in detail["detail"] if d["id"] == exam["qid"])
    assert item["auto"] is True
    assert item["check_passed"] == item["check_total"] == 4
    assert item["earned"] == exam["score"]


def test_undone_work_is_pointed_out_check_by_check(server, exam, lab):
    """没做完要**指出是哪一问没做**，不是只给个分数 —— 老师阅卷页靠这个。"""
    def half(root: Path):
        (root / "win02" / "会徽" / "冬梦.txt").write_bytes("写错了".encode("gbk"))

    _, (ok, _msg, _got) = run_exam(server, exam, lab, "26090102", "桌面丙", half)
    assert ok

    subs = call(server, "GET", f"/api/exams/{exam['exam']['id']}/submissions",
                token=exam["token"])
    sub = next(s for s in subs if s["student_no"] == "26090102")
    detail = call(server, "GET",
                  f"/api/exams/{exam['exam']['id']}/submissions/{sub['id']}",
                  token=exam["token"])
    item = next(d for d in detail["detail"] if d["id"] == exam["qid"])
    assert 0 < item["check_passed"] < item["check_total"]
    bad = [c for c in item["checks"] if not c["ok"]]
    assert bad and all(c["desc"] and c["why"] for c in bad), "每一条没过的都要说清是哪一步"


def test_missing_prefix_wrecks_the_score(server, exam, lab):
    """路径前缀掉了，操作题就废了 —— 出问题时第一个查它。

    这条不是在测后端，是**把这个坑钉在测试里**：它是这条链路最容易悄悄坏掉的
    地方，坏了之后日志里什么都看不出来。

    注意症状不是"整整 0 分"而是**接近 0**：`missing`（"把某文件删掉了"）这类
    反向检查点，在服务器眼里"哪个路径都找不到"恰好就是通过。所以别拿"分数是不是
    正好 0"当判据，要看**通过的检查点是不是只剩反向的那几条**。
    """
    pack = package.ExamPackage(api.fetch_exam(server, exam["exam"]["token"],
                                              lab["out"] / "卷.ekb"))
    snapshot.clear_root(lab["root"], force=True)
    snapshot.mark_root(lab["root"])
    pack.deploy_files(lab["root"])
    do_the_work(lab["root"])
    shot = snapshot.snapshot(lab["root"])

    got = states.collect(pack.paper, lab["root"], "")      # 忘了前缀
    payload = states.payload({}, got)
    ok, _msg, _got = api.submit(server, pack.token,
                                {"no": "26090103", "name": "桌面丁", "cls": "九年级1班"},
                                payload)
    assert ok

    subs = call(server, "GET", f"/api/exams/{exam['exam']['id']}/submissions",
                token=exam["token"])
    sub = next(s for s in subs if s["student_no"] == "26090103")
    detail = call(server, "GET",
                  f"/api/exams/{exam['exam']['id']}/submissions/{sub['id']}",
                  token=exam["token"])
    item = next(d for d in detail["detail"] if d["id"] == exam["qid"])
    passed = [c["desc"] for c in item["checks"] if c["ok"]]
    assert passed == ["删除「待删除.tmp」"], f"只该剩反向检查点空过，实际通过了 {passed}"


def test_same_number_cannot_submit_twice(server, exam, lab):
    run_exam(server, exam, lab, "26090104", "桌面戊")
    _, (ok, msg, _) = run_exam(server, exam, lab, "26090104", "桌面戊")
    assert not ok and "交过卷" in msg


def test_submitted_exam_is_greyed_out_next_time(server, exam, lab):
    """交过的考试下次登录要标出来，别让学生白考一场才被挡回来。"""
    run_exam(server, exam, lab, "26090105", "桌面己")
    mine = next(e for e in api.signin(server, "26090105")["exams"]
                if e["id"] == exam["exam"]["id"])
    assert mine["submitted"] is True and mine["can_take"] is False


# ================================================================ 断网与补传
def test_offline_submit_keeps_the_paper(server, exam, lab):
    """服务器不在也不能丢卷：本地那份 .ans 先写，上传失败只是失败。"""
    pack = package.ExamPackage(api.fetch_exam(server, exam["exam"]["token"],
                                              lab["out"] / "卷.ekb"))
    snapshot.clear_root(lab["root"], force=True)
    snapshot.mark_root(lab["root"])
    pack.deploy_files(lab["root"])
    do_the_work(lab["root"])
    shot = snapshot.snapshot(lab["root"])
    got = states.collect(pack.paper, lab["root"], pack.logical_root)
    student = {"no": "26090106", "name": "桌面庚", "cls": "九年级1班"}
    path = package.write_answer(lab["out"] / "26090106-桌面庚", pack, student, {},
                                shot, "", "测试", got)

    ok, msg, _ = api.submit("http://127.0.0.1:9", pack.token, student,
                            states.payload({}, got))
    assert not ok and "连不上" in msg
    assert path.exists(), "上传失败了，本地那份必须还在"
    store.mark_uploaded(lab["out"], path.name, False, msg)
    assert path in store.pending_uploads(lab["out"])


def test_retry_upload_needs_nothing_but_the_ans(server, exam, lab):
    """**补传只看那个 .ans**：程序重开过、换了台机器也能补。

    所以口令、路径前缀、哪几道题要塞快照，全部写在答案包里。第一版漏了这三样，
    "重开程序补传"这条路根本走不通。
    """
    pack = package.ExamPackage(api.fetch_exam(server, exam["exam"]["token"],
                                              lab["out"] / "卷.ekb"))
    snapshot.clear_root(lab["root"], force=True)
    snapshot.mark_root(lab["root"])
    pack.deploy_files(lab["root"])
    do_the_work(lab["root"])
    shot = snapshot.snapshot(lab["root"])
    student = {"no": "26090107", "name": "桌面辛", "cls": "九年级1班"}
    path = package.write_answer(lab["out"] / "26090107-桌面辛", pack, student, {},
                                shot, "", "测试",
                                states.collect(pack.paper, lab["root"], pack.logical_root))

    # 从这里开始只有 path，别的什么都不知道 —— 就像第二天开机点「补传」
    answer, _shot = package.read_answer(path)
    ok, _msg, back = api.submit(server, answer["token"], answer["student"],
                                states.payload(answer["answers"], answer["states"]))
    assert ok and back.get("score", 0) > 0
