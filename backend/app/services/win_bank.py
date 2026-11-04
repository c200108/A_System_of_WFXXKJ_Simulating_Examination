"""Windows 操作题：按题库里的**完整原题**逐题写死的考场文件和检查点。

和 wps_bank.py 是一个道理：通用规则（stem.py 的 parse_win）是按题干句式猜的，
「在"win"文件夹中新建一个文件夹，命名为"图片资料"」「把 A 和 B 两个文件同时复制到……」
这种写法它认不全，还会把文件铺错地方。补充题是老师照着真机考场出的，考场里有
哪些文件、每一问怎么判，照着原题写清楚。

## 真文件素材

考场里的图片要是**真图片**：学生在真机上双击能打开，才像真考场。
文件节点上带 `asset`（相对 app/assets/ 的路径），桌面端铺考场时读这个文件的
原始字节落盘（见 routers/desk.py 的 _files_of）；网页仿真器不认这个键，照旧显示
占位图 —— 那边本来就不加载真实图片。

## 怎么接进来

stem.parse_win() 先按题干里的关键句查这张表，查到就用这里的，查不到才走通用规则。
返回的路径**不带** C:/EXAM 前缀，和 parse_win 的输出一样，由 stem.auto_sim 统一加。
"""

from __future__ import annotations

from typing import List, Optional


def C(desc: str, score: int, is_: str = "", **assertion) -> dict:
    """一条检查点。is_ 就是断言里的 is（"dir"/"file"），Python 关键字只好绕一下。"""
    if is_:
        assertion["is"] = is_
    return {"desc": desc, "score": score, "assert": assertion}


def D() -> dict:
    return {"type": "dir"}


def F(content: str = "", asset: str = "") -> dict:
    node = {"type": "file", "content": content}
    if asset:
        node["asset"] = asset
    return node


# ================================================================ 各题
NOTE_TEXT = ("人工智能学习笔记\n\n1. 人工智能简称 AI。\n2. 人脸识别属于计算机视觉。\n"
             "3. 生成式 AI 可以生成文章、图像和音乐。\n")


def _s_win_ai_life() -> dict:
    """补充题·Windows：2026 潍坊中考操作题专项「课堂操作综合例题_人工智能」第一部分。

    检查点分值是占本题的百分比（合计 100），本题在卷面上占几分由组卷时定，
    判分按比例折算（exam.scale_sim）。
    """
    w = "win"
    fs = {
        w: D(),
        f"{w}/学习笔记.txt": F(NOTE_TEXT),
        f"{w}/废弃文件.txt": F("这是一个废弃的旧文件，按题目要求将它删除。\n"),
        f"{w}/智慧课堂.jpg": F("[智慧课堂].jpg 考试素材文件",
                            asset="supplement/win_ai_life/zhihui_ketang.jpg"),
        f"{w}/机器人比赛.png": F("[机器人比赛].png 考试素材文件",
                             asset="supplement/win_ai_life/jiqiren_bisai.png"),
    }
    pic, doc = f"{w}/图片资料", f"{w}/文档资料"
    checks = [
        C("① 新建文件夹「图片资料」", 10, op="exists", path=pic, is_="dir"),
        C("② 新建文件夹「文档资料」", 10, op="exists", path=doc, is_="dir"),
        # 复制要两头都看（copied）：目标有、原文件也在。拆成两条，什么都不做也白拿「原文件在」的分
        C("③ 「智慧课堂.jpg」复制到「图片资料」（原文件保留）", 10, op="copied",
          path=f"{pic}/智慧课堂.jpg", **{"from": f"{w}/智慧课堂.jpg"}),
        C("③ 「机器人比赛.png」复制到「图片资料」（原文件保留）", 10, op="copied",
          path=f"{pic}/机器人比赛.png", **{"from": f"{w}/机器人比赛.png"}),
        C("④ 「文档资料」里有「学习笔记.txt」", 8, op="exists", path=f"{doc}/学习笔记.txt", is_="file"),
        C("④ 移过去的是原来那份笔记（内容没变）", 4, op="content", path=f"{doc}/学习笔记.txt",
          has="人脸识别属于计算机视觉"),
        C("④ 是移动：原位置不再有「学习笔记.txt」", 8, op="missing", path=f"{w}/学习笔记.txt"),
        C("⑤ 「文档资料」里新建「人工智能学习心得.docx」", 16, op="exists",
          path=f"{doc}/人工智能学习心得.docx", is_="file"),
        C("⑥ 「图片资料」里新建「科技节汇报.pptx」", 14, op="exists",
          path=f"{pic}/科技节汇报.pptx", is_="file"),
        C("⑦ 删除「废弃文件.txt」", 10, op="missing", path=f"{w}/废弃文件.txt"),
    ]
    return {"fs": fs, "checks": checks}


# 按题干里的关键句认题。两句都在才算 —— 只认一句容易撞上别的题
BANK = [
    (("人工智能学习心得.docx", "科技节汇报.pptx"), _s_win_ai_life),
]


def lookup(stem: str) -> Optional[dict]:
    """在表里就返回 {"kind": "win", "env", "checks", "todo": []}，不在返回 None。"""
    text = str(stem or "")
    for keys, make in BANK:
        if all(k in text for k in keys):
            got = make()
            return {"kind": "win", "env": {"fs": got["fs"], "recycle": {}},
                    "checks": got["checks"], "todo": []}
    return None


def names() -> List[str]:
    return [keys[0] for keys, _ in BANK]
