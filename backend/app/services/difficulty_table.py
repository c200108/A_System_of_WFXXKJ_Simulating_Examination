"""读 legacy/题目难度.json —— 部署时按题干哈希查这张表给题目赋难度。

为什么要有这张表：`estimate()` 是按题型和题干长度**猜**的，而这张表是**本地
那份库里实际的值**，包含老师手工调过的部分。写进 Git 跟着代码走，新服务器
部署出来的难度就和本地一模一样，不依赖"重新猜一遍碰巧猜出同样结果"。

查不到的题（老师后来加的）仍然走 estimate()，所以这张表不需要保持完整。

表在 legacy/ 里，和它描述的那份原始题库放在一起；docker-compose.yml 已经把
legacy/ 只读挂进容器，容器里也读得到。
"""

import json
import os

# 容器里 __file__ 是 /app/app/services/difficulty_table.py，
# 往上四层到 /，再进 legacy —— 正好是 compose 挂载的那个目录。
# 本地开发时往上四层到项目根，同样能找到。
TABLE_PATH = os.path.join(
    os.path.dirname(  # backend/ 或 /app
        os.path.dirname(  # backend/app
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    ),
    "legacy",
    "题目难度.json",
)

_cache: dict[str, int] | None = None


def load(path: str | None = None) -> dict[str, int]:
    """{题干哈希: 难度}。文件不在、坏了、格式不对都当作空表 —— 这只是锦上添花，
    绝不能因为它让部署起不来。"""
    global _cache
    if path is None and _cache is not None:
        return _cache

    table: dict[str, int] = {}
    try:
        with open(path or TABLE_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        for item in raw.get("题目") or []:
            h = item.get("hash")
            level = item.get("难度")
            if h and isinstance(level, int) and 1 <= level <= 5:
                table[h] = level
    except (OSError, ValueError, AttributeError):
        table = {}

    if path is None:
        _cache = table
    return table


def level_for(stem_hash: str, fallback: int) -> int:
    """查表；查不到就用调用方估出来的值。"""
    return load().get(stem_hash, fallback)
