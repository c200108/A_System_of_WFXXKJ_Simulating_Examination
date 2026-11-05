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
    # 设置文件现在写在 %LOCALAPPDATA% 里（"只发一个 exe"）。不把这两个也挪走，
    # 自检里的登录就会把测试用的地址写进**这台开发机自己**的客户端设置里。
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
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


def test_exe里练的打字算进首页(app, server, exam):
    """机房和线上都报过：exe 里练完打字，首页的「练习次数 / 最快速度 /
    平均正确率」一直是 0。

    成绩其实交上去了（老师在成绩页看得见），只是 exe 交的时候没带登录令牌，
    服务端认不出是谁，记录没挂到学生账号上 —— 而首页只统计挂了账号的记录。
    这条按学生真实的操作走一遍：登录、进打字页、敲一段、交，再看首页。
    """
    shell = signed_in(app, server, "26090112")
    before = api.home(server, app.token)["typing_count"]

    shell.go("typing")
    page = shell.body
    assert settle(app, until=lambda: getattr(page, "passage", "")), "练习文本没取回来"
    page.entry.insert("1.0", page.passage[:40])
    page.started = time.time() - 30          # 当作敲了半分钟
    page.submit()
    assert settle(app, until=lambda: "已记录" in page.live.cget("text")),         page.live.cget("text")

    home = api.home(server, app.token)
    assert home["typing_count"] == before + 1, "exe 里交的打字成绩没算进首页"
    assert home["typing_best_speed"] > 0


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
    # 自检里的窗口是隐藏的，量出来的宽度忽大忽小（看前面的用例把它摆成了什么样），
    # 「窗口窄了自动收起答题卡」会随机触发。默认关掉，专门测它的用例自己打开
    frame = app.frame
    frame.AUTO_FOLD_WIDTH = 0
    if frame._auto_folded:
        frame.toggle_card()
    return frame


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
    values = {r.cget("value") for r in radios}
    for r in radios:
        # 两道保险各验一条：变量初值不是空串（不会撞上第三态），
        # tristatevalue 也不是空串（就算初值哪天改回空串也还挡得住）
        now = r.getvar(r.cget("variable"))
        assert now not in values, "一上来不该有选中项"
        assert now != "", "空串会被 Tk 当成第三态，四个选项全变黑点"
        assert r.cget("tristatevalue") != ""

    radios[0].invoke()
    app.root.update()
    assert frame.answers["8888"] == "A"


def two_choice_questions(frame):
    """给答题页塞两道选择题 —— 自检库里的卷子全是操作题。"""
    frame.paper = [
        {"id": "7001", "no": 1, "type": "选择题", "score": 3,
         "stem": "切换当前活动窗口的快捷键是（ ）",
         "options": [{"label": "A", "content": "Alt+Tab"},
                     {"label": "B", "content": "Ctrl+C"}]},
        {"id": "7002", "no": 2, "type": "选择题", "score": 3,
         "stem": "保存文件的快捷键是（ ）",
         "options": [{"label": "A", "content": "Ctrl+S"},
                     {"label": "B", "content": "Ctrl+P"}]},
    ]
    frame.num_btns = frame.num_btns[:2]
    frame.show(0)
    frame.app.root.update()


def test_picking_an_option_jumps_to_the_next_question(app, server, exam):
    """选完自动跳下一题 —— 中考的机考客户端就是这么走的，学生不用再点一次。

    跳之前停 220 毫秒：立刻跳的话学生看不见自己刚点上的那个点，会以为没点上。
    """
    frame = start_exam(app, server, exam, "26090113")
    two_choice_questions(frame)

    radios = [w for w in frame.area.winfo_children() if isinstance(w, tk.Radiobutton)]
    radios[0].invoke()
    assert frame.answers["7001"] == "A"
    assert frame.index == 0, "不该立刻跳 —— 学生得看见自己点上了"
    assert settle(app, 3, lambda: frame.index == 1), "220 毫秒后该跳到第 2 题"


def test_the_last_question_does_not_jump(app, server, exam):
    """最后一题没有下一题，点了不能跳到别处去。"""
    frame = start_exam(app, server, exam, "26090113")
    two_choice_questions(frame)
    frame.show(1)
    app.root.update()
    [w for w in frame.area.winfo_children() if isinstance(w, tk.Radiobutton)][0].invoke()
    settle(app, 1.5, lambda: False)
    assert frame.index == 1


def test_long_question_scrolls_and_keeps_the_buttons(app, server, exam):
    """**题干再长，底下那两个按钮也得在。**

    原来页脚是在 body 之后 pack 的：题干一长，Tk 先把空间分给上面的内容，
    「上一题/下一题」被挤扁甚至挤没，学生只剩答题卡能跳题，还以为程序坏了。
    现在页脚钉在底部先 pack，内容区改成可滚动的画布。
    """
    frame = start_exam(app, server, exam, "26090113")
    frame.paper = [{"id": "7003", "no": 1, "type": "选择题", "score": 3,
                    "stem": "很长的题干。" * 300,
                    "options": [{"label": x, "content": "选项" + x * 40}
                                for x in "ABCD"]}]
    frame.num_btns = frame.num_btns[:1]
    frame.show(0)
    settle(app, 2, lambda: False)

    # 自检里窗口是隐藏的，winfo_ismapped() 一律是 0 —— 用「被谁管着」和算出来的
    # 尺寸判，这两样隐藏也照样算
    foot = frame.tip.master
    assert foot.winfo_manager() == "pack" and foot.winfo_height() == 48, \
        f"页脚被挤成了 {foot.winfo_height()} 像素高"
    buttons = [w for w in foot.winfo_children() if isinstance(w, tk.Button)]
    assert len(buttons) == 2 and all(b.winfo_manager() == "pack" for b in buttons)
    assert all(b.winfo_width() > 40 for b in buttons), "按钮被挤窄了"

    # 内容区能滚：滚动范围比一屏高得多
    top, bottom = frame.canvas.bbox("all")[1], frame.canvas.bbox("all")[3]
    assert bottom - top > 600, f"这么长的题干只排出 {bottom - top} 像素？"
    frame.canvas.yview_moveto(1.0)
    app.root.update()
    assert frame.canvas.yview()[0] > 0, "滚不动"


def test_the_scrollbar_comes_and_goes_with_the_content(app, server, exam, monkeypatch):
    """内容一屏放得下就把滚动条收起来，放不下再拿出来。

    自检里窗口是隐藏的，`winfo_height()` 恒为 1，量不出"够不够高"——
    所以直接把画布高度喂给它，两个方向各验一次。
    """
    frame = start_exam(app, server, exam, "26090113")
    two_choice_questions(frame)
    settle(app, 2, lambda: False)

    monkeypatch.setattr(frame.canvas, "winfo_height", lambda: 9999)
    frame._page_resized()
    assert frame.bar.winfo_manager() != "pack", "两道选择题就占一屏？不该有滚动条"

    monkeypatch.setattr(frame.canvas, "winfo_height", lambda: 10)
    frame._page_resized()
    assert frame.bar.winfo_manager() == "pack", "内容放不下时得有滚动条"


def test_switching_question_scrolls_back_to_the_top(app, server, exam):
    """上一题拉到了底，换一题得回到顶上 —— 不回的话这一题的题干藏在上面看不见。"""
    frame = start_exam(app, server, exam, "26090113")
    two_choice_questions(frame)
    frame.canvas.yview_moveto(1.0)
    frame.show(1)
    app.root.update()
    assert frame.canvas.yview()[0] == 0


def test_没有图的拖拽题说清楚由老师评阅(app, server, exam):
    """老考试包、或者服务端认不出来的拖拽题：没有图可画。给一个「打开」按钮只会
    打开空的考试根目录，学生进去什么都没有，以为程序坏了 —— 老实说清楚。"""
    frame = start_exam(app, server, exam, "26090119")
    frame.paper = [{"id": "9999", "no": 1, "type": "操作题", "score": 5,
                    "stem": "请将符合智能家居的设备拖拽到指定区域。"}]
    frame.num_btns = frame.num_btns[:1]
    frame.show(0)
    app.root.update()

    words = labels_in(frame.area)
    assert any("老师评阅" in t for t in words), words
    assert not any("打 开" in t for t in words), "不该给打开按钮"


def test_拖拽题在答题界面上能拖_进度和草稿都记上(app, server, exam):
    """真实的答题界面里放一道流程图题：画得出来、放了卡片答题卡变蓝、草稿里存着
    —— 机房跳闸重开，学生不用把卡片再拖一遍。"""
    from app.services import drag
    from client import dragboard

    entry = next(e for e in drag.BANK if e["key"] == "Q325-成绩")
    frame = start_exam(app, server, exam, "26090120")
    frame.paper = [{"id": "8888", "no": 1, "type": "操作题", "score": 10, "stem": entry["stem"],
                    "sim": {"kind": "drag", "open": "", "manual": False, "env": entry["env"]}}]
    frame.num_btns = frame.num_btns[:1]
    frame.show(0)
    app.root.update()

    boards = [w for w in _walk(frame.area) if isinstance(w, dragboard.DragBoard)]
    assert boards, "答题区里没有拖拽作答板"
    board = boards[0]
    assert "已答 0" in frame.progress.cget("text")
    board.place("i1", "A")
    board.place("i3", "B")
    assert "已答 1" in frame.progress.cget("text"), frame.progress.cget("text")

    draft = store.load_draft(app.package.exam_id, app.student["no"])
    assert draft["drags"]["8888"] == {"placed": {"A": ["i1"], "B": ["i3"]}}


def _walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from _walk(child)


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


# ================================================================ 交卷之后
def submitted(app, server, exam, no):
    """考一场、交一次卷，回到主界面的考试列表。"""
    frame = start_exam(app, server, exam, no)
    do_the_work(app.exam_root)
    frame.do_submit()
    assert settle(app, 20, on(app, exam_ui.DoneFrame))
    app.back_to_shell()
    shell = app.frame
    assert settle(app, until=lambda: shell.body.exams), "考试列表没加载出来"
    return shell


def test_score_shows_up_in_the_exam_list(app, server, exam):
    """**考完就能看见自己考了多少。**

    分数来自服务器（老师批完就变），不是本机算的 —— 所以点一下刷新就能看到
    新分。这也是"交卷后不再显示开始考试"那条的另一半：卷子交了，得有个交代。
    """
    shell = submitted(app, server, exam, "26090112")
    words = " ".join(labels_in(shell.body))
    mine = next(e for e in shell.body.exams if e["id"] == exam["exam"]["id"])
    assert mine["submitted"], "服务器那边没记上交卷"
    assert "已交卷" in words
    if mine.get("score") is not None:
        assert str(mine["score"]) in words, "分数没显示出来"


def test_submitted_exam_offers_review_not_start(app, server, exam):
    """交过卷就不该再有「开始考试」—— 点下去只会撞一个"你已经交过了"。"""
    shell = submitted(app, server, exam, "26090117")
    assert "查 看" in labels_in(shell.body)
    # 列表上还有别的考试没交，「开始考试」的个数应当正好等于还能考的场次
    can = [e for e in shell.body.exams
           if not e.get("submitted") or e.get("allow_retake")]
    assert labels_in(shell.body).count("开始考试") == len(can)


def test_review_shows_my_answers_without_telling_me_right_or_wrong(app, server, exam):
    """回看页默认只显示"我选了什么"。

    考试分批考时，先考完的学生要是能看到对错，题目当场就传出去了。对错要等
    老师在网页后台开了「考后可看答案」才出现，而且是**服务器决定发不发**。
    """
    shell = submitted(app, server, exam, "26090118")
    mine = next(e for e in shell.body.exams if e["id"] == exam["exam"]["id"])
    shell.go("review", mine)
    page = shell.body
    assert isinstance(page, ui.ReviewPage)
    assert settle(app, until=lambda: "我的作答" in " ".join(labels_in(page))), \
        page.msg.cget("text")

    words = " ".join(labels_in(page))
    assert "正确答案" not in words, "老师还没开放答案，不该显示正确答案"
    assert "✓ 正确" not in words and "✗ 错误" not in words, "不该显示对错"
    # 回看是考试页下面的一层：侧边栏仍然停在「考试」，顶上多一个返回
    assert shell.page == "review"
    shell.go("exam")
    assert isinstance(shell.body, ui.ExamListPage)


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


def test_typing_blocks_copy_and_paste(app, server, exam):
    """打字练习**只能一个字一个字敲**。

    能复制原文、粘贴到答题框的话，速度和正确率就都是假的，这个练习也就没意义。
    四条路都要堵：Ctrl 快捷键、中键粘贴、右键菜单、Tk 的虚拟事件 —— 少堵一条
    就能绕过去。
    """
    shell = signed_in(app, server)
    shell.go("typing")
    page = shell.body
    for widget in (page.entry, page.text_view):
        for seq in ("<Control-v>", "<Control-V>", "<Control-c>", "<Control-x>",
                    "<Button-3>", "<<Paste>>", "<<Copy>>"):
            assert widget.bind(seq), f"{seq} 没堵上"

    # 真按一下 Ctrl+V：什么都不该进来
    page.entry.delete("1.0", "end")
    app.root.clipboard_clear()
    app.root.clipboard_append("抄来的一大段文字")
    page.entry.event_generate("<<Paste>>")
    app.root.update()
    assert page.entry.get("1.0", "end-1c") == "", "粘贴没被拦住"


def test_typing_needs_something_typed(app, server, exam):
    shell = signed_in(app, server)
    shell.go("typing")
    shell.body.submit()
    assert "先敲几个字" in shell.body.live.cget("text")


def test_刷新按钮3秒只能点一次(app, server, exam):
    """一个机房几十个人一起狂点刷新，每点一下就把这一页的接口全打一遍。"""
    shell = signed_in(app, server)
    shell.go("exam")
    shell.refresh()
    once = shell.body
    assert str(shell.refresh_btn["state"]) == "disabled"
    shell.refresh()
    assert shell.body is once, "3 秒内又刷了一次"
    assert settle(app, 5, until=lambda: str(shell.refresh_btn["state"]) == "normal"),         "3 秒过了按钮没放开"
    shell.refresh()
    assert shell.body is not once


def test_打字没打完一半交不了(app, server, exam, typing_limits_on):
    shell = signed_in(app, server)
    shell.go("typing")
    page = shell.body
    assert settle(app, until=lambda: page.passage), page.msg.cget("text")
    assert page.ratio == 0.5, "规则要从服务端配置里拿"
    page.entry.insert("end", page.passage[:5])
    page.started = time.time() - 5
    page.submit()
    assert "还没打完 50%" in page.live.cget("text")
    assert str(page.submit_btn["state"]) == "normal", "没交出去，按钮不该锁"


def _half(page):
    return page.passage[: -(-len(page.passage) // 2)]


def test_打字一分钟只能交一次_挡回来的那次停表等着自动交(app, server, exam, typing_limits_on):
    from conftest import age_rate_hits

    shell = signed_in(app, server, "26090113")
    before = api.home(server, app.token)["typing_count"]
    shell.go("typing")
    page = shell.body
    assert settle(app, until=lambda: page.passage), page.msg.cget("text")
    page.entry.insert("end", _half(page))
    page.started = time.time() - 60
    page.submit()
    assert settle(app, until=lambda: "已记录" in page.live.cget("text")), page.live.cget("text")

    page.started = time.time() - 50
    page.submit()
    assert settle(app, until=lambda: page.frozen), page.live.cget("text")
    assert "秒后自动交" in page.live.cget("text")
    assert str(page.entry["state"]) == "disabled" and page.started is None, "等的时候要停表、锁输入框"
    assert str(page.submit_btn["state"]) == "disabled"

    age_rate_hits(61)
    page.wait_then_send(0)                 # 当作倒数到了
    assert settle(app, until=lambda: "已记录" in page.live.cget("text")), page.live.cget("text")
    assert page.frozen is None and str(page.entry["state"]) == "normal"
    assert api.home(server, app.token)["typing_count"] == before + 2, "扣着的那次没交上去"


def test_取过的文本记着_只有换一段才去要新的_每分钟最多三次(app, server, exam, typing_limits_on):
    shell = signed_in(app, server)
    shell.go("typing")
    page = shell.body
    assert settle(app, until=lambda: page.passage), page.msg.cget("text")
    first = page.passage

    # 刷新、来回切页都不该再占次数
    shell.go("home")
    shell.go("typing")
    page = shell.body
    assert settle(app, until=lambda: page.passage)
    assert page.passage == first, "切回来应该还是刚才那段"

    for _ in range(2):                     # 第 2、3 次
        page.fetch(fresh=True)
        assert settle(app, until=lambda: str(page.swap_btn["state"]) == "normal")
    kept = page.passage
    page.fetch(fresh=True)                 # 第 4 次：被挡
    assert settle(app, until=lambda: "秒后可换" in page.swap_btn.cget("text")),         page.msg.cget("text")
    assert "每分钟最多换 3 次" in page.msg.cget("text")
    assert page.passage == kept, "被挡回来不该把手上这段弄没"


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


# ================================================================ 姓名登录版
# `build.py --name-login` 打出来的那一版：先选班级，账号填中文姓名，初始密码 123456。
# 学生是这几条用例自己建的，不占上面那串学号。
@pytest.fixture
def name_app(app):
    app.name_login = True
    app.sign_out()                          # 按姓名登录版重画登录页
    return app


def _name_student(server, no, name, cls_name="1班"):
    """建一个学生，返回他所在班级的显示名（登录页班级下拉里的那一项）。"""
    from conftest import call, teacher_token
    tk_ = teacher_token(server)
    classes = call(server, "GET", "/api/classes", token=tk_)
    got = next((c for c in classes if c["name"] == cls_name), None)
    if got is None:
        got = call(server, "POST", "/api/classes", {"grade": "九年级", "name": cls_name}, tk_)
    call(server, "POST", "/api/students",
         {"student_no": no, "name": name, "class_id": got["id"]}, tk_)
    return got["grade"] + got["name"]


def _pick_class(app, server, display):
    """像学生那样：连上教师端、班级下拉里选自己的班。"""
    f = app.frame
    f.set_classes({c["display"]: c["id"] for c in api.login_classes(server)})
    f.vars["cls"].set(display)


def test_姓名登录版_登录页写的是班级姓名和123456(name_app):
    words = " ".join(labels_in(name_app.frame))
    assert "姓　　名" in words and "初始密码 123456" in words
    assert "姓名登录版" in words
    assert "班　　级" in words, "姓名登录版要先选班级"
    assert "拼音" not in words
    assert set(name_app.frame.vars) == {"server", "cls", "no", "password"}
    name_app.frame.vars["server"].set("127.0.0.1:8000")
    name_app.frame.vars["no"].set("")
    name_app.frame.login()
    assert "姓名和密码都要填" in name_app.frame.msg.cget("text")


def test_姓名登录版_班级姓名加123456登得进去(name_app, server, exam):
    _pick_class(name_app, server, _name_student(server, "26090131", "姓名登录甲"))
    shell = signed_in(name_app, server, "姓名登录甲", "123456")
    assert name_app.student["no"] == "26090131"
    assert settle(name_app, until=lambda: hasattr(shell.body, "pwd"))
    assert "初始密码是 123456" in " ".join(labels_in(shell.body))


def test_姓名登录版_密码不对就说(name_app, server, exam):
    _pick_class(name_app, server, _name_student(server, "26090132", "姓名登录乙"))
    f = name_app.frame
    f.vars["server"].set(server)
    f.vars["no"].set("姓名登录乙")
    f.vars["password"].set("26090132")          # 学号那套初始密码这里不认
    f.login()
    settle(name_app, 20, lambda: f.msg.cget("text"))
    assert "密码" in f.msg.cget("text")


def test_姓名登录版_要先选班级(name_app, server, exam):
    _name_student(server, "26090137", "姓名登录戊")
    f = name_app.frame
    f.set_classes({c["display"]: c["id"] for c in api.login_classes(server)})
    f.vars["server"].set(server)
    f.vars["no"].set("姓名登录戊")
    f.vars["password"].set("123456")
    f.login()
    assert "请先选择班级" in f.msg.cget("text")


def test_姓名登录版_重名按班级分开(name_app, server, exam):
    one = _name_student(server, "26090133", "姓名登录重")
    two = _name_student(server, "26090134", "姓名登录重", "7班")
    assert one != two
    _pick_class(name_app, server, two)
    signed_in(name_app, server, "姓名登录重", "123456")
    assert name_app.student["no"] == "26090134"
    name_app.sign_out()
    # 同一个班里再来一位同名的：只能填学号
    _name_student(server, "26090138", "姓名登录重", "7班")
    _pick_class(name_app, server, two)
    f = name_app.frame
    f.vars["server"].set(server)
    f.vars["no"].set("姓名登录重")
    f.vars["password"].set("123456")
    f.login()
    settle(name_app, 20, lambda: f.msg.cget("text"))
    assert "学号" in f.msg.cget("text")
    signed_in(name_app, server, "26090138", "123456")
    assert name_app.student["no"] == "26090138"


def test_姓名登录版_改了密码之后用新密码(name_app, server, exam):
    _pick_class(name_app, server, _name_student(server, "26090135", "姓名登录丙"))
    shell = signed_in(name_app, server, "姓名登录丙", "123456")
    assert settle(name_app, until=lambda: hasattr(shell.body, "pwd"))
    page = shell.body
    for key, value in (("old", "123456"), ("new", "Kaoshi2026"), ("again", "Kaoshi2026")):
        page.pwd[key].set(value)
    page.save_password()
    assert settle(name_app, until=lambda: page.pwd_msg.cget("text"))
    assert "已修改" in page.pwd_msg.cget("text"), page.pwd_msg.cget("text")
    name_app.sign_out()
    signed_in(name_app, server, "姓名登录丙", "Kaoshi2026")


def test_姓名登录版_离线也按姓名找人(name_app, server, exam, monkeypatch, tmp_path):
    raw = api.fetch_exam(server, exam["exam"]["token"], tmp_path / "离线.ekb")
    monkeypatch.setattr("client.ui.filedialog.askopenfilename", lambda **k: str(raw))
    f = name_app.frame
    f.vars["server"].set("")
    f.vars["no"].set("查无此人")
    f.offline()
    assert "名单里没有这个姓名" in f.msg.cget("text")
    f.vars["no"].set("桌面丙")
    f.offline()
    assert settle(name_app, until=on(name_app, exam_ui.ExamFrame)), f.msg.cget("text")
    assert name_app.student["no"] == "26090102", "按姓名找到人之后，交卷要带上他的学号"
    assert name_app.student["name"] == "桌面丙"


def test_离线名单按班级姓名找人的规矩():
    roster = [
        {"no": "1", "name": "张伟", "cls": "八年级1班"},
        {"no": "2", "name": "张伟", "cls": "九年级2班"},
        {"no": "3", "name": "李雷", "cls": "八年级1班"},
        {"no": "5", "name": "张伟", "cls": "九年级2班"},
    ]
    from client.ui import roster_by_name
    assert roster_by_name(roster, " 李雷 ")[0]["no"] == "3"
    hit, why = roster_by_name(roster, "张伟")
    assert hit is None and "选择班级" in why
    assert roster_by_name(roster, "张伟", "八年级1班")[0]["no"] == "1"
    hit, why = roster_by_name(roster, "张伟", "九年级2班")
    assert hit is None and "学号" in why
    assert roster_by_name(roster, "李雷", "九年级2班") == (None, "")
    assert roster_by_name(roster, "zhangwei") == (None, "")


# ================================================================ 交卷门槛
def test_交卷门槛_一半向上取整():
    assert exam_ui.submit_needs(30, 45 * 60) == (15, 1350)
    assert exam_ui.submit_needs(10, 40 * 60) == (5, 20 * 60)
    assert exam_ui.submit_needs(7, 61) == (4, 31)
    assert exam_ui.submit_needs(31, 40 * 60) == (16, 1200)
    assert exam_ui.submit_needs(1, 1) == (1, 1)
    assert exam_ui.submit_needs(0, 0) == (0, 0)


def test_交卷门槛_时间和题数都够了才放行(app, server, exam, monkeypatch):
    frame = start_exam(app, server, exam, "26090119")
    shown = []
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: shown.append(a[1]))
    submitted_ = []
    monkeypatch.setattr(frame, "do_submit", lambda *a, **k: submitted_.append(1))

    total = app.package.duration_min * 60
    need_q, need_sec = exam_ui.submit_needs(len(frame.paper), total)
    # 被门槛拦住时客户端先在后台问一次教师端最新设置（老师可能刚打开「允许提前交卷」），
    # 问完才弹提示 —— 所以点完要等提示真的弹出来，不能当场就看
    def press():
        n = len(shown)
        frame.confirm_submit()
        settle(app, 10, lambda: len(shown) > n or submitted_)

    # 刚开考、一题没答：两样都不够
    press()
    assert not submitted_ and "才能交卷" in shown[-1] and "再答" in shown[-1]
    assert "才能交卷" in (frame.tick() or frame.tip.cget("text"))

    # 题答够了、时间还不够
    for q in frame.paper[:need_q]:
        frame.answers[str(q["id"])] = "A"
    press()
    assert not submitted_ and "再等" in shown[-1] and "再答" not in shown[-1]

    # 时间也够了
    frame.left = total - need_sec
    assert frame.gate_reason() == ""
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: True)   # 「确定交卷吗？」点是
    press()
    assert submitted_ == [1]


def test_交卷门槛_时间到了照样自动交(app, server, exam):
    """门槛只挡学生手动交卷；时间到了一题没答也得交上去。"""
    frame = start_exam(app, server, exam, "26090120")
    frame.left = 0
    frame.tick()
    assert settle(app, 20, on(app, exam_ui.DoneFrame))


# ================================================================ 窗口：答题卡折叠、最小尺寸、一键收缩（4.13.1）
def mixed_paper(frame):
    """六种题各一道：win / wps 能收缩，html / AI / 拖拽 / 客观题不能。"""
    frame.paper = [
        {"id": "6001", "no": 1, "type": "操作题", "score": 5, "stem": "在 win02 里新建文件夹。",
         "sim": {"kind": "win", "open": "win02"}},
        {"id": "6002", "no": 2, "type": "操作题", "score": 5, "stem": "把标题设为黑体二号。",
         "sim": {"kind": "wps", "open": ""}},
        {"id": "6003", "no": 3, "type": "操作题", "score": 5, "stem": "修改网页标题。",
         "sim": {"kind": "html", "open": ""}},
        {"id": "6004", "no": 4, "type": "选择题", "score": 3, "stem": "保存的快捷键是（ ）",
         "options": [{"label": "A", "content": "Ctrl+S"}, {"label": "B", "content": "Ctrl+P"}]},
        {"id": "6005", "no": 5, "type": "操作题", "score": 5, "stem": "让 AI 写一首诗。",
         "sim": {"kind": "ai"}},
        {"id": "6006", "no": 6, "type": "操作题", "score": 5, "stem": "把设备拖到区域里。",
         "sim": {"kind": "drag"}},
    ]
    frame.num_btns = frame.num_btns[:len(frame.paper)]
    frame.show(0)
    frame.app.root.update()


def shrink_shown(frame) -> bool:
    return frame.btn_shrink.winfo_manager() == "pack"


def test_最小窗口按屏幕算_宽八分之一高三分之一():
    assert exam_ui.exam_minsize(1920, 1080) == (240, 360)
    assert exam_ui.exam_minsize(1366, 768) == (170, 256)
    assert exam_ui.exam_minsize(1024, 768) == (128, 256)
    assert exam_ui.exam_minsize(0, 0) == (1, 1)


def test_答题时最小尺寸放宽_离开答题换回来(app, server, exam):
    before = tuple(app.root.minsize())
    frame = start_exam(app, server, exam, "26090121")
    want = exam_ui.exam_minsize(app.root.winfo_screenwidth(), app.root.winfo_screenheight())
    assert tuple(app.root.minsize()) == want
    frame.destroy()
    app.frame = None
    assert tuple(app.root.minsize()) == before


def test_窗口窄了交卷按钮也不会被挤掉(app, server, exam):
    """pack 先满足先摆的：「交卷」得在标题前面摆，窗口一窄被挤掉的是标题。"""
    frame = start_exam(app, server, exam, "26090121")
    kids = frame.topbar.pack_slaves()
    assert kids[0] is frame.btn_submit and kids[1] is frame.clock


def test_答题卡能折叠_再点展开(app, server, exam):
    frame = start_exam(app, server, exam, "26090121")
    assert frame.side.winfo_manager() == "pack" and frame.btn_fold.cget("text") == "←"
    frame.btn_fold.invoke()
    app.root.update()
    assert frame.card_folded and frame.side.winfo_manager() == ""
    assert frame.btn_fold.cget("text") == "→"
    assert frame.fold_col.winfo_manager() == "pack", "收起后按钮本身得留着"
    frame.btn_fold.invoke()
    app.root.update()
    assert not frame.card_folded and frame.side.winfo_manager() == "pack"
    # 展开后还在按钮左边，不能跑到题目区右边去
    assert frame.body.pack_slaves()[:2] == [frame.side, frame.fold_col]
    assert frame.btn_fold.cget("text") == "←"


def test_一键收缩只在win和wps题出现(app, server, exam):
    frame = start_exam(app, server, exam, "26090121")
    mixed_paper(frame)
    seen = []
    for i in range(len(frame.paper)):
        frame.show(i)
        app.root.update()
        seen.append(shrink_shown(frame))
    assert seen == [True, True, False, False, False, False]
    frame.show(0)
    assert frame.btn_shrink.master is frame.head_row, "放在题目标题栏右侧"


def test_一键收缩只留题干_还原放回原样(app, server, exam):
    frame = start_exam(app, server, exam, "26090121")
    mixed_paper(frame)
    frame.toggle_card()                       # 先把答题卡收起来，还原后也得是收起的
    app.root.geometry("1000x680+30+20")
    app.root.update()
    geo = app.root.geometry()

    frame.btn_shrink.invoke()
    app.root.update()
    assert frame.shrunk and frame.btn_shrink.cget("text") == "还原"
    for w in (frame.topbar, frame.foot, frame.side, frame.fold_col, frame.area):
        assert w.winfo_manager() == "", f"{w} 收缩时该藏起来"
    assert frame.stem.winfo_manager() == "pack" and frame.head_row.winfo_manager() == "pack"
    assert app.root.attributes("-topmost") in (1, True, "1")
    # 收缩时临时放开最小尺寸（设的是 1×1；Windows 自己给带标题栏的窗口留了一百来像素宽的下限）
    mw, mh = app.root.minsize()
    assert mh == 1 and mw <= 200, f"收缩时得临时放开最小尺寸，现在是 {mw}×{mh}"
    # 贴到屏幕右上角（Windows 上第一次设的位置会被吞掉，撞过）
    x = int(app.root.geometry().split("+")[1])
    assert x > app.root.winfo_screenwidth() // 2, f"收缩后该在屏幕右边，现在 x={x}"

    frame.btn_shrink.invoke()
    app.root.update()
    assert not frame.shrunk and frame.btn_shrink.cget("text") == "一键收缩"
    assert app.root.attributes("-topmost") in (0, False, "0")
    assert tuple(app.root.minsize()) == frame._exam_minsize
    assert app.root.geometry() == geo
    assert frame.card_folded and frame.side.winfo_manager() == ""
    for w in (frame.topbar, frame.foot, frame.fold_col, frame.area):
        assert w.winfo_manager() == "pack"
    assert frame.pack_slaves() == [frame.topbar, frame.foot, frame.body]


def test_收缩中切到win或wps题保持收缩_切到别的题自动还原(app, server, exam):
    frame = start_exam(app, server, exam, "26090121")
    mixed_paper(frame)
    frame.shrink()
    frame.show(1)                             # win -> wps：接着缩着，题干换成新题
    app.root.update()
    assert frame.shrunk and frame.stem.cget("text") == "把标题设为黑体二号。"
    assert frame.area.winfo_manager() == "", "换了题也只留题干"
    frame.show(2)                             # -> 网页题：自动还原
    app.root.update()
    assert not frame.shrunk and frame.area.winfo_manager() == "pack"
    assert frame.topbar.winfo_manager() == "pack" and not shrink_shown(frame)
    for i in (3, 4, 5):                       # 客观题、AI、拖拽一样
        frame.show(0)
        frame.shrink()
        frame.show(i)
        assert not frame.shrunk, f"第 {i + 1} 题不该缩着"


def test_交卷前先还原(app, server, exam, monkeypatch):
    frame = start_exam(app, server, exam, "26090121")
    mixed_paper(frame)
    frame.shrink()
    seen = []
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: seen.append(frame.shrunk))
    frame._asked_live = True                  # 别去问教师端，直接弹门槛提示
    frame.confirm_submit()
    assert not frame.shrunk and seen == [False]


def test_时间到自动交卷前先还原(app, server, exam, monkeypatch):
    frame = start_exam(app, server, exam, "26090122")
    mixed_paper(frame)
    frame.shrink()
    seen = []
    monkeypatch.setattr(messagebox, "showinfo", lambda *a, **k: seen.append(frame.shrunk))
    frame.left = 0
    frame.tick()
    assert seen == [False]
    assert settle(app, 20, on(app, exam_ui.DoneFrame))
    assert app.root.attributes("-topmost") in (0, False, "0")


def test_关窗口的确认框前先还原(app, server, exam, monkeypatch):
    frame = start_exam(app, server, exam, "26090121")
    mixed_paper(frame)
    frame.shrink()
    seen = []
    monkeypatch.setattr(messagebox, "askyesno", lambda *a, **k: seen.append(frame.shrunk) or False)
    app.on_close()
    assert seen == [False]


def test_窗口窄了自动收起答题卡_让出位置给题目(app, server, exam):
    frame = start_exam(app, server, exam, "26090121")
    frame.AUTO_FOLD_WIDTH = exam_ui.ExamFrame.AUTO_FOLD_WIDTH
    frame._body_resized(type("E", (), {"width": 300})())
    assert frame.card_folded and frame.side.winfo_manager() == ""
    frame._body_resized(type("E", (), {"width": 900})())
    assert not frame.card_folded and frame.side.winfo_manager() == "pack"
    # 学生自己收起的，拉宽了也不替他展开
    frame.toggle_card()
    frame._body_resized(type("E", (), {"width": 900})())
    assert frame.card_folded


def test_选择判断题乱序_按学号打乱_交的是原字母(app, server, exam):
    """考试包开了乱序：答题界面按「考试 + 学号」打乱，选的是新位置的字母，记下的是原字母。"""
    frame = start_exam(app, server, exam, "26090121")
    ops = [{"label": x, "content": "选项" + x} for x in "ABCD"]
    app.package.paper = [{"id": f"s{i}", "no": i + 1, "type": "选择题", "score": 2,
                          "section": "一", "stem": f"第{i}题", "options": ops} for i in range(8)]
    app.package.manifest["shuffle"] = True
    frame.destroy()
    frame = exam_ui.ExamFrame(app)
    app.frame = frame
    frame.pack(fill="both", expand=True)
    again = exam_ui.ExamFrame(app)             # 同一个学生再开一次：顺序一样
    assert [q["id"] for q in again.paper] == [q["id"] for q in frame.paper]
    again.destroy()
    assert sorted(q["id"] for q in frame.paper) == [f"s{i}" for i in range(8)]
    assert [q["id"] for q in frame.paper] != [f"s{i}" for i in range(8)] or \
        any(o["label"] != o["show"] for q in frame.paper for o in q["options"])

    frame.show(0)
    app.root.update()
    radios = [w for w in frame.area.winfo_children() if isinstance(w, tk.Radiobutton)]
    q = frame.paper[0]
    assert [r.cget("text")[0] for r in radios] == list("ABCD")      # 屏幕上 A B C D 依次排
    assert [r.cget("value") for r in radios] == [o["label"] for o in q["options"]]
    radios[0].invoke()
    assert frame.answers[q["id"]] == q["options"][0]["label"]       # 记的是原字母
