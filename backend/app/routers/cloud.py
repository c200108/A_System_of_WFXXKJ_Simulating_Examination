"""个人云盘（2.25.0）的接口：老师看自己的空间、免登录打开、改云盘密码；管理员设总容量、给老师分空间。

怎么搭的、配额怎么管，见 services/cloud.py 开头。
"""

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, is_root, require_admin
from ..models import CloudAccount, User
from ..security import verify_password
from ..services import cloud

router = APIRouter(prefix="/api/cloud", tags=["个人云盘"])

MB = cloud.MB


def _fail(e: Exception, code: int = 400):
    raise HTTPException(status_code=code, detail=str(e)) from e


def _acc_out(acc: CloudAccount | None) -> dict:
    if acc is None:
        return {"allocated": False, "quota_bytes": 0, "used_bytes": 0, "over_quota": False,
                "login": "", "password_custom": False, "checked_at": None}
    return {
        "allocated": acc.quota_mb > 0,
        "quota_bytes": acc.quota_mb * MB,
        "used_bytes": acc.used_bytes,
        "over_quota": acc.over_quota,
        "login": acc.login,
        "password_custom": acc.password_custom,
        "checked_at": acc.checked_at,
    }


# ---------------------------------------------------------------- 老师自己
@router.get("/me", summary="我的个人云盘：分没分到、多大、用了多少")
def my_cloud(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"enabled": cloud.enabled(), **_acc_out(db.get(CloudAccount, user.id))}


@router.post("/open", summary="打开个人云盘（免登录：换一个 OpenList 令牌）")
def open_cloud(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not cloud.enabled():
        raise HTTPException(status_code=503, detail="这台服务器没有启用个人云盘，请联系系统管理员")
    try:
        token = cloud.open_token(db, user)
    except PermissionError as e:
        _fail(e, 403)
    except cloud.CloudError as e:
        _fail(e, 503)
    # 前端把令牌存进 localStorage 的 wfxxcloud:token，再打开 /cloud/（键名的前缀见 cloud.HEAD_SCRIPT）
    return {"token": token, "storage_key": cloud.TOKEN_KEY_PREFIX + "token", "url": "/cloud/"}


class CloudPasswordIn(BaseModel):
    password: str = Field(max_length=64)


@router.post("/password", summary="单独设一个云盘密码（直接打开 /cloud 登录时用）")
def set_cloud_password(body: CloudPasswordIn, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    from .auth import check_password

    acc = db.get(CloudAccount, user.id)
    if acc is None or acc.quota_mb <= 0:
        raise HTTPException(status_code=403, detail="你还没有分配个人云盘空间")
    pwd = check_password(body.password)
    try:
        acc.password_custom = True
        cloud.sync(db, user, acc, password=pwd)
        db.commit()
    except cloud.CloudError as e:
        db.rollback()
        _fail(e, 503)
    return _acc_out(acc)


class CloudSyncIn(BaseModel):
    current_password: str = Field(max_length=64)


@router.post("/password/sync", summary="云盘密码改回和教师端一致")
def sync_cloud_password(body: CloudSyncIn, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    acc = db.get(CloudAccount, user.id)
    if acc is None or acc.quota_mb <= 0:
        raise HTTPException(status_code=403, detail="你还没有分配个人云盘空间")
    # 要明文才设得过去，所以请老师再输一次教学平台的登录密码
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="教学平台的登录密码不对")
    try:
        acc.password_custom = False
        cloud.sync(db, user, acc, password=body.current_password)
        db.commit()
    except cloud.CloudError as e:
        db.rollback()
        _fail(e, 503)
    return _acc_out(acc)


# ---------------------------------------------------------------- OpenList 登录页
class OlLoginIn(BaseModel):
    username: str = Field(default="", max_length=64)
    password: str = Field(default="", max_length=128)
    otp_code: str = Field(default="", max_length=16)
    plain: bool = False


@router.post("/ol-login", include_in_schema=False)
def openlist_login(body: OlLoginIn, request: Request, db: Session = Depends(get_db)):
    """OpenList 登录页的登录（页面头上的脚本改送过来的），回 OpenList 自己格式的 JSON。"""
    if not cloud.enabled():
        return {"code": 500, "message": "这台服务器没有启用个人云盘", "data": None}
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "")
    try:
        return cloud.login_page(db, body.model_dump(), body.plain, ip)
    except cloud.CloudError as e:
        return {"code": 500, "message": str(e), "data": None}


# ---------------------------------------------------------------- 全校共享（2.25.6）
@router.get("/shared", summary="全校老师共享出来的云盘资源（标出共享者）")
def shared(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not cloud.enabled():
        return {"enabled": False, "items": []}
    acc = db.get(CloudAccount, user.id)
    try:
        return {"enabled": True, "items": cloud.shared_items(db, acc.login if acc else "")}
    except cloud.CloudError as e:
        _fail(e, 503)


@router.get("/shared/ol", include_in_schema=False)
def shared_for_cloud_page(authorization: str = Header(default=""), db: Session = Depends(get_db)):
    """云盘页面里「全校共享」面板用：带的是 OpenList 的令牌，问 OpenList 确认是谁。"""
    if not cloud.enabled():
        raise HTTPException(status_code=503, detail="没有启用个人云盘")
    try:
        login = cloud.whoami(authorization)
        if not login:
            raise HTTPException(status_code=401, detail="云盘登录已失效，刷新页面重新登录")
        return {"items": cloud.shared_items(db, login)}
    except cloud.CloudError as e:
        _fail(e, 503)


# ---------------------------------------------------------------- 管理员
def _service_state(db: Session) -> tuple[bool, str]:
    if not cloud.enabled():
        return False, "没有启用（docker-compose.yml 里没有 openlist 服务）"
    try:
        cloud.ensure_setup(db)
        cloud.client().storages()      # 真问一次：做过初始化以后 ensure_setup 不再联网
        return True, ""
    except cloud.CloudError as e:
        return False, str(e)


@router.get("/admin", summary="云盘总览：磁盘、总容量、已分配、各老师用量（管理员）")
def admin_overview(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    ok, err = _service_state(db)
    accounts = list(db.scalars(select(CloudAccount)))
    out = {
        "enabled": cloud.enabled(),
        "service_ok": ok,
        "service_error": err,
        "root_dir_host": "/home/WFXXKJ_ExamSystem_CloudStorage",
        "disk": cloud.disk(),
        "total_bytes": cloud.total_mb(db) * MB,
        "allocated_bytes": sum(a.quota_mb for a in accounts) * MB,
        "used_bytes": sum(a.used_bytes for a in accounts if a.quota_mb > 0),
        "accounts": {a.user_id: _acc_out(a) for a in accounts},
    }
    # 出问题时要进 OpenList 后台看日志、查文件：只告诉部署时建的那个系统管理员
    if is_root(admin):
        out["openlist_admin"] = {"username": cloud.ADMIN_LOGIN, "password": cloud.admin_password()}
    return out


class TotalIn(BaseModel):
    total_gb: float = Field(ge=0, le=1024 * 1024)


@router.put("/admin/total", summary="设云盘总容量（管理员）")
def set_total(body: TotalIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    mb = int(round(body.total_gb * cloud.GB_MB))
    d = cloud.disk()
    if d and mb * MB > d["total"]:
        raise HTTPException(status_code=400, detail=(
            f"超过了磁盘的总大小（{d['total'] / MB / cloud.GB_MB:.1f} GB），"
            "云盘总容量不能比放它的那块盘还大"))
    allocated = cloud.allocated_mb(db)
    if mb < allocated:
        raise HTTPException(status_code=400, detail=(
            f"已经给老师们分出去 {cloud.fmt_mb(allocated)} 了，总容量不能比这还小，先收回一些再改"))
    cloud.set_total_mb(db, mb)
    db.commit()
    return {"total_bytes": mb * MB}


class QuotaIn(BaseModel):
    quota_gb: float = Field(ge=0, le=1024 * 1024)


@router.put("/admin/users/{user_id}", summary="给一位老师分配 / 调整 / 收回（0）空间（管理员）")
def set_user_quota(user_id: int, body: QuotaIn, _: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not cloud.enabled():
        raise HTTPException(status_code=503, detail="这台服务器没有启用个人云盘")
    mb = int(round(body.quota_gb * cloud.GB_MB))
    if body.quota_gb > 0 and mb == 0:
        mb = 1
    try:
        acc = cloud.set_quota(db, user, mb)
    except cloud.CloudError as e:
        db.rollback()
        _fail(e)
    return _acc_out(acc)


# ---------------------------------------------------------------- nginx 上传闸门
REASONS = ("nologin", "none", "over", "total", "nolength")


@router.api_route("/gate", methods=["GET", "POST", "PUT"], include_in_schema=False)
def upload_gate(
    authorization: str = Header(default=""),
    x_upload_length: str = Header(default=""),
    x_upload_kind: str = Header(default="put"),
    db: Session = Depends(get_db),
):
    """frontend/nginx/cloud.conf 里的 auth_request：204 放行，403 + X-Cloud-Reason 拒绝。"""
    try:
        length = int(x_upload_length) if x_upload_length.strip() else None
        if length is not None and length < 0:
            length = None
    except ValueError:
        length = None
    reason = cloud.gate(db, authorization, length, writes=(x_upload_kind != "other"))
    if reason:
        return Response(status_code=403, headers={"X-Cloud-Reason": reason})
    return Response(status_code=204)

