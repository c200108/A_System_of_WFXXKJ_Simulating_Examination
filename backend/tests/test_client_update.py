"""学生端 exe 检查更新：清单和下载两个公开接口（自建更新源，预留，默认关着）。"""

import json

import pytest

from app.config import settings

EXE = b"MZ" + b"\0" * 1000


@pytest.fixture
def updates(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "client_update_dir", str(tmp_path))
    monkeypatch.setattr(settings, "client_updates_enabled", True)
    for ch in ("online", "lan"):
        (tmp_path / ch).mkdir()
    return tmp_path


def _put(root, channel, data):
    (root / channel / "update.json").write_text(json.dumps(data, ensure_ascii=False),
                                                encoding="utf-8")


def test_默认关着_清单和下载都是404(client, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "client_update_dir", str(tmp_path))
    (tmp_path / "online").mkdir()
    _put(tmp_path, "online", {"version": "4.12.0"})
    (tmp_path / "online" / "a.exe").write_bytes(EXE)
    assert settings.client_updates_enabled is False
    assert client.get("/api/client/update.json").status_code == 404
    assert client.get("/api/client/download/online/a.exe").status_code == 404


def test_清单不用登录_裸文件名改成下载地址(client, updates):
    _put(updates, "online", {
        "version": "4.12.0", "notes": "说明",
        "assets": {"win32-runtime": {"url": "exam-client-4.12.0-win32-runtime.exe",
                                     "size": 5, "sha256": "ab"},
                   "win64": "exam-client-4.12.0-win64.exe",
                   "win32": "http://cdn.example.cn/x.exe"}})
    res = client.get("/api/client/update.json")
    assert res.status_code == 200 and res.headers["cache-control"] == "no-cache"
    data = res.json()
    assert data["version"] == "4.12.0"
    assert data["assets"]["win32-runtime"] == {
        "url": "download/online/exam-client-4.12.0-win32-runtime.exe", "size": 5, "sha256": "ab"}
    assert data["assets"]["win64"]["url"] == "download/online/exam-client-4.12.0-win64.exe"
    assert data["assets"]["win32"]["url"] == "http://cdn.example.cn/x.exe"     # 完整地址原样


def test_两个渠道各是各的(client, updates):
    _put(updates, "online", {"version": "4.12.0"})
    _put(updates, "lan", {"version": "4.11.5"})
    assert client.get("/api/client/update.json?channel=lan").json()["version"] == "4.11.5"
    assert client.get("/api/client/update.json?channel=online").json()["version"] == "4.12.0"


def test_没发布过和没有的渠道是404(client, updates):
    assert client.get("/api/client/update.json?channel=lan").status_code == 404
    assert client.get("/api/client/update.json?channel=beta").status_code == 404


def test_换服务器_清单里只写moved_to也照样返回(client, updates):
    _put(updates, "online", {"moved_to": "https://update.example.cn/api/client/update.json"})
    assert client.get("/api/client/update.json").json() == {
        "moved_to": "https://update.example.cn/api/client/update.json"}


def test_清单坏了给500说清楚(client, updates):
    (updates / "lan" / "update.json").write_text("{坏的", encoding="utf-8")
    res = client.get("/api/client/update.json?channel=lan")
    assert res.status_code == 500 and "读不出来" in res.json()["detail"]


def test_下载exe(client, updates):
    (updates / "lan" / "exam-client-4.12.0-win32-runtime.exe").write_bytes(EXE)
    res = client.get("/api/client/download/lan/exam-client-4.12.0-win32-runtime.exe")
    assert res.status_code == 200 and res.content == EXE
    assert res.headers["content-type"] == "application/octet-stream"
    assert res.headers["content-length"] == str(len(EXE))


@pytest.mark.parametrize("path", [
    "/api/client/download/lan/没有这个.exe",
    "/api/client/download/lan/update.json",              # 只给 exe
    "/api/client/download/lan/..%2F..%2Fapp.db",
    "/api/client/download/lan/%2E%2E%5Cx.exe",
    "/api/client/download/beta/a.exe",
])
def test_下载只认渠道目录里的exe(client, updates, path):
    (updates / "lan" / "update.json").write_text("{}", encoding="utf-8")
    res = client.get(path)
    # 机房版后端还托管着网页：解码后跑出 /api/client/download 的路径会落到网页的兜底（index.html），
    # 那也行 —— 要紧的是**没有文件被下载出去**
    assert res.status_code == 404 or "octet-stream" not in res.headers.get("content-type", "")
