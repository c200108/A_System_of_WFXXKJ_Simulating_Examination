"""补充题库：跟着代码走的一批题，**新部署、老服务器升级都会自动有**。

## 为什么不放进 legacy/ 那份原题库

原题库（legacy/信息技术组卷台.html）只在**题库是空的时候**灌一次 —— 已经在用的
服务器、导过数据的机房版都不会再读它。补充题要的是"拉了新代码就有"，所以单独
放这里，由 app.seed 每次启动时补一遍：

- 按题干哈希查重，库里已有（包括老师删到回收站里的）就跳过，**不会重复插入**，
  也不会把老师删掉的题又变出来；
- 老师在题库里改过补充题（改了题干就是另一道题了），原样不动；
- 来源一律记「补充题」，题库页按来源一筛就能看到这一批。

## 题目的环境和得分点

操作题的考场文件和检查点不存在这里，存在 services/win_bank.py、services/wps_bank.py
—— 和原题库的操作题一样**按题干现算**（stem.auto_sim），导库、换版本都丢不了。

## 加一道补充题

1. 在 QUESTIONS 里加一条（题干照考场里的写法写全，学生只看得到题干）；
2. 操作题再去 win_bank / wps_bank 里写死环境和检查点；
3. 跑 `python backend/tools/验操作题.py`，照着做对必须满分。
"""

from __future__ import annotations

from typing import List

SOURCE = "补充题"

QUESTIONS: List[dict] = [
    {
        "code": "B001",
        "type": "操作题",
        "scope": "Windows系统操作",
        "stem": (
            "本题工作目录:D:\\EXAM\n"
            "请打开本题工作目录下的\"win\"文件夹，按要求完成以下操作:\n"
            "①在\"win\"文件夹中新建一个文件夹，命名为\"图片资料\"。\n"
            "②在\"win\"文件夹中新建一个文件夹，命名为\"文档资料\"。\n"
            "③把\"智慧课堂.jpg\"和\"机器人比赛.png\"两个文件同时复制到\"图片资料\"文件夹中"
            "（原来的两个文件仍要保留）。\n"
            "④把\"学习笔记.txt\"移动到\"文档资料\"文件夹中（原来的位置不再保留该文件）。\n"
            "⑤在\"文档资料\"文件夹中新建一个Word文档，命名为\"人工智能学习心得.docx\"。\n"
            "⑥在\"图片资料\"文件夹中新建一个演示文稿，命名为\"科技节汇报.pptx\"。\n"
            "⑦删除\"win\"文件夹中的\"废弃文件.txt\"。"
        ),
        "answer": (
            "①进入win文件夹，右键空白处选择【新建】-【文件夹】，命名为“图片资料”；"
            "②同样方法新建文件夹“文档资料”；"
            "③按住Ctrl同时选中“智慧课堂.jpg”和“机器人比赛.png”，右键【复制】，进入“图片资料”右键【粘贴】；"
            "④右键“学习笔记.txt”选择【剪切】，进入“文档资料”右键【粘贴】；"
            "⑤进入“文档资料”，右键【新建】-【DOCX 文档】（Word文档），命名为“人工智能学习心得.docx”；"
            "⑥进入“图片资料”，右键【新建】-【PPTX 演示文稿】，命名为“科技节汇报.pptx”；"
            "⑦回到win文件夹，选中“废弃文件.txt”按Delete删除。"
        ),
    },
    {
        "code": "B002",
        "type": "操作题",
        "scope": "WPS文字操作",
        "stem": (
            "本题工作目录:D:\\EXAM\n"
            "请打开本题工作目录中的\"人工智能改变生活.docx\"，完成以下操作:\n"
            "①把文中的错别字用\"查找替换\"全部改正：\"智彗\"改为\"智慧\"，\"深渡\"改为\"深度\"，"
            "\"科计\"改为\"科技\"。\n"
            "②把标题\"人工智能改变生活\"设置为：黑体、二号、居中对齐。\n"
            "③把标题下面的第一段（替换后以\"从智慧家居\"开头、以\"必修课。\"结尾的那一段）设置为："
            "左右各缩进2字符，段前1行、段后0.5行，行距1.5倍。\n"
            "④把其余正文段落设置为：宋体、四号字，首行缩进2字符，行距固定值24磅。\n"
            "⑤在文章最后另起一段，输入下面这段文字:\"作为新时代的中学生，我们要努力学习科学知识，"
            "积极动手实践，迎接人工智能时代的到来。对于人工智能的应用，我们要合理使用，认真辨别。"
            "我们应该遵守法律法规，成为数字时代的合法公民。这也意味着在享受技术便利的同时，"
            "主动承担起维护网络秩序的责任。\"\n"
            "⑥以原文件名、原位置保存文档后关闭。"
        ),
        "answer": (
            "①【开始】-【查找替换】-【替换】，依次把“智彗”替换为“智慧”、“深渡”替换为“深度”、"
            "“科计”替换为“科技”，每次点【全部替换】；"
            "②选中标题，字体选黑体、字号选二号，点【居中对齐】；"
            "③选中第一段，右键【段落】，文本之前、文本之后各缩进2字符，段前1行、段后0.5行，"
            "行距选1.5倍行距；"
            "④选中其余三段，字体宋体、字号四号，右键【段落】，特殊格式选首行缩进2字符，"
            "行距选固定值、设置值24磅；"
            "⑤光标移到文末按回车另起一段，输入指定文字；"
            "⑥按Ctrl+S保存后关闭WPS。"
        ),
    },
]


def seed_supplement(db) -> int:
    """库里没有的补充题补进去，返回新增几道。调用方负责 commit。"""
    from sqlalchemy import select

    from ..models import Question
    from .difficulty import estimate
    from .importer import stem_hash

    have = set(db.scalars(select(Question.stem_hash)).all())
    added = 0
    for item in QUESTIONS:
        h = stem_hash(item["stem"])
        if h in have:
            continue
        db.add(Question(
            code=item["code"], type=item["type"], stem=item["stem"], stem_hash=h,
            answer=item["answer"], scope=item["scope"], source=SOURCE,
            difficulty=estimate(item["type"], item["stem"], item["scope"], 0),
        ))
        have.add(h)
        added += 1
    return added


def is_supplement(stem: str) -> bool:
    from .importer import stem_hash
    return stem_hash(stem) in {stem_hash(q["stem"]) for q in QUESTIONS}
