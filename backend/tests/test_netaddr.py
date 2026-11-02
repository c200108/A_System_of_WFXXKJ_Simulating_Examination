"""学生链接用的服务器地址：老师在服务器本机用 localhost 打开后台时，换成学生访问得到的地址。"""

from app.services import netaddr


def test_排序_公网优先_默认路由其次_虚拟网卡往后():
    got = netaddr.rank(
        ["127.0.0.1", "169.254.3.4", "198.18.0.1", "192.168.56.1", "10.1.2.3",
         "172.20.9.233", "8.8.4.4", "192.168.1.20", "0.0.0.0", "224.0.0.1", "192.168.1.20"],
        primary="172.20.9.233")
    # 回环、169.254、代理 TUN（198.18/15）、0.0.0.0、组播都排除，重复的只留一个
    assert got == ["8.8.4.4", "172.20.9.233", "192.168.1.20", "10.1.2.3", "192.168.56.1"]


def test_默认路由是代理TUN时_真实网卡不吃亏():
    """Clash 之类开着 TUN 时，默认路由查出来的是 198.18.0.1：排除它，剩下的按局域网规则排。"""
    got = netaddr.rank(["198.18.0.1", "192.168.233.1", "192.168.228.1", "172.20.9.233"],
                       primary="198.18.0.1")
    assert got == ["172.20.9.233", "192.168.233.1", "192.168.228.1"]


def test_容器里不报地址(monkeypatch):
    monkeypatch.setenv("RUNNING_IN_DOCKER", "1")
    assert netaddr.server_addresses() == []


def test_接口要登录_返回地址列表(client, auth, monkeypatch):
    assert client.get("/api/config/addresses").status_code == 401
    monkeypatch.setattr("app.routers.config.server_addresses", lambda: ["192.168.1.20"])
    got = client.get("/api/config/addresses", headers=auth).json()
    assert got["ips"] == ["192.168.1.20"] and "public_base_url" in got and "in_container" in got
    # 公开的 /api/config 里不带内网地址
    assert "ips" not in client.get("/api/config").json()
