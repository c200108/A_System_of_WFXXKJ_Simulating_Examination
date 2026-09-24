"""前端容器里 nginx 的转发规则。

真出过：配图在题库、组卷、网页答题里全裂，只有 exe 正常。原因是「按扩展名缓存静态
文件」那条正则 location（\.(png|jpg|…)$）优先级比普通前缀 location 高，
/uploads/images/x.jpg 先被它截走、去前端的 html 目录里找，找不到就 404。
转给后端的前缀 location 必须带 ^~，前缀匹配上了就不再看正则。
"""

import re
from pathlib import Path

CONF = Path(__file__).resolve().parents[2] / "frontend" / "nginx.conf"


def _locations():
    return re.findall(r"^\s*location\s+(\S+)(?:\s+(\S+))?\s*\{", CONF.read_text(encoding="utf-8"), re.M)


def test_有按扩展名的正则时_转给后端的前缀都带脱字符():
    locs = _locations()
    has_regex = any(mod in ("~", "~*") for mod, _ in locs)
    assert has_regex, "正则 location 没了的话这条测试就该改写"
    for prefix in ("/uploads/", "/api/"):
        mods = [mod for mod, path in locs if path == prefix or mod == prefix]
        assert ("^~",) == tuple(mods), f"{prefix} 必须写成 location ^~ {prefix}，现在是 {mods}"


def test_配图转给后端():
    text = CONF.read_text(encoding="utf-8")
    block = text.split("location ^~ /uploads/", 1)[1].split("}", 1)[0]
    assert "proxy_pass http://backend:8000" in block
