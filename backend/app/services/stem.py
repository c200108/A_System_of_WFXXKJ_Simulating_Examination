"""读题干，造检查点。

## 为什么需要它

题库里 43 道操作题，只有 1 道配了仿真环境和检查点 —— 其余 42 道只有题干。
判分引擎再全，没有检查点也判不了。手工给 42 道题点环境、点检查点，是几天的活。

好在这些题干**格式高度统一**（都是中考信息技术的标准写法）：

    本题工作目录:D:\\EXAM\\windows操作
    请打开本题工作目录下的系统基本操作文件夹，按要求完成以下操作:
    ①在"动物"文件夹中新建一个名为"珍稀动物"的文件夹。
    ②将"爱护动物.jpg"文件复制到"动物世界"文件夹中。

一句一个操作，动词就那么几个。所以能从题干直接算出**初始环境**和**检查点**。

## 造出来的东西要老师过一眼

这是**草稿，不是成品**。解析器认不出来的句子会原样留在 `todo` 里，老师在网页
仿真器里补。所以工具默认只打印不写库，要写得显式加 `--apply`（见
`backend/tools/stem_to_sim.py`）。

## 初始环境是倒推的

题干只说"要做成什么样"，没说"现在是什么样"。但两者是对应的：

    「把 A 里的 F 移动到 B」  →  开考时 A/F 得在、B 得在
    「在 C 里新建 D」        →  开考时 C 得在、D 不能在
    「把 E 删掉」            →  开考时 E 得在

倒推出来的环境不一定和原卷一模一样（原卷里可能还有别的干扰文件），但**判分
需要的那几个对象一个不缺**，这就够用了。

顺带解掉一个看着吓人的歧义：「在winkt\培训文件夹中新建」—— 文件夹是叫「培训」
还是叫「培训文件夹」？中文里两种写法长得一模一样。**但这不影响判分**：初始环境
和检查点都是这里一起生成的，两边用的是同一个名字，学生在磁盘上看到什么就在什么
里做。只有"拿原卷的素材配我们生成的检查点"时才会对不上，而原卷素材本来就不在
题库里。
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from . import drag
from .sim import blank_para

# 仿真环境里的路径统一带这个前缀，和老师在网页仿真器里点出来的写法一致
ROOT = "C:/EXAM"

# 题干里的引号五花八门：中文引号、英文引号、书名号式的方引号
Q = r"[\"“”'‘’「」『』]"
ITEM = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]|\(\d\)|（\d）|^\s*\d[．.、]")


def _clean(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).replace("：", ":")


def _quoted(text: str) -> list[str]:
    """揪出题干里所有引号包着的东西 —— 文件名、文件夹名、要替换的词都在引号里。"""
    return [m.group(1) for m in re.finditer(Q + r"([^\"“”'‘’「」『』]{1,60})" + Q, text)]


def split_items(stem: str) -> list[str]:
    """按 ①②③ 把题干拆成一条条操作。

    拆不开时整段当一条 —— 有些题只有一句话（「请将符合智能家居的设备拖拽到
    指定区域」），拆了反而丢信息。
    """
    text = str(stem or "").replace("\r", "")
    parts = re.split(r"(?=[①②③④⑤⑥⑦⑧⑨⑩])", text)
    got = [p.strip() for p in parts[1:] if p.strip()]
    if got:
        return got
    # 没有 ①②③ 的，退一步按 "1." "(1)" 拆
    parts = re.split(r"(?=(?:^|\n)\s*(?:\(\d\)|（\d）|\d[．.、]))", text)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) > 6] or [text.strip()]


def guess_kind(stem: str, scope: str = "") -> str:
    """这道题是哪一类。

    **先看题干再看知识范围** —— 题库里知识范围填错的不少：有三道明明是 WPS
    文字题，知识范围却挂在「Windows系统操作」下面。

    `.docx` 要看动词才能定性，这是踩过的：

        「请打开本题工作目录中的"物联网改变生活.docx"」  → WPS 文字题
        「在"IT"文件夹下创建"计算机技术.docx"文件」      → **文件操作题**

    只看见 .docx 就当 WPS，后一道会被配上一个文档环境，整道题判不了。
    """
    flat = _clean(stem)
    if "AI工具" in flat or "生成式人工智能" in flat:
        return "ai"
    # 别把「标签」单独当线索：「带有电子标签的餐盘」是物联网题，被它误判过
    if re.search(r"HTML|网页标题|网页中的图片|网页背景|一级标题|<[a-z]+>|HTML标签",
                 flat, re.I):
        return "html"
    # **文件管理的动词一出现就是文件操作题**，哪怕文件名是 .doc。
    # 踩过：「请打开本题工作目录下的 win06 文件夹……把"重阳节.doc"重命名为
    # "老人节.doc"」——"打开"后面 40 个字内出现了 .doc，被当成 WPS 文字题，
    # 于是整道题配了个文档环境，五问一问也判不出来。
    # 「移动到」光有动词不算数：WPS 题里"把第四段移动到文章末尾"也是移动。
    # 必须连着文件夹/文件才算文件管理 —— 否则排版题会被当成文件操作题，
    # 整道题一个检查点也出不来。
    filework = re.search(r"重命名|改名为"
                         r"|(?:移动|复制)(?:到|至)[^。]{0,20}文件夹"
                         r"|文件夹[^。]{0,12}(?:移动|复制)"
                         r"|删除[^。]{0,10}文件夹?"
                         r"|(?:新建|建立|创建)[^。]{0,10}文件夹", flat)
    # 排版术语 → WPS 文字题
    typo = re.search(r"替换(?:为|成)|首行缩进|段前|段后|行距|对齐|自然段|页眉|页脚"
                     r"|纸张|边距|字号|字形|分栏|艺术字|文本框|下划线|样式", flat)
    if "WPS文字" in flat or (typo and not filework):
        return "wps"
    # 打开/编辑某个 .docx（而且不是在做文件管理）→ WPS 文字题
    if re.search(r"(?:打开|编辑)[^。；;：:，,]{0,40}\.docx?", flat) and not filework:
        return "wps"
    if filework or re.search(r"文件夹|新建|创建|移动|复制|删除|重命名", flat):
        return "win"
    return {"WPS文字操作": "wps", "人工智能": "ai",
            "Windows系统操作": "win"}.get(scope, "")


# ================================================================ Windows
def _in_folder(flat: str) -> str:
    """这一句里的「在"X"文件夹中」是哪个文件夹。没写就是工作目录本身。"""
    m = re.search(r"在" + Q + r"([^\"“”'‘’「」『』]{1,30}?)" + Q + r"文件夹[中下里]", flat)
    return m.group(1) if m else ""


def _context_folder(flat: str) -> str:
    """这一句说的是**哪个文件夹里**的事。

    「在"ks"文件夹中新建……」和「将"ks"文件夹中的……」说的都是 ks 里的事，
    但后者没有"在"字。两种都要认 —— 认不出的后果是文件铺到工作目录根上，
    而题干说它在 ks 里。
    """
    m = re.search(Q + r"([^\"“”'‘’「」『』]{1,30}?)" + Q + r"文件夹[中下里]", flat)
    return m.group(1) if m else ""


def _base_dir(stem: str) -> str:
    r"""这道题的工作目录叫什么。真题里三种写法都有：

        请打开本题工作目录下的 win06 文件夹        → win06
        请打开本题工作目录（C：\EXAM\Win操作）     → Win操作
        本题工作目录:D:\EXAM\windows操作           → windows操作

    **第二种一定要认**。不认的话整道题的文件全落在考试根目录下，而题干说的是
    `C:\EXAM\Win操作` —— 学生打开工作目录，里面空空如也，题目提到的文件夹
    一个都没有。踩过这个坑。

    没写就用空串，操作路径直接挂在考试根下。
    """
    flat = _clean(stem)
    m = re.search(r"打开本题工作目录[下中]的" + Q + r"?([^\"“”'‘’「」『』，,。:：（）()]{1,20}?)"
                  + Q + r"?文件夹", flat)
    if m:
        return m.group(1)
    # 括号里（或冒号后面）给了完整路径：取最后一段当工作目录名
    m = re.search(r"(?:本题)?工作目录[^A-Za-z]{0,3}([A-Za-z]:[\\/][^）)，,。；;]{1,60})", flat)
    if m:
        tail = [x for x in re.split(r"[\\/]+", m.group(1)) if x and ":" not in x]
        # 去掉最外面那层 EXAM —— 考试根本来就是它，再套一层就成了 C:/EXAM/EXAM
        while tail and tail[0].upper() in ("EXAM", "KS"):
            tail.pop(0)
        return "/".join(tail)
    return ""


TEXT_EXT = {".txt", ".log", ".csv", ".md", ".html", ".htm", ".css", ".js", ".ini"}


def file_node(name: str) -> dict:
    """给考场里的素材文件编一份内容。

    文本文件写几句和文件名相称的话，学生打开看得懂；二进制类型（图片、表格、
    数据库）**只放一行说明**：这些题考的是移动/复制/删除，学生不会去打开它们，
    而伪造一个能打开的 .jpg 不值当。
    """
    stem_name = name.rsplit(".", 1)[0]
    ext = ("." + name.rsplit(".", 1)[1].lower()) if "." in name else ""
    if ext in TEXT_EXT:
        return {"type": "file",
                "content": f"{stem_name}\n\n这是考试素材文件，用于本题的文件操作。\n"}
    return {"type": "file", "content": f"[{stem_name}]{ext} 考试素材文件"}


def _web_page(resource: str, href: str) -> dict:
    """一张真能打开的素材网页：标题 + 一条指向资料的链接。

    题干说「打开网页文件……在网页中找到 X 资料」，学生双击打开的就是这张页面，
    点那条链接（或者右键另存）就能拿到资料。用 GBK 落盘 —— 考场是中文 Windows，
    浏览器按系统默认编码认，UTF-8 会显示成乱码。
    """
    html = (f"<html><head><meta charset=\"gb2312\"><title>安全教育资料</title></head>"
            f"<body><h2>安全教育资料</h2>"
            f"<p>下面是本站提供的资料，右键另存即可下载。</p>"
            f"<ul><li><a href=\"{href}\">{resource}</a></li></ul>"
            f"</body></html>")
    return {"type": "file", "content": html}


def _join(*parts: str) -> str:
    bits = [str(p).replace("\\", "/").strip("/") for p in parts if p]
    return "/".join(b for b in bits if b)


VAGUE = re.compile(r"^(?:对应|相应|合适|最合适|恰当|正确|该|所属)的?$")


def _win_item(text: str, base: str, fs: dict, checks: list, todo: list) -> None:
    """一条 Windows 操作。认得出就写进 fs/checks，认不出丢进 todo。"""
    flat = _clean(text)
    names = _quoted(flat)

    # 「移动到**对应的**文件夹中」「移到**最合适的**文件夹」—— 目标是泛指，
    # 要学生自己判断该放哪儿。机器判不了这种题，硬判只会判错；更糟的是
    # 会在考场里建一个真叫「对应的」的文件夹，学生看了一脸问号。
    if re.search(r"(?:移动|复制|放)到(?:对应|相应|合适|最合适|恰当|正确)的?文件夹", flat):
        todo.append(text.strip())
        return

    # ① 在 A 文件夹中新建一个名为"N"的文件夹
    m = re.search(Q + r"?([^\"“”'‘’「」『』]{0,30}?)" + Q + r"?文件夹[中下里]新建一个名为"
                  + Q + r"(.+?)" + Q + r"的文件夹", flat)
    if m:
        where, name = m.group(1), m.group(2)
        fs[_join(base, where)] = {"type": "dir"}
        checks.append({"desc": f"在「{where or '工作目录'}」中新建文件夹「{name}」", "score": 5,
                       "assert": {"op": "exists", "path": _join(base, where, name),
                                  "is": "dir"}})
        return

    # ① 在 X\Y 文件夹中新建一个演示文稿文件，命名为:"N.ext"  /  在"IT"文件夹下创建"N.docx"文件
    m = re.search(r"在" + Q + r"?([^\"“”'‘’「」『』]{0,40}?)" + Q + r"?文件夹[中下里]"
                  r"(?:新建|创建).*?" + Q + r"([^\"“”'‘’「」『』]+?\.[A-Za-z0-9]{1,5})" + Q, flat)
    if m:
        where, name = m.group(1), m.group(2)
        fs[_join(base, where)] = {"type": "dir"}
        checks.append({"desc": f"在「{where or '工作目录'}」中新建文件「{name}」", "score": 5,
                       "assert": {"op": "exists", "path": _join(base, where, name),
                                  "is": "file"}})
        return

    # ① 在"A"文件夹中新建一个 word 文档，文件名为"N"（**没写扩展名**）
    m = re.search(r"在" + Q + r"?([^\"“”'‘’「」『』]{0,40}?)" + Q + r"?文件夹[中下里]"
                  r"(?:新建|创建)[^。]{0,10}?(word|Word|WORD|文本|演示文稿|表格)"
                  r"[^。]{0,8}?文件名为" + Q + r"([^\"“”'‘’「」『』]+?)" + Q, flat)
    if m:
        where, kind, name = m.group(1), m.group(2).lower(), m.group(3)
        ext = {"word": ".docx", "文本": ".txt", "演示文稿": ".pptx", "表格": ".xlsx"}[kind]
        if "." not in name:
            name += ext
        fs[_join(base, where)] = {"type": "dir"}
        checks.append({"desc": f"在「{where}」中新建「{name}」", "score": 5,
                       "assert": {"op": "exists", "path": _join(base, where, name),
                                  "is": "file"}})
        return

    # ② 将 A 文件夹中的文件"F1"和"F2"都移动到 B 文件夹中
    m = re.search(r"将" + Q + r"?([^\"“”'‘’「」『』]{0,40}?)" + Q + r"?文件夹[中下里]的文件"
                  r"(.+?)(?:都)?(移动|复制)到" + Q + r"?([^\"“”'‘’「」『』]{0,40}?)"
                  + Q + r"?文件夹", flat)
    if m:
        src, blob, verb, dst = m.group(1), m.group(2), m.group(3), m.group(4)
        files = _quoted(blob) or [x for x in re.split(r"和|、|,|，", blob) if x.strip()]
        for name in files:
            checks.append({"desc": f"把「{name}」{verb}到「{dst}」", "score": 4,
                           "assert": {"op": "exists", "path": _join(base, dst, name)}})
            if verb == "移动":
                checks.append({"desc": f"「{src}」里不再有「{name}」", "score": 2,
                               "assert": {"op": "missing", "path": _join(base, src, name)}})
            fs[_join(base, src, name)] = file_node(name)
        fs[_join(base, src)] = {"type": "dir"}
        fs[_join(base, dst)] = {"type": "dir"}
        return

    # ② 将"学习"文件夹中的"比赛.txt"移动至"winkt"文件夹  —— 「移动至」不是「移动到」
    m = re.search(Q + r"?([^\"“”'‘’「」『』]{0,40}?)" + Q
                  + r"?文件夹[中下里]的" + Q
                  + r"([^\"“”'‘’「」『』]+?)" + Q
                  + r"(?:文件)?(移动|复制)(?:到|至)" + Q
                  + r"?([^\"“”'‘’「」『』]{0,40}?)" + Q + r"?文件夹", flat)
    if m:
        src, name, verb, dst = m.group(1), m.group(2), m.group(3), m.group(4)
        # **目的地跟着源走**：「把 ks 里的 X 移到『交通安全』里」——交通安全就在
        # ks 下面，不在工作目录根上。题干里那句「保存到"ks\消防安全"下」就是
        # 证据。目的地自己写了路径（winktiles）就按它写的来。
        under = _join(base, src) if src and "/" not in dst and "\\" not in dst else base
        fs[_join(base, src, name)] = file_node(name)
        fs[_join(under, dst)] = {"type": "dir"}
        checks.append({"desc": f"把「{name}」{verb}到「{dst}」", "score": 5,
                       "assert": {"op": "exists", "path": _join(under, dst, name)}})
        if verb == "移动":
            checks.append({"desc": f"「{src}」里不再有「{name}」", "score": 3,
                           "assert": {"op": "missing", "path": _join(base, src, name)}})
        return

    # ② 以"X.rar"为名保存到"ks\消防安全"下  —— 从网页里另存资料那一问。
    #    真题里这一问考的是"会不会另存到指定位置"，判的就是那个文件在不在。
    m = re.search(r"以" + Q + r"([^\"“”'‘’「」『』]+?)" + Q + r"为名(?:保存|另存)到"
                  + Q + r"?([^\"“”'‘’「」『』]{1,40}?)" + Q + r"?[下里中]", flat)
    if m:
        name, where = m.group(1), m.group(2).replace("\\", "/")
        fs[_join(base, where)] = {"type": "dir"}
        checks.append({"desc": f"把「{name}」保存到「{where}」下", "score": 5,
                       "assert": {"op": "exists", "path": _join(base, where, name)}})
        # **这一问得真能做出来**：题干说"打开网页文件 X.htm，在网页中找到 Y 资料"，
        # 那网页里就得真有 Y 这份资料，而且真能下下来。铺一个占位文本的 .htm
        # 等于告诉学生"自己编一个吧"——他只能手工新建一个空文件蒙过去。
        page = re.search(r"网页文件" + Q + r"([^\"“”'‘’「」『』]+?\.html?)" + Q, flat)
        want = re.search(r"(?:找到|下载)" + Q + r"([^\"“”'‘’「」『』]{1,30}?)" + Q, flat)
        if page and want:
            ext = name.rsplit(".", 1)[-1] if "." in name else "rar"
            res = f"资料/{want.group(1)}.{ext}"
            fs[_join(base, "资料")] = {"type": "dir"}
            fs[_join(base, res)] = file_node(res.rsplit("/", 1)[-1])
            fs[_join(base, page.group(1))] = _web_page(want.group(1), res)
        return

    # ② 将"A"文件夹中"B"文件夹中不合适的/多余的文件删除
    #    题干没点名删哪一个 —— 那就铺一个**明显不搭**的进去，学生一眼认得出，
    #    判分看的也是同一个文件
    m = re.search(Q + r"?([^\"“”'‘’「」『』]{1,30}?)" + Q + r"?文件夹[中下里]"
                  + Q + r"([^\"“”'‘’「」『』]{1,30}?)" + Q + r"文件夹[中下里]"
                  r"(?:不合适|不恰当|多余|不属于[^。]{0,20}?)的文件(?:都)?删除", flat)
    if m:
        outer, inner = m.group(1), m.group(2)
        odd = "无关文件.txt"
        fs[_join(base, outer, inner)] = {"type": "dir"}
        fs[_join(base, outer, inner, odd)] = {
            "type": "file",
            "content": f"这个文件和「{inner}」没有关系，是本题要删掉的那一个。\n"}
        checks.append({"desc": f"删掉「{inner}」里不合适的那个文件（{odd}）", "score": 5,
                       "assert": {"op": "missing",
                                  "path": _join(base, outer, inner, odd)}})
        return

    # ② 将"F.jpg"文件复制/移动到"D"文件夹中  （源就在工作目录下）
    m = re.search(Q + r"([^\"“”'‘’「」『』]+?\.[A-Za-z0-9]{1,5})" + Q + r"(?:文件)?(复制|移动)到"
                  + Q + r"?([^\"“”'‘’「」『』]{0,40}?)" + Q + r"?文件夹", flat)
    if m:
        name, verb, dst = m.group(1), m.group(2), m.group(3)
        src = _join(base, name)
        fs[src] = file_node(name)
        fs[_join(base, dst)] = {"type": "dir"}
        checks.append({"desc": f"把「{name}」{verb}到「{dst}」", "score": 5,
                       "assert": {"op": "exists", "path": _join(base, dst, name)}})
        if verb == "移动":
            checks.append({"desc": f"原位置不再有「{name}」", "score": 3,
                           "assert": {"op": "missing", "path": src}})
        return

    # ② 把"A\B"文件夹中的"F.jpg"文件删除
    m = re.search(Q + r"?([^\"“”'‘’「」『』]{0,40}?)" + Q + r"?文件夹[中下里]的" + Q
                  + r"([^\"“”'‘’「」『』]+?)" + Q + r"(?:文件)?删除", flat)
    if m:
        where, name = m.group(1), m.group(2)
        fs[_join(base, where)] = {"type": "dir"}
        fs[_join(base, where, name)] = file_node(name)
        checks.append({"desc": f"删除「{where}」里的「{name}」", "score": 5,
                       "assert": {"op": "missing", "path": _join(base, where, name)}})
        return

    # ② 将文件"F.jpg"移动到"D"文件夹中  —— 和上一条只差「文件」两个字的位置。
    #    真题里两种语序都有，少认一种就漏判一问
    m = re.search(r"(?:将|把)文件" + Q + r"([^\"“”'‘’「」『』]+?)"
                  + Q + r"(移动|复制)到" + Q + r"?([^\"“”'‘’「」『』]{0,40}?)"
                  + Q + r"?文件夹", flat)
    if m:
        name, verb, dst = m.group(1), m.group(2), m.group(3)
        src = _join(base, name)
        fs[src] = file_node(name)
        fs[_join(base, dst)] = {"type": "dir"}
        checks.append({"desc": f"把「{name}」{verb}到「{dst}」", "score": 5,
                       "assert": {"op": "exists", "path": _join(base, dst, name)}})
        if verb == "移动":
            checks.append({"desc": f"原位置不再有「{name}」", "score": 3,
                           "assert": {"op": "missing", "path": src}})
        return

    # 「在winkt文件夹中新建文件夹"机器人"」/「新建一个名为"X"的文件夹」
    m = re.search(r"在" + Q + r"?([^\"“”'‘’「」『』]{0,30}?)" + Q
                  + r"?文件夹[中下里]新建文件夹" + Q
                  + r"([^\"“”'‘’「」『』]+?)" + Q, flat)
    if m:
        where, name = m.group(1), m.group(2)
        fs[_join(base, where)] = {"type": "dir"}
        checks.append({"desc": f"在「{where}」中新建文件夹「{name}」", "score": 5,
                       "assert": {"op": "exists", "path": _join(base, where, name),
                                  "is": "dir"}})
        return

    # 「在"A"文件夹中，新建名为"B"的文件夹」/「建立一个新的文件夹"B"」——
    # 真题里"新建"和"建立"、"名为X的文件夹"和"文件夹X"四种搭配都有，
    # 少认一种就漏判一问
    m = re.search(r"在" + Q + r"?([^\"“”'‘’「」『』]{0,30}?)" + Q
                  + r"?文件夹[中下里]?[，,]?\s*(?:新建|建立|创建)[^。]{0,8}?"
                  + Q + r"([^\"“”'‘’「」『』]+?)" + Q + r"(?:的)?文件夹", flat)
    if m:
        where, name = m.group(1), m.group(2)
        fs[_join(base, where)] = {"type": "dir"}
        checks.append({"desc": f"在「{where or '工作目录'}」中新建文件夹「{name}」", "score": 5,
                       "assert": {"op": "exists", "path": _join(base, where, name),
                                  "is": "dir"}})
        return

    # 「在"外国节日"文件夹中建立一个新的文件夹"圣诞节"」—— 名字跟在"文件夹"**后面**
    m = re.search(r"在" + Q + r"?([^\"“”'‘’「」『』]{0,30}?)" + Q
                  + r"?文件夹[中下里][^。]{0,10}?(?:新建|建立|创建)[^。]{0,6}?文件夹"
                  + Q + r"([^\"“”'‘’「」『』]+?)" + Q, flat)
    if m:
        where, name = m.group(1), m.group(2)
        fs[_join(base, where)] = {"type": "dir"}
        checks.append({"desc": f"在「{where or '工作目录'}」中新建文件夹「{name}」", "score": 5,
                       "assert": {"op": "exists", "path": _join(base, where, name),
                                  "is": "dir"}})
        return

    m = re.search(r"(?:新建|建立|创建)(?:一个)?(?:新的)?(?:名为)?" + Q + r"(.+?)" + Q
                  + r"(?:的)?文件夹", flat)
    if m:
        name = m.group(1)
        checks.append({"desc": f"新建文件夹「{name}」", "score": 5,
                       "assert": {"op": "exists", "path": _join(base, name), "is": "dir"}})
        return

    # ③ 在"X"文件夹中，将按名称排序后的**中间一个**文件改名为"Y.doc"
    #    题干没点名是哪个文件，那就铺一组出来，让"中间一个"只有一种理解。
    #    漏过一次：这一问整句没认出来，考场里连「长江中下游平原」文件夹都没有。
    m = re.search(r"(?:按|以)?(?:名称|名字|文件名)排序(?:后)?的?(?:最)?中间(?:的)?(?:那)?一个文件"
                  r"(?:重命名|改名)为" + Q + r"([^\"“”'‘’「」『』]+?)" + Q, flat)
    if m:
        new = m.group(1)
        where = _in_folder(flat)
        ext = new.rsplit(".", 1)[-1] if "." in new else "doc"
        trio = _sorted_trio(where, ext)
        fs[_join(base, where)] = {"type": "dir"}
        for name in trio:
            fs[_join(base, where, name)] = file_node(name)
        checks.append({"desc": f"把「{where}」里按名称排在中间的「{trio[1]}」改名为「{new}」",
                       "score": 5, "assert": {"op": "exists", "path": _join(base, where, new),
                                              "is": "file"}})
        checks.append({"desc": f"改完不该还有「{trio[1]}」（改的是中间那一个）", "score": 3,
                       "assert": {"op": "missing", "path": _join(base, where, trio[1])}})
        return

    # ③ 把"A.doc"（文件）重命名 / 改名为"B.doc"
    #    **原名必须铺出来**，否则学生打开文件夹里根本没有要改的那个文件
    m = re.search(Q + r"([^\"“”'‘’「」『』]+?)" + Q + r"(?:文件|文件夹)?(?:重命名|改名)为"
                  + Q + r"([^\"“”'‘’「」『』]+?)" + Q, flat)
    if m:
        old, new = m.group(1), m.group(2)
        where = _in_folder(flat)
        src, dst = _join(base, where, old), _join(base, where, new)
        # 是文件还是文件夹：先看题干怎么说（"将**文件**'房屋'重命名为…"），
        # 没说才看有没有扩展名。说了"文件"却铺成文件夹，学生打开一看类型都不对
        said_file = re.search(r"文件" + Q + r"?" + re.escape(old), flat) or "." in old
        said_dir = re.search(r"文件夹" + Q + r"?" + re.escape(old), flat)
        fs[src] = file_node(old) if (said_file and not said_dir) else {"type": "dir"}
        if where:
            fs[_join(base, where)] = {"type": "dir"}
        checks.append({"desc": f"把「{old}」改名为「{new}」", "score": 5,
                       "assert": {"op": "exists", "path": dst}})
        checks.append({"desc": f"改完不该还有「{old}」", "score": 3,
                       "assert": {"op": "missing", "path": src}})
        return

    # ③ 将名为"X"的文件夹/文件 复制|移动到"Y"文件夹中
    m = re.search(r"名为" + Q + r"([^\"“”'‘’「」『』]+?)" + Q + r"的(文件夹|文件)"
                  r"(复制|移动)到" + Q + r"?([^\"“”'‘’「」『』]{0,40}?)" + Q + r"?文件夹", flat)
    if m:
        name, what, verb, dst = m.group(1), m.group(2), m.group(3), m.group(4)
        src = _join(base, name)
        fs[src] = {"type": "dir"} if what == "文件夹" else file_node(name)
        fs[_join(base, dst)] = {"type": "dir"}
        checks.append({"desc": f"把{what}「{name}」{verb}到「{dst}」", "score": 5,
                       "assert": {"op": "exists", "path": _join(base, dst, name)}})
        if verb == "移动":
            checks.append({"desc": f"原位置不再有「{name}」", "score": 3,
                           "assert": {"op": "missing", "path": src}})
        return

    # ③ 删除"A"文件夹中的图片文件 —— 题干没点名是哪一个，那就**铺一个出来**，
    #    学生看到的和判分看的是同一个文件，题目才做得成
    m = re.search(r"删除" + Q + r"?([^\"“”'‘’「」『』]{0,30}?)" + Q
                  + r"?文件夹[中下里]的(图片|图像|音频|视频|文本)文件", flat)
    if m:
        where, what = m.group(1), m.group(2)
        ext = {"图片": ".jpg", "图像": ".jpg", "音频": ".mp3",
               "视频": ".mp4", "文本": ".txt"}[what]
        name = f"示例{what}{ext}"
        fs[_join(base, where)] = {"type": "dir"}
        fs[_join(base, where, name)] = file_node(name)
        checks.append({"desc": f"删除「{where}」里的{what}文件「{name}」", "score": 5,
                       "assert": {"op": "missing", "path": _join(base, where, name)}})
        return

    # ③ 删除"A"文件夹中（某个说不清是哪一个）的文件 —— 题干常写成
    #    「不属于3D在医学领域应用的文件」「不合适的文件」。铺一个明显不搭的进去
    m = re.search(r"删除" + Q + r"?([^\"“”'‘’「」『』]{1,30}?)" + Q
                  + r"?文件夹[中下里](?:不|多余|无关)[^。]{0,30}?的文件", flat)
    if m:
        where = m.group(1)
        odd = "无关文件.txt"
        fs[_join(base, where)] = {"type": "dir"}
        fs[_join(base, where, odd)] = {
            "type": "file",
            "content": f"这个文件和「{where}」没有关系，是本题要删掉的那一个。"}
        checks.append({"desc": f"删掉「{where}」里不该在的那个文件（{odd}）", "score": 5,
                       "assert": {"op": "missing", "path": _join(base, where, odd)}})
        return

    # ③ 删除"X"文件夹（整个文件夹，不是里面的文件）
    m = re.search(r"删除" + Q + r"([^\"“”'‘’「」『』]+?)" + Q + r"文件夹(?![中下里])", flat)
    if m:
        name = m.group(1)
        fs[_join(base, name)] = {"type": "dir"}
        checks.append({"desc": f"删除文件夹「{name}」", "score": 5,
                       "assert": {"op": "missing", "path": _join(base, name)}})
        return

    # 认不出来的一律留痕。**悄悄扔掉比判错更糟** —— 老师会以为这道题判全了，
    # 实际漏了一问，而且没有任何地方提示他
    if len(flat) > 6 and not re.fullmatch(r"[^。]*(保存|退出|完成以上操作)[^。]*。?", flat):
        todo.append(text.strip())


# 「按名称排序后的中间一个文件」要铺的那一组。**排序以学生屏幕上看到的为准**：
# 中文 Windows 的资源管理器按拼音排，而程序里的 sorted() 按码位排，两种经常
# 对不上（「太湖」码位最小、拼音却排在后面）。这里挑的名字**两种排法结果
# 一样**，不然学生照着屏幕改对了，判分却说改错了。
#   巢湖(chao, U+5DE2) < 江汉(jiang, U+6C5F) < 鄱阳湖(po, U+9131)
SORTED_TRIOS = {
    "长江中下游平原": ("巢湖平原", "江汉平原", "鄱阳湖平原"),
}


def _sorted_trio(folder: str, ext: str) -> tuple:
    """铺三个文件，中间那个是要改名的。没见过的文件夹用「资料A/B/C」：
    前缀相同、只差一个英文字母，拼音和码位两种排法都是 A<B<C。"""
    names = SORTED_TRIOS.get(folder) or ("资料A", "资料B", "资料C")
    return tuple(f"{n}.{ext}" for n in names)


def _seed_mentioned(stem: str, base: str, fs: dict, checks: list) -> None:
    """题干点过名的文件和文件夹，**没被任何规则铺出来的，补铺**。

    这是这套生成里最要紧的一条兜底。解析器认不出某一问不要紧（那一问不判分），
    但**不能让学生打开工作目录发现题目说的文件根本不存在** —— 他会以为自己
    找错了地方，或者以为程序坏了，然后在那一问上耗掉整场考试的时间。

    踩过：「打开网页文件"安全教育网.htm"……保存到"ks\\消防安全"下」那一问解析
    不出来，于是 安全教育网.htm 和 ks\\消防安全 都没铺，考场里只有另外两问的
    文件。

    **要做的（学生的答案）一律不铺**：检查点里 exists 指向的路径就是答案，
    预先铺出来等于把题做了。
    """
    made = {str((c.get("assert") or {}).get("path") or "")
            for c in checks if (c.get("assert") or {}).get("op") == "exists"}
    # 按**名字**排除，不只按路径：「火灾逃生.rar」要学生存到 ks\消防安全 下，
    # 那就哪儿都不能预先铺一个同名的出来，否则这一问白送分
    taken = {p.rsplit("/", 1)[-1] for p in made}
    have = {p.rsplit("/", 1)[-1] for p in fs}

    for item in split_items(stem):
        flat = _clean(item)
        here = _context_folder(flat)             # 这一句在说哪个文件夹里的事
        # 「在"X"文件夹中，……」—— X 本身也得有。原来这里直接跳过了 X（本意是
        # 别把它铺到它自己里面去），结果是**哪儿都没铺**：win04 那道题第 (2) 问
        # 没有规则认得，考场里就少了整个「长江中下游平原」文件夹
        if here and "/" not in here and "\\" not in here:
            spot = _join(base, here)
            if spot not in fs and here not in {p.rsplit("/", 1)[-1] for p in made}:
                fs[spot] = {"type": "dir"}
                have.add(here)
        for token in _quoted(flat):
            token = token.strip().strip("。，,、")
            if not token or len(token) > 40 or token == here:
                continue
            parts = [p for p in re.split(r"[\\/]+", token) if p]
            name = parts[-1]
            ext = name.rsplit(".", 1)[-1] if "." in name else ""
            is_file = bool(ext) and len(ext) <= 5 and not ext.isdigit()
            # **只铺说得清是什么的东西**：带扩展名的文件，或者题干明说是"文件夹"
            # 的、写成路径的。「火灾逃生方法」是网页里的一段资料名，不是文件，
            # 铺出来只会让学生更糊涂
            # **引号要紧贴着 token**：不加这个限制，「打印材料」会因为题干里那句
            # 「"3D打印材料"文件夹」而被当成文件夹（它是那个名字的后半截）
            looks_like_dir = (len(parts) > 1
                              or re.search(Q + re.escape(token) + Q + r"文件夹", flat))
            # 题干明说了是文件的也铺：「将**文件**"3D打印头盖骨"移动到……」——
            # 这类名字没有扩展名，不认的话学生打开文件夹里根本没有这个文件
            said_file = re.search(r"文件" + Q + re.escape(token) + Q, flat) or \
                re.search(Q + re.escape(token) + Q + r"文件(?!夹)", flat)
            if not is_file and not looks_like_dir and not said_file:
                continue
            is_file = is_file or bool(said_file and not looks_like_dir)
            if name in taken or name in have:    # 是答案，或者别处已经铺过了
                continue
            # 「改名为"长江三角洲.doc"」「新建……"校园安全"」——这些是**要做出来的**，
            # 预先铺出来等于把题做了一半，学生打开一看还以为自己已经做过
            if re.search(r"(?:改名|重命名|命名|保存|另存)为" + Q + re.escape(token) + Q, flat)                     or re.search(r"(?:新建|建立|创建)[^。]{0,12}?" + Q + re.escape(token) + Q, flat):
                continue
            under = "" if len(parts) > 1 else here   # 带路径的自己说清了位置
            path = _join(base, under, *parts)
            if path in made or path in fs:
                continue
            bits = path.split("/")
            for i in range(1, len(bits)):        # 父目录得先有
                fs.setdefault("/".join(bits[:i]), {"type": "dir"})
            fs[path] = file_node(name) if is_file else {"type": "dir"}
            have.add(name)


def parse_win(stem: str) -> dict:
    base = _base_dir(stem)
    fs: dict = {}
    checks: list = []
    todo: list = []
    for item in split_items(stem):
        _win_item(item, base, fs, checks, todo)
    _seed_mentioned(stem, base, fs, checks)
    if base:
        fs.setdefault(base, {"type": "dir"})
    # 补齐父目录：判分器按路径找，父目录不在就找不到
    for path in list(fs):
        parts = path.split("/")
        for i in range(1, len(parts)):
            fs.setdefault("/".join(parts[:i]), {"type": "dir"})
    return {"kind": "win", "env": {"fs": fs, "recycle": {}},
            "checks": checks, "todo": todo}


# ================================================================ WPS 文字
SIZE_WORDS = "初号|小初|一号|小一|二号|小二|三号|小三|四号|小四|五号|小五|六号|小六|七号|八号"
# 字体名要**写全**，别用「华文 + 任意两三个汉字」这种通配 —— 它会把
# 「孔子对中华文明的五大贡献.pdf」里的"华文明的五"当成字体，造出一条
# 谁也做不到的检查点（学生的字体下拉里根本没有这个字体）。踩过。
FONT_WORDS = (r"黑体|宋体|新宋体|楷体|仿宋|微软雅黑|等线|隶书|幼圆|方正姚体"
              r"|华文(?:宋体|楷体|仿宋|中宋|细黑|行楷|彩云|琥珀|隶书|新魏)")
ALIGN_WORDS = {"居中": "center", "右对齐": "right", "左对齐": "left",
               "两端对齐": "justify", "分散对齐": "distribute"}


_NOT_EXCERPT = re.compile(
    r"^(?:" + FONT_WORDS + r"|" + SIZE_WORDS + r"|标题[0-9]?|正文|副标题|普通数字[0-9]?"
    r"|[上下左右]+型环绕|紧密型环绕|四周型环绕|嵌入型|浮于文字上方|衬于文字下方"
    r"|居中|左对齐|右对齐|两端对齐|分散对齐|加粗|倾斜|斜体"
    r"|[^一-龥]{0,4}下划线|.{0,4}波浪线|着重号|删除线|艺术字"
    r"|[0-9.]+|[A-Za-z]+[0-9]*|.{0,5}色"
    # 带扩展名的是文件名，不可能是段落原文
    r"|.{1,30}\.(?:docx?|wps|pdf|txt|jpe?g|png|gif|rar|zip|pptx?|xlsx?))$")


def _quote_text(word: str) -> str:
    """把题干抄出来的那一段还原成一句能读的话。

    真题里抄原文都带省略号：「"李绅（772﹣846）……被誉为'悯农诗人'。"」。
    直接把省略号前那半截放进文档，学生看到的是半句话；整句连起来才像文章。
    """
    text = str(word or "").strip()
    bits = re.split(r"…+|\.{3,}|。{3,}", text, maxsplit=1)
    if len(bits) < 2 or not bits[1].strip():
        return bits[0].strip() if bits else text
    head, tail = bits[0].strip(), bits[1].strip()
    head = head.rstrip("，,、；;")          # 省略号前常带个逗号，别接出"，，"
    # 前半截已经收句了（。」”），就直接接上；没收句的补个逗号
    joiner = "" if head.endswith(("。", "！", "？", "”", "」", "’")) else "，"
    text = f"{head}{joiner}{tail}"
    # 题干里的引号套引号（"……被誉为'悯农诗人'。"）会让摘出来的话断在半截上。
    # 最后那一小截既短又没收句，多半就是断掉的，去掉比留着通顺
    parts = re.split(r"[，,]", text)
    if len(parts) > 1 and len(parts[-1]) < 6 and not parts[-1].rstrip("。").endswith(
            ("。", "！", "？", "”", "」")):
        text = "，".join(parts[:-1])
    if not text.endswith(("。", "！", "？", "”", "」")):
        text += "。"
    return text


def _excerpt(flat: str, least: int = 4) -> str:
    """题干里抄的那段**原文**：「将第2自然段（"远处的群山……花瓣儿。"）设为……」

    用它按内容定位段落，比按序号稳 —— 学生要是在前面插了一段，序号就全错位了。
    省略号前那一截就够认段落，也正好当作要塞进生成正文里的那句话。

    **能按内容找就别按序号找。** 同一道题里常常又有"把第 3 段移到最后"，
    段落一挪，按序号定位的检查点就全指错了 —— 学生做对了反而判错。

    引号里的东西不一定是原文：字体名、字号、样式名、环绕方式也都带引号。
    所以短的、像术语的一律不算（见 _NOT_EXCERPT）。
    """
    for word in _quoted(flat):
        head = re.split(r"…+|\.{3,}|。{2,}", word)[0].strip("　 、，,。;；")
        if len(head) >= least and not _NOT_EXCERPT.match(word.strip()):
            # **返回引号里的原样**（省略号也留着）：放进文档时用 _quote_text()
            # 接成一句完整的话，定位段落时用 _quote_key() 取前十个字。
            return word.strip()
    # 也有不用引号、用括号抄原文的：「将文档的第一自然段（人工智能……文化情景的
    # 有力支撑。）段落格式设置为……」。只认带省略号的 —— 括号里还常是"(IOT)"这种注释
    for m in re.finditer(r"[（(]([^（）()]{4,80}?(?:…+|\.{3,})[^（）()]*)[）)]", flat):
        return m.group(1).strip()
    return ""


def _quote_key(word: str) -> str:
    """拿这段原文的前十个字当"钥匙"，用来在文档里找到它所在的那一段。

    只取前十个字：学生可能在那一段里改了后半截（题目就常要求改），
    拿整段去比会找不到。
    """
    head = re.split(r"…+|\.{3,}|。{2,}", str(word or ""))[0].strip("　 、，,。;；“”\"")
    return head[:10]


def _wps_item(text: str, checks: list, todo: list, needs: list,
              title: list | None = None, quotes: list | None = None) -> None:
    """一条 WPS 操作。

    needs 收集「要被替换掉的词」—— **这些词必须出现在生成的原文里**，
    否则学生打开文档根本找不到要替换的东西，这一问谁也做不出来。
    第一版漏了这件事，生成的文档是两行占位符，题目等于没法做。
    """
    flat = _clean(text)
    hit = False

    # 一句话里同时说了标题和正文：「将文档标题字体设置为黑体、二号，正文字体
    # 设置为宋体、四号」。两个目标两套格式，**得拆开各判各的** —— 不拆只会
    # 认出一半，学生做全了也只能拿一半分。
    if "标题" in flat and "正文" in flat and flat.count("设置") >= 2:
        for half in re.split(r"[，,；;]", flat):
            if "设置" in half:
                _wps_item(half, checks, todo, needs, title, quotes)
        return

    # 「将文章的标题设置为"标题"样式，**并**为正文第一自然段中的文字"……"添加
    # "双下划线"」—— 一句话管两件事，目标还不是同一段。不拆的话两套要求会挤在
    # 一个目标上，而那个目标多半还是正则从两个引号中间捞出来的一串废话。
    if re.search(r"[，,]并|；|;", flat) and len(_quoted(flat)) >= 2:
        halves = [h for h in re.split(r"[，,]并|；|;", flat) if len(_clean(h)) > 6]
        if len(halves) > 1:
            for half in halves:
                _wps_item(half, checks, todo, needs, title, quotes)
            return

    # 「将文章的标题设置为"标题"样式」—— 引号里是**样式名**，不是标题内容。
    # 不单独认的话，正则会从"标题"的后引号一路捞到下一个前引号，造出一个
    # 「样式，并为正文第一自然段中的文字」这样的假标题，整段文档跟着跑偏。
    m = re.search(r"(?:标题|题目)[^。]{0,6}?(?:设置|设|应用)为?" + Q
                  + r"(标题[0-9]?|正文|副标题)" + Q + r"样式", flat)
    if m:
        style = m.group(1)
        checks.append({"desc": f"标题应用「{style}」样式", "score": 4,
                       "assert": {"op": "para", "at": 0,
                                  "style": style}})
        return

    # ① 将文档中所有的"A"替换为/替换成"B"，或者「把文中所有的"A"改为"B"」
    m = re.search(Q + r"([^\"“”'‘’「」『』]+?)" + Q + r"(?:全部)?(?:替换|改)(?:为|成)" + Q
                  + r"([^\"“”'‘’「」『』]+?)" + Q, flat)
    if m and re.search(r"文中|文档中|全部|所有", flat):
        old, new = m.group(1), m.group(2)
        needs.append(old)
        checks.append({"desc": f"把「{old}」全部替换为「{new}」", "score": 4,
                       "assert": {"op": "text", "absent": old, "present": new}})
        return

    # ② 页眉 / 页脚：「为文档添加页眉为"春天"」「添加页脚，内容为"1"」
    m = re.search(r"(页眉|页脚)[^。]{0,8}?(?:为|内容为|是)\s*" + Q
                  + r"([^\"“”'‘’「」『』]{1,20})" + Q, flat)
    if m:
        which, word = m.group(1), m.group(2)
        checks.append({"desc": f"添加{which}「{word}」", "score": 4,
                       "assert": {"op": "header" if which == "页眉" else "footer",
                                  "has": word}})
        return

    # ② 纸张大小：「设置纸张大小为A4」「设置文档页面为B5纸大小」
    m = re.search(r"(?:纸张|页面)[^。]{0,6}?(A3|A4|A5|B4|B5|16开)", flat, re.I)
    if m:
        want = m.group(1).upper() if m.group(1).lower() != "16开" else "16开"
        checks.append({"desc": f"纸张设为 {want}", "score": 4,
                       "assert": {"op": "page", "size": want}})
        # 不 return：同一句里常常还跟着页边距、页码

    # ② 页边距：「左、右边距均为2厘米」「左右页边距为2.5厘米，上下页边距为2厘米」
    seen = set()
    for m in re.finditer(r"(左右|上下|左、右|上、下|左|右|上|下)(?:页)?边距"
                         r"[^0-9。]{0,8}(\d+(?:\.\d+)?)\s*厘米", flat):
        where, value = m.group(1), float(m.group(2))
        keys = {"左右": ("left", "right"), "左、右": ("left", "right"),
                "上下": ("top", "bottom"), "上、下": ("top", "bottom"),
                "左": ("left",), "右": ("right",),
                "上": ("top",), "下": ("bottom",)}[where]
        keys = tuple(k for k in keys if k not in seen)
        if not keys:
            continue
        seen.update(keys)
        checks.append({"desc": f"{where}边距 {value} 厘米", "score": 3,
                       "assert": {"op": "page", **{k: value for k in keys}}})
    if seen:
        return

    # ③ 把某一段移到最后：「将自然段（"春雨过后……"）移动到最后」
    #    判的是"最后一段是不是它"，正好对上 order.last
    if re.search(r"移(?:动)?到(?:文档|文章)?(?:的)?(?:最后|末尾)", flat):
        raw = _excerpt(flat, least=3)
        if raw:
            key = _quote_key(raw)
            (quotes if quotes is not None else needs).append(_quote_text(raw))
            checks.append({"desc": f"把「{key}」那一段移到最后", "score": 4,
                           "assert": {"op": "order", "last": key[:8]}})
            return

    # ③ 在文章最后输入一段新的文字:"……"
    m = re.search(r"(?:在文章|文章)?最后输入一段新的文字:?" + Q + r"(.+?)" + Q, flat)
    if m:
        words = m.group(1)
        # 只比前 12 个字：学生手打长句难免有出入，判"这段在不在"就够了
        checks.append({"desc": "在文章最后加上要求的那段文字", "score": 4,
                       "assert": {"op": "order", "last": words[:12]}})
        return

    # 格式类：先找"对谁"，再找"设成什么"
    target = None
    excerpt = ""
    # 「将标题文字"让青春在不懈奋斗中绽放绚丽之花"设置为……」——**引号是必需的**。
    # 不要引号的话，「将文档标题字体格式设置为黑体」会把"字体"两个字当成标题
    # 内容，生成一条永远找不到那一段的检查点。踩过。
    m = re.search(r"(?:标题|题目)(?:文字)?[，,]?" + Q + r"([^\"“”'‘’「」『』]{3,30})" + Q, flat)
    if m and re.search(r"设置|设为|格式化", flat):
        target = {"has": m.group(1)[:10]}
        # 题干点名了标题原文，文档里就得真有这句话 —— 检查点按内容找段落
        if title is not None:
            title.append(m.group(1))
    elif _excerpt(flat):
        # 「将文中介绍作者李绅的一段文字（"李绅（772﹣846）……"）字体格式化为……」
        # —— 真题里几乎都会把那一段的原文抄在括号里。**按内容找段落**，
        # 而且把这句原文塞进生成的正文里，学生才找得到要改的那一段。
        #
        # 但**先别急着塞**：这一句也可能压根没有格式要求（"插入艺术字'家国情怀'"），
        # 那 needs 就白加了一句不相干的话进正文。等确认出了检查点再塞（见下面）。
        excerpt = _excerpt(flat)
        target = {"has": _quote_key(excerpt)}
    elif "标题" in flat or "题目" in flat:
        target = 0                        # 没给标题内容就按第一段算
    elif re.search(r"第一(?:个)?(?:自然)?段", flat):
        # 生成的文档第 0 段是标题，「第一自然段」是正文第一段，即下标 1。
        # 以前这里给的是 0，检查点全打在标题上，学生改对了正文第一段反而不得分
        target = 1
    elif re.search(r"第\s*([2-9１-９二三四五六七八九])\s*(?:个)?(?:自然)?段", flat):
        m2 = re.search(r"第\s*([2-9１-９二三四五六七八九])\s*(?:个)?(?:自然)?段", flat)
        digits = {"二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
                  "七": 7, "八": 8, "九": 9}
        raw = m2.group(1)
        n = digits.get(raw) or int(raw) if not raw.isdigit() else int(raw)
        # 生成的文档第 0 段是标题，所以「第 N 自然段」就是下标 N
        target = min(n, 4)
    elif re.search(r"正文(?:所有)?段落|所有段落|正文", flat):
        target = 1                        # 正文从第二段起

    want: dict = {}
    m = re.search(FONT_WORDS, flat)
    if m:
        want["font"] = m.group(0)
    m = re.search(SIZE_WORDS, flat)
    if m:
        want["size"] = m.group(0)
    # 字形：加粗、倾斜、下划线。**下划线只判"有没有"** —— 双下划线、波浪线
    # 在 .docx 里是 w:u 的不同取值，客户端读回来只有"有/无"，判样式会冤枉人
    if re.search(r"加粗|粗体|字形为粗", flat):
        want["bold"] = True
    if re.search(r"倾斜|斜体", flat):
        want["italic"] = True
    if re.search(r"下划线", flat):
        want["underline"] = True
    m = re.search(r"(红|绿|蓝|黄|紫|橙)色", flat)
    if m:
        want["color"] = m.group(0)
    if re.search(r"设置为" + Q + r"?标题" + Q + r"?样式|应用[^。]{0,4}标题样式", flat):
        want["style"] = "标题"            # 判分时「标题」「标题 1」都认，见 sim.same_style
    for word, value in ALIGN_WORDS.items():
        if word in flat:
            want["align"] = value
            break
    m = re.search(r"首行缩进(?:为)?(\d+(?:\.\d+)?)(?:个)?字符", flat)
    if m:
        want["indent"] = float(m.group(1))
    # 「文本之前2个字符」——真题里"缩进"两个字常常省掉
    m = re.search(r"文本之前(?:缩进)?(\d+(?:\.\d+)?)(?:个)?字符", flat)
    if m:
        want["left"] = float(m.group(1))
    m = re.search(r"文本之后(?:缩进)?(\d+(?:\.\d+)?)(?:个)?字符", flat)
    if m:
        want["right"] = float(m.group(1))
    m = re.search(r"段前(?:间距)?(?:为)?(\d+(?:\.\d+)?)行", flat)
    if m:
        want["before"] = float(m.group(1))
    m = re.search(r"段后(?:间距)?(?:为)?(\d+(?:\.\d+)?)行", flat)
    if m:
        want["after"] = float(m.group(1))
    m = re.search(r"行距(?:为)?固定值(\d+(?:\.\d+)?)磅", flat)
    if m:
        want["line"] = {"type": "fixed", "value": float(m.group(1))}
    else:
        m = re.search(r"(\d+(?:\.\d+)?)倍行距", flat)
        if m:
            want["line"] = {"type": "multiple", "value": float(m.group(1))}

    if want and target is not None:
        if excerpt and quotes is not None:
            # 到这一步才确认：这一句真的在要求格式，那句原文得进正文（独占一段）
            quotes.append(_quote_text(excerpt))
        # 一句话里常同时要求好几项（黑体、二号、居中），拆成几条检查点 ——
        # 学生只做对一半时能拿一半分，老师也看得出差在哪一项
        labels = {"font": "字体", "size": "字号", "align": "对齐", "indent": "首行缩进",
                  "left": "文本之前缩进", "right": "文本之后缩进",
                  "before": "段前间距", "after": "段后间距", "line": "行距",
                  "bold": "加粗", "italic": "倾斜", "underline": "下划线",
                  "color": "字体颜色", "style": "样式"}
        for key, value in want.items():
            checks.append({"desc": f"设置{labels.get(key, key)}", "score": 3,
                           "assert": {"op": "para", "at": target, key: value}})
        return

    if not hit and len(flat) > 8 and "保存" not in flat and "退出" not in flat:
        todo.append(text.strip())


# 补白用的句子。**围着这道题的题目写**，不要"XX正在深刻改变我们的学习与生活"
# 那种谁都套得上的模板 —— 学生打开文档一看，文章和题目毫无关系，会以为整套题
# 配错了。这几句套在"孔子对中华文明的贡献""我见到了春天""外卖小哥夺冠"上都读得通。
FILLER = [
    "《{topic}》是这次要整理的文稿。通读一遍会发现，文章本身是完整的，"
    "只是排版还没有理顺，字体、段落和页面都需要按要求重新设置。",
    "文章围绕{topic}展开：先摆出事实，再讲道理，最后落到我们今天该怎么看、"
    "怎么做。行文平实，读起来并不费力。",
    "读到这里不妨停一停，想一想{topic}对今天的我们究竟意味着什么。"
    "很多当时看着寻常的细节，放在更长的时间里才显出分量。",
    "把{topic}这件事讲清楚并不容易，需要耐心，也需要一点取舍。"
    "这篇文稿做的就是这件事。",
]


def _article(topic: str, needs: list, quotes: list | None = None) -> list[dict]:
    """生成一篇**和这道题有关**的正文。

    两条硬要求：

    1. **题干抄出来的每一句原文都要原样出现，而且各自独占一段。**
       检查点是按内容找段落的：两句挤在同一段里，两套格式会互相覆盖；
       少了哪一句，学生翻遍文档也找不到要改的地方 —— 那一问就成了死题。
       踩过：一整篇都是模板套话，题干里"孔子整理的《诗经》……"那句压根不在
       文档里，检查点却指着它，判出来的分是假的。

    2. **要被替换的词必须真的出现**：题目说「把 A 换成 B」，文档里没有 A 的话
       这一问谁也做不出来。

    文章质量到不了课文的水平（题库里只有题干，没有原卷素材），但主题对得上、
    句子通顺、篇幅够做排版 —— 这三条能保证。
    """
    body: list[str] = []
    for quote in (quotes or []):
        text = quote.strip()
        # 题干里引的可能就是标题本身（「在文章顶部添加文章标题"风中的一棵树"」），
        # 而标题已经单独是一段了，再抄一遍就成了重复
        if text.rstrip("。").strip() == str(topic).strip():
            continue
        if not text.endswith(("。", "！", "？", "”", "」")):
            text += "。"
        # 原文独占一段，后面补一句引子，读着像正常文章而不是一句孤零零的摘抄
        body.append(f"{text}这一点，正是读{topic}时最值得留意的地方。")

    for line in FILLER:                       # 补到四段：太短了排版看不出效果
        if len(body) >= 4:
            break
        body.append(line.format(topic=topic))

    for i, word in enumerate(needs):          # 要被替换的词，挨段塞
        at = min(i, len(body) - 1)
        body[at] = f"{body[at]}文中多处提到{word}，{word}这个说法贯穿全篇。"
    return [{**blank_para(), "text": t} for t in body]


def parse_wps(stem: str) -> dict:
    """WPS 文字题。

    文档是**这里现生成的**：题库里只有题干，没有原卷素材。内容围着题目写，
    题干抄出来的原文原样放进去 —— 学生打开文档得能找到题目说的那几段，
    否则整道题没法做。
    """
    checks: list = []
    todo: list = []
    needs: list = []
    quotes: list = []
    title: list = []
    for item in split_items(stem):
        _wps_item(item, checks, todo, needs, title, quotes)

    # 文稿叫什么：先找带扩展名的文件名，再找「"X"文稿 / 文档 / 文章」。
    # 两种都找不到才退回"文档"——退到那一步，正文就只能写成套话了
    flat = str(stem)
    m = (re.search(Q + r"([^\"“”'‘’「」『』]+?)\.(?:docx?|wps)" + Q, flat)
         or re.search(Q + r"([^\"“”'‘’「」『』]{2,30})" + Q + r"(?:文稿|文档|文章)", flat)
         or re.search(r"(?:编辑|修改|整理)" + Q + r"([^\"“”'‘’「」『』]{2,30})" + Q, flat))
    name = m.group(1) if m else "文档"
    topic = re.sub(r"[0-9]+$", "", name).strip() or "信息技术"

    head = title[0] if title else topic
    paras = [{**blank_para(), "text": head}] + _article(topic, needs, quotes)
    env = {"name": f"{name}.docx", "paras": paras}
    return {"kind": "wps", "env": env, "checks": checks, "todo": todo}


# ================================================================ 网页（HTML）
def _html_item(text: str, checks: list, todo: list) -> None:
    """一条网页操作。

    **不能匹配到一个就收手**：真题里一个 ② 常塞两件事 ——
    「将网页背景色修改为深红色"#980015"；网页中的图片修改为"智慧食堂.jpg"」。
    早先匹配到图片就返回，背景色那一问直接漏判，而且没有任何提示。
    """
    flat = _clean(text)
    before = len(checks)

    # ① 修改网页标题为"X" / 将网页标题修改为"X"
    m = re.search(r"网页标题(?:修改)?为" + Q + r"(.+?)" + Q, flat) or \
        re.search(r"将网页标题修改为" + Q + r"(.+?)" + Q, flat)
    if m:
        checks.append({"desc": f"网页标题改成「{m.group(1)}」", "score": 4,
                       "assert": {"op": "title", "equals": m.group(1)}})

    # ① 将网页中的一级标题内容修改为"X"
    m = re.search(r"(一级标题|二级标题)(?:内容)?(?:修改)?为" + Q + r"(.+?)" + Q, flat)
    if m:
        tag = "h1" if m.group(1) == "一级标题" else "h2"
        checks.append({"desc": f"{m.group(1)}改成「{m.group(2)}」", "score": 4,
                       "assert": {"op": "sel", "selector": tag, "text": m.group(2)}})

    # ② 图片那一条，真题里至少三种写法：
    #      将网页中的图片修改为"F.jpg"
    #      将班级照片"22.jpg"换成为"heying.jpg"
    #      使用相对路径设置图片链接为img文件夹下"无人机图片.jpg"
    #    少认一种就漏判一问，所以一并认
    m = (re.search(r"图片(?:链接)?(?:修改|换成|设置)?为?[^\"“”'‘’「」『』]{0,10}" + Q
                   + r"([^\"“”'‘’「」『』]+?\.[A-Za-z]{2,4})" + Q, flat)
         or re.search(r"换成为?" + Q + r"([^\"“”'‘’「」『』]+?\.[A-Za-z]{2,4})" + Q, flat))
    if m:
        name = m.group(1)
        checks.append({"desc": f"图片换成「{name}」", "score": 4,
                       "assert": {"op": "attr", "selector": "img", "name": "src",
                                  "has": name}})
        # 「img文件夹下」——用相对路径，src 里得带上那一层目录
        if re.search(r"img文件夹|相对路径", flat):
            checks.append({"desc": "图片用相对路径指到 img 文件夹", "score": 2,
                           "assert": {"op": "attr", "selector": "img", "name": "src",
                                      "has": "img/"}})
        for key, label in (("width", "宽度"), ("height", "高度")):
            mm = re.search(label + r"(?:为)?" + Q + r"?(\d+)(?:px)?" + Q + r"?", flat)
            if mm:
                checks.append({"desc": f"图片{label} {mm.group(1)}px", "score": 2,
                               "assert": {"op": "attr", "selector": "img",
                                          "name": key, "has": mm.group(1)}})

    # ② 将网页背景色修改为深红色"#980015"
    m = re.search(r"背景色(?:修改)?为[^#]*?(#[0-9a-fA-F]{3,6})", flat)
    if m:
        checks.append({"desc": f"网页背景色设为 {m.group(1)}", "score": 4,
                       "assert": {"op": "css", "selector": "body",
                                  "prop": "background-color", "equals": m.group(1)}})

    # ② 加一个新段落，内容为"Y"
    m = re.search(r"(?:新)?段落[^“”\"]{0,12}内容为" + Q + r"(.+?)" + Q, flat)
    if m:
        checks.append({"desc": f"加一段「{m.group(1)[:12]}」", "score": 4,
                       "assert": {"op": "sel", "selector": "p", "text": m.group(1)[:12]}})

    if len(checks) == before and len(flat) > 8 and not re.search(r"保存|退出", flat):
        todo.append(text.strip())


def parse_html(stem: str) -> dict:
    """网页题。初始文件给一份能直接改的空架子，老师可以再补内容。"""
    checks: list = []
    todo: list = []
    for item in split_items(stem):
        _html_item(item, checks, todo)
    env = {"files": {
        "index.html": ("<html>\n<head>\n<meta charset=\"utf-8\">\n<title></title>\n"
                       "<link rel=\"stylesheet\" href=\"style.css\">\n</head>\n"
                       "<body>\n<h1></h1>\n<p></p>\n<img src=\"\">\n</body>\n</html>"),
        "style.css": "/* 在这里写样式 */\n",
    }}
    return {"kind": "html", "env": env, "checks": checks, "todo": todo}


# ================================================================ AI 工具
def parse_ai(stem: str) -> dict:
    """AI 工具题**不用出检查点** —— 服务器按题干现算（见 sim.auto_checks_for_ai）。

    所以这里只给一个空环境，把题目挂上就行。老师一个字都不用填。
    """
    return {"kind": "ai", "env": {}, "checks": [], "todo": []}


# ================================================================ 入口
def parse(stem: str, scope: str = "") -> dict | None:
    """读一道操作题的题干，造出仿真环境和检查点。

    认不出题型就返回 None —— 拖拽题（物联网、网络结构图）这类交互，题干里没有
    可判的终态，硬造只会造出判不准的检查点，不如老实留给老师。
    """
    kind = guess_kind(stem, scope)
    if kind == "win":
        got = parse_win(stem)
    elif kind == "wps":
        got = parse_wps(stem)
    elif kind == "html":
        got = parse_html(stem)
    elif kind == "ai":
        got = parse_ai(stem)
    else:
        return None
    got["scope_guess"] = kind
    return got


@lru_cache(maxsize=512)
def auto_sim(stem_text: str, scope: str = "") -> dict | None:
    """**没配仿真任务的操作题，按题干当场推一份出来。**

    这是整条链路的兜底，也是它能扛住版本升级和数据导入的原因：

        老师从 2.8.0 导出数据、导进 4.x 的新库 —— `sim_task_id` 全是空。
        要是只认数据库里配好的那份，所有操作题一夜之间全变成"不能自动判分"，
        而且表面上看不出毛病（题目照出，就是没有文件、没有检查点）。

    题干是跟着题目走的，导库不会丢。所以**以题干为准**：开考铺什么文件、
    交卷查什么，全从题干算。数据库里配了的仍然优先（老师手工调过的更准），
    没配的走这里。

    返回 `{"kind", "env", "checks"}`，路径都带上了 `C:/EXAM` 前缀 ——
    环境和检查点是一起算的，两边用同一套路径，不会对不上。

    结果按题干缓存：出包和判分都会走到这儿，同一道题一场考试里要算好几十遍。
    """
    got = parse(stem_text or "", scope or "")
    if not got or (got["kind"] != "ai" and not got["checks"]):
        # 通用规则认不出来的，再查拖拽题清单（流程图、结构图热区、设备归类、
        # 本机 IP、程序填空 —— 见 drag.py）。
        #
        # **顺序不能反过来。** 清单是按题干里的几句话认题的，放在前面会把规则
        # 认得好好的题抢走：一道「智慧食堂」宣传网页的 HTML 题，就曾被当成
        # 「智慧食堂」管理系统的结构图拖拽题，题干被整段换掉。
        return drag.auto(stem_text or "", scope or "")

    env, checks = got["env"], got["checks"]
    fs = env.get("fs")
    if isinstance(fs, dict):
        env = {**env, "fs": {f"{ROOT}/{k}": v for k, v in fs.items()}}
    out_checks = []
    for c in checks:
        a = dict(c.get("assert") or {})
        if "path" in a:
            a["path"] = f"{ROOT}/{a['path']}"
        out_checks.append({**c, "assert": a})
    return {"kind": got["kind"], "env": env, "checks": out_checks}


# ================================================================ 学生看到的题干（2.12.0）
EXAM_DIR = "C:\\EXAM"

# 「本题工作目录:D:\EXAM\windows操作」—— 冒号后面到行尾是一个路径（题库里还有
# 「D:\EXAM windows操作02」这种少了斜杠的写法，照样整段换掉）
_HEAD = re.compile(r"(本题工作目录\s*[:：]\s*)[A-Za-z]\s*[:：][^\n，。；;]*")
# 「请打开本题工作目录（C：\EXAM\Win操作）按照要求……」
_PAREN = re.compile(r"(工作目录\s*[（(]\s*)[A-Za-z]\s*[:：][^）)\n]*([）)])")
_OPENER = re.compile(r"打开本题工作目录\s*[下中]的[^，。\n]{0,24}?文件夹")


def _shape(checks) -> list:
    """检查点去掉「在哪一段」以后的样子：描述、分值、要求。"""
    out = []
    for c in checks or []:
        a = {k: v for k, v in (c.get("assert") or {}).items() if k != "at"}
        out.append((str(c.get("desc") or ""), int(c.get("score") or 0),
                    json.dumps(a, ensure_ascii=False, sort_keys=True)))
    return out


def refresh_wps(stem_text: str, env, checks) -> Optional[dict]:
    """库里存的 WPS 题要是**按题干自动生成、没被老师改过**的，换成按现在的规则重算的那份。

    为什么要有这一步：环境和检查点是生成时存进库的。规则修好以后（括号里抄的
    原文要放进文档、「第一自然段」指正文第一段），老库里的旧版本不会跟着变；
    恢复备份、导入旧的 exam-data 数据包，旧版本又原样回来了 —— 修了等于没修。

    怎么认"没被改过"：检查点除了定位（at）以外，描述、分值、要求和现在生成的
    一条不差，文档名也一样。老师在仿真器里动过的（加减检查点、改描述、改分）
    对不上，原样保留 —— 手工调过的比规则准。

    不写库：出卷和判分时当场换，导多少次旧数据都一样生效。
    """
    got = auto_sim(stem_text or "")
    if not got or got["kind"] != "wps" or not isinstance(env, dict):
        return None
    if str(env.get("name") or "") != str(got["env"].get("name") or ""):
        return None
    if _shape(checks) != _shape(got["checks"]):
        return None
    return got


def workdir_of(stem: str, kind: str, env: dict | None = None) -> str:
    r"""这道题在考场里的工作目录（Windows 写法）。说不上来返回空串。

    - Windows 题：题干说「打开本题工作目录下的 X 文件夹」的，工作目录就是 C:\EXAM，
      学生从那儿进 X；只给了完整路径的，是 C:\EXAM\<那个文件夹>；
    - WPS 题：文档铺在考试文件夹根上，C:\EXAM。
    """
    if kind == "win":
        if _OPENER.search(stem or ""):
            return EXAM_DIR
        tops = {str(k)[len(ROOT) + 1:].split("/")[0]
                for k in ((env or {}).get("fs") or {}) if str(k).startswith(ROOT + "/")}
        tops.discard("")
        top = next(iter(tops)) if len(tops) == 1 else _base_dir(stem).split("/")[0]
        return EXAM_DIR + ("\\" + top if top else "")
    if kind == "wps":
        return EXAM_DIR
    return ""


def student_stem(stem: str, kind: str, env: dict | None = None) -> str:
    r"""学生看到的题干：**工作目录、文件名按考场里实际的位置和名字写**。

    题库里的题干是原卷照抄的，写的是 `D:\EXAM\windows操作02`、`C：\EXAM\WPS文字`、
    「外卖小哥夺冠.wps」，而考场一律铺在 C:\EXAM 下，文档一律是 .docx。学生照着题干找，
    盘符、文件夹、扩展名三样都对不上（2.12.0 报上来的）。

    库里的原题干不动 —— 改了它，下次导库就认不出这道题，环境和检查点也是按原题干算的。
    AI 题不铺文件，那句工作目录只会让人去找一个不存在的文件夹，直接去掉。
    """
    text = str(stem or "")
    if kind == "ai":
        return re.sub(r"^[ \t]*本题工作目录\s*[:：][^\n]*\n?", "", text, flags=re.M)
    where = workdir_of(text, kind, env)
    if where:
        text = _HEAD.sub(lambda m: m.group(1) + where, text)
        text = _PAREN.sub(lambda m: m.group(1) + where + m.group(2), text)
    if kind == "wps" and env:
        from .docx_io import docx_name      # 文档真正的名字；局部导入免得和 docx_io 绕成环
        real = docx_name(env)
        text = re.sub(re.escape(real[:-len(".docx")]) + r"\.(?:wps|doc)(?![xX])", real, text)
    return text


def rename_workdir(stem: str, old: str, new: str) -> str:
    """一张卷子上两道题的工作目录同名、后一道改了名时，题干跟着改。"""
    text = re.sub(r"(打开本题工作目录\s*[下中]的\s*" + Q + r"?)" + re.escape(old)
                  + r"(" + Q + r"?\s*文件夹)", lambda m: m.group(1) + new + m.group(2), stem, count=1)
    return text.replace(EXAM_DIR + "\\" + old, EXAM_DIR + "\\" + new)
