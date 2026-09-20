"""桌面客户端（desktop/）和网页后台之间的那条线。

## 桌面端不是另一套系统

它是**这场考试的另一个客户端**。交卷走的还是 `/api/take/{token}/submit` ——
那个接口本来就是免登录、服务端判分、答卷直接进成绩页的，桌面端和网页端交上来
的东西形状一样，后端根本不在乎是谁交的。判分、成绩页、阅卷界面一行都不用改。

所以这个文件只做一件事：**把「学生机器上要有什么」打成一个包** ——
题目、初始文件、考试口令、名单。答案和检查点**一律留在服务器**。

## 四个接口，够了

    GET  /api/desk/ping           探活，开考前让监考老师知道网通不通
    POST /api/desk/signin         学生报考号姓名 → 认人 → 给他自己的考试列表
    GET  /api/desk/exam/{token}   学生取卷：下载这场考试的 .ekb（免登录）
    GET  /api/desk/export/{id}    老师手工导包，给没网的考场留的后路

`signin` 是整条链路的关键：**机房里只分发 exe，不发考试包**。学生开机输考号，
客户端拿着考号去问服务器"我是谁、我今天考什么"，答案全部来自教师端的库
（students / exams / papers），老师在网页上组卷发布，考场这边立刻就能考。

名单不再是包里的一份拷贝，而是**每次开考现问现答** —— 老师临时加个转学生、
改个班级，不用重新导包。

## 路径对齐（这是最容易出错的一处）

网页版仿真器里的路径是 `C:/EXAM/win02/会徽` 这样的绝对写法，检查点也按这个
写。桌面客户端在真机上铺考场，考试文件夹可能在 `C:\EXAM`，也可能在别处，
它拍的快照是**相对考试文件夹**的。

对齐办法：包里带一个 `logical_root`（就是仿真环境里那个公共前缀），
客户端交卷前把快照的每个路径都加上这个前缀。这样服务器那边的检查点
一个字都不用改。

## 桌面端支持哪些操作题

题目配图也在包里（`images/`）：题库里的图是 jpg，而 Tkinter 只认 PNG，
所以在这儿转一道（见 services/images.py）。不转的话带图题在学生机上就是没有图。

    win   仿真环境里的文件原样铺到真机，交卷时拍文件夹快照
    wps   段落模型写成真 .docx，学生用真 WPS 改，交卷时读回段落比格式
    html  网页文件原样铺出去，学生用记事本改，交卷时读回源码
    ai    对话式的题，成果不在文件系统里，由客户端的对话框收集

三类操作题**都是自动判分**，用的还是老师在网页仿真器里点出来的那份检查点。
"""

import io
import json
import zipfile
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from urllib.parse import quote

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Exam, ExamSubmission, Student, User
from ..schemas import ExamBrief, SignInIn, SignInOut, StudentBrief
from ..services import docx_io, images
from ..services.exam import group_items, load_items, strip_answers

router = APIRouter(prefix="/api/desk", tags=["桌面客户端"])

PKG_FORMAT = 1
DESK_KINDS = ("win", "html", "wps", "ai")


def _dump(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=1).encode("utf-8")


def _common_root(paths) -> str:
    """一堆 C:/EXAM/win02/… 的公共前缀。没有就返回空串。

    **盘符本身（"C:"）要排除在外**：网页仿真器里有时会把盘符也当一个节点存进
    环境，它的"父目录"是空的，参与计算会把公共前缀直接算成空 —— 于是桌面端
    交上来的快照不加前缀，那道题全班判 0 分，报错还是"找不到文件"。
    老师手工建的那道题就踩了这个，测出来才发现。
    """
    parts = None
    for p in paths:
        rel = str(p).replace("\\", "/")
        if "/" not in rel.rstrip("/"):
            continue                     # "C:" 这种光杆盘符，跳过
        bits = rel.split("/")[:-1]
        parts = bits if parts is None else [a for a, b in zip(parts, bits) if a == b]
        if not parts:
            return ""
    return "/".join(parts or [])


def _files_of(kind: str, env: dict) -> dict:
    """把仿真环境变成"要铺到考场机器上的文件"。

    返回 {相对路径: bytes 或 None}，None 表示这是个空文件夹 ——
    **空文件夹必须单独列出来**：「在『会徽』文件夹中新建……」这类题，
    会徽本身就是空的，漏了它学生打开就找不到地方。
    """
    out: dict[str, bytes | None] = {}
    if kind == "win":
        fs = env.get("fs") or {}
        root = _common_root(fs.keys()) or _common_root(list(fs.keys()) + ["x"])
        for path, node in fs.items():
            rel = str(path).replace("\\", "/")
            if root and rel.startswith(root + "/"):
                rel = rel[len(root) + 1:]
            elif root and rel == root:
                continue
            if not rel:
                continue
            if (node or {}).get("type") == "dir":
                out[rel] = None
            else:
                # 文本内容按 GBK 落盘：考场是 XP/Win7，记事本默认就是 ANSI，
                # 这样学生打开看到的和老师出题时看到的才一致
                text = str((node or {}).get("content") or "")
                out[rel] = text.encode("gbk", "replace") if text else b""
    elif kind == "html":
        for name, text in (env.get("files") or {}).items():
            out[str(name)] = str(text or "").encode("utf-8")
    elif kind == "wps":
        # 仿真环境里文档是一串段落，不是文件。桌面端要让学生在**真 WPS 里**做，
        # 就得先有个真文件 —— 这里把段落写成标准 .docx。
        # 学生改完存盘，客户端再读回段落交上来，检查点两边通用。
        out[docx_io.docx_name(env)] = docx_io.build_docx(env)
    return out


def _root_of(kind: str, env: dict) -> str:
    """快照前缀。只有 win 题需要 —— 它交的是绝对路径的文件夹快照；
    wps 交的是文档本身，html 交的是源码，都不带路径。"""
    if kind != "win":
        return ""
    return _common_root((env.get("fs") or {}).keys())


@router.get("/ping", summary="客户端探活")
def ping():
    """桌面客户端启动时探一下服务器通不通，好早点提示监考老师。"""
    return {"ok": True, "server": settings.public_base_url or "", "at": datetime.now().isoformat()}


def build_package(db: Session, exam: Exam, server: str = "") -> bytes:
    """把一场考试打成 .ekb（zip）。老师手工导包和学生联网取卷共用这一份。

    **只有这一个地方生产考试包**，答案不出后端这条规矩就只需要在这里守住。
    """
    items = load_items(db, exam.paper)
    if not items:
        raise HTTPException(status_code=400, detail="这场考试的卷子是空的")

    # 学生能看的那一份，和网页端取卷走同一个函数 —— 答案和检查点在这一步摘掉
    groups = strip_answers(group_items(items))
    paper, files, logical_root = [], {}, ""
    pics: dict[str, bytes] = {}
    no = 0
    for g in groups:
        for q in g["items"]:
            no += 1
            row = {
                "id": str(q["id"]), "no": no, "type": q["type"],
                "stem": q.get("stem", ""), "score": int(q.get("score") or 0),
                "section": g.get("name") or q["type"],
            }
            if q.get("options"):
                row["options"] = q["options"]
            # 配图：转成 PNG 放进包里。**不转的话学生看到的是一道没有图的带图题**
            # —— Tkinter 不认 JPEG，而题库里的图基本都是 jpg
            got_img = images.as_png(q.get("image_url") or "")
            if got_img:
                name, data = got_img
                pics[name] = data
                row["image"] = name
            sim = q.get("sim") or {}
            if sim:
                kind = sim.get("kind")
                if kind not in DESK_KINDS:
                    # 没见过的题型，桌面端不敢瞎判，题目照出、按人工评阅走
                    row["sim"] = {"kind": kind or "", "open": "", "manual": True}
                else:
                    got = _files_of(kind, sim.get("env") or {})
                    files.update(got)
                    logical_root = logical_root or _root_of(kind, sim.get("env") or {})
                    first = sorted(got)[0] if got else ""
                    row["sim"] = {
                        "kind": kind,
                        # win 题打开所在文件夹，wps/html 题直接打开那个文件
                        "open": first.split("/")[0] if kind == "win" else first,
                        # 三类都能自动判分了：win 看文件夹快照、wps 看文档格式、
                        # html 看源码。manual 只留给没配仿真环境的题
                        "manual": False,
                    }
            paper.append(row)

    roster = _roster(db, exam)
    base = (server or settings.public_base_url or "").strip().rstrip("/")
    manifest = {
        "format": PKG_FORMAT,
        "exam_id": str(exam.id),
        "title": exam.title,
        "school": exam.paper.school or "",
        "duration_min": _minutes(exam.paper.duration),
        "count": len(paper),
        "full_score": sum(q["score"] for q in paper),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        # 桌面端交卷就是拿这两样去调 /api/take/{token}/submit
        "server": base,
        "token": exam.token,
        # 快照路径要加的前缀，服务器这边的检查点才对得上
        "logical_root": logical_root,
        "roster": roster,
    }

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", _dump(manifest))
        z.writestr("paper.json", _dump(paper))
        for rel, data in sorted(files.items()):
            if data is None:
                z.writestr("files/" + rel.rstrip("/") + "/", b"")
            else:
                z.writestr("files/" + rel, data)
        # 配图单独一层，不跟考场文件混在一起 —— 它们不铺到 C:\EXAM，
        # 是答题界面上显示用的
        for name, data in sorted(pics.items()):
            z.writestr("images/" + name, data)

    return buf.getvalue()


def _as_download(raw: bytes, title: str) -> Response:
    return Response(
        content=raw,
        media_type="application/octet-stream",
        headers={"Content-Disposition":
                 f"attachment; filename*=UTF-8''{quote(title + '.ekb')}"},
    )


@router.get("/export/{exam_id}", summary="老师手工导出桌面考试包（.ekb）")
def export_pkg(
    exam_id: int,
    server: str = Query("", description="客户端交卷要连的服务器地址，留空用配置里的"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """给没网的考场留的后路：导出来拷 U 盘，和 exe 放一个文件夹。

    正常流程不用它 —— 学生端联网 signin 之后自己就把卷子取下来了。
    """
    exam = db.get(Exam, exam_id)
    if not exam or not exam.paper:
        raise HTTPException(status_code=404, detail="这场考试不存在")
    return _as_download(build_package(db, exam, server), exam.title)


@router.post("/signin", response_model=SignInOut, summary="学生端认人：我是谁、我考什么")
def signin(body: SignInIn, db: Session = Depends(get_db)):
    """考号 + 姓名 → 教师端库里的那个学生 → 他今天能考的考试。

    **这里不发口令给不相干的人**：只返回目标班级包含该生的考试。老师在网页上
    「发布考试」时选的班级，就是这里的准入名单，不用再维护第二份。

    故意不做成"登录"：学生没有密码，学号也不是秘密（同班同学都知道）。真正的
    防线在别处 —— 答案和检查点永远不出后端，判分在服务端做，同一学号只能交一次。
    这个接口能做到的是**别把卷子发给不该考的人**，做到这一点就够了。
    """
    no = (body.student_no or "").strip()
    name = (body.name or "").strip()
    if not no:
        raise HTTPException(status_code=400, detail="请输入考号")

    stu = db.scalar(select(Student).where(Student.student_no == no, Student.is_active.is_(True)))
    if not stu:
        raise HTTPException(status_code=404, detail="名单里没有这个考号，请找监考老师")
    if name and stu.name != name:
        raise HTTPException(status_code=403, detail=f"考号 {no} 对应的姓名不是「{name}」")

    rows = db.scalars(
        select(Exam).where(Exam.is_open.is_(True)).order_by(Exam.created_at.desc())
    ).all()
    mine = []
    for exam in rows:
        if not _covers(exam, stu.student_class):
            continue
        if not exam.paper:
            continue
        done = db.scalar(
            select(ExamSubmission).where(ExamSubmission.exam_id == exam.id,
                                         ExamSubmission.student_no == no)
        )
        mine.append(ExamBrief(
            id=exam.id,
            title=exam.title,
            token=exam.token,
            duration_min=_minutes(exam.paper.duration),
            submitted=bool(done),
            # 交过卷又不许重考的，客户端直接灰掉，别让学生白考一场才被 409 挡回来
            can_take=bool(exam.allow_retake or not done),
        ))

    return SignInOut(
        student=StudentBrief(no=stu.student_no, name=stu.name, cls=stu.student_class),
        exams=mine,
    )


@router.get("/exam/{token}", summary="学生端取卷：下载这场考试的考试包")
def fetch_pkg(
    token: str,
    server: str = Query("", description="交卷要连的地址，留空用配置里的"),
    db: Session = Depends(get_db),
):
    """免登录，凭口令取卷 —— 和网页端 `/api/take/{token}` 同一个准入规则。

    包里依然没有答案、没有检查点（build_package 保证）。学生机上能拿到的最多
    是题目本身，那本来就印在卷子上。
    """
    exam = db.scalar(select(Exam).where(Exam.token == token))
    if not exam or not exam.paper:
        raise HTTPException(status_code=404, detail="口令无效，请向老师确认")
    if not exam.is_open:
        raise HTTPException(status_code=403, detail="这场考试已经关闭")
    return _as_download(build_package(db, exam, server), exam.title)


def _covers(exam: Exam, cls: str) -> bool:
    """这场考试面向这个班吗。没写目标班级 = 全校统考，谁都能考。"""
    names = [c.strip() for c in (exam.target_classes or "").split(",") if c.strip()]
    return not names or (cls or "").strip() in names


def _roster(db: Session, exam: Exam) -> list[dict]:
    """名单直接取这场考试的目标班级 —— 老师不用再手工维护一份。

    没指定班级（全校统考）就不带名单，客户端那边也就不核对。
    一场考试的名单动辄几百人，全带上会让每台机器都多下载一份，不划算。
    """
    names = [c.strip() for c in (exam.target_classes or "").split(",") if c.strip()]
    if not names:
        return []
    rows = db.scalars(
        select(Student).where(Student.student_class.in_(names), Student.is_active.is_(True))
        .order_by(Student.student_class, Student.student_no)
    ).all()
    return [{"no": s.student_no, "name": s.name, "cls": s.student_class} for s in rows]


def _minutes(duration: str) -> int:
    """卷面上的「40」「40分钟」都变成 40。"""
    digits = "".join(ch for ch in str(duration or "") if ch.isdigit())
    return int(digits) if digits else 45
