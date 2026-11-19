"""从本网站导出学生端 exe，带上本网站地址（2.23.2）。"""

from pathlib import Path
from urllib.parse import unquote

import pytest

from app.config import settings
from app.services import client_exe

ROOT = Path(__file__).resolve().parents[2]


def _fake_exe(with_slot=True) -> bytes:
    """假 exe：前后各一截乱字节，中间夹着版本信息里那段占位（UTF-16）。"""
    mid = (client_exe.MARK + client_exe.FILL * client_exe.SIZE).encode("utf-16-le") if with_slot else b""
    return b"MZ" + bytes(range(256)) * 40 + mid + bytes(range(255, -1, -1)) * 40


@pytest.fixture
def exe_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "client_exe_dir", str(tmp_path))
    (tmp_path / "exam-client-4.15.0-win32-runtime.exe").write_bytes(_fake_exe())
    (tmp_path / "exam-client-4.14.2-win64.exe").write_bytes(_fake_exe(with_slot=False))
    return tmp_path


def test_地址槽读写_长度不变():
    data = _fake_exe()
    assert client_exe.read_slot(data) == ""
    out = client_exe.write_slot(data, "https://exam.school.cn:8443")
    assert len(out) == len(data)
    assert client_exe.read_slot(out) == "https://exam.school.cn:8443"
    # 再写一次（换地址）也行
    assert client_exe.read_slot(client_exe.write_slot(out, "192.168.1.8")) == "192.168.1.8"
    with pytest.raises(ValueError):
        client_exe.write_slot(_fake_exe(with_slot=False), "192.168.1.8")
    for bad in ("", "a b", "exam.cn/path", "javascript:alert(1)", "x" * 200, "1.2.3.4~"):
        with pytest.raises(ValueError):
            client_exe.write_slot(data, bad)


def test_和学生端那份规则一致():
    """服务端写、学生端读：标记、长度、填充、编码必须一样。"""
    import importlib.util

    f = ROOT / "desktop" / "client" / "slot.py"
    if not f.exists():
        pytest.skip("没有 desktop/")
    spec = importlib.util.spec_from_file_location("desk_slot", f)
    desk = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(desk)
    assert (desk.MARK, desk.FILL, desk.SIZE, desk.ENC) == \
        (client_exe.MARK, client_exe.FILL, client_exe.SIZE, client_exe.ENC)
    data = desk.MARK.encode(desk.ENC) + desk.placeholder()[len(desk.MARK):].encode(desk.ENC)
    assert desk.read(client_exe.write_slot(data, "http://10.0.0.5:3315")) == "http://10.0.0.5:3315"


def test_改文件名的写法():
    assert client_exe.renamed("exam-client-4.15.0-win32.exe", "http://10.0.0.5:3315") == \
        "exam-client-4.15.0-win32@10.0.0.5_3315.exe"
    assert client_exe.renamed("考试客户端-64位@111.1.1.1_80.exe", "https://exam.school.cn") == \
        "考试客户端-64位@exam.school.cn.exe", "原来名字里的地址换掉"


def test_清单和两种导出(client, auth, exe_dir):
    got = client.get("/api/system/clients", headers=auth).json()
    assert got["source"] == "local" and len(got["items"]) == 2
    assert any("Win7" in i["label"] for i in got["items"])

    name = "exam-client-4.15.0-win32-runtime.exe"
    res = client.get(f"/api/system/clients/{name}", headers=auth,
                     params={"how": "name", "addr": "https://exam.school.cn:8443"})
    assert res.status_code == 200
    assert unquote(res.headers["x-file-name"]) == "exam-client-4.15.0-win32-runtime@exam.school.cn_8443.exe"
    assert res.content == (exe_dir / name).read_bytes(), "改名的方式 exe 内容一个字节不动"

    res = client.get(f"/api/system/clients/{name}", headers=auth,
                     params={"how": "slot", "addr": "https://exam.school.cn:8443"})
    assert res.status_code == 200 and unquote(res.headers["x-file-name"]) == name
    assert client_exe.read_slot(res.content) == "https://exam.school.cn:8443"
    assert (exe_dir / name).read_bytes() == _fake_exe(), "原文件不能被改"

    old = "exam-client-4.14.2-win64.exe"
    res = client.get(f"/api/system/clients/{old}", headers=auth, params={"how": "slot", "addr": "10.0.0.5"})
    assert res.status_code == 409 and "改文件名" in res.json()["detail"]
    assert client.get(f"/api/system/clients/{old}", headers=auth,
                      params={"how": "name", "addr": "10.0.0.5"}).status_code == 200

    assert client.get(f"/api/system/clients/{name}", headers=auth,
                      params={"addr": "exam.cn/../x"}).status_code == 400
    assert client.get("/api/system/clients/nope.exe", headers=auth,
                      params={"addr": "10.0.0.5"}).status_code == 404


def test_只有系统管理员能导(client, teacher_auth, exe_dir):
    assert client.get("/api/system/clients", headers=teacher_auth).status_code == 403
    assert client.get("/api/system/clients/exam-client-4.15.0-win32-runtime.exe",
                      headers=teacher_auth, params={"addr": "10.0.0.5"}).status_code == 403
