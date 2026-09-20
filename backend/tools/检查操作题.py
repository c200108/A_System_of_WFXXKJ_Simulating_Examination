# -*- coding: utf-8 -*-
"""体检：拿**题库里真实的操作题**走一遍 —— 铺考场 → 按检查点做对 → 判分。

    python backend/tools/检查操作题.py

**只读库，不写库。** 它回答一句话：现在发一场考试，学生机上到底有没有文件、
交卷之后到底判不判得出分。

配完题（`stem_to_sim.py --apply`）之后跑一遍，或者改完判分逻辑之后跑一遍。
输出里出现「考场是空的」或者「没判满」，就是那道题现在发出去会出事。

它模拟的"学生"是照着检查点做的，所以**判不满就说明题目本身不自洽** ——
要么初始环境少铺了东西，要么检查点指向了环境里没有的路径。"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(r"D:\Pythonproject\A_System_of_WFXXKJ_Simulating_Examination")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "desktop"))

import pymysql                                                   # noqa: E402
from app.routers.desk import _files_of, _root_of                 # noqa: E402
from app.services import sim                                     # noqa: E402
from client import docx, snapshot, states                        # noqa: E402

c = pymysql.connect(host="127.0.0.1", user="root", password="root",
                    database="exam", charset="utf8mb4")
cur = c.cursor()
cur.execute("""select q.id, q.scope, s.kind, s.env_json, s.checks_json, q.stem
               from questions q join sim_tasks s on s.id = q.sim_task_id
               where q.type='操作题' and q.is_deleted=0 order by q.id""")
rows = cur.fetchall()
print(f"库里有仿真任务的操作题：{len(rows)} 道\n")

work = Path(tempfile.mkdtemp(prefix="bankcheck-"))
bad = []

for qid, scope, kind, env_json, checks_json, stem_text in rows:
    env = json.loads(env_json or "{}")
    checks = json.loads(checks_json or "[]")
    files = _files_of(kind, env)
    logical = _root_of(kind, env)

    # —— 铺考场：完全照 package.deploy_files 的做法
    box = work / f"q{qid}"
    shutil.rmtree(box, ignore_errors=True)
    box.mkdir(parents=True)
    n_files = n_dirs = 0
    for rel, data in files.items():
        target = box / rel
        if data is None:
            target.mkdir(parents=True, exist_ok=True)
            n_dirs += 1
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            n_files += 1

    note = f"#{qid} [{scope}] {kind}：铺出 {n_files} 文件 / {n_dirs} 空文件夹，{len(checks)} 个检查点"

    if kind == "ai":
        got = sim.run_checks("ai", sim.checks_for("ai", checks, stem_text, 10),
                             {"messages": [{"role": "user", "text": stem_text}]})
        print(note + f" → 把题干原样提交，判 {got['score']}/{got['full']}")
        if got["score"] <= 0:
            bad.append((qid, "AI 题提交了题干却judge不出分"))
        continue

    if n_files + n_dirs == 0:
        print(note + "  ← 考场是空的！")
        bad.append((qid, "一个文件都没铺出来"))
        continue

    # —— 学生按检查点把题做对（这就是"标准答案"）
    for chk in checks:
        a = chk.get("assert") or {}
        if kind == "win":
            rel = a.get("path", "")[len(logical) + 1:] if logical else a.get("path", "")
            target = box / rel
            if a.get("op") == "exists":
                if a.get("is") == "dir":
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if not target.exists():
                        target.write_text("学生新建的", encoding="gbk")
            elif a.get("op") == "missing" and target.exists():
                target.unlink() if target.is_file() else shutil.rmtree(target)

    if kind == "wps":
        # 学生用真 WPS 改：照检查点把格式改到位、把词替换掉、末尾加一段
        from app.services import docx_io
        paras = [dict(p) for p in env.get("paras") or []]
        tail = None
        for chk in checks:
            a = chk.get("assert") or {}
            if a.get("op") == "para":
                at = a.get("at")
                i = at if isinstance(at, int) else 0
                if 0 <= i < len(paras):
                    for k, v in a.items():
                        if k not in ("op", "at"):
                            paras[i][k] = v
            elif a.get("op") == "text":
                old, new = a.get("absent"), a.get("present")
                if old:
                    for p in paras:
                        p["text"] = p["text"].replace(old, new or "")
            elif a.get("op") == "order" and a.get("last"):
                tail = a["last"]
        if tail:
            paras.append({**sim.blank_para(), "text": tail + "（学生补写）"})
        name = docx_io.docx_name(env)
        (box / name).write_bytes(docx_io.build_docx({**env, "paras": paras}))

    if kind == "html":
        # 学生用记事本改网页
        page = (box / "index.html").read_text(encoding="utf-8")
        css = []
        for chk in checks:
            a = chk.get("assert") or {}
            if a.get("op") == "title":
                page = page.replace("<title></title>", f"<title>{a['equals']}</title>")
            elif a.get("op") == "sel" and a.get("selector") in ("h1", "h2", "p"):
                tag = a["selector"]
                page = page.replace(f"<{tag}></{tag}>", f"<{tag}>{a.get('text','')}</{tag}>", 1)
            elif a.get("op") == "attr":
                want = a.get("has", "")
                if a["name"] == "src":
                    cur_src = page.split('<img src="')[1].split('"')[0] if '<img src="' in page else ""
                    new_src = want if want.endswith("/") is False else want
                    page = page.replace(f'<img src="{cur_src}"',
                                        f'<img src="{cur_src + new_src if want == "img/" else new_src}"')
                else:
                    page = page.replace("<img ", f'<img {a["name"]}="{want}" ', 1)
            elif a.get("op") == "css":
                css.append(f'{a["selector"]} {{ {a["prop"]}: {a["equals"]}; }}')
        (box / "index.html").write_text(page, encoding="utf-8")
        if css:
            (box / "style.css").write_text("\n".join(css), encoding="utf-8")

    open_rel = sorted(files)[0].split("/")[0] if kind == "win" else (
        sorted(files)[0] if files else "")
    if kind == "wps":
        open_rel = docx_io.docx_name(env)
    state = states.state_for(kind, box, open_rel, logical)
    got = sim.run_checks(kind, checks, state)
    flag = "" if got["score"] == got["full"] else "   ← 没判满"
    print(note + f" → 标准答案判 {got['score']}/{got['full']}{flag}")
    if got["score"] != got["full"]:
        bad.append((qid, [r["desc"] + "：" + r["why"] for r in got["results"] if not r["ok"]]))

print()
if bad:
    print(f"有 {len(bad)} 道题不对：")
    for qid, why in bad:
        print(f"  #{qid} {why}")
else:
    print("全部通过：每道题都铺出了文件，按题干做对就能判满分。")
shutil.rmtree(work, ignore_errors=True)
sys.exit(1 if bad else 0)
