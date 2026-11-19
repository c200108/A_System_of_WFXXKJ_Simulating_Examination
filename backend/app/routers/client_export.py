"""从本网站导出学生端 exe，自动带上本网站地址（2.23.2）。只有系统管理员能用。

单独一个文件（不放进 system.py）：机房版没有主机助手那一套，但同样要能导出带本机地址的 exe。
导出的两种方式和 exe 从哪来，见 services/client_exe.py。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

try:
    from ..deps import require_root
except ImportError:            # 机房版没有「部署时建的那个系统管理员」这一层，管理员就能导
    from ..deps import require_admin as require_root
from ..models import User

router = APIRouter(prefix="/api/system", tags=["系统维护"])
@router.get("/clients", summary="能导出的学生端 exe 清单（本地「发布」文件夹或 GitHub 最新版）")
def client_catalog(_: User = Depends(require_root)):
    from ..services import client_exe
    return client_exe.catalog()


@router.get("/clients/{name}", summary="导出一个学生端 exe，带上本网站地址")
def client_download(
    name: str,
    addr: str,
    how: str = "slot",
    _: User = Depends(require_root),
):
    """how=name：改文件名（`…@地址.exe`），老版 exe 也认；how=slot：地址写进 exe 里，文件名不变（4.15.0 起）。

    addr 由网页带上来（浏览器地址栏里的那个，`location.origin`）—— 老师用什么地址打开的网站，
    学生就连什么地址；服务器自己猜不准（前面有 nginx、端口映射、域名）。"""
    from urllib.parse import quote

    from ..services import client_exe
    if how not in ("name", "slot"):
        raise HTTPException(status_code=400, detail="how 只能是 name（改文件名）或 slot（写进 exe）")
    addr = addr.strip().rstrip("/")
    if not client_exe.valid_addr(addr):
        raise HTTPException(status_code=400, detail=f"地址「{addr}」不对：只能是域名或 IP，可带端口")
    try:
        data = client_exe.fetch(name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"没有 {name} 这个 exe，刷新一下清单再选")
    except Exception as exc:                                # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"从 GitHub 下载 {name} 失败（{exc.__class__.__name__}），稍后再试")
    if how == "name":
        out_name = client_exe.renamed(name, addr)
    else:
        try:
            data = client_exe.write_slot(data, addr)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        out_name = name
    return Response(content=data, media_type="application/octet-stream", headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(out_name)}",
        "X-File-Name": quote(out_name),
    })
