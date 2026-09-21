# -*- coding: utf-8 -*-
r"""操作题体检：题干 → 环境 + 检查点 → 铺考场 → 照着做对 → 判分。

    python backend/tools/验操作题.py                     体检题库里全部操作题
    python backend/tools/验操作题.py --xlsx 题库.xlsx    体检一份导出的 Excel
    python backend/tools/验操作题.py --xlsx 题库.xlsx -n 7   盯着第 7 道看细节

## 它回答一句话

**这道题发出去，学生机上有没有文件、交卷之后判不判得出分。**

模拟的"学生"是照着检查点做的，所以判不满就说明题目本身不自洽：要么初始环境少
铺了东西，要么检查点指向了环境里没有的路径，要么生成的文档根本表达不了那个格式
（写下去读回来就丢了）。这三种在考场上的表现都一样 —— 学生做完了，分数是零，
而老师那边什么错都看不到。

## 新加了题就跑一遍

题库加题不用配环境（检查点是**按题干现算**的，见 app/services/stem.py 的
auto_sim），但**得确认算得出来**。认不出来的题这里会标成「拖拽题」——
那类题目前在 exe 里只占位、由老师评阅，不是错误。
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "desktop"))

from app.routers.desk import _files_of, _root_of                 # noqa: E402
from app.services import docx_io, sim, stem as stem_rules        # noqa: E402
from client import states                                        # noqa: E402


def from_xlsx(path: Path) -> list[dict]:
    from openpyxl import load_workbook
    ws = load_workbook(path).active
    head = [c.value for c in ws[1]]
    rows = [dict(zip(head, r)) for r in ws.iter_rows(min_row=2, values_only=True)]
    return [{"stem": str(r.get("题干") or ""), "scope": str(r.get("知识范围") or ""),
             "type": str(r.get("题型") or ""), "id": i}
            for i, r in enumerate(rows, 1) if str(r.get("题型") or "") == "操作题"]


def from_db() -> list[dict]:
    from sqlalchemy import select
    from app.database import SessionLocal
    from app.models import Question
    db = SessionLocal()
    return [{"stem": q.stem or "", "scope": q.scope or "", "type": q.type, "id": q.id}
            for q in db.scalars(select(Question).where(
                Question.is_deleted.is_(False), Question.type == "操作题"))]


def do_the_work(kind: str, env: dict, checks: list, box: Path, logical: str) -> None:
    """一个照着检查点把题做对的"学生"。这就是这道题的标准答案。"""
    if kind == "win":
        for chk in checks:
            a = chk.get("assert") or {}
            path = str(a.get("path") or "")
            rel = path[len(logical) + 1:] if logical and path.startswith(logical) else path
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
            elif a.get("op") == "content":
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(str(a.get("has") or ""), encoding="gbk")
        return

    if kind == "html":
        folder = next((box / rel for rel in ("网页", ".") if (box / rel).is_dir()), box)
        page = (folder / "index.html").read_text(encoding="utf-8")
        css = []
        for chk in checks:
            a = chk.get("assert") or {}
            op = a.get("op")
            if op == "title":
                page = page.replace("<title></title>", f"<title>{a['equals']}</title>")
            elif op == "sel" and a.get("selector") in ("h1", "h2", "p"):
                tag = a["selector"]
                page = page.replace(f"<{tag}></{tag}>",
                                    f"<{tag}>{a.get('text', '')}</{tag}>", 1)
            elif op == "attr" and a.get("selector") == "img":
                want = str(a.get("has") or "")
                now = page.split('<img src="')[1].split('"')[0] if '<img src="' in page else ""
                if a.get("name") == "src":
                    page = page.replace(f'<img src="{now}"',
                                        f'<img src="{now + want if want.endswith("/") else want}"')
                else:
                    page = page.replace("<img ", f'<img {a["name"]}="{want}" ', 1)
            elif op == "css":
                css.append(f'{a["selector"]} {{ {a["prop"]}: {a["equals"]}; }}')
        (folder / "index.html").write_text(page, encoding="utf-8")
        if css:
            (folder / "style.css").write_text("\n".join(css), encoding="utf-8")
        return

    if kind != "wps":
        return

    paras = [dict(p) for p in env.get("paras") or []]
    page = dict(env.get("page") or {})
    header = footer = ""
    tail = None
    for chk in checks:
        a = chk.get("assert") or {}
        op = a.get("op")
        if op == "para":
            at = a.get("at")
            idx = None
            if isinstance(at, dict):
                key = str(at.get("has") or "")
                idx = next((j for j, p in enumerate(paras)
                            if key and key in str(p.get("text") or "")), None)
            elif isinstance(at, int) and 0 <= at < len(paras):
                idx = at
            if idx is None:
                continue                      # 找不到那一段，判分时会报出来
            for key, value in a.items():
                if key in ("op", "at"):
                    continue
                # 学生在 WPS 里点的是调色板，存进 .docx 的是十六进制；
                # 检查点写的是「红色」，这里替他挑一个真红色
                if key == "color" and value in sim.COLOR_ALIASES:
                    value = "#" + sorted(sim.COLOR_ALIASES[value])[0]
                paras[idx][key] = value
        elif op == "text":
            old, new = a.get("absent"), a.get("present")
            if old:
                for p in paras:
                    p["text"] = str(p["text"]).replace(old, new or "")
        elif op == "order" and a.get("last"):
            tail = a["last"]
        elif op == "page":
            page.update({k: v for k, v in a.items() if k != "op"})
        elif op in ("header", "footer"):
            word = a.get("equals") or a.get("has") or ""
            if op == "header":
                header = word
            else:
                footer = word
    if tail:
        keep = [p for p in paras if tail not in str(p.get("text") or "")]
        moved = [p for p in paras if tail in str(p.get("text") or "")]
        paras = keep + (moved or [{**sim.blank_para(), "text": tail}])
    (box / docx_io.docx_name(env)).write_bytes(docx_io.build_docx(
        {**env, "paras": paras, "page": page, "header": header, "footer": footer}))


def check_one(row: dict, work: Path, loud: bool = False) -> tuple:
    """返回 (类别, 得分, 满分, 一句话)。"""
    got = stem_rules.auto_sim(row["stem"], row["scope"])
    if not got:
        return "drag", 0, 0, "题干解析不出操作 → 按拖拽题处理（exe 里占位，老师评阅）"

    kind, env, checks = got["kind"], got["env"], got["checks"]
    if kind == "ai":
        ran = sim.run_checks("ai", sim.checks_for("ai", checks, row["stem"], 10),
                             {"messages": [{"role": "user", "text": row["stem"]}]})
        return kind, ran["score"], ran["full"], "把题干原样提交就能拿分"

    files = _files_of(kind, env)
    logical = _root_of(kind, env)
    box = work / f"q{row['id']}"
    shutil.rmtree(box, ignore_errors=True)
    box.mkdir(parents=True)
    for rel, data in files.items():
        target = box / rel
        if data is None:
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    if not files:
        return kind, 0, 0, "考场是空的 —— 一个文件都没铺出来"

    do_the_work(kind, env, checks, box, logical)
    # 打开的是什么：win 和 html 打开文件夹，wps 打开那份文档
    first = sorted(files)[0]
    open_rel = (first.split("/")[0] if kind in ("win", "html")
                else (docx_io.docx_name(env) if kind == "wps" else first))
    state = states.state_for(kind, box, open_rel, logical)
    ran = sim.run_checks(kind, checks, state)

    if loud:
        print("题干：", " ".join(row["stem"].split())[:220])
        print("\n铺出来的东西：")
        for rel in sorted(files):
            print("   ", rel + ("/" if files[rel] is None else ""))
        print("\n检查点：")
        for r in ran["results"]:
            print(f"   [{'√' if r['ok'] else '×'}] {r['desc']}（{r['score']} 分）"
                  f"　—— {r['why']}")

    bad = [r["why"] for r in ran["results"] if not r["ok"]]
    return kind, ran["score"], ran["full"], "满分" if not bad else "；".join(bad[:2])


def main() -> int:
    ap = argparse.ArgumentParser(description="操作题体检")
    ap.add_argument("--xlsx", default="", help="体检一份导出的 Excel，不给就读题库")
    ap.add_argument("-n", type=int, default=0, help="只看第几道（从 1 数），打印细节")
    args = ap.parse_args()

    rows = from_xlsx(Path(args.xlsx)) if args.xlsx else from_db()
    print(f"操作题 {len(rows)} 道\n")
    work = Path(tempfile.mkdtemp(prefix="opcheck-"))
    bad, drag = [], []

    for i, row in enumerate(rows, 1):
        if args.n and i != args.n:
            continue
        kind, score, full, why = check_one(row, work, loud=bool(args.n))
        flag = "√" if (full and score == full) else ("·" if kind == "drag" else "×")
        print(f"{flag} {i:3d}. [{row['scope'][:10]:10s}] {kind:5s} {score:3d}/{full:<3d} {why[:46]}")
        if kind == "drag":
            drag.append(i)
        elif not full or score != full:
            bad.append(i)

    print()
    if bad:
        print(f"**有问题的 {len(bad)} 道**：{bad}")
        print("判不满就是题目不自洽 —— 上面那一行写了是哪一条没过。")
    else:
        print("全部自洽：铺得出文件，照着题干做对就能判满分。")
    if drag:
        print(f"按拖拽题处理的 {len(drag)} 道：{drag}（exe 里占位，由老师评阅）")
    shutil.rmtree(work, ignore_errors=True)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
