"""系统管理员账号设置里的「数据备份」和「一键更新」（2.18.0）。

只有部署时建的那个系统管理员（.env 的 ADMIN_USERNAME）能用，见 deps.require_root。

## 导出：后端自己就能做

和 scripts/data-export.sh 产出的是**同一个 exam-data 文件夹**（tables/*.jsonl、meta.json、
uploads.tar.gz、config.yaml、settings.env、MANIFEST.txt），只是打成一个 zip 直接下载：

    exam-data-20261104-153000.zip
    └── exam-data/
        ├── tables/…  meta.json  uploads.tar.gz  config.yaml  settings.env  MANIFEST.txt

解压出来的 exam-data 文件夹拿去 `sudo bash scripts/data-import.sh exam-data` 也能导，
和以前命令行导出的没有区别；机房版的「数据搬家」也认。

## 导入、一键更新：要交给宿主机

导入要重建容器，更新要跑 update-from-zip.sh（rsync 代码、docker compose build/up）——
这些都得在**宿主机**上做，容器里的后端够不着 Docker，也不该够得着（把 docker.sock
挂进来等于把整台服务器的 root 交给了网页）。所以：

1. 后端只负责收文件、**先体检**（压缩包是不是完整的 exam-data / 项目 main 压缩包，
   导入还要先试算一遍，有问题当场报，什么都不动），然后在任务目录里留一张单子；
2. 宿主机上的「主机助手」（scripts/host-agent.sh，scripts/host-agent-install.sh 装成
   systemd 服务，盯着 data/host-jobs/queue/）接单，跑固定的几种动作，日志写回任务目录；
3. 网页隔几秒来问一次进度。升级、重建容器的时候后端会重启，问不通是正常的，接着问。

主机助手只认 `import` / `update-github` / `update-zip` 三种动作，单子里的东西只当数据，
不会被当成命令执行。

## 任务目录

    data/host-jobs/
        agent.json              主机助手装好时写的（没有它 = 没装，网页上给出安装命令）
        queue/<任务号>           排队的单子（主机助手接了就删）
        jobs/<任务号>/
            job.json            动作、谁提交的、什么时候
            exam-data/          导入：解好的备份
            <原文件名>.zip       更新：上传的或下载的压缩包，文件名原样保留
            status.json         主机助手写：running / ok / failed
            log.txt             主机助手写：脚本的完整输出
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from .. import clock
from ..config import settings
from ..deps import require_root
from ..models import User
from ..security import verify_password

router = APIRouter(prefix="/api/system", tags=["系统维护"])

BACKEND_DIR = Path(__file__).resolve().parents[2]          # backend/（容器里是 /app）
REPO_ZIP_URL = "https://github.com/c200108/A_System_of_WFXXKJ_Simulating_Examination/archive/refs/heads/main.zip"
ACTIONS = ("import", "update-github", "update-zip")
ACTION_LABEL = {"import": "导入备份数据", "update-github": "从 GitHub 一键更新",
                "update-zip": "上传压缩包更新"}
# 排队超过这么久主机助手还没接，就当它没在跑，不再挡着新任务
QUEUE_STALE_SEC = 10 * 60
CHUNK = 1024 * 1024


# ---------------------------------------------------------------- 工具
def _jobs_root() -> Path:
    return Path(settings.host_jobs_dir).resolve()


def _agent() -> dict:
    """主机助手装没装：装好时它会写 agent.json。"""
    f = _jobs_root() / "agent.json"
    if not f.is_file():
        return {"installed": False}
    try:
        info = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = {}
    return {"installed": True, **{k: info.get(k) for k in ("version", "installed_at", "project_dir")}}


def _check_password(user: User, password: str) -> None:
    if not password or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=400, detail="登录密码不对。这一步会动整台服务器，要再输一次密码确认")


def _read_json(f: Path) -> dict:
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _job_view(job_dir: Path, log_tail: int = 0) -> dict:
    job = _read_json(job_dir / "job.json")
    st = _read_json(job_dir / "status.json")
    queued = (_jobs_root() / "queue" / job_dir.name).exists()
    status = st.get("status") or ("queued" if queued else "lost")
    out = {
        "id": job_dir.name,
        "action": job.get("action", ""),
        "label": ACTION_LABEL.get(job.get("action", ""), job.get("action", "")),
        "file": job.get("file", ""),
        "created_at": job.get("created_at", ""),
        "by": job.get("by", ""),
        "status": status,                    # queued / running / ok / failed / lost
        "started_at": st.get("started_at", ""),
        "finished_at": st.get("finished_at", ""),
        "message": st.get("message", ""),
    }
    if log_tail:
        log = job_dir / "log.txt"
        try:
            with open(log, "rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - log_tail))
                text = f.read().decode("utf-8", "replace")
        except OSError:
            text = ""
        # 脚本给终端上的色，网页上不要
        out["log"] = re.sub(r"\x1b\[[0-9;]*m", "", text)
    return out


def _busy() -> dict | None:
    """有没有正在排队 / 正在跑的任务。一次只许一个：两个升级同时跑会把代码目录搅乱。"""
    jobs = _jobs_root() / "jobs"
    if not jobs.is_dir():
        return None
    now = time.time()
    for d in sorted(jobs.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        v = _job_view(d)
        if v["status"] == "running":
            return v
        if v["status"] == "queued":
            try:
                age = now - (d / "job.json").stat().st_mtime
            except OSError:
                age = 0
            if age < QUEUE_STALE_SEC:
                return v
    return None


def _new_job_dir() -> Path:
    if not _agent()["installed"]:
        raise HTTPException(status_code=409, detail=(
            "服务器上还没装「主机助手」，网页上做不了导入和更新。"
            "在服务器项目目录里运行一次：sudo bash scripts/host-agent-install.sh"))
    busy = _busy()
    if busy:
        raise HTTPException(status_code=409, detail=f"「{busy['label']}」还没做完，等它结束再来")
    job_id = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    d = _jobs_root() / "jobs" / job_id
    d.mkdir(parents=True)
    return d


def _submit(job_dir: Path, action: str, user: User, **extra) -> dict:
    assert action in ACTIONS
    job = {"action": action, "by": user.username,
           "created_at": clock.now().isoformat(sep=" ", timespec="seconds"), **extra}
    (job_dir / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    queue = _jobs_root() / "queue"
    queue.mkdir(parents=True, exist_ok=True)
    # 最后才放单子：主机助手看到单子时，文件一定都齐了
    (queue / job_dir.name).write_text(action, encoding="utf-8")
    return _job_view(job_dir)


def _save_upload(up: UploadFile, dest: Path) -> int:
    size = 0
    with open(dest, "wb") as f:
        while True:
            chunk = up.file.read(CHUNK)
            if not chunk:
                break
            f.write(chunk)
            size += len(chunk)
    return size


def _safe_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    """压缩包里不许有绝对路径、..、符号链接 —— 解压出圈就能覆盖服务器上任意文件。"""
    out = []
    for info in zf.infolist():
        p = PurePosixPath(info.filename.replace("\\", "/"))
        if p.is_absolute() or ".." in p.parts or re.match(r"^[A-Za-z]:", info.filename):
            raise HTTPException(status_code=400, detail=f"压缩包里有不安全的路径：{info.filename}")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise HTTPException(status_code=400, detail=f"压缩包里有符号链接：{info.filename}")
        out.append(info)
    return out


ZIP_NAME_RE = re.compile(r"[^\w.\-()一-鿿]+")


def _clean_zip_name(name: str) -> str:
    """上传的文件名原样留着（主机助手按它找文件），只去掉路径和怪字符。"""
    base = os.path.basename((name or "").replace("\\", "/")).strip()
    base = ZIP_NAME_RE.sub("_", base).strip("._") or "upload.zip"
    if not base.lower().endswith(".zip"):
        base += ".zip"
    return base[:120]


# ---------------------------------------------------------------- exam-data 包
def find_exam_data(names: list[str]) -> str | None:
    """在压缩包的文件列表里找 exam-data 的根（meta.json 和 tables/ 所在的那一层）。

    只认两种摆法：根上就是 meta.json + tables/，或者外面套**一层**文件夹（exam-data/、
    exam-data-回滚点-xxx/ 都行）。再深的不认 —— 那多半是把别的东西打包进来了。
    返回根前缀（"" 或 "exam-data/"），不是 exam-data 包返回 None。
    """
    norm = [n.replace("\\", "/") for n in names]
    for prefix in sorted({n.split("/")[0] + "/" for n in norm if "/" in n} | {""}, key=len):
        if prefix + "meta.json" not in norm:
            continue
        tables = [n for n in norm if n.startswith(prefix + "tables/") and n.endswith(".jsonl")]
        if len(tables) >= 5:
            return prefix
    return None


def check_project_zip(names: list[str]) -> str | None:
    """是不是在线版项目的 main 压缩包：外面一层文件夹，里面有升级脚本、compose、后端。

    返回那层文件夹名（GitHub 下的是 A_System_of_WFXXKJ_Simulating_Examination-main），不是返回 None。
    """
    norm = {n.replace("\\", "/") for n in names}
    tops = {n.split("/")[0] for n in norm if "/" in n}
    for top in tops:
        need = (f"{top}/scripts/update-from-zip.sh", f"{top}/docker-compose.yml",
                f"{top}/backend/Dockerfile")
        if all(x in norm for x in need):
            return top
    return None


def _settings_env() -> str:
    """和 data-export.sh 一样只导非机密的部署设置。容器里看不到 .env，按环境变量能拿到的写。"""
    lines = [f"# 网页导出于 {clock.now():%F %T}", "# 只有部署设置，**没有任何口令**。还原时可选择性套用。"]
    for key in ("REGISTRY", "WEB_PORT", "CORS_ORIGINS", "PUBLIC_BASE_URL", "HTTPS_PORT", "SSL_CERT_DIR"):
        if os.environ.get(key):
            lines.append(f"{key}={os.environ[key]}")
    return "\n".join(lines) + "\n"


def _config_path() -> Path | None:
    from ..siteconfig import _candidate_paths

    return next((Path(p) for p in _candidate_paths() if os.path.isfile(p)), None)


def _run_tool(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    """在后端目录里跑 tools 下的脚本（和 data-export.sh / data-import.sh 调的是同一份）。"""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, "-m", *args], cwd=str(BACKEND_DIR), env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)


# ---------------------------------------------------------------- 接口
@router.get("/status", summary="主机助手装没装、有没有任务在跑")
def status(_: User = Depends(require_root)):
    jobs = _jobs_root() / "jobs"
    recent = []
    if jobs.is_dir():
        recent = [_job_view(d) for d in sorted(jobs.iterdir(), reverse=True)[:8] if d.is_dir()]
    return {"agent": _agent(), "busy": _busy(), "recent": recent, "repo_zip_url": REPO_ZIP_URL}


@router.get("/jobs/{job_id}", summary="一个任务的进度和日志")
def job(job_id: str, _: User = Depends(require_root)):
    if not re.fullmatch(r"[\w-]{1,64}", job_id):
        raise HTTPException(status_code=404, detail="没有这个任务")
    d = _jobs_root() / "jobs" / job_id
    if not (d / "job.json").is_file():
        raise HTTPException(status_code=404, detail="没有这个任务")
    return _job_view(d, log_tail=60_000)


@router.get("/backup/export", summary="导出完整数据（exam-data 压缩包）")
def export_backup(bg: BackgroundTasks, _: User = Depends(require_root)):
    work = Path(tempfile.mkdtemp(prefix="exam-export-"))
    bg.add_task(shutil.rmtree, work, True)
    data = work / "exam-data"
    got = _run_tool("tools.export_data", str(data))
    if got.returncode != 0:
        raise HTTPException(status_code=500, detail="导出失败：" + (got.stderr or got.stdout)[-800:])
    meta = _read_json(data / "meta.json")
    tables = list((data / "tables").glob("*.jsonl"))
    # 宁可失败也不要给出一个看着成功的空备份（同 data-export.sh）
    if not meta or len(tables) < 5:
        raise HTTPException(status_code=500, detail=f"只导出了 {len(tables)} 张表，备份无效")

    cfg = _config_path()
    if cfg:
        shutil.copyfile(cfg, data / "config.yaml")
    (data / "settings.env").write_text(_settings_env(), encoding="utf-8")
    rows = "\n".join(f"{name}={info.get('行数', 0)}" for name, info in sorted(meta.get("表", {}).items()))
    (data / "MANIFEST.txt").write_text(
        "信息科技教学平台 —— 数据导出清单（网页导出）\n"
        f"导出时间 : {clock.now():%F %T}\n来源主机 : {os.environ.get('HOSTNAME', '')}\n\n"
        f"--- 各表行数（还原后拿这个核对）---\n{rows}\n", encoding="utf-8")

    name = f"exam-data-{clock.now():%Y%m%d-%H%M%S}.zip"
    out = work / name
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for f in sorted(data.rglob("*")):
            if f.is_file():
                # uploads.tar.gz 已经压过了，再压一遍白费 CPU
                kind = zipfile.ZIP_STORED if f.suffix == ".gz" else zipfile.ZIP_DEFLATED
                zf.write(f, f.relative_to(work).as_posix(), compress_type=kind)
    return FileResponse(out, media_type="application/zip", filename=name)


@router.post("/backup/import", summary="上传 exam-data 压缩包，导入并重建容器")
def import_backup(
    file: UploadFile = File(...),
    password: str = Form(""),
    user: User = Depends(require_root),
):
    _check_password(user, password)
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="要上传的是 .zip 压缩包（导出得到的 exam-data-….zip）")
    job_dir = _new_job_dir()
    try:
        tmp = job_dir / "upload.zip"
        _save_upload(file, tmp)
        try:
            zf = zipfile.ZipFile(tmp)
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="不是有效的 zip 文件，可能没传完整")
        with zf:
            members = _safe_members(zf)
            prefix = find_exam_data([m.filename for m in members])
            if prefix is None:
                raise HTTPException(status_code=400, detail=(
                    "这不是完整的 exam-data 数据包：里面要有 meta.json 和 tables 文件夹（至少 5 张表）。"
                    "请上传本页「导出数据」得到的压缩包，或把 data-export.sh 导出的 exam-data 文件夹整个压成 zip"))
            dest = job_dir / "exam-data"
            for m in members:
                rel = m.filename.replace("\\", "/")
                if not rel.startswith(prefix) or m.is_dir():
                    continue
                target = dest / rel[len(prefix):]
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(m) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out, CHUNK)
        tmp.unlink()

        # 先试算（不写库）：列不对、MySQL 装不下的数据，当场报出来，服务器什么都不动
        got = _run_tool("tools.import_data", str(dest))
        report = (got.stdout + ("\n" + got.stderr if got.stderr else "")).strip()
        (job_dir / "dry-run.txt").write_text(report, encoding="utf-8")
        if got.returncode != 0:
            raise HTTPException(status_code=400, detail="试算没通过，本机数据一个字都没动：\n" + report[-1500:])
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    meta = _read_json(job_dir / "exam-data" / "meta.json")
    view = _submit(job_dir, "import", user, file=file.filename or "",
                   exported_at=meta.get("导出时间", ""))
    view["dry_run"] = report[-4000:]
    return view


@router.post("/update/github", summary="一键更新：从 GitHub 下载 main 压缩包升级")
def update_github(password: str = Form(""), user: User = Depends(require_root)):
    _check_password(user, password)
    job_dir = _new_job_dir()
    # 下载交给主机助手：宿主机上可能配了 GitHub 加速（setup-github-cn.sh），容器里没有
    return _submit(job_dir, "update-github", user, url=REPO_ZIP_URL)


@router.post("/update/upload", summary="一键更新：上传项目 main 压缩包升级")
def update_upload(
    file: UploadFile = File(...),
    password: str = Form(""),
    user: User = Depends(require_root),
):
    _check_password(user, password)
    name = _clean_zip_name(file.filename or "")
    job_dir = _new_job_dir()
    try:
        dest = job_dir / name
        _save_upload(file, dest)
        try:
            with zipfile.ZipFile(dest) as zf:
                top = check_project_zip([m.filename for m in _safe_members(zf)])
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="不是有效的 zip 文件，可能没传完整")
        if not top:
            raise HTTPException(status_code=400, detail=(
                "这不像在线版项目的压缩包：里面要有 scripts/update-from-zip.sh、docker-compose.yml、"
                "backend/Dockerfile。请上传 GitHub 仓库页 Code → Download ZIP 下来的那个（不用解压）"))
    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise
    return _submit(job_dir, "update-zip", user, file=name, top=top)
