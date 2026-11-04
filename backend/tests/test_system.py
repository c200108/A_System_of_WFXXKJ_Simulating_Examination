"""系统管理员的「数据备份」「一键更新」（2.18.0，routers/system.py + scripts/host-agent.sh）。

后端这一半：只有部署时建的系统管理员能用；导出的 zip 就是完整的 exam-data；
导入、更新先体检（不是 exam-data / 不是项目压缩包 / 路径不安全 / 试算不过 → 当场拒，
什么都不留），过了才给宿主机的主机助手留单子；一次只许一件。

主机助手这一半：在一个假项目目录里真跑 host-agent.sh，看它是不是照
「cd 到 zip 所在目录 → unzip -p 取出 u.sh → bash u.sh <zip>」三步走，
而且 zip 叫什么名字都认。
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from app.config import settings
from app.routers import system

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture()
def jobs(tmp_path, monkeypatch):
    root = tmp_path / "host-jobs"
    root.mkdir()
    monkeypatch.setattr(settings, "host_jobs_dir", str(root))
    return root


def _agent_on(root: Path) -> None:
    (root / "agent.json").write_text('{"version": "2.18.0"}', encoding="utf-8")


def _export(client, auth) -> bytes:
    res = client.get("/api/system/backup/export", headers=auth)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"
    assert "exam-data-" in res.headers["content-disposition"]
    return res.content


def _zip(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _project_zip(top="A_System_of_WFXXKJ_Simulating_Examination-main", script="echo hi\n") -> bytes:
    return _zip({f"{top}/scripts/update-from-zip.sh": script, f"{top}/docker-compose.yml": "x",
                 f"{top}/backend/Dockerfile": "x", f"{top}/README.md": "x"})


# ================================================================ 谁能用
def test_only_root_admin(client, auth, jobs):
    assert client.get("/api/system/status", headers=auth).status_code == 200
    me = client.get("/api/auth/me", headers=auth).json()
    assert me["is_root"] is True

    # 另一个管理员也不行：动整台服务器的事只给部署时建的那一个
    client.post("/api/auth/users", headers=auth, json={
        "username": "admin2", "password": "admin2pw", "name": "副管理员", "role": "admin"})
    tok = client.post("/api/auth/login", data={"username": "admin2", "password": "admin2pw"}).json()
    other = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.get("/api/auth/me", headers=other).json()["is_root"] is False
    for method, url in (("get", "/api/system/status"), ("get", "/api/system/backup/export"),
                        ("post", "/api/system/update/github")):
        assert getattr(client, method)(url, headers=other).status_code == 403
    assert client.get("/api/system/status").status_code == 401


# ================================================================ 导出
def test_export_is_a_full_exam_data_zip(client, auth, jobs):
    with zipfile.ZipFile(io.BytesIO(_export(client, auth))) as zf:
        names = zf.namelist()
        assert system.find_exam_data(names) == "exam-data/"
        for f in ("meta.json", "config.yaml", "settings.env", "MANIFEST.txt", "uploads.tar.gz"):
            assert f"exam-data/{f}" in names, f
        assert "exam-data/tables/questions.jsonl" in names
        assert "PASSWORD" not in zf.read("exam-data/settings.env").decode("utf-8")
        meta = json.loads(zf.read("exam-data/meta.json"))
        assert meta["表"]["users"]["行数"] >= 1


# ================================================================ 导入
def test_import_needs_agent(client, auth, jobs):
    res = client.post("/api/system/backup/import", headers=auth,
                      files={"file": ("exam-data.zip", _export(client, auth))},
                      data={"password": "admin123"})
    assert res.status_code == 409 and "host-agent-install.sh" in res.json()["detail"]


def test_import_checks_password_then_queues(client, auth, jobs):
    _agent_on(jobs)
    data = _export(client, auth)
    bad = client.post("/api/system/backup/import", headers=auth,
                      files={"file": ("exam-data.zip", data)}, data={"password": "wrong"})
    assert bad.status_code == 400 and "密码" in bad.json()["detail"]

    res = client.post("/api/system/backup/import", headers=auth,
                      files={"file": ("exam-data-20261104.zip", data)}, data={"password": "admin123"})
    assert res.status_code == 200, res.text
    job = res.json()
    assert job["action"] == "import" and job["status"] == "queued"
    assert "试算" in job["dry_run"]
    d = jobs / "jobs" / job["id"]
    assert (d / "exam-data" / "meta.json").is_file()
    assert len(list((d / "exam-data" / "tables").glob("*.jsonl"))) >= 5
    assert (jobs / "queue" / job["id"]).read_text() == "import"

    # 一次只许一件
    again = client.post("/api/system/update/github", headers=auth, data={"password": "admin123"})
    assert again.status_code == 409 and "还没做完" in again.json()["detail"]

    # 主机助手接单、做完
    (jobs / "queue" / job["id"]).unlink()
    (d / "status.json").write_text('{"status": "ok", "message": "完成"}', encoding="utf-8")
    (d / "log.txt").write_text("\x1b[32m✓ 还原完成\x1b[0m\n", encoding="utf-8")
    got = client.get(f"/api/system/jobs/{job['id']}", headers=auth).json()
    assert got["status"] == "ok" and got["log"] == "✓ 还原完成\n"
    assert client.get("/api/system/status", headers=auth).json()["busy"] is None


@pytest.mark.parametrize("files, why", [
    ({"a.txt": "x"}, "exam-data"),
    ({"exam-data/meta.json": "{}", "exam-data/tables/a.jsonl": ""}, "exam-data"),
    ({"../../etc/evil": "x"}, "不安全"),
])
def test_import_rejects_wrong_zip_and_leaves_nothing(client, auth, jobs, files, why):
    _agent_on(jobs)
    res = client.post("/api/system/backup/import", headers=auth,
                      files={"file": ("x.zip", _zip(files))}, data={"password": "admin123"})
    assert res.status_code == 400 and why in res.json()["detail"]
    assert not any((jobs / "jobs").iterdir())
    assert not (jobs / "queue").exists() or not any((jobs / "queue").iterdir())


def test_import_not_a_zip(client, auth, jobs):
    _agent_on(jobs)
    res = client.post("/api/system/backup/import", headers=auth,
                      files={"file": ("x.zip", b"not a zip")}, data={"password": "admin123"})
    assert res.status_code == 400 and "zip" in res.json()["detail"]


def test_find_exam_data_layouts():
    tables = [f"tables/t{i}.jsonl" for i in range(5)]
    assert system.find_exam_data(["meta.json", *tables]) == ""
    assert system.find_exam_data([f"exam-data-回滚点-1/{n}" for n in ["meta.json", *tables]]) == "exam-data-回滚点-1/"
    assert system.find_exam_data([f"a/b/{n}" for n in ["meta.json", *tables]]) is None   # 套了两层不认
    assert system.find_exam_data(["meta.json", *tables[:4]]) is None


# ================================================================ 一键更新
def test_update_github_queues(client, auth, jobs):
    _agent_on(jobs)
    res = client.post("/api/system/update/github", headers=auth, data={"password": "admin123"})
    assert res.status_code == 200, res.text
    job = json.loads((jobs / "jobs" / res.json()["id"] / "job.json").read_text(encoding="utf-8"))
    assert job["action"] == "update-github" and job["url"].endswith("/main.zip")


def test_update_upload_keeps_file_name(client, auth, jobs):
    _agent_on(jobs)
    res = client.post("/api/system/update/upload", headers=auth,
                      files={"file": ("我的 项目-main (1).zip", _project_zip("Proj-main"))},
                      data={"password": "admin123"})
    assert res.status_code == 200, res.text
    job = res.json()
    assert job["action"] == "update-zip" and job["file"] == "我的_项目-main_(1).zip"
    assert (jobs / "jobs" / job["id"] / job["file"]).is_file()


def test_update_upload_rejects_other_zip(client, auth, jobs):
    _agent_on(jobs)
    res = client.post("/api/system/update/upload", headers=auth,
                      files={"file": ("x.zip", _zip({"x/readme.md": "x"}))}, data={"password": "admin123"})
    assert res.status_code == 400 and "update-from-zip.sh" in res.json()["detail"]
    assert not any((jobs / "jobs").iterdir())


# ================================================================ 主机助手（真跑脚本）
needs_root_bash = pytest.mark.skipif(
    os.name == "nt" or not hasattr(os, "geteuid") or os.geteuid() != 0
    or not all(shutil.which(x) for x in ("bash", "flock", "unzip")),
    reason="主机助手要在 Linux 上用 root 跑，要有 flock、unzip")


def _fake_project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    (proj / "scripts").mkdir(parents=True)
    shutil.copy(REPO / "scripts" / "host-agent.sh", proj / "scripts" / "host-agent.sh")
    return proj


def _queue(proj: Path, action: str, files: dict) -> Path:
    jobs = proj / "data" / "host-jobs"
    d = jobs / "jobs" / "20261104-1"
    d.mkdir(parents=True)
    (d / "job.json").write_text(json.dumps({"action": action}), encoding="utf-8")
    for name, data in files.items():
        (d / name).write_bytes(data)
    (jobs / "queue").mkdir(parents=True, exist_ok=True)
    (jobs / "queue" / "20261104-1").write_text(action)
    return d


# 假的升级脚本：把它收到的参数、当前目录、EXAM_DIR 记下来
SPY = 'echo "args=$*"; echo "pwd=$(pwd)"; echo "exam_dir=$EXAM_DIR"; echo "升级完成"\n'


@needs_root_bash
@pytest.mark.parametrize("zip_name", ["A_System_of_WFXXKJ_Simulating_Examination-main.zip",
                                      "随便改的名字.zip"])
def test_agent_runs_the_three_steps_with_any_zip_name(tmp_path, zip_name):
    proj = _fake_project(tmp_path)
    d = _queue(proj, "update-zip", {zip_name: _project_zip(script=SPY)})
    subprocess.run(["bash", str(proj / "scripts" / "host-agent.sh")], check=True, timeout=60)

    log = (d / "log.txt").read_text(encoding="utf-8")
    assert f"args={zip_name}" in log            # bash u.sh <下载/上传的那个名字>
    assert f"pwd={d}" in log                    # 在 zip 所在目录里跑
    assert f"exam_dir={proj}" in log
    assert json.loads((d / "status.json").read_text())["status"] == "ok"
    assert not (proj / "data" / "host-jobs" / "queue" / "20261104-1").exists()
    assert not list(d.glob("*.zip")) and not (d / "u.sh").exists()   # 用完清掉


@needs_root_bash
def test_agent_marks_failure(tmp_path):
    proj = _fake_project(tmp_path)
    d = _queue(proj, "update-zip", {"x.zip": _project_zip(script='echo "[失败] 构建不过"; exit 1\n')})
    subprocess.run(["bash", str(proj / "scripts" / "host-agent.sh")], check=True, timeout=60)
    assert json.loads((d / "status.json").read_text())["status"] == "failed"
    assert "[失败] 构建不过" in (d / "log.txt").read_text(encoding="utf-8")


@needs_root_bash
def test_agent_ignores_unknown_action_and_bad_ids(tmp_path):
    proj = _fake_project(tmp_path)
    d = _queue(proj, "rm-rf", {})
    queue = proj / "data" / "host-jobs" / "queue"
    (queue / "..%2f..%2fetc").write_text("import")
    subprocess.run(["bash", str(proj / "scripts" / "host-agent.sh")], check=True, timeout=60)
    assert json.loads((d / "status.json").read_text())["status"] == "failed"
    assert "不认识的动作" in (d / "log.txt").read_text(encoding="utf-8")
    assert not any(queue.iterdir())


@needs_root_bash
def test_agent_downloads_then_runs(tmp_path):
    """update-github：先下载到任务目录（按服务器给的名字存），再走同样三步。"""
    import functools
    import http.server
    import threading

    if not shutil.which("curl"):
        pytest.skip("没有 curl")
    site = tmp_path / "site"
    site.mkdir()
    (site / "main.zip").write_bytes(_project_zip(script=SPY))
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        proj = _fake_project(tmp_path)
        d = _queue(proj, "update-github", {})
        env = {**os.environ, "UPDATE_ZIP_URL": f"http://127.0.0.1:{srv.server_port}/main.zip",
               "HOME": str(tmp_path)}
        subprocess.run(["bash", str(proj / "scripts" / "host-agent.sh")], check=True, timeout=60, env=env)
    finally:
        srv.shutdown()
    log = (d / "log.txt").read_text(encoding="utf-8")
    assert "已下载：main.zip" in log and "args=main.zip" in log, log
    assert json.loads((d / "status.json").read_text())["status"] == "ok"
