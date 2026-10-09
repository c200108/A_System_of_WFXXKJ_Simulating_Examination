"""教师端安卓 APP 用的两个接口（5.0.0）。

APP 是原生安卓应用（界面全部在手机上画，不打开网页），功能和教师端网页一一对应，
业务数据走的就是网页版用的那一套 /api 接口，同一个教师令牌。APP 额外需要的只有两件：

1. **认服务器**（/api/app/info，公开）。老师在登录页手填地址，填错了（少个端口、
   填成了学生端地址、填成了别的网站）要能当场说清楚，而不是登录时报一句"请求失败"。
   顺带把校名、平台名发过去，登录成功前就能在 APP 上显示学校自己的名字。

2. **保持登录**（/api/app/session，要教师令牌）。网页版令牌 12 小时过期，
   老师早上登一次、下午再打开 APP 就被踢回登录页，体验很差。APP 在前台时
   每隔几分钟调一次这个接口，它做三件事：
   - 证明网络和服务器都通（APP 据此显示/收起"连接已断开"的提示）；
   - 令牌用掉四分之一寿命就换一张新的，所以只要 APP 隔三差五打开过，就永远不会过期；
   - 返回最新的账号信息（管理员改了角色，APP 里的菜单跟着变）。

**为什么不用 WebSocket 长连接**：这套系统没有需要服务器主动推给老师的东西，
长连接只会让手机一直醒着、耗电，服务器还要多维持一堆连接，nginx 也得另配。
APP 只在前台时发心跳，退到后台就一个请求都不发，零耗电；回到前台立刻补一次。
一次心跳就一两百字节，五分钟一次，一天开一小时也就十几 KB。
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import ChangelogEntry, User
from ..security import create_access_token, decode_token
from ..siteconfig import site
from .auth import _user_out
from .community import version_key

router = APIRouter(prefix="/api/app", tags=["教师端 APP"])

# APP 和服务器之间的协议版本。APP 发现服务器的协议比自己新、自己看不懂时，
# 提示老师去更新 APP；反过来服务器旧了，提示管理员升级服务器。
# 只有接口语义变了才加一，加字段不算。
PROTOCOL = 1

# 心跳间隔（秒），APP 按服务器给的来，以后想调不用重新发 APP
HEARTBEAT_SECONDS = 300

_bearer = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def _server_version(db: Session) -> str:
    rows = db.execute(
        select(ChangelogEntry.version, ChangelogEntry.released_on).distinct()
    ).all()
    if not rows:
        return ""
    return max(rows, key=lambda r: (r[1], version_key(r[0])))[0]


@router.get("/info", summary="APP 认服务器用（公开）")
def app_info(db: Session = Depends(get_db)):
    """`app` 字段固定为 wfxxkj-exam：APP 靠它认出"这确实是本系统的服务器"。"""
    return {
        "app": "wfxxkj-exam",
        "protocol": PROTOCOL,
        "server_version": _server_version(db),
        "school": site.school.name,
        "title": site.site.title,
        "brand": site.site.brand,
        "favicon": site.site.favicon,
        "heartbeat_seconds": HEARTBEAT_SECONDS,
    }


@router.post("/session", summary="APP 心跳：保持登录、必要时换新令牌")
def app_session(
    token: str = Depends(_bearer),
    user: User = Depends(get_current_user),
):
    """令牌已用掉四分之一寿命就发一张新的，否则 `token` 为 null，APP 继续用旧的。

    不是每次都换：同一时间网页和 APP 拿着的令牌最好一致，频繁换只会徒增状态；
    四分之一是个宽松的点，12 小时的令牌每 3 小时换一次，离过期永远还远。
    """
    now = datetime.now(timezone.utc)
    lifetime = settings.jwt_expire_minutes * 60
    # get_current_user 已经验过令牌，这里再解一次只为读签发时间
    payload = decode_token(token)
    issued = int(payload.get("iat") or 0)
    age = now.timestamp() - issued
    fresh = None
    if age >= lifetime / 4:
        fresh = create_access_token(user.id, user.role)
    return {
        "ok": True,
        "server_time": now.isoformat(),
        "token": fresh,
        "expires_in": lifetime if fresh else max(0, int(lifetime - age)),
        "heartbeat_seconds": HEARTBEAT_SECONDS,
        "user": _user_out(user),
    }
