"""仿真操作题：环境、检查点、判分。

操作题原来只能老师一份份看着给分。这里让三类操作题能机器判：

    win   Windows 文件管理   —— 虚拟文件系统
    wps   WPS 文字排版       —— 段落 + 页面设置的文档模型
    html  网页编程           —— 学生写的真代码

## 判的是终态，不是步骤

新建文件夹可以右键菜单、可以菜单栏、可以快捷键、可以拖拽；设置居中可以点
工具栏、可以 Ctrl+E、可以右键段落对话框。**按"点了哪几下"判分会把做对的
判错**，真考也是查结果文件，不查你怎么点的。

所以每个小问是一个**检查点**：一条针对最终状态的断言 + 一档分。做对几问
得几问的分，部分给分。操作日志照样存着，但只用于回放和申诉，不参与判分。

## 判分只在服务端

学生能改 JS、能改 localStorage。浏览器只负责把终态和日志交上来，
断言在这里跑。检查点（也就是答案）永远不发给学生 —— 和题目答案一样，
由 sim_for_student() 这一道关卡挡着。

## 老师仍有最终决定权

机器判出来的分是**预填**，写进答卷的 manual_json，老师在成绩页能改。
机器判错了老师能救 —— 不留人工出口的判分系统，出一次错就没人再信它。
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser

KINDS = ("win", "wps", "html")
KIND_NAMES = {"win": "Windows 操作", "wps": "WPS 文字", "html": "网页编程"}

# 学生交上来的终态最大多大。正常一道题几 KB，这个上限只用来挡住恶意的超大包
MAX_STATE_BYTES = 512 * 1024


# ================================================================ 通用
def blank_env(kind: str) -> dict:
    """一个空环境。新建仿真题时给个能直接用的起点。"""
    if kind == "win":
        return {"fs": {"C:/EXAM": {"type": "dir"}}, "recycle": {}}
    if kind == "wps":
        return {
            "name": "范文.wps",
            "paras": [{"text": "标题", **blank_para()}],
            "page": {"left": 3.18, "right": 3.18, "top": 2.54, "bottom": 2.54,
                     "orient": "portrait"},
            "header": "", "footer": "", "columns": 1,
        }
    return {"files": {"index.html": "<html>\n<head>\n<title></title>\n</head>\n"
                                    "<body>\n\n</body>\n</html>"}}


def blank_para() -> dict:
    """段落的默认格式。文档模型故意做成"格式挂在段落上"——中考的 WPS 题
    九成是「把某段设成……」，按段落记既够用又好断言。"""
    return {"font": "宋体", "size": "五号", "bold": False, "italic": False,
            "underline": False, "color": "", "align": "left", "indent": 0,
            "line": None, "before": 0, "after": 0}


def load_state(raw) -> dict:
    """把学生交上来的东西读成终态 dict。

    学生那边交的是 {"state": 终态, "log": [操作…]}（见 SimHost.vue），这里
    只取 state；日志留着是给回放和申诉用的，不参与判分。直接给一份终态也认。

    读不出来就当空的，不抛异常 —— 判分环节炸掉会让整份卷子交不上去，代价太大。
    """
    if isinstance(raw, dict):
        got = raw
    else:
        text = str(raw or "").strip()
        if not text or len(text.encode("utf-8", "ignore")) > MAX_STATE_BYTES:
            return {}
        try:
            got = json.loads(text)
        except (ValueError, TypeError):
            return {}
    if not isinstance(got, dict):
        return {}
    inner = got.get("state")
    return inner if isinstance(inner, dict) else got


def sim_for_student(task: dict) -> dict:
    """发给学生的那一份：只有环境，没有检查点。

    检查点就是答案。这里和 exam.strip_answers() 是同一个道理 ——
    多留一道关卡，以后改代码时不至于不小心把答案漏出去。
    """
    return {
        "id": task.get("id"),
        "kind": task.get("kind"),
        "title": task.get("title") or "",
        "env": task.get("env") or {},
    }


# ================================================================ 判分入口
def run_checks(kind: str, checks: list[dict], state: dict) -> dict:
    """逐个检查点断言，返回得分和每一条的通过情况。

    单条检查点抛异常时算没通过并把原因记下来，不让一条坏规则毁掉整道题。
    """
    runner = {"win": _check_win, "wps": _check_wps, "html": _check_html}.get(kind)
    results = []
    got = full = 0
    for i, chk in enumerate(checks or []):
        pts = max(0, int(chk.get("score") or 0))
        full += pts
        try:
            ok, why = runner(chk.get("assert") or {}, state) if runner else (False, "未知的题型")
        except Exception as exc:                      # noqa: BLE001 —— 见上面的说明
            ok, why = False, f"检查点写得有问题：{exc}"
        if ok:
            got += pts
        results.append({
            "no": i + 1,
            "desc": chk.get("desc") or f"第 {i + 1} 问",
            "score": pts,
            "earned": pts if ok else 0,
            "ok": ok,
            "why": why,
        })
    return {"score": got, "full": full, "results": results}


# ================================================================ win
def _fs(state: dict) -> dict:
    fs = state.get("fs")
    return fs if isinstance(fs, dict) else {}


def norm_path(path: str) -> str:
    """路径统一成 C:/a/b：反斜杠换成斜杠、去掉重复斜杠和结尾斜杠、盘符大写。

    学生在仿真器里点出来的路径和老师写检查点时敲的路径，写法难免不一样，
    不统一的话「明明建对了却判错」会成为最常见的投诉。
    """
    s = str(path or "").strip().replace("\\", "/")
    s = re.sub(r"/{2,}", "/", s).rstrip("/")
    if re.match(r"^[a-zA-Z]:", s):
        s = s[0].upper() + s[1:]
    return s


def _find(fs: dict, path: str):
    """按规范化后的路径取节点。大小写敏感 —— Windows 不区分大小写，
    但文件名大小写错了在中考里同样算错，这里跟着严。"""
    want = norm_path(path)
    for key, node in fs.items():
        if norm_path(key) == want and isinstance(node, dict):
            return node
    return None


def _check_win(a: dict, state: dict):
    op = a.get("op")
    fs = _fs(state)
    path = norm_path(a.get("path") or "")
    name = path.rsplit("/", 1)[-1] or path
    node = _find(fs, path)

    if op == "exists":
        if not node:
            return False, f"找不到「{name}」"
        want = a.get("is")
        if want and node.get("type") != want:
            got = "文件夹" if node.get("type") == "dir" else "文件"
            return False, f"「{name}」是{got}，要求是{'文件夹' if want == 'dir' else '文件'}"
        return True, f"「{name}」在"

    if op == "missing":
        return (False, f"「{name}」还在，应该删掉") if node else (True, f"「{name}」已经不在了")

    if op == "in_recycle":
        recycle = state.get("recycle") or {}
        hit = any(norm_path(k) == path for k in recycle)
        return (True, f"「{name}」在回收站里") if hit else (False, f"回收站里没有「{name}」")

    if op == "content":
        if not node:
            return False, f"找不到「{name}」"
        text = str(node.get("content") or "")
        if "equals" in a:
            want = str(a["equals"])
            return (text.strip() == want.strip(),
                    "内容对上了" if text.strip() == want.strip() else "文件内容和要求的不一样")
        want = str(a.get("has") or "")
        return (want in text, f"内容里有「{want}」" if want in text else f"内容里没有「{want}」")

    if op == "attr":
        if not node:
            return False, f"找不到「{name}」"
        for key, label in (("readonly", "只读"), ("hidden", "隐藏")):
            if key in a and bool(node.get(key)) != bool(a[key]):
                return False, f"「{name}」的{label}属性不对"
        return True, f"「{name}」的属性对了"

    if op == "count":
        # 某个文件夹下有几个东西。用来判「把三个文件都移进去」这类要求
        under = norm_path(a.get("path") or "") + "/"
        n = sum(1 for k in fs if norm_path(k).startswith(under)
                and "/" not in norm_path(k)[len(under):])
        want = int(a.get("equals", 0))
        return (n == want, f"「{name}」里有 {n} 项，要求 {want} 项")

    return False, f"不认识的检查方式：{op}"


# ================================================================ wps
SIZE_ALIASES = {
    "初号": 42, "小初": 36, "一号": 26, "小一": 24, "二号": 22, "小二": 18,
    "三号": 16, "小三": 15, "四号": 14, "小四": 12, "五号": 10.5, "小五": 9,
    "六号": 7.5, "小六": 6.5, "七号": 5.5, "八号": 5,
}


def same_size(a, b) -> bool:
    """「二号」和 22 是同一个字号。老师写检查点时两种写法都有人用。"""
    def pt(v):
        if v is None or v == "":
            return None
        s = str(v).strip()
        if s in SIZE_ALIASES:
            return SIZE_ALIASES[s]
        try:
            return float(s)
        except ValueError:
            return None
    pa, pb = pt(a), pt(b)
    return pa is not None and pb is not None and abs(pa - pb) < 0.01


def _paras(state: dict) -> list[dict]:
    got = state.get("paras")
    return [p for p in got if isinstance(p, dict)] if isinstance(got, list) else []


def _pick_para(paras: list[dict], at):
    """按序号或按内容找段落。

    按内容找是刻意支持的：题目常说「将描写『深圳男孩……』所在段落设为……」，
    而学生可能在前面插过段落，段落序号会变 —— 按序号判就冤枉人了。
    """
    if isinstance(at, dict):
        key = str(at.get("has") or "").strip()
        for p in paras:
            if key and key in str(p.get("text") or ""):
                return p
        return None
    try:
        i = int(at)
    except (TypeError, ValueError):
        return None
    return paras[i] if 0 <= i < len(paras) else None


PARA_LABELS = {
    "font": "字体", "size": "字号", "bold": "加粗", "italic": "倾斜",
    "underline": "下划线", "color": "颜色", "align": "对齐方式",
    "indent": "首行缩进", "before": "段前间距", "after": "段后间距",
}
ALIGN_NAMES = {"left": "左对齐", "center": "居中", "right": "右对齐",
               "justify": "两端对齐", "distribute": "分散对齐"}


def _check_wps(a: dict, state: dict):
    op = a.get("op")
    paras = _paras(state)

    if op == "para":
        p = _pick_para(paras, a.get("at", 0))
        if not p:
            return False, "找不到要检查的那一段（段落被删了，或者内容被改了）"
        for key in ("font", "color"):
            if key in a and str(p.get(key) or "") != str(a[key]):
                return False, f"{PARA_LABELS[key]}是「{p.get(key) or '默认'}」，要求「{a[key]}」"
        if "size" in a and not same_size(p.get("size"), a["size"]):
            return False, f"字号是「{p.get('size') or '默认'}」，要求「{a['size']}」"
        for key in ("bold", "italic", "underline"):
            if key in a and bool(p.get(key)) != bool(a[key]):
                want = "要" if a[key] else "不要"
                return False, f"{want}{PARA_LABELS[key]}"
        if "align" in a and str(p.get("align") or "left") != str(a["align"]):
            got = ALIGN_NAMES.get(str(p.get("align") or "left"), p.get("align"))
            return False, f"对齐方式是{got}，要求{ALIGN_NAMES.get(a['align'], a['align'])}"
        for key in ("indent", "before", "after"):
            if key in a and abs(float(p.get(key) or 0) - float(a[key])) > 0.01:
                return False, f"{PARA_LABELS[key]}是 {p.get(key) or 0}，要求 {a[key]}"
        if "line" in a:
            want, got = a["line"], p.get("line")
            if not _same_line(got, want):
                return False, f"行距不对（要求{_line_text(want)}）"
        return True, "这一段的格式对了"

    if op == "text":
        whole = "\n".join(str(p.get("text") or "") for p in paras)
        if "absent" in a and str(a["absent"]) in whole:
            return False, f"文中还有「{a['absent']}」没改掉"
        if "present" in a and str(a["present"]) not in whole:
            return False, f"文中找不到「{a['present']}」"
        return True, "文字内容对了"

    if op == "order":
        texts = [str(p.get("text") or "") for p in paras]
        if not texts:
            return False, "文档是空的"
        if "first" in a and str(a["first"]) not in texts[0]:
            return False, "第一段不是要求的那一段"
        if "last" in a and str(a["last"]) not in texts[-1]:
            return False, "最后一段不是要求的那一段"
        return True, "段落顺序对了"

    if op == "page":
        page = state.get("page") or {}
        for key, label in (("left", "左边距"), ("right", "右边距"),
                           ("top", "上边距"), ("bottom", "下边距")):
            if key in a and abs(float(page.get(key) or 0) - float(a[key])) > 0.01:
                return False, f"{label}是 {page.get(key) or 0} 厘米，要求 {a[key]} 厘米"
        if "orient" in a and str(page.get("orient") or "portrait") != str(a["orient"]):
            return False, "纸张方向不对"
        return True, "页面设置对了"

    if op in ("header", "footer"):
        got = str(state.get(op) or "").strip()
        label = "页眉" if op == "header" else "页脚"
        if "equals" in a:
            return (got == str(a["equals"]).strip(),
                    f"{label}是「{got or '空'}」，要求「{a['equals']}」")
        want = str(a.get("has") or "")
        return (want in got, f"{label}里{'有' if want in got else '没有'}「{want}」")

    if op == "columns":
        got = int(state.get("columns") or 1)
        want = int(a.get("equals") or 1)
        return (got == want, f"当前分了 {got} 栏，要求 {want} 栏")

    if op == "count":
        want = int(a.get("equals") or 0)
        return (len(paras) == want, f"现在有 {len(paras)} 段，要求 {want} 段")

    return False, f"不认识的检查方式：{op}"


def _same_line(got, want) -> bool:
    if not isinstance(got, dict) or not isinstance(want, dict):
        return got == want
    if str(got.get("type")) != str(want.get("type")):
        return False
    return abs(float(got.get("value") or 0) - float(want.get("value") or 0)) < 0.01


def _line_text(line) -> str:
    if not isinstance(line, dict):
        return "默认"
    kind = {"fixed": "固定值", "multiple": "多倍行距", "least": "最小值"}.get(
        str(line.get("type")), str(line.get("type")))
    unit = "磅" if line.get("type") in ("fixed", "least") else "倍"
    return f"{kind} {line.get('value')}{unit}"


# ================================================================ html
class _Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag, attrs=None, parent=None):
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[_Node] = []
        self.parent = parent
        self.text = ""

    def walk(self):
        for c in self.children:
            yield c
            yield from c.walk()

    def all_text(self) -> str:
        return (self.text + "".join(c.all_text() for c in self.children)).strip()


VOID = {"br", "hr", "img", "input", "meta", "link", "area", "base", "col",
        "embed", "param", "source", "track", "wbr"}


class _Builder(HTMLParser):
    """够用就行的 HTML 树。不引第三方库 —— 判分要在服务器上跑，
    少一个依赖少一处升级时会坏的地方。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        node = _Node(tag, {k: (v if v is not None else "") for k, v in attrs}, self.cur)
        self.cur.children.append(node)

    def handle_endtag(self, tag):
        node = self.cur
        while node is not self.root:
            if node.tag == tag:
                self.cur = node.parent
                return
            node = node.parent
        # 没配对的结束标签就当没看见：学生写的 HTML 本来就常常不闭合，
        # 不该因为少一个 </p> 就整道题判 0 分

    def handle_data(self, data):
        self.cur.text += data


def parse_html(text: str) -> _Node:
    b = _Builder()
    try:
        b.feed(str(text or ""))
    except Exception:                                  # noqa: BLE001
        pass
    return b.root


_SEL = re.compile(
    r"^([a-zA-Z][\w-]*|\*)?"                 # 标签
    r"((?:#[\w-]+|\.[\w-]+|\[[^\]]+\])*)$"   # #id .class [attr] [attr=值]
)
_COND = re.compile(r"#([\w-]+)|\.([\w-]+)|\[([^\]=]+)(?:([~^$*]?=)\"?'?([^\]\"']*)\"?'?)?\]")


def _match_one(node: _Node, part: str) -> bool:
    m = _SEL.match(part.strip())
    if not m:
        return False
    tag, rest = m.group(1), m.group(2) or ""
    if tag and tag != "*" and node.tag.lower() != tag.lower():
        return False
    for mid, cls, attr, oper, val in _COND.findall(rest):
        if mid and node.attrs.get("id") != mid:
            return False
        if cls and cls not in (node.attrs.get("class") or "").split():
            return False
        if attr:
            if attr not in node.attrs:
                return False
            if oper:
                got = node.attrs.get(attr) or ""
                if oper == "=" and got != val:
                    return False
                if oper == "*=" and val not in got:
                    return False
                if oper == "^=" and not got.startswith(val):
                    return False
                if oper == "$=" and not got.endswith(val):
                    return False
    return True


def select(root: _Node, selector: str) -> list[_Node]:
    """支持 `标签#id.类[属性=值]` 和用空格表示的后代关系，够初中网页题用。"""
    parts = [p for p in str(selector or "").split() if p]
    if not parts:
        return []
    found = [n for n in root.walk() if _match_one(n, parts[0])]
    for part in parts[1:]:
        nxt = []
        for base in found:
            nxt += [n for n in base.walk() if _match_one(n, part)]
        found = nxt
    return found


def _html_of(state: dict, file: str | None) -> str:
    files = state.get("files")
    if not isinstance(files, dict) or not files:
        return ""
    if file and file in files:
        return str(files[file] or "")
    return str(next(iter(files.values())) or "")


def _check_html(a: dict, state: dict):
    op = a.get("op")
    raw = _html_of(state, a.get("file"))

    if op == "raw":
        want = str(a.get("has") or "")
        hit = want.lower() in raw.lower()
        return hit, f"代码里{'有' if hit else '没有'}「{want}」"

    root = parse_html(raw)

    if op == "sel":
        sel = str(a.get("selector") or "")
        hit = select(root, sel)
        if "text" in a:
            want = str(a["text"]).strip()
            hit = [n for n in hit if want in n.all_text()]
        low = int(a.get("min", 1))
        if len(hit) < low:
            return False, f"「{sel}」找到 {len(hit)} 个，至少要 {low} 个"
        if "max" in a and len(hit) > int(a["max"]):
            return False, f"「{sel}」找到 {len(hit)} 个，最多 {a['max']} 个"
        return True, f"「{sel}」找到 {len(hit)} 个"

    if op == "attr":
        sel = str(a.get("selector") or "")
        name = str(a.get("name") or "")
        hit = select(root, sel)
        if not hit:
            return False, f"没找到「{sel}」"
        vals = [n.attrs.get(name, "") for n in hit if name in n.attrs]
        if not vals:
            return False, f"「{sel}」上没有 {name} 属性"
        if "equals" in a:
            want = str(a["equals"])
            return (want in vals, f"{name} 是 {vals[0]}，要求 {want}")
        if "has" in a:
            want = str(a["has"])
            hit2 = any(want in v for v in vals)
            return hit2, f"{name} 里{'有' if hit2 else '没有'}「{want}」"
        return True, f"「{sel}」有 {name} 属性"

    if op == "title":
        got = "".join(n.all_text() for n in select(root, "title")).strip()
        want = str(a.get("equals") or "")
        return (got == want, f"标题是「{got or '空'}」，要求「{want}」")

    return False, f"不认识的检查方式：{op}"


# ================================================================ 出题辅助
# 让老师在仿真器里把题做一遍，按「以当前状态为答案」，这里把初始环境和终态
# 一比，把改动翻译成检查点草稿。老师再改措辞、分值，删掉不想考的。
#
# 手写检查点 JSON 这件事，指望一线老师做是不现实的 —— 出题门槛决定了这套
# 系统最后有没有人用。
def propose(kind: str, env: dict, state: dict) -> list[dict]:
    maker = {"win": _propose_win, "wps": _propose_wps, "html": _propose_html}.get(kind)
    return maker(env or {}, state or {}) if maker else []


def _chk(desc: str, assertion: dict, score: int = 2) -> dict:
    return {"desc": desc, "score": score, "assert": assertion}


def _propose_win(env: dict, state: dict) -> list[dict]:
    before, after = _fs(env), _fs(state)
    bkeys = {norm_path(k) for k in before}
    out = []

    for key, node in after.items():
        path = norm_path(key)
        if re.fullmatch(r"[A-Za-z]:", path):
            continue                       # 盘符本身不是学生建出来的东西
        name = path.rsplit("/", 1)[-1]
        if path not in bkeys:
            kind = "dir" if node.get("type") == "dir" else "file"
            word = "文件夹" if kind == "dir" else "文件"
            out.append(_chk(f"新建{word}「{name}」", {"op": "exists", "path": path, "is": kind}))
            continue
        old = _find(before, path) or {}
        if str(old.get("content") or "") != str(node.get("content") or ""):
            text = str(node.get("content") or "").strip()
            if text:
                out.append(_chk(f"「{name}」里写上内容",
                                {"op": "content", "path": path, "has": text[:20]}))
        for attr, label in (("readonly", "只读"), ("hidden", "隐藏")):
            if bool(old.get(attr)) != bool(node.get(attr)):
                out.append(_chk(f"把「{name}」设为{label}" if node.get(attr) else f"取消「{name}」的{label}",
                                {"op": "attr", "path": path, attr: bool(node.get(attr))}))

    akeys = {norm_path(k) for k in after}
    for key in before:
        path = norm_path(key)
        if path not in akeys and not re.fullmatch(r"[A-Za-z]:", path):
            out.append(_chk(f"删掉「{path.rsplit('/', 1)[-1]}」", {"op": "missing", "path": path}))
    return out


def _propose_wps(env: dict, state: dict) -> list[dict]:
    out = []
    b_page, a_page = env.get("page") or {}, state.get("page") or {}
    changed = {k: a_page[k] for k in ("left", "right", "top", "bottom", "orient")
               if k in a_page and a_page.get(k) != b_page.get(k)}
    if changed:
        out.append(_chk("按要求设置页面", {"op": "page", **changed}, 3))

    for key, label in (("header", "页眉"), ("footer", "页脚")):
        got = str(state.get(key) or "").strip()
        if got != str(env.get(key) or "").strip() and got:
            out.append(_chk(f"添加{label}「{got}」", {"op": key, "equals": got}))

    if int(state.get("columns") or 1) != int(env.get("columns") or 1):
        out.append(_chk(f"分为 {state.get('columns')} 栏",
                        {"op": "columns", "equals": int(state.get("columns") or 1)}))

    before = {str(p.get("text") or ""): p for p in _paras(env)}
    keys = ("font", "size", "bold", "italic", "underline", "color",
            "align", "indent", "before", "after", "line")
    for p in _paras(state):
        text = str(p.get("text") or "")
        old = before.get(text)
        if old is None:
            continue                       # 内容改过的段落，格式差异说不清，留给老师自己加
        diff = {k: p.get(k) for k in keys
                if k in p and p.get(k) != old.get(k) and p.get(k) not in (None, "")}
        if diff:
            head = text.strip()[:10] or "这一段"
            out.append(_chk(f"把「{head}」所在段落按要求设置格式",
                            {"op": "para", "at": {"has": text.strip()[:10]}, **diff}, 3))

    gone = [t for t in before if t and t not in
            {str(p.get("text") or "") for p in _paras(state)}]
    for text in gone[:3]:
        out.append(_chk(f"删掉或改写「{text.strip()[:10]}」这一段",
                        {"op": "text", "absent": text.strip()[:10]}))
    return out


def _propose_html(env: dict, state: dict) -> list[dict]:
    before = parse_html(_html_of(env, None))
    after = parse_html(_html_of(state, None))
    b_count: dict[str, int] = {}
    for n in before.walk():
        b_count[n.tag] = b_count.get(n.tag, 0) + 1

    a_count: dict[str, int] = {}
    for n in after.walk():
        a_count[n.tag] = a_count.get(n.tag, 0) + 1

    out = []
    for tag, n in a_count.items():
        if tag in ("#root", "html", "head", "body"):
            continue
        if n > b_count.get(tag, 0):
            out.append(_chk(f"写出 {tag} 标签", {"op": "sel", "selector": tag, "min": n}))

    title = "".join(x.all_text() for x in select(after, "title")).strip()
    if title and title != "".join(x.all_text() for x in select(before, "title")).strip():
        out.append(_chk(f"网页标题设为「{title}」", {"op": "title", "equals": title}))
    return out
