"""题目难度（1~5）的估算。

题库里原来没有难度这一列，三百多道题不可能靠人一条条标，所以给一个
**保守的自动估值**：先按题型定个底，再按题干长度和知识范围微调。

这是估算，不是判定 —— 它的作用是让新导入的题、老题库有个合理的起点，
老师看着不对随时在题库页面改。所以：
- 宁可都落在 2~4 之间，也不轻易给 1 或 5；
- 规则写得简单可读，老师问起来能解释得清。

同一套规则三处共用：0010 迁移给历史题目补值、导入时「难度」一栏留空、
界面上新增题目不选难度。三处结果一致，不会出现"同一道题两个难度"。
"""

import re

# 题型底分：判断题二选一最容易，操作题要动手做最难
_BY_TYPE = {
    "判断题": 2,
    "选择题": 3,
    "填空题": 3,
    "操作题": 4,
}
_DEFAULT_BASE = 3

# 偏难的知识范围 +1：编程、人工智能、物联网这几类初中生普遍吃力
_HARDER = ("Python", "编程", "程序", "算法", "人工智能", "物联网", "网络")
# 偏易的知识范围 -1：概念常识题居多
_EASIER = ("信息基础", "信息技术", "硬件", "软件")

MIN, MAX = 1, 5


def _visible_len(stem: str) -> int:
    """题干长度按去掉空白后算 —— 排版里的换行和空格不该让题目显得更难。"""
    return len(re.sub(r"\s+", "", stem or ""))


def estimate(qtype: str, stem: str = "", scope: str = "", option_count: int = 0) -> int:
    """估一个 1~5 的难度。三处调用点共用，改这里三处一起变。"""
    score = _BY_TYPE.get((qtype or "").strip(), _DEFAULT_BASE)

    n = _visible_len(stem)
    if n >= 90:
        score += 1          # 长题干多半带情境或材料，读都要读一会儿
    elif n <= 20:
        score -= 1          # 一句话的题基本是记忆性的

    s = scope or ""
    if any(k in s for k in _HARDER):
        score += 1
    elif any(k in s for k in _EASIER):
        score -= 1

    if option_count >= 5:
        score += 1          # 选项超过四个，排除法不好使了

    return max(MIN, min(MAX, score))


def clamp(value, fallback: int | None = None) -> int | None:
    """把用户填的难度收进 1~5。认不出来时返回 fallback（默认 None 表示"没填"）。"""
    if value is None or value == "":
        return fallback
    try:
        n = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return fallback
    return max(MIN, min(MAX, n))
