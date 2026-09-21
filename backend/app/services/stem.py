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

import re
from functools import lru_cache

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


def _base_dir(stem: str) -> str:
    """「请打开本题工作目录下的**系统基本操作**文件夹」里那个文件夹名。

    没写就用空串 —— 操作路径直接挂在考试根下。
    """
    flat = _clean(stem)
    m = re.search(r"打开本题工作目录[下中]的" + Q + r"?([^\"“”'‘’「」『』，,。:：]{1,20}?)"
                  + Q + r"?文件夹", flat)
    return m.group(1) if m else ""


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


def _join(*parts: str) -> str:
    bits = [str(p).replace("\\", "/").strip("/") for p in parts if p]
    return "/".join(b for b in bits if b)


def _win_item(text: str, base: str, fs: dict, checks: list, todo: list) -> None:
    """一条 Windows 操作。认得出就写进 fs/checks，认不出丢进 todo。"""
    flat = _clean(text)
    names = _quoted(flat)

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

    # ② 将"学习"文件夹中的"比赛.txt"移动至"winkt"文件夹  —— 「移动至」不是「移动到」
    m = re.search(Q + r"?([^\"“”'‘’「」『』]{0,40}?)" + Q
                  + r"?文件夹[中下里]的" + Q
                  + r"([^\"“”'‘’「」『』]+?)" + Q
                  + r"(?:文件)?(移动|复制)(?:到|至)" + Q
                  + r"?([^\"“”'‘’「」『』]{0,40}?)" + Q + r"?文件夹", flat)
    if m:
        src, name, verb, dst = m.group(1), m.group(2), m.group(3), m.group(4)
        fs[_join(base, src, name)] = file_node(name)
        fs[_join(base, dst)] = {"type": "dir"}
        checks.append({"desc": f"把「{name}」{verb}到「{dst}」", "score": 5,
                       "assert": {"op": "exists", "path": _join(base, dst, name)}})
        if verb == "移动":
            checks.append({"desc": f"「{src}」里不再有「{name}」", "score": 3,
                           "assert": {"op": "missing", "path": _join(base, src, name)}})
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

    # ③ 把"A.doc"（文件）重命名 / 改名为"B.doc"
    #    **原名必须铺出来**，否则学生打开文件夹里根本没有要改的那个文件
    m = re.search(Q + r"([^\"“”'‘’「」『』]+?)" + Q + r"(?:文件|文件夹)?(?:重命名|改名)为"
                  + Q + r"([^\"“”'‘’「」『』]+?)" + Q, flat)
    if m:
        old, new = m.group(1), m.group(2)
        where = _in_folder(flat)
        src, dst = _join(base, where, old), _join(base, where, new)
        fs[src] = {"type": "dir"} if "." not in old else file_node(old)
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

    # ③ 删除"X"文件夹（整个文件夹，不是里面的文件）
    m = re.search(r"删除" + Q + r"([^\"“”'‘’「」『』]+?)" + Q + r"文件夹", flat)
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


def parse_win(stem: str) -> dict:
    base = _base_dir(stem)
    fs: dict = {}
    checks: list = []
    todo: list = []
    for item in split_items(stem):
        _win_item(item, base, fs, checks, todo)
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
FONT_WORDS = r"黑体|宋体|楷体|仿宋|微软雅黑|华文[\u4e00-\u9fa5]{1,3}|等线|隶书|幼圆"
ALIGN_WORDS = {"居中": "center", "右对齐": "right", "左对齐": "left",
               "两端对齐": "justify", "分散对齐": "distribute"}


_NOT_EXCERPT = re.compile(
    r"^(?:" + FONT_WORDS + r"|" + SIZE_WORDS + r"|标题|正文|普通数字\d?"
    r"|[上下左右]+型环绕|紧密型环绕|四周型环绕|居中|左对齐|右对齐"
    r"|[0-9.]+|[A-Za-z]+\d*|.{0,5}色)$")


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
            return head[:24]
    return ""


def _wps_item(text: str, checks: list, todo: list, needs: list,
              title: list | None = None) -> None:
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
                _wps_item(half, checks, todo, needs, title)
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
        key = _excerpt(flat, least=3)
        if key:
            needs.append(key)
            checks.append({"desc": f"把「{key[:10]}」那一段移到最后", "score": 4,
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
        key = _excerpt(flat)
        needs.append(key)
        target = {"has": key[:10]}
    elif "标题" in flat or "题目" in flat:
        target = 0                        # 没给标题内容就按第一段算
    elif re.search(r"第一(?:自然)?段", flat):
        target = 0
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
        want["style"] = "标题1"
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


ARTICLE = [
    "{topic}正在深刻改变我们的学习与生活。从课堂到校园，从家庭到城市，"
    "它带来的变化随处可见，也对每个人提出了新的要求。",
    "认识{topic}，先要了解它的基本原理与典型应用。只有把概念弄清楚，"
    "才能在真实场景中判断什么时候该用它、怎么用才合适。",
    "在实践中，我们既要看到{topic}带来的便利，也要留意其中的风险。"
    "保护个人信息、遵守使用规范，是每一位使用者应尽的责任。",
    "面向未来，希望同学们主动学习相关知识，动手尝试，在解决实际问题的过程中"
    "不断提升自己的信息素养。",
]


def _article(topic: str, needs: list) -> list[dict]:
    """给 WPS 题生成一篇像样的原文。

    **要被替换的词必须真的出现在正文里** —— 题目说「把 A 替换成 B」，文档里
    没有 A 的话这一问谁也做不出来。所以先把正文写好，再把这些词嵌进去。

    正文内容随便写没关系（考的是排版和查找替换，不是阅读理解），但**篇幅要够**：
    只有两行的文档，「正文所有段落设为首行缩进」这类题看不出效果，学生会以为
    自己做错了。
    """
    body = [text.format(topic=topic) for text in ARTICLE]
    for i, word in enumerate(needs):
        # 挨段塞，别全堆在第一段 —— 查找替换要能替换到多处才像真题
        at = i % len(body)
        body[at] = f"{body[at]}这里特别提到{word}，{word}是其中的关键一环。"
    return [{**blank_para(), "text": t} for t in body]


def parse_wps(stem: str) -> dict:
    """WPS 文字题。

    文档是**这里现生成的**：题库里只有题干，没有原卷素材。内容按题目名起一篇
    短文，够学生做排版和查找替换就行 —— 考点在格式和操作，不在文章本身。
    """
    checks: list = []
    todo: list = []
    needs: list = []
    title: list = []
    for item in split_items(stem):
        _wps_item(item, checks, todo, needs, title)

    name = "文档"
    m = re.search(Q + r"([^\"“”'‘’「」『』]+?)\.(?:docx?|wps)" + Q, str(stem))
    if m:
        name = m.group(1)
    topic = re.sub(r"[0-9]+$", "", name).strip() or "信息技术"

    paras = [{**blank_para(), "text": title[0] if title else topic}] +         _article(topic, needs)
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
    if not got:
        return None
    if got["kind"] != "ai" and not got["checks"]:
        return None                  # 认出题型却一条检查点都没造出来，不如不给

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
