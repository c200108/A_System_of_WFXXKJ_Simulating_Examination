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
    assert _includes(FRONT / "nginx.conf") == ["base.conf", "static.conf", "backend.conf", "cloud.conf"]


def test_https配置_80上只跳网页_接口和配图照旧服务():
    """学生端 exe 用 http.client，不跟随跳转：填着 http 地址的 exe 不能因为开了 https 就挂掉。"""
    text = (NGINX / "https.conf").read_text(encoding="utf-8")
    plain, tls = text.split("listen 443", 1)
    assert "listen 80;" in plain
    assert "include /etc/nginx/exam/backend.conf;" in plain
    assert "include /etc/nginx/exam/static.conf;" not in plain
    assert re.search(r"location / \{\s*return 301 __HTTPS_ORIGIN__\$request_uri;", plain)
    for inc in ("base.conf", "static.conf", "backend.conf", "cloud.conf"):
        assert f"include /etc/nginx/exam/{inc};" in tls
    # 云盘是网页，80 上跟着跳 https，不单独服务
    assert "cloud.conf" not in plain
    assert "/etc/nginx/ssl/fullchain.pem" in tls and "/etc/nginx/ssl/key.pem" in tls


def test_dockerfile把规则和切换脚本都拷进镜像():
    text = (FRONT / "Dockerfile").read_text(encoding="utf-8")
    for name in ("base.conf", "static.conf", "backend.conf", "cloud.conf", "https.conf"):
        assert f"nginx/{name}" in text
    assert "/etc/nginx/exam/http.conf" in text
    assert "/docker-entrypoint.d/40-exam-https.sh" in text


@pytest.mark.skipif(not shutil.which("sh"), reason="没有 sh")
def test_切换脚本语法():
    subprocess.run(["sh", "-n", str(NGINX / "40-exam-https.sh")], check=True)


def test_切换脚本是LF换行():
    """CRLF 的话容器里报 bad interpreter，前端整个起不来。"""
    assert b"\r\n" not in (NGINX / "40-exam-https.sh").read_bytes()


# ---------------------------------------------------------------- 个人云盘（2.25.0）
CLOUD = NGINX / "cloud.conf"


def _cloud():
    return re.sub(r"#.*", "", CLOUD.read_text(encoding="utf-8"))


def test_云盘前缀带脱字符_openlist的静态文件不被按扩展名的正则截走():
    assert re.search(r"location \^~ /cloud/ \{", _cloud())


def test_openlist不写死在proxy_pass里_它没起来前端照样能启动():
    """写死 http://openlist:5244 的话 nginx 启动时就要解析，openlist 容器不在整个网站都起不来。"""
    text = _cloud()
    assert "proxy_pass http://openlist" not in text
    assert "set $openlist_upstream http://openlist:5244;" in text
    assert "resolver 127.0.0.11" in text
    assert text.count("proxy_pass $openlist_upstream;") == 3


def test_上传先问后端额度_绕得过额度的接口一律挡掉():
    text = _cloud()
    put = text.split("location ~ ^/cloud/api/fs/(put|form)$", 1)[1].split("}", 1)[0]
    assert "auth_request /_cloud_gate;" in put
    gate = text.split("location = /_cloud_gate {", 1)[1].split("}", 1)[0]
    assert "internal;" in gate and "proxy_pass http://backend:8000/api/cloud/gate;" in gate
    assert "proxy_pass_request_body off;" in gate and "X-Upload-Length $http_content_length" in gate
    groups = re.findall(r"location ~ \^/cloud/api/fs/\(([^)]*)\)", text)
    blocked = next(g for g in groups if "multipart/" in g).split("|")
    for name in ("multipart/", "add_offline_download", "torrent/", "seed/"):
        assert name in blocked
    assert "location = /cloud/api/me/update" in text


def test_云盘的提示是合法json():
    import json

    for body in re.findall(r"return 200 '(\{.*?\})';", CLOUD.read_text(encoding="utf-8")):
        data = json.loads(body)
        assert data["code"] in (401, 403) and data["message"]


def test_花括号配对():
    text = _cloud()
    # 去掉引号里的内容再数（JSON 里有花括号）
    bare = re.sub(r"'[^']*'", "''", text)
    assert bare.count("{") == bare.count("}")


def test_问额度的子请求不受全站30m上限():
    """子请求和上传共用请求头（Content-Length 是整个文件），不放开的话 >30MB 的上传被判 413 → 500（2.25.1）。"""
    text = _cloud()
    for loc in ("location = /_cloud_gate {", "location = /_cloud_gate_other {"):
        block = text.split(loc, 1)[1].split("}", 1)[0]
        assert "client_max_body_size 0;" in block, loc
