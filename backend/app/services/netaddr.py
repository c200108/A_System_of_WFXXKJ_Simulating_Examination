"""这台服务器自己的 IPv4 地址：给「学生打开 http://…/dazi」这类链接找一个学生访问得到的地址。

老师在服务器本机用 localhost / 127.0.0.1 打开后台时，浏览器地址学生是访问不到的。
没配 PUBLIC_BASE_URL 的话，就用这里查到的地址：**公网 IP 优先，其次局域网 IPv4**，
排除回环、169.254（没拿到 DHCP 时的自动地址）、0.0.0.0、组播，以及 198.18.0.0/15 ——
代理软件（Clash 之类）的 TUN 虚拟网卡就用这一段，学生连不上它。

只查本机网卡，不去外网问「我的公网 IP 是多少」：机房里多半没外网，问了也是白等。
网卡上直接配着公网 IP 的服务器自然排在最前；在 NAT 后面的服务器查不到公网 IP，
那就得在 .env 里配 PUBLIC_BASE_URL。

在 Docker 容器里查到的是容器自己的地址（172.x），学生访问不到，所以容器里返回空，
前端提示去配 PUBLIC_BASE_URL。
"""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Iterable, List


_TUN = ipaddress.ip_network("198.18.0.0/15")


def _usable(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return (a.version == 4 and not a.is_loopback and not a.is_link_local
            and not a.is_unspecified and not a.is_multicast and a not in _TUN)


def rank(ips: Iterable[str], primary: str = "") -> List[str]:
    """排顺序：公网 → 默认路由那块网卡（多半就是插网线的那块）→ 其余局域网地址。

    局域网地址里，**末位是 .1 的往后放**：VMware、VirtualBox 这类虚拟网卡给宿主机的地址
    几乎都是 x.x.x.1（192.168.56.1、192.168.233.1），真正的学生机、服务器很少是 .1。
    同一档再按 192.168 → 10 → 172.16/12 排。
    """
    seen, out = set(), []
    for ip in ips:
        if ip not in seen and _usable(ip):
            seen.add(ip)
            out.append(ip)

    def key(ip: str):
        a = ipaddress.ip_address(ip)
        if a.is_global:
            return (0, 0)
        if ip == primary:
            return (1, 0)
        dot1 = 1 if ip.endswith(".1") else 0
        for i, net in enumerate(("192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12")):
            if a in ipaddress.ip_network(net):
                return (2 + dot1, i)
        return (4, 0)

    return sorted(out, key=key)


def _primary() -> str:
    """默认路由走的那块网卡的地址。UDP 的 connect 只选路由、不发包，没网也不会卡。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return ""
    finally:
        s.close()


def in_container() -> bool:
    return os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER") == "1"


def server_addresses() -> List[str]:
    """本机可给学生用的 IPv4，按 rank 排好；容器里返回空。"""
    if in_container():
        return []
    found = []
    primary = _primary()
    if primary:
        found.append(primary)
    try:
        found += [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    return rank(found, primary)
