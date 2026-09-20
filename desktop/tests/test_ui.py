# -*- coding: utf-8 -*-
"""界面自检：把窗口真建出来，每一屏都走一遍。

上一个项目吃过亏：编译过、测试过，组件却因为一个初始化顺序问题一加载就崩 ——
**"能 import"证明不了界面能用**。所以这里真的 `Tk()`、真的点按钮，只是不显示窗口。

同一个进程里只用一个 Tk 根窗口：开第二个会让 Tcl 被踩坏，报错里的文件名每次
还不一样。
"""

from __future__ import annotations

import gc
import time
import tkinter as tk
from tkinter import messagebox

import pytest

from client import api, exam_ui, store, ui

from test_flow import do_the_work


@pytest.fixture(autouse=True)
def no_dialogs(monkeypatch):
    """界面里会弹「接着考吗」「确定交卷吗」，自检里一律当成"是"。"""
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: None)
    monkeypatch.setattr(messagebox, "showwarning", lambda *a, **k: None)
    monkeypatch.setattr(messagebox, "showerror", lambda *a, **k: None)


@pytest.fixture(scope="session")
def tk_root():
    """**整场自检就这一个根窗口。**

    一个进程里反复 `Tk()` / `destroy()`，同时后台还跑着 uvicorn 线程，Tcl 会被
    踩坏 —— 症状是 "couldn't read file scrlbar.tcl" 这种莫名其妙的报错。
    """
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture(autouse=True, scope="session")
def gc_on_main_thread():
    """自动回收关掉，改成每个用例结束时在主线程手动收。

    Tk 的 StringVar 被回收时会回调 Tcl。自动 GC 是"谁分配得多就在谁那儿触发"，
    这里分配得最多的是跑后端的那个线程 —— 于是 Tcl 在非主线程被调用，轻则一堆
    "main thread is not in main loop"，重则直接崩。
    """
    gc.disable()
    yield
    gc.enable()


@pytest.fixture
def app(tmp_path, monkeypatch, tk_root):
    """一个不显示的考试程序。设置文件和草稿都丢进临时目录。

    草稿默认写在系统 TEMP 里，**跨测试甚至跨次运行都留着** —— 上一次跑留下的
    草稿会被这次的"接着考吗"恢复进来，测出来的就不是本用例的状态了。撞过一次。
    """
    monkeypatch.setattr(store, "here", lambda: tmp_path)
    monkeypatch.setenv("TEMP", str(tmp_path))
    got = ui.ExamApp(tmp_path / "EXAM", tmp_path / "答案包", root=tk_root)
    yield got
    # 先掐掉还在排队的定时器，别让上一个用例的轮询跑到下一个里去。
    # 走 tk.call 而不是 after_cancel：后者还会顺手删掉 widget 上登记的那条
    # Tcl 命令，接着 destroy() 再删一次就报 "can't delete Tcl command"。
    for handle in tk_root.tk.call("after", "info"):
        tk_root.tk.call("after", "cancel", handle)
    if got.frame:
        got.frame.destroy()
    gc.collect()


def settle(app, seconds: float = 20.0, until=None):
    """转界面的事件循环，直到条件成立或者超时。

    别写成 `for _ in range(40): update()` —— 那一圈瞬间就跑完了，而联网那几步
    在后台线程里，根本还没回来。要**真的等**。
    """
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.root.update()
        if until is None or until():
            return True
        time.sleep(0.02)
    app.root.update()
    return until is None or until()


def on(app, screen):
    return lambda: isinstance(app.frame, screen)


def labels_in(widget) -> list[str]:
    """把一块界面里所有文字抓出来，用于断言"屏幕上说了什么"。"""
    out = []

    def walk(w):
        for kid in w.winfo_children():
            if isinstance(kid, (tk.Label, tk.Button)):
                try:
                    out.append(kid.cget("text"))
                except tk.TclError:
                    pass
            walk(kid)
    walk(widget)
    return out


def signed_in(app, server, no="26090111", password=None):
    """登录进主界面。**初始密码就是学号**，所以不给密码就用学号。"""
    f = app.frame
    f.vars["server"].set(server)
    f.vars["no"].set(no)
    f.vars["password"].set(password if password is not None else no)
    f.login()
    assert settle(app, until=on(app, ui.ShellFrame)), f"没登上：{f.msg.cget('text')}"
    return app.frame


# ================================================================ 登录
def test_login_screen_builds(app):
    assert isinstance(app.frame, ui.LoginFrame)
    assert set(app.frame.vars) == {"server", "no", "password"}


def test_address_is_required(app):
    app.frame.vars["server"].set("")
    app.frame.vars["no"].set("26090111")
    app.frame.login()
    assert "地址" in app.frame.msg.cget("text")


def test_number_and_password_are_required(app):
    app.frame.vars["server"].set("127.0.0.1:8000")
    app.frame.vars["no"].set("26090111")
    app.frame.vars["password"].set("")
    app.frame.login()
    assert "密码" in app.frame.msg.cget("text")


def test_bad_server_shows_the_reason_not_a_crash(app):
    app.frame.vars["server"].set("127.0.0.1:9")
    app.frame.vars["no"].set("26090111")
    app.frame.vars["password"].set("26090111")
    app.frame.login()
    settle(app, 20, lambda: app.frame.msg.cget("text"))
    assert "连不上" in app.frame.msg.cget("text")
    assert isinstance(app.frame, ui.LoginFrame), "连不上就该留在原地，不能往下走"


def test_wrong_password_says_so(app, server, exam):
    app.frame.vars["server"].set(server)
    app.frame.vars["no"].set("26090111")
    app.frame.vars["password"].set("肯定不对")
    app.frame.login()
    settle(app, 20, lambda: app.frame.msg.cget("text"))
    assert "密码" in app.frame.msg.cget("text")


def test_server_is_remembered_across_runs(app, server, exam):
    """机房里一台一台输地址太折腾：输一次就记住，下次开机直接连。"""
    signed_in(app, server)
    assert store.remembered_server() == server


# ================================================================ 主界面
def test_sidebar_opens_on_the_home_page(app, server, exam):
    """**打开默认停在首页** —— 和学生网页端一样。"""
    shell = signed_in(app, server)
    assert shell.page == "home"
    assert [k for k, _i, _n in shell.PAGES] == ["home", "exam", "typing"]


def test_home_shows_who_i_am_and_the_numbers(app, server, exam):
    shell = signed_in(app, server)
    assert settle(app, until=lambda: "能参加的考试" in " ".join(labels_in(shell.holder)))
    words = " ".join(labels_in(shell.holder))
    assert "打字练习" in words
    assert "修改密码" in words, "首页要能改密码"


def test_changing_the_password_checks_the_two_inputs(app, server, exam):
    shell = signed_in(app, server, "26090115")
    assert settle(app, until=lambda: hasattr(shell.body, "pwd"))
    page = shell.body
    page.pwd["old"].set("26090115")
    page.pwd["new"].set("newpass123")
    page.pwd["again"].set("打错了")
    page.save_password()
    assert "不一致" in page.pwd_msg.cget("text")


def test_changing_the_password_really_changes_it(app, server, exam):
    """改完要能用新密码登进来 —— 只看提示语不算数。"""
    shell = signed_in(app, server, "26090116")
    assert settle(app, until=lambda: hasattr(shell.body, "pwd"))
    page = shell.body
    for key, value in (("old", "26090116"), ("new", "Kaoshi2026"),
                       ("again", "Kaoshi2026")):
        page.pwd[key].set(value)
    page.save_password()
    assert settle(app, until=lambda: page.pwd_msg.cget("text"))
    assert "已修改" in page.pwd_msg.cget("text"), page.pwd_msg.cget("text")

    app.sign_out()
    signed_in(app, server, "26090116", "Kaoshi2026")


def test_the_sidebar_switches_pages(app, server, exam):
    shell = signed_in(app, server)
    shell.go("typing")
    assert shell.page == "typing" and isinstance(shell.body, ui.TypingPage)
    shell.go("exam")
    assert isinstance(shell.body, ui.ExamListPage)


def test_refresh_reloads_the_current_page(app, server, exam):
    """老师随时会发新考试，学生不该为了看见它去重开程序。"""
    shell = signed_in(app, server)
    shell.go("exam")
    first = shell.body
    shell.refresh()
    assert shell.body is not first, "刷新之后应该是重新拉过的一页"
    assert "已更新" in shell.hint.cget("text")


# ================================================================ 考试
def test_exam_list_shows_my_exam(app, server, exam):
    shell = signed_in(app, server)
    shell.go("exam")
    assert settle(app, until=lambda: shell.body.exams)
    assert any(e["id"] == exam["exam"]["id"] for e in shell.body.exams)


def test_starting_an_exam_wipes_whatever_was_there(app, server, exam):
    """**每场考试都是全新环境**：上一场留下的东西先清掉再铺。

    不清的话，上一个考生新建的文件夹还在，这一场的学生一打开就看见"已经做好了"。
    """
    app.exam_root.mkdir(parents=True, exist_ok=True)
    (app.exam_root / "上一场留下的.txt").write_text("旧的", encoding="utf-8")
    (app.exam_root / "上一场的文件夹").mkdir()

    start_exam(app, server, exam, "26090120")
    assert not (app.exam_root / "上一场留下的.txt").exists()
    assert not (app.exam_root / "上一场的文件夹").exists()
    assert (app.exam_root / "win02").is_dir(), "新考场没铺出来"


def start_exam(app, server, exam, no):
    shell = signed_in(app, server, no)
    shell.go("exam")
    assert settle(app, until=lambda: shell.body.exams), "考试列表没加载出来"
    shell.body.start(next(e for e in shell.body.exams
                          if e["id"] == exam["exam"]["id"]))
    assert settle(app, until=on(app, exam_ui.ExamFrame)), shell.body.msg.cget("text")
    return app.frame


# ================================================================ 答题
def test_every_question_type_renders(app, server, exam):
    frame = start_exam(app, server, exam, "26090113")
    seen = {}
    for i in range(len(frame.paper)):
        frame.show(i)
        app.root.update()
        seen[frame.paper[i]["type"]] = seen.get(frame.paper[i]["type"], 0) + 1
    assert seen and "操作题" in seen


def test_choices_start_unselected(app, server, exam):
    """**没作答时每个选项都该是空框。**

    Tk 的 Radiobutton 有"第三态"：绑定变量等于 tristatevalue（默认空串）时，
    它画成"值未定"的样子 —— Windows 上就是实心黑点。于是学生一进题就看见
    四个选项全黑，以为自己选过了。
    """
    frame = start_exam(app, server, exam, "26090113")
    # 自检库里没有客观题（卷子全是 fixture 现建的必出操作题），自己塞一道
    frame.paper = [{"id": "8888", "no": 1, "type": "选择题", "score": 3,
                    "stem": "切换当前活动窗口的快捷键是（ ）",
                    "options": [{"label": "A", "content": "Alt+Tab"},
                                {"label": "B", "content": "Ctrl+C"},
                                {"label": "C", "content": "Alt+F4"},
                                {"label": "D", "content": "Win+D"}]}]
    frame.num_btns = frame.num_btns[:1]
    frame.show(0)
    app.root.update()

    radios = [w for w in frame.area.winfo_children() if isinstance(w, tk.Radiobutton)]
    assert radios, "选择题没渲染出选项"
    for r in radios:
        assert r.cget("tristatevalue") != "", "空串当第三态，选项会显示成黑点"
        assert r.getvar(r.cget("variable")) == "", "一上来不该有选中项"

    radios[0].invoke()
    app.root.update()
    assert frame.answers["8888"] == "A"


def test_a_drag_question_reserves_its_answer_area(app, server, exam):
    """拖拽题（热区、流程图）交互还没做。

    给一个「打开」按钮只会打开空的考试根目录，学生进去什么都没有，以为程序坏了。
    现在先说清楚，并**把作答区的位置占住** —— 将来那块换成 Canvas 就行。
    """
    frame = start_exam(app, server, exam, "26090119")
    frame.paper = [{"id": "9999", "no": 1, "type": "操作题", "score": 5,
                    "stem": "请将符合智能家居的设备拖拽到指定区域。"}]
    frame.num_btns = frame.num_btns[:1]
    frame.show(0)
    app.root.update()

    words = labels_in(frame.area)
    assert any("拖拽题" in t for t in words), words
    assert any("作答区（待开发）" in t for t in words), "作答区的位置要先占住"
    assert not any("打 开" in t for t in words), "不该给打开按钮"


def test_answering_marks_the_card_and_saves_a_draft(app, server, exam):
    frame = start_exam(app, server, exam, "26090113")
    qid = str(frame.paper[0]["id"])
    frame.answer(qid, "A")
    assert "已答 1" in frame.progress.cget("text")
    # 断电续考靠的就是这份草稿，机房跳闸不是小概率事件
    draft = store.load_draft(app.package.exam_id, app.student["no"])
    assert draft["answers"][qid] == "A"


def test_countdown_shows(app, server, exam):
    frame = start_exam(app, server, exam, "26090113")
    frame.tick()
    assert ":" in frame.clock.cget("text")


# ================================================================ 交卷
def test_submit_uploads_wipes_and_logs(app, server, exam):
    frame = start_exam(app, server, exam, "26090114")
    do_the_work(app.exam_root)
    frame.do_submit()
    settle(app, 20, on(app, exam_ui.DoneFrame))

    assert isinstance(app.frame, exam_ui.DoneFrame)
    ans = list(app.out_dir.glob("*.ans"))
    assert ans, "本机备份没写出来"
    assert store.upload_state(app.out_dir)[ans[0].name]["ok"] is True
    assert not store.pending_uploads(app.out_dir)

    # 每台机器留一份能核对的考试记录 —— 中考的做法，排查时第一个翻它
    log = store.read_log(app.out_dir)
    assert len(log) == 2 and "26090114" in log[1] and "已上传" in log[1], log

    # **交完卷考场自动清空** —— 不清的话下一位考生开考时铺不进来，
    # 上一个人的答案还留在磁盘上给人抄
    left = list(app.exam_root.rglob("*")) if app.exam_root.exists() else []
    assert not left, f"考场没清干净：{[p.name for p in left[:5]]}"


def test_upload_failure_still_keeps_the_paper(app, server, exam, monkeypatch):
    """**交卷不能因为上传失败而失败**：卷子先落地，传不上去只是待补传。"""
    frame = start_exam(app, server, exam, "26090117")
    do_the_work(app.exam_root)
    monkeypatch.setattr(api, "submit",
                        lambda *a, **k: (False, "连不上教师端（模拟断网）", {}))
    frame.do_submit()
    settle(app, 20, on(app, exam_ui.DoneFrame))

    assert hasattr(app.frame, "retry_btn"), "上传失败的交完页要有「重试上传」"
    assert len(store.pending_uploads(app.out_dir)) == 1


def test_retry_after_a_restart(app, server, exam, monkeypatch):
    """**补传只靠那个 .ans**：程序重开过、手上没有考试包，照样交得上。"""
    frame = start_exam(app, server, exam, "26090118")
    do_the_work(app.exam_root)
    monkeypatch.setattr(api, "submit", lambda *a, **k: (False, "模拟断网", {}))
    frame.do_submit()
    settle(app, 20, on(app, exam_ui.DoneFrame))
    assert store.pending_uploads(app.out_dir)

    # 模拟"第二天开机"：网通了，但手上什么上下文都没有
    monkeypatch.undo()
    app.package = None
    assert app.retry_pending(server) == (1, 1)
    assert not store.pending_uploads(app.out_dir)


# ================================================================ 打字练习
def test_typing_page_fetches_a_passage(app, server, exam):
    shell = signed_in(app, server)
    shell.go("typing")
    page = shell.body
    assert settle(app, until=lambda: page.passage or page.msg.cget("text"))
    assert page.mode.get() == "中文"


def test_typing_result_comes_from_the_server(app, server, exam):
    """速度、正确率、星级**都由后端算** —— 客户端只报敲了多少、对了多少、用了多久，
    和网页端一个口径，两边成绩才能放进同一张表里比。"""
    shell = signed_in(app, server)
    shell.go("typing")
    page = shell.body
    assert settle(app, until=lambda: page.passage), \
        "没取到练习文本：" + page.msg.cget("text")

    page.entry.insert("end", page.passage[:12])
    page.started = time.time() - 6
    page.submit()
    assert settle(app, until=lambda: "已记录" in page.live.cget("text")), \
        page.live.cget("text")
    assert "字/分" in page.live.cget("text")


def test_typing_needs_something_typed(app, server, exam):
    shell = signed_in(app, server)
    shell.go("typing")
    shell.body.submit()
    assert "先敲几个字" in shell.body.live.cget("text")


# ================================================================ 离线后路
def test_offline_needs_a_number(app, server, exam, monkeypatch, tmp_path):
    raw = api.fetch_exam(server, exam["exam"]["token"], tmp_path / "离线.ekb")
    monkeypatch.setattr("client.ui.filedialog.askopenfilename", lambda **k: str(raw))
    app.frame.vars["no"].set("")
    app.frame.offline()
    assert "学号" in app.frame.msg.cget("text")


def test_offline_start_works_without_the_network(app, server, exam, monkeypatch, tmp_path):
    """机房网炸了也要考得成 —— 老师导出来的包能直接开考，交卷存本机。"""
    raw = api.fetch_exam(server, exam["exam"]["token"], tmp_path / "离线.ekb")
    monkeypatch.setattr("client.ui.filedialog.askopenfilename", lambda **k: str(raw))
    f = app.frame
    f.vars["server"].set("")
    f.vars["no"].set("26090101")
    f.offline()
    assert settle(app, until=on(app, exam_ui.ExamFrame)), f.msg.cget("text")
    assert (app.exam_root / "win02" / "素材" / "冬奥介绍.txt").exists()
