# -*- coding: utf-8 -*-
"""把试卷 Word 文档拆成题库导入表。

    python -m tools.docx_to_bank "D:\\试卷文件夹"

也可以直接把几个文件丢进来：

    python -m tools.docx_to_bank 卷1.docx 卷2.docx

跑完在试卷旁边生成 `题库导入-<名字>-N题.xlsx` 和 `bank-images/`，
直接在「题库 → 批量导入」上传那个 xlsx 就行。Windows 上更省事的办法是
把文件夹拖到 scripts/试卷转题库.bat 上面，见 docs/试卷转题库.md。

## 认得什么样的文档

菁优网导出的那种「参考答案与试题解析」卷：

    12．（2分）·（2024•山东模拟）题干……（　　）
    A．xx    B．xx
    C．xx    D．xx
    【考点】信息安全．菁优网版权所有
    【答案】C
    【分析】……

自己排版的卷子多半认不出来，跑完会告诉你一道都没拆出来。

## 有意不做的事

- **【分析】一概不取**。那是出卷网站自己写的解析，不是题目本身。
  操作题的【答案】是一长串操作步骤，同理不抄，答案栏写「略」——
  这类题本来就由老师在「考试 → 成绩」里人工打分。
- **不连数据库、不调接口**。产出就是一个 xlsx，导不导、导之前改不改，
  都在你手里。

## 知识范围和难度是猜的

知识范围按题干里的关键词归到题库配置的那十类，难度按题型加"要不要
动笔算"估 1~5。**归错是常事**（一道考 Photoshop 的题在原卷里被标成
"Python程序设计基础"），导入前扫一眼这两列，或者导入后在题库页面改。
"""

import argparse
import difflib
import os
import re
import shutil
import sys
import zipfile
from collections import Counter
from xml.etree import ElementTree as ET

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# ================================================================ 配置
# 题库只认这十类知识范围（config.yaml 的 bank.scopes）。这里写一份默认的，
# 找得到 config.yaml 就以那份为准 —— 你改过配置，这个工具跟着变。
SCOPES = [
    "信息基础与信息技术", "计算机硬件", "计算机软件", "Windows系统操作", "WPS文字操作",
    "信息安全与网络道德", "计算机网络基础", "Python编程基础", "人工智能", "物联网",
]


def load_scopes() -> list[str]:
    try:
        from app.siteconfig import site  # noqa: WPS433

        got = [s for s in site.bank.scopes if s]
        return got or SCOPES
    except Exception:
        return SCOPES


# ================================================================ 一、读 docx
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def read_docx(path: str, tag: str, images: dict) -> list[str]:
    """读出一行行文字。遇到图片写成 [图:文件名]，图片本身记到 images 里。

    不用 python-docx —— docx 本身就是个 zip，读 word/document.xml 就够了，
    少装一个依赖。
    """
    with zipfile.ZipFile(path) as z:
        rels = {}
        try:
            for rel in ET.fromstring(z.read("word/_rels/document.xml.rels")):
                target = rel.get("Target", "")
                if "media/" in target:
                    rels[rel.get("Id")] = "word/" + target.lstrip("/").replace("../", "")
        except KeyError:
            pass

        root = ET.fromstring(z.read("word/document.xml"))
        seen: dict[str, str] = {}

        def mark(rid):
            member = rels.get(rid)
            if not member:
                return "[图]"
            if member not in seen:
                name = f"{tag}-{os.path.basename(member)}"
                seen[member] = name
                try:
                    images[name] = z.read(member)
                except KeyError:
                    pass
            return f"[图:{seen[member]}]"

        lines = []
        for p in root.find(W + "body").iter(W + "p"):
            out = []
            for node in p.iter():
                if node.tag == W + "t":
                    out.append(node.text or "")
                elif node.tag == W + "tab":
                    out.append("\t")
                elif node.tag == W + "br":
                    out.append(" ")
                elif node.tag == A + "blip":
                    out.append(mark(node.get(R + "embed")))
                elif node.tag == "{urn:schemas-microsoft-com:vml}imagedata":
                    out.append(mark(node.get(R + "id")))
            text = re.sub(r"[ \t]+", " ", "".join(out).replace("\u3000", " ")).strip()
            if text:
                lines.append(text)
        return lines


# ================================================================ 二、拆成一道道题
Q_HEAD = re.compile(r"^(\d{1,3})[．.、]\s*")
SECTION = re.compile(r"^[一二三四五六七八九十]+\s*[、．.]")
OPT_ONE = re.compile(r"^([A-DＡ-Ｄ])\s*[．.、,，:：]\s*(.*)$")
OPT_SPLIT = re.compile(r"(?=(?:^|[\t 　])[A-D][．.、])")
TAIL = re.compile(r"声明：试题解析著作权")
IMG_TAG = re.compile(r"\[图:([^\]]+)\]")


def strip_prefix(text: str) -> str:
    """去掉题号、分值、出处：「12．（2分）·（2024•山东模拟）正文」→「正文」"""
    text = Q_HEAD.sub("", text, count=1)
    for _ in range(2):
        text = re.sub(r"^（\s*\d+(\.\d+)?\s*分\s*）", "", text).strip()
        text = re.sub(r"^[·•]\s*", "", text).strip()
        text = re.sub(r"^（\s*20\d\d[^）]{0,14}）", "", text).strip()
    return text


def split_options(line: str):
    """一行里可能并排几个选项（A．甲 B．乙），拆开；拆不出返回 None。"""
    out = []
    for part in (p.strip() for p in OPT_SPLIT.split(line) if p.strip()):
        m = OPT_ONE.match(part)
        if not m:
            return None
        out.append([m.group(1), m.group(2).strip()])
    return out or None


def split_questions(lines: list[str], source: str) -> list[dict]:
    section, blocks, cur = "", [], None
    for line in lines:
        if TAIL.search(line):
            break  # 底下是网站的版权声明，不是题
        if SECTION.match(line) and not Q_HEAD.match(line):
            section = line
            continue

        m = Q_HEAD.match(line)
        # 【答案】里也会有 "1．…" 这种分条编号（多小问的操作题尤其常见），
        # 不能见到数字就当新题。规矩：在答案段里，只有编号比当前题号大才算新题 ——
        # 答案里的分条都是从 1 重新数的，不会大过题号。
        if m and (cur is None or not cur["_ans"] or int(m.group(1)) > cur["no"]):
            if cur:
                blocks.append(cur)
            cur = {"no": int(m.group(1)), "section": section, "source": source,
                   "head": [strip_prefix(line)], "opts": [], "point": "",
                   "answer": [], "_ans": False, "_ana": False}
            continue
        if cur is None:
            continue

        if line.startswith("【考点】"):
            cur["point"] = re.sub(r"．?菁优网版权所有", "", line[4:]).strip()
            cur["_ans"] = cur["_ana"] = False
        elif line.startswith("【答案】"):
            cur["_ans"], cur["_ana"] = True, False
            cur["answer"].append(line[4:].strip())
        elif line.startswith(("【分析】", "【点评】", "【解答】")):
            cur["_ana"], cur["_ans"] = True, False
        elif cur["_ana"]:
            continue
        elif cur["_ans"]:
            cur["answer"].append(line)
        else:
            opts = split_options(line)
            if opts:
                cur["opts"] += opts
            else:
                cur["head"].append(line)
    if cur:
        blocks.append(cur)

    for b in blocks:
        b.pop("_ans"), b.pop("_ana")
        b["stem"] = "\n".join(b.pop("head")).strip()
        b["answer"] = " ".join(b["answer"]).strip()
    return blocks


# ================================================================ 三、清洗
JUDGE_TAIL = re.compile(r"\s*([√×对错])\s*[。.]?\s*（\s*判断对错\s*）\s*[。.]?\s*$")
# 操作步骤的话术。答案里出现这些，说明是"怎么点鼠标"的解说，不是题目的答案
STEP_WORDS = re.compile(r"单击|双击|右键|鼠标|在弹出的|工具栏|菜单|选项卡")
TRUE_WORDS = ("√", "对", "T", "正确", "是")


def guess_type(section: str, stem: str, opts: list) -> str:
    if "填空" in section:
        return "填空题"
    if "判断" in section:
        return "判断题"
    if any(k in section for k in ("操作", "文件管理", "解答")):
        return "操作题"
    if len(opts) >= 2:
        return "选择题"
    # 选择题栏目里偶尔混进一道没有选项的大题，按长短判：长的是操作题
    return "操作题" if len(stem) > 60 else ""


def clean_one(b: dict) -> dict:
    stem, ans = b["stem"], b["answer"]
    qtype = guess_type(b["section"], stem, b["opts"])

    imgs = IMG_TAG.findall(stem)
    opt_img = any(IMG_TAG.search(o) or o.strip() == "[图]" for _, o in b["opts"])

    if qtype == "判断题":
        # 原卷把答案印在题干里：「…只有一个。 √ （判断对错）」
        m = JUDGE_TAIL.search(stem)
        if m:
            stem = stem[: m.start()].strip()
            ans = ans or m.group(1)
        a = ans.strip().rstrip("。.")
        ans = "正确" if a in TRUE_WORDS else ("错误" if a else "")
    elif qtype == "填空题":
        # 答案也印在题干里：「可使用 input 函数」→ 挖成下划线
        a = ans.strip().rstrip("。.")
        first = re.split(r"[；;]|（或", a)[0].strip()
        for cand in (a, first):
            if cand and f" {cand} " in stem:
                stem = stem.replace(f" {cand} ", " ＿＿＿＿ ", 1)
                break
            if cand and cand in stem:
                stem = stem.replace(cand, "＿＿＿＿", 1)
                break
        ans = a
    elif qtype == "选择题":
        m = re.match(r"^([A-D])\b", ans.strip())
        ans = m.group(1) if m else ans.strip()[:1].upper()
    else:
        # 操作题的【答案】是出卷网站写的操作步骤，不抄 —— 认出"单击…右键…
        # 在弹出的窗口中"这类步骤话术，或者一长串，就换成「略」。
        # 短的、又不像步骤的（Python 补全题的 ①float ②else、几行代码）
        # 是题目本身的答案，留着。
        ans = ans.strip()
        if not ans or len(ans) > 120 or STEP_WORDS.search(ans):
            ans = "略（按题干要求逐步操作，完成后保存文件）"

    stem = re.sub(r"\s*[。.]?\s*（\s*判断对错\s*）", "", stem)
    stem = IMG_TAG.sub("", stem).replace("[图]", "").strip()
    stem = re.sub(r"\n{2,}", "\n", re.sub(r"[ ]{2,}", " ", stem))

    return {"source": b["source"], "no": b["no"], "type": qtype, "stem": stem,
            "opts": [[lb, IMG_TAG.sub("[图]", t).strip()] for lb, t in b["opts"]],
            "answer": ans, "point": b["point"], "imgs": imgs, "opt_img": opt_img}


# ================================================================ 四、知识范围
# (知识范围, 关键词)。从上往下匹配，先命中的算数 —— 顺序就是优先级。
# 安全排在网络前面：「防火墙」「网络道德」这类题考的是安全意识，不是网络原理。
RULES = [
    ("物联网", r"物联|传感器|智能家居|RFID|射频|NB-IoT|ZigBee|智能穿戴|感知层|"
               r"智能门锁|智能路灯|车联网|嵌入式|单片机|开源硬件|Arduino|掌控板|温湿度|"
               r"智能手环|智能垃圾|智能喷头|智能风扇|智能摄像头|ETC|无人驾驶快递|"
               r"智慧(农业|果园|交通|校园|城市|图书馆|大棚)|"
               r"子系统|反馈控制|执行模块|呈现模块|感知模块|自动分拣"),
    ("人工智能", r"人工智能|机器学习|深度学习|神经网络|语音识别|语音输入|人脸识别|图像识别|"
                r"文字识别|指纹|虹膜|生物特征|无人驾驶|自动驾驶|机器人|图灵|KNN|"
                r"虚拟现实|专家系统|智能推荐"),
    # Py(t)hon 那几种常见错拼也认（原卷里就有写成 Pyhon 的）。
    # 两个词要挡一下：「下列表述正确的是」里的"列表"、WPS 里的"首行缩进"，
    # 不挡的话一道排版操作题会被当成编程题
    ("Python编程基础", r"[Pp]y(th|ht|t|h)?on|print|input|for |while |range|变量|循环|"
                      r"分支|程序段|代码|流程图|算法|编程|程序设计|语句|函数|运算符|"
                      r"表达式|赋值|注释|IDLE|(?<!下)列表|元组|(?<!首行)(?<!悬挂)缩进|\.py"),
    ("WPS文字操作", r"WPS|Word|文档|段落|首行缩进|字号|字体|页眉|页脚|分栏|文本框|艺术字|"
                   r"项目符号|查找与替换|页边距|环绕方式|格式刷|幻灯片|演示文稿|"
                   r"Excel|单元格|工作表|排版|打印预览|纸张"),
    ("Windows系统操作", r"Windows|资源管理器|回收站|文件夹|快捷方式|快捷键|任务栏|桌面|"
                       r"窗口|重命名|剪切|复制|粘贴|文件名|命名|扩展名|文件属性|磁盘|C盘|"
                       r"控制面板|系统属性|解压|WinRAR"),
    ("信息安全与网络道德", r"病毒|杀毒|木马|黑客|防火墙|密码|安全|加密|备份|隐私|知识产权|"
                         r"版权|侵权|盗版|违法|法律|道德|谣言|诈骗|沉迷|不良信息|实名|"
                         r"身份认证|权限|漏洞|勒索"),
    ("计算机网络基础", r"网络|Internet|因特网|互联网|IP地址|域名|网址|URL|浏览器|网页|"
                     r"电子邮件|E﹣mail|E-mail|邮箱|局域网|广域网|城域网|路由|交换机|"
                     r"网关|协议|TCP|HTTP|FTP|搜索引擎|上网|下载|WiFi|光纤|带宽|"
                     r"服务器|云盘|网盘|收藏夹|主页|首页|HTML|拓扑"),
    ("计算机硬件", r"硬件|CPU|中央处理器|内存|运算器|控制器|存储器|硬盘|主板|显卡|显示器|"
                  r"键盘|鼠标|打印机|扫描仪|摄像头|音箱|U盘|光驱|输入设备|输出设备|"
                  r"外设|主频|接口|USB|冯•诺依曼|冯诺依曼|超级计算机|RAM|ROM|"
                  r"键位|指法|基准键"),
    ("计算机软件", r"软件|操作系统|系统软件|应用软件|驱动|鸿蒙|格式工厂|Photoshop|画图|"
                  r"美图|会声会影|音频|视频|图像|图片|像素|分辨率|MP3|MP4|AVI|WAV|"
                  r"JPG|GIF|BMP|采样|剪辑|3D打印|建模"),
    ("信息基础与信息技术", r"信息|二进制|十进制|字节|比特|KB|MB|GB|TB|存储单位|编码|ASCII|"
                        r"数字化|载体|时效性|共享性|信息技术|计算机的发展|电子管|晶体管|"
                        r"集成电路|数据库|大数据|条形码|二维码"),
]

# 题干里一点线索都没有时，拿原卷的【考点】兜底
POINT_MAP = {
    "Python程序设计基础": "Python编程基础", "Python程序基本结构": "Python编程基础",
    "程序结构": "Python编程基础", "算法与程序设计": "Python编程基础",
    "物联网": "物联网", "机器人与传感器": "物联网", "人工智能": "人工智能",
    "Word基本操作": "WPS文字操作", "Word版面编排": "WPS文字操作",
    "Word表格处理": "WPS文字操作",
    "网络应用": "计算机网络基础", "网络基础知识": "计算机网络基础",
    "网页制作": "计算机网络基础",
    "信息安全": "信息安全与网络道德", "网络安全道德": "信息安全与网络道德",
    "计算机系统": "计算机软件", "计算机工作原理": "计算机硬件",
    "计算机的发展及应用": "信息基础与信息技术",
    "信息与信息技术": "信息基础与信息技术", "信息的获取": "信息基础与信息技术",
    "信息的加工与表达": "信息基础与信息技术",
    "声音的获取与加工": "计算机软件", "视频的获取与加工": "计算机软件",
    "图片的获取与加工": "计算机软件",
}


def guess_scope(item: dict, scopes: list[str]) -> str:
    """**先只看题干**，题干里找不到线索才连选项一起看。

    反过来做会被选项带偏：「计算机的发展经历了电子管、（ ）、集成电路……」
    有个选项写着"物联网计算机"，连选项一起匹配就归到物联网去了。
    """
    for text in (item["stem"], item["stem"] + " " + " ".join(o[1] for o in item["opts"])):
        for scope, pattern in RULES:
            if scope in scopes and re.search(pattern, text):
                return scope
    p = item["point"].split("；")[0].strip()
    got = POINT_MAP.get(p) or POINT_MAP.get(item["point"].strip())
    return got if got in scopes else scopes[0]


# ================================================================ 五、难度
# 要动笔算、或者要在脑子里把程序跑一遍的。只在题干上匹配，不看选项 ——
# 选项里出现 // 或 % 多半是把运算符当答案（记忆题），网址里的 // 更不相干。
CALC = re.compile(r"进制|转换为|转化为|换算|最多能存|个字节|运行结果|输出结果|执行结果|"
                  r"的值是|返回结果|结果是（|结果为（|的结果是|流程图|程序段|算法后")
URL = re.compile(r"https?[：:]//\S*")
COMBO = re.compile(r"①.*②")               # ①②③④ 组合项，要逐条判断
RECALL = re.compile(r"^(在[^，。]{0,12}中，)?[^，。]{0,24}(是|的是|叫做|称为|简称|全称)（ ）$")
HARD_SCOPES = ("人工智能", "物联网")


def guess_level(item: dict, scope: str) -> int:
    """估 1~5。底分按题型，再看要不要算、要不要读一大段情境。"""
    qtype, stem = item["type"], item["stem"]
    n = len(re.sub(r"\s+", "", stem))

    if qtype == "操作题":
        steps = len(re.findall(r"（\s*\d\s*）", stem))
        return 5 if steps >= 4 or "程序" in stem or "编程" in stem else 4
    if qtype == "填空题":
        return 4 if scope in ("Python编程基础", "计算机网络基础") else 3
    if qtype == "判断题":
        score = 2
        if scope in ("Python编程基础",) + HARD_SCOPES:
            score += 1          # 这几类概念新，学生印象浅
        if n <= 18:
            score -= 1          # 「文件删除后一定进回收站」这种一眼就能判
        return max(1, min(5, score))

    score = 3
    if CALC.search(URL.sub("", stem)):
        score += 2              # 要动笔算或跑程序，最费劲
    elif COMBO.search(stem + " ".join(o[1] for o in item["opts"])):
        score += 1
    elif n >= 80:
        score += 1              # 长情境题，读都要读一会儿
    if RECALL.match(stem) and not CALC.search(stem):
        score -= 1              # 直接问定义、简称
    if scope == "Python编程基础":
        score += 1              # 编程是初中最吃力的一块
    elif scope in HARD_SCOPES and n >= 40:
        # 新内容里的情境题确实难；但「物联网的基础是（ ）」这种一句话的
        # 定义题并不难，不该因为属于新单元就整体上浮一档
        score += 1
    elif scope == "信息基础与信息技术":
        score -= 1
    return max(1, min(5, score))


# ================================================================ 六、查重
def dedup_key(item: dict) -> str:
    s = item["stem"] + "|" + "|".join(o[1] for o in item["opts"])
    return re.sub(r"[\s（）()【】。，,、；;：:？?\"“”'’]", "", s)


def dedup(items: list[dict], ratio: float):
    """题干+选项相似度超过阈值的只留第一道，再按题干去掉空白查一遍。

    第二遍是照着题库自己的判重（stem_hash）来的：题干一模一样、只有选项里
    人名不同的两道题，导进去也只会留一道，不如这里就留一道。
    """
    kept, dropped = [], []          # kept 里存 (题, 比对用的字符串)
    for x in items:
        ka = dedup_key(x)
        hit = None
        for y, kb in kept:
            if abs(len(ka) - len(kb)) > max(len(ka), len(kb), 1) * 0.2:
                continue            # 长度差太多，不可能像，省一次逐字比对
            if difflib.SequenceMatcher(None, ka, kb).ratio() >= ratio:
                hit = y
                break
        (dropped.append((x, hit)) if hit else kept.append((x, ka)))

    seen, unique = {}, []
    for x, _ in kept:
        h = re.sub(r"\s+", "", x["stem"])
        if h in seen:
            dropped.append((x, seen[h]))
            continue
        seen[h] = x
        unique.append(x)
    return unique, dropped


# ================================================================ 七、写表
COLS = ["题型", "题干", "可选项", "答案", "知识范围", "图片", "难度"]
WIDTH = {"题型": 9, "题干": 66, "可选项": 40, "答案": 12, "知识范围": 20, "图片": 30, "难度": 7}
TYPE_ORDER = ["选择题", "判断题", "填空题", "操作题"]


def write_xlsx(items, scopes, out_dir, images, with_images, label=""):
    os.makedirs(out_dir, exist_ok=True)
    img_dir = os.path.join(out_dir, "bank-images")
    if with_images:
        shutil.rmtree(img_dir, ignore_errors=True)
        os.makedirs(img_dir, exist_ok=True)

    items.sort(key=lambda x: (scopes.index(x["scope"]),
                              TYPE_ORDER.index(x["type"]) if x["type"] in TYPE_ORDER else 9,
                              x["level"]))

    wb = Workbook()
    ws = wb.active
    ws.title = "题目"
    ws.append(COLS)

    used = 0
    for x in items:
        url = ""
        if with_images and x["imgs"] and x["imgs"][0] in images:
            name = x["imgs"][0]
            with open(os.path.join(img_dir, name), "wb") as f:
                f.write(images[name])
            url = f"/uploads/bank-images/{name}"
            used += 1
        ws.append([
            x["type"], x["stem"],
            "\n".join(f"{lb}.{t}" for lb, t in x["opts"]) if x["type"] != "判断题" else "",
            x["answer"], x["scope"], url, x["level"],
        ])

    fill = PatternFill("solid", fgColor="DDEBF7")
    for i, c in enumerate(COLS, 1):
        cell = ws.cell(row=1, column=i)
        cell.font, cell.fill = Font(bold=True), fill
        ws.column_dimensions[get_column_letter(i)].width = WIDTH[c]
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    ws.freeze_panes = "A2"

    # 说明表没有「题型」「题干」表头，导入时整表跳过，不会被当成题目读
    ws2 = wb.create_sheet("说明")
    for line in [
        ["这份表怎么来的"],
        ["由 backend/tools/docx_to_bank.py 从试卷 Word 文档自动拆出来的。"],
        [f"共 {len(items)} 道题，表头和列序与「题库导入模板」一致，"],
        ["直接在「题库 → 批量导入」上传即可。"],
        [],
        ["题型", *(f"{k} {v}" for k, v in Counter(x['type'] for x in items).most_common())],
        ["难度", *(f"{k}级 {v}" for k, v in sorted(Counter(x['level'] for x in items).items()))],
        [],
        ["知识范围"],
        *[[k, v] for k, v in Counter(x["scope"] for x in items).most_common()],
        [],
        ["带图的题"],
        [f"{used} 道题的题干里有图，图片在同目录的 bank-images 文件夹里。"],
        ["导入前把 bank-images 整个拷到服务器的 data/uploads/ 下面，"],
        ["否则这些题会显示成裂图。不想要图就把「图片」整列清空。"],
        [],
        ["请务必过目"],
        ["知识范围和难度是程序估的，会有估错的。导入前扫一眼这两列，"],
        ["或者导入后在题库页面改 —— 改了不影响已经发出去的卷子。"],
    ]:
        ws2.append(line)
    ws2.column_dimensions["A"].width = 64
    ws2.column_dimensions["B"].width = 16
    ws2["A1"].font = Font(bold=True, size=13)

    # 文件名带上试卷文件夹的名字，攒了几批之后还能认出哪份是哪份
    name = f"题库导入-{label or '题目'}-{len(items)}题.xlsx"
    path = os.path.join(out_dir, name)
    wb.save(path)
    return path, used


# ================================================================ 主流程
def collect(paths: list[str]) -> list[str]:
    """把命令行给的文件夹 / 文件摊平成一串 .docx。"""
    out = []
    for p in paths:
        if os.path.isdir(p):
            out += [os.path.join(p, f) for f in sorted(os.listdir(p))
                    if f.lower().endswith(".docx") and not f.startswith("~$")]
        elif p.lower().endswith(".docx"):
            out.append(p)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="把试卷 Word 文档拆成题库导入表",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='例：python -m tools.docx_to_bank "D:\\试卷"',
    )
    ap.add_argument("paths", nargs="+", help="试卷文件夹，或者若干个 .docx 文件")
    ap.add_argument("-o", "--out", help="输出到哪个文件夹（默认放试卷旁边）")
    ap.add_argument("--no-images", action="store_true", help="不要图片，图片列留空")
    ap.add_argument("--similar", type=float, default=0.95,
                    help="相似度超过多少算重复，默认 0.95")
    args = ap.parse_args(argv)

    files = collect(args.paths)
    if not files:
        print("没找到 .docx 文件。把试卷文件夹拖过来，或者直接给几个 .docx。")
        return 1

    scopes = load_scopes()
    images: dict[str, bytes] = {}
    raw, per_file = [], []

    print(f"读 {len(files)} 个文档……")
    for i, path in enumerate(files, 1):
        name = os.path.basename(path)
        try:
            lines = read_docx(path, f"p{i:02d}", images)
        except Exception as exc:
            print(f"  ✗ {name[:36]:38} 打不开：{exc}")
            per_file.append((name, 0))
            continue
        got = [clean_one(b) for b in split_questions(lines, name)]
        raw += got
        per_file.append((name, len(got)))
        print(f"  · {name[:36]:38} {len(got):3} 题")

    # 认不出题型的、四个选项都是图片的，都留不住
    bad_type = [x for x in raw if not x["type"]]
    opt_img = [x for x in raw if x["opt_img"]]
    items = [x for x in raw if x["type"] and not x["opt_img"]]
    if not items:
        print("\n一道题都没拆出来。这个工具只认菁优网那种带【答案】的卷子，"
              "\n自己排版的卷子请手工填模板。")
        return 1

    for x in items:
        x["scope"] = guess_scope(x, scopes)
        x["level"] = guess_level(x, x["scope"])

    items, dupes = dedup(items, args.similar)

    src_dir = os.path.dirname(os.path.abspath(files[0]))
    out_dir = args.out or os.path.join(src_dir, "题库导入")
    path, used = write_xlsx(items, scopes, out_dir, images, not args.no_images,
                            label=os.path.basename(src_dir))

    print(f"\n拆出 {len(raw)} 道，丢掉 {len(bad_type) + len(opt_img)} 道，"
          f"重复 {len(dupes)} 道，最终 {len(items)} 道")
    if opt_img:
        print(f"  丢掉的里面 {len(opt_img)} 道是「四个选项都是图片」—— 模板一道题只放一张图，表达不了")
    if bad_type:
        print(f"  另有 {len(bad_type)} 道认不出题型（多半不是题目）")
    for x, y in dupes[:6]:
        print(f"  重复：{x['source'][:14]}#{x['no']} 同 {y['source'][:14]}#{y['no']}  {x['stem'][:28]}")
    if len(dupes) > 6:
        print(f"  …… 还有 {len(dupes) - 6} 道重复的")

    print("\n题型", dict(Counter(x["type"] for x in items).most_common()))
    print("难度", dict(sorted(Counter(x["level"] for x in items).items())))
    print("范围", dict(Counter(x["scope"] for x in items).most_common()))
    print(f"\n写出：{path}")
    if used:
        print(f"图片：{os.path.join(out_dir, 'bank-images')}（{used} 张）"
              f"\n      导入前把这个文件夹整个拷到服务器的 data/uploads/ 下面")
    print("\n下一步：在「题库 → 批量导入」上传这个 xlsx。"
          "\n        知识范围和难度是估的，上传前扫一眼这两列。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
