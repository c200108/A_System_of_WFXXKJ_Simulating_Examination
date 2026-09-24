"""按「这台电脑」限频：打字交成绩、换练习文本（2.11.0）。

**认电脑不认人**：一个人换台机器照样能练，同一台机器换个号也躲不过去。
网页端把一个随机设备号存在浏览器里，exe 按本机网卡和机器名算一个，都放在
`X-Device-Id` 头里带上来；没带（旧版学生端）就退回认 IP。

线上服务器那种整个机房走一个出口 IP 的，全靠设备号才分得开 —— 所以 IP 只是兜底。
设备号是客户端给的，清掉浏览器数据就换了一个；校内工具，防的是手快乱点，不是防攻击。

计数落库（rate_hits）而不是放内存：后端开了好几个工作进程，内存里各算各的等于没限。
"""

import math
import re
from datetime import timedelta

from fastapi import HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .. import clock
from ..models import RateHit

_DEVICE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
KEEP = timedelta(hours=1)


def device_of(request: Request) -> str:
    dev = (request.headers.get("x-device-id") or "").strip()
    if _DEVICE.match(dev):
        return "d:" + dev
    # 服务器版前面是 nginx，它把真实地址放在 X-Real-IP 里；机房版直连，看 client
    ip = (request.headers.get("x-real-ip") or "").strip()
    if not ip and request.client:
        ip = request.client.host
    return "ip:" + (ip or "?")[:64]


def check(db: Session, action: str, who: str, limit: int, window_sec: int, tip: str) -> None:
    """窗口里已经做满 limit 次就回 429，detail 是 tip 后面接「N 秒后再试」。

    只查不记：动作真的做成了再 `hit`，没做成的（比如文本库是空的）不占次数。
    """
    if limit <= 0 or window_sec <= 0:
        return
    now = clock.now()
    recent = db.scalars(
        select(RateHit.at)
        .where(RateHit.action == action, RateHit.who == who,
               RateHit.at > now - timedelta(seconds=window_sec))
        .order_by(RateHit.at)
    ).all()
    if len(recent) < limit:
        return
    # 最早那一次滑出窗口，就又能做了
    wait = max(1, math.ceil((recent[-limit] + timedelta(seconds=window_sec) - now).total_seconds()))
    raise HTTPException(status_code=429, detail=f"{tip}，{wait} 秒后再试",
                        headers={"Retry-After": str(wait)})


def hit(db: Session, action: str, who: str) -> None:
    """记一次。顺手把这个动作一小时以前的旧记录清掉，表永远只有最近的一点点。不提交。"""
    now = clock.now()
    db.execute(delete(RateHit).where(RateHit.action == action, RateHit.at < now - KEEP))
    db.add(RateHit(action=action, who=who, at=now))
