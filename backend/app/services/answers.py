"""客观题怎么比对答案（2.27.0）：多选题、填空题。

## 多选题

还是「选择题」这个题型，答案写几个字母（ABD）就是多选。学生交上来的是勾中的**原选项字母**
（乱序时显示的是新字母，交的仍是原字母，见 frontend/src/shuffle.js），顺序不论：
「DBA」和「ABD」一样。**全对才得分**，漏选、错选都不给分 —— 和测评卷上写的规矩一致。

## 填空题

答案按「；」分成几个空，前面可以带「第一空：」：

    第一空：数据（特征数据）；第二空：特征库
    专业（或"领域专属"）
    姿态；关键

括号里的是**也算对**的说法（「或」「也可」这类字去掉）。学生每个空一个输入框，交上来的是
JSON 数组字符串 `["数据","特征库"]`；只有一个空时也可以直接是那个字符串（老客户端只有一个
输入框）。比对前去掉空格、标点、引号，不分全角半角、大小写。**按空给分**：两个空对一个给一半。
"""

from __future__ import annotations

import json
import re
import unicodedata

_CN_NUM = "一二三四五六七八九十"
_BLANK_HEAD = re.compile(rf"^第[{_CN_NUM}\d]+空\s*[:：]\s*")
_PAREN = re.compile(r"[（(]([^（）()]*)[）)]")
# 括号里的「或」「也可」引出的是另一种说法；正文里只认「/」分隔（「颜色、纹理」是一个答案，不是二选一）
_ALT_SPLIT = re.compile(r"\s*(?:或者|或|也可以|也可|/|／)\s*")
_MAIN_SPLIT = re.compile(r"\s*[/／]\s*")
_PUNCT = re.compile(r"[\s\"'“”‘’「」『』《》〈〉()（）\[\]【】,，。.、;；:：!！?？·]")


def letters(text: str) -> str:
    """选择题的答案 / 作答 → 排好序、去重的字母串（'DBA' → 'ABD'，'A,C' → 'AC'）。"""
    got = {c for c in unicodedata.normalize("NFKC", text or "").upper() if "A" <= c <= "Z"}
    return "".join(sorted(got))


def is_multi(item: dict) -> bool:
    """选择题的答案是不是不止一个字母。"""
    return item.get("type") == "选择题" and len(letters(item.get("answer") or "")) > 1


def _norm(text: str) -> str:
    return _PUNCT.sub("", unicodedata.normalize("NFKC", text or "").lower())


def blank_keys(answer: str) -> list[list[str]]:
    """填空题答案 → 每个空可以接受的写法。"""
    text = (answer or "").strip()
    text = re.sub(r"^[（(]?\s*答案\s*[:：]\s*", "", text)
    if text.count("（") + text.count("(") < text.count("）") + text.count(")"):
        text = re.sub(r"[）)]\s*$", "", text)      # 「（答案：…）」去掉开头后剩下的右括号
    out: list[list[str]] = []
    for part in re.split(r"[；;\n]", text):
        part = _BLANK_HEAD.sub("", part.strip())
        if not part:
            continue
        alts = []
        main = _PAREN.sub("", part)
        alts += [a for a in _MAIN_SPLIT.split(main) if a.strip()]
        for inner in _PAREN.findall(part):
            alts += [a for a in _ALT_SPLIT.split(inner) if a.strip()]
        keys = []
        for a in alts:
            k = _norm(a)
            if k and k not in keys:
                keys.append(k)
        if keys:
            out.append(keys)
    return out


def blank_count(item: dict) -> int:
    """这道填空题有几个空（发给学生，好画几个输入框 —— 只有个数，不是答案）。"""
    n = len(blank_keys(item.get("answer") or ""))
    if n:
        return n
    runs = re.findall(r"_{3,}|＿{2,}|（\s*）|\(\s*\)", item.get("stem") or "")
    return max(1, len(runs))


def split_blanks(mine: str) -> list[str]:
    """学生交上来的填空作答 → 每个空写了什么。"""
    mine = (mine or "").strip()
    if mine.startswith("["):
        try:
            got = json.loads(mine)
            if isinstance(got, list):
                return ["" if v is None else str(v) for v in got]
        except ValueError:
            pass
    return [mine]


def check_blanks(mine: str, answer: str) -> tuple[int, int]:
    """返回 (答对几个空, 一共几个空)。答案解析不出空来返回 (0, 0)，由调用方退回整串比对。"""
    keys = blank_keys(answer)
    if not keys:
        return 0, 0
    got = split_blanks(mine)
    hits = 0
    for i, ok in enumerate(keys):
        if i < len(got) and _norm(got[i]) in ok:
            hits += 1
    return hits, len(keys)


def judge(item: dict, mine: str, correct: str) -> tuple[bool, float]:
    """客观题判一道：返回 (全对没有, 得分比例 0~1)。correct 是 right_letter() 换算过的答案。"""
    qtype = item.get("type")
    if qtype == "选择题":
        ok = bool(letters(mine)) and letters(mine) == letters(correct)
        return ok, 1.0 if ok else 0.0
    if qtype == "填空题":
        hits, total = check_blanks(mine, correct)
        if total:
            return hits == total, hits / total
    ok = (mine or "").strip() == (correct or "").strip()
    return ok, 1.0 if ok else 0.0
