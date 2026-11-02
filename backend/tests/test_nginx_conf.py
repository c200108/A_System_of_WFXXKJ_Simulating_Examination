"""前端容器里 nginx 的转发规则。

真出过：配图在题库、组卷、网页答题里全裂，只有 exe 正常。原因是「按扩展名缓存静态
文件」那条正则 location（\.(png|jpg|…)$）优先级比普通前缀 location 高，
/uploads/images/x.jpg 先被它截走、去前端的 html 目录里找，找不到就 404。
转给后端的前缀 location 必须带 ^~，前缀匹配上了就不再看正则。
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[2] / "frontend"
NGINX = FRONT / "nginx"
# 规则拆在 frontend/nginx/ 下几个文件里，http（nginx.conf）和 https（nginx/https.conf）共用
CONF_FILES = [NGINX / "static.conf", NGINX / "backend.conf"]


def _text():
    return "\n".join(p.read_text(encoding="utf-8") for p in CONF_FILES)


def _locations():
    return re.findall(r"^\s*location\s+(\S+)(?:\s+(\S+))?\s*\{", _text(), re.M)


def test_有按扩展名的正则时_转给后端的前缀都带脱字符():
    locs = _locations()
    has_regex = any(mod in ("~", "~*") for mod, _ in locs)
    assert has_regex, "正则 location 没了的话这条测试就该改写"
    for prefix in ("/uploads/", "/api/"):
        mods = [mod for mod, path in locs if path == prefix or mod == prefix]
        assert ("^~",) == tuple(mods), f"{prefix} 必须写成 location ^~ {prefix}，现在是 {mods}"


def test_配图转给后端():
    text = _text()
    block = text.split("location ^~ /uploads/", 1)[1].split("}", 1)[0]
    assert "proxy_pass http://backend:8000" in block


# ---------------------------------------------------------------- 可选的 HTTPS

def _includes(path):
    return re.findall(r"^\s*include\s+/etc/nginx/exam/(\S+);", path.read_text(encoding="utf-8"), re.M)


def test_默认配置只开80_规则全都引进来():
    text = (FRONT / "nginx.conf").read_text(encoding="utf-8")
    assert re.search(r"^\s*listen 80;", text, re.M)
    assert "443" not in re.sub(r"#.*", "", text), "没配证书的学校不该碰 443"
    assert _includes(FRONT / "nginx.conf") == ["base.conf", "static.conf", "backend.conf"]


def test_https配置_80上只跳网页_接口和配图照旧服务():
    """学生端 exe 用 http.client，不跟随跳转：填着 http 地址的 exe 不能因为开了 https 就挂掉。"""
    text = (NGINX / "https.conf").read_text(encoding="utf-8")
    plain, tls = text.split("listen 443", 1)
    assert "listen 80;" in plain
    assert "include /etc/nginx/exam/backend.conf;" in plain
    assert "include /etc/nginx/exam/static.conf;" not in plain
    assert re.search(r"location / \{\s*return 301 __HTTPS_ORIGIN__\$request_uri;", plain)
    for inc in ("base.conf", "static.conf", "backend.conf"):
        assert f"include /etc/nginx/exam/{inc};" in tls
    assert "/etc/nginx/ssl/fullchain.pem" in tls and "/etc/nginx/ssl/key.pem" in tls


def test_dockerfile把规则和切换脚本都拷进镜像():
    text = (FRONT / "Dockerfile").read_text(encoding="utf-8")
    for name in ("base.conf", "static.conf", "backend.conf", "https.conf"):
        assert f"nginx/{name}" in text
    assert "/etc/nginx/exam/http.conf" in text
    assert "/docker-entrypoint.d/40-exam-https.sh" in text


@pytest.mark.skipif(not shutil.which("sh"), reason="没有 sh")
def test_切换脚本语法():
    subprocess.run(["sh", "-n", str(NGINX / "40-exam-https.sh")], check=True)


def test_切换脚本是LF换行():
    """CRLF 的话容器里报 bad interpreter，前端整个起不来。"""
    assert b"\r\n" not in (NGINX / "40-exam-https.sh").read_bytes()
