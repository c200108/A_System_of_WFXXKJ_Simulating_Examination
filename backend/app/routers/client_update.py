"""学生端 exe 的「检查更新」：更新清单 + 下载。公开、只读，学生端没登录也能查。

**预留，默认关着**（CLIENT_UPDATES_ENABLED=true 才开）：现在学生端默认只查联网版公开仓库的
GitHub Releases，下载也走 GitHub，不占学校服务器的带宽。以后要换成自己的服务器
（比如推广到别的学校、GitHub 连不上），打开这个开关、打包时 --update-url 指过来就行。

## 文件放在哪

服务器上一个目录（`CLIENT_UPDATE_DIR`，默认 `./data/client-updates`，docker 里挂到宿主机），
按渠道分子目录：

    client-updates/
      online/            联网版 exe（烤了本服务器地址的那几个）
        update.json
        exam-client-4.12.0-win32-runtime.exe …
      lan/               机房版 exe（不烤地址）
        update.json
        exam-client-4.12.0-win32-runtime.exe …

update.json 和 exe 都由 `desktop/tools/生成更新包.py` 生成，scp 上来就行，**不用重启后端**：
每次请求都现读文件。

## 两个接口

    GET /api/client/update.json?channel=online|lan     清单（不给 channel 当 online）
    GET /api/client/download/{channel}/{文件名}         下载 exe（流式，不整个读进内存）

清单里 assets 的 url 写的是**裸文件名**（生成工具就这么写），这里返回前改成
`download/<渠道>/<文件名>` —— 学生端按清单地址解析相对路径，正好落在下载接口上。
写了完整地址（http://… 或以 / 开头）的原样返回，方便把 exe 放到别的机器上。

## 换服务器

清单里可以只写一个 `moved_to`（新清单地址），学生端读到就转去新地址查。
流程见 desktop/README.md「换服务器」。
"""

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from ..config import settings

router = APIRouter(prefix="/api/client", tags=["学生端更新"])

CHANNELS = ("online", "lan")
MANIFEST = "update.json"
# 只认生成工具起的那种名字：字母数字点横线下划线，.exe 结尾。挡掉 ../ 之类
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.exe$")


def _dir(channel: str) -> Path:
    if not settings.client_updates_enabled:
        # 预留的接口，默认关着：和没有这个接口一样回 404
        raise HTTPException(404, "Not Found")
    if channel not in CHANNELS:
        raise HTTPException(404, f"没有这个更新渠道：{channel}（只有 {' / '.join(CHANNELS)}）")
    return Path(settings.client_update_dir) / channel


def _rewrite(data: dict, channel: str) -> dict:
    """assets 里的裸文件名 → download/<渠道>/<文件名>（相对清单地址）。"""
    assets = data.get("assets")
    if not isinstance(assets, dict):
        return data
    out = {}
    for key, val in assets.items():
        item = {"url": val} if isinstance(val, str) else dict(val or {})
        url = str(item.get("url") or "")
        if url and "://" not in url and not url.startswith("/") and "/" not in url:
            item["url"] = f"download/{channel}/{url}"
        out[key] = item
    return {**data, "assets": out}


@router.get("/update.json", summary="学生端更新清单（公开）")
def manifest(channel: str = Query("online", description="online = 联网版，lan = 机房版")):
    path = _dir(channel) / MANIFEST
    if not path.is_file():
        raise HTTPException(404, "这个渠道还没有发布任何版本")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"更新清单读不出来：{exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(500, "更新清单格式不对（应该是一个 JSON 对象）")
    # 发新版时清单会被覆盖，别让浏览器、代理缓存住旧的
    return JSONResponse(_rewrite(data, channel), headers={"Cache-Control": "no-cache"})


@router.get("/download/{channel}/{name}", summary="下载学生端 exe（公开）")
def download(channel: str, name: str):
    if not SAFE_NAME.match(name):
        raise HTTPException(404, "没有这个文件")
    path = _dir(channel) / name
    if not path.is_file():
        raise HTTPException(404, "没有这个文件")
    return FileResponse(path, media_type="application/octet-stream", filename=name)
