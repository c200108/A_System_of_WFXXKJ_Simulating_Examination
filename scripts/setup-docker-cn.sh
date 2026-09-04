#!/usr/bin/env bash
# 国内服务器上准备 Docker 环境（Ubuntu 22.04 / Debian 系）。
#
#   sudo bash scripts/setup-docker-cn.sh
#
# 做三件事：
#   1. 用阿里云 apt 源装 Docker（官方 get.docker.com 在国内经常连不上）
#   2. 逐个探测国内镜像加速站，把**实际可用的**写进 /etc/docker/daemon.json
#   3. 拉一个小镜像验证确实能用
#
# 国内的公共加速站关停、限流很频繁，所以这里不写死某一个，而是当场测。
# 全都不通时会告诉你怎么申请阿里云专属加速器（最稳，但要账号）。

set -uo pipefail

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YEL='\033[33m'; C_RED='\033[31m'; C_OFF='\033[0m'
step() { printf "\n${C_CYAN}%s${C_OFF}\n" "$1"; }
ok()   { printf "      ${C_GREEN}%s${C_OFF}\n" "$1"; }
warn() { printf "      ${C_YEL}%s${C_OFF}\n" "$1"; }
die()  { printf "\n${C_RED}[失败] %s${C_OFF}\n\n" "$1"; exit 1; }

[ "$(id -u)" = "0" ] || die "需要 root 权限，请用：sudo bash $0"

echo "=================================================="
echo "   Docker 国内环境准备（Ubuntu / Debian）"
echo "=================================================="

# ---------------------------------------------------------------- 1 装 Docker
step "[1/4] 检查 Docker..."

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    ok "已安装  $(docker --version | sed 's/Docker version //')"
else
    warn "未安装（或缺 compose 插件），用阿里云源安装"

    . /etc/os-release
    CODENAME="${VERSION_CODENAME:-jammy}"
    DISTRO_ID="${ID:-ubuntu}"

    apt-get update -qq || die "apt update 失败，先确认系统的 apt 源可用"
    apt-get install -y -qq ca-certificates curl gnupg >/dev/null || die "基础包安装失败"

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://mirrors.aliyun.com/docker-ce/linux/${DISTRO_ID}/gpg" \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes \
        || die "下载 Docker GPG 密钥失败，检查服务器能否访问 mirrors.aliyun.com"
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.aliyun.com/docker-ce/linux/${DISTRO_ID} ${CODENAME} stable" \
        > /etc/apt/sources.list.d/docker.list

    apt-get update -qq || die "添加 Docker 源后 apt update 失败"
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
        docker-buildx-plugin docker-compose-plugin >/dev/null \
        || die "Docker 安装失败"

    systemctl enable --now docker >/dev/null 2>&1
    ok "已安装  $(docker --version | sed 's/Docker version //')"
fi

# ---------------------------------------------------------------- 2 探测加速站
step "[2/4] 探测可用的镜像加速站..."
echo "      逐个真实拉取小镜像验证，只写入确实能拉下来的（每个最多 90 秒）。"

# docker.1ms.run 排第一：2026-09 实测可用，作为默认首选。
# 后面几个是备选，前面的不通时自动往下试。
CANDIDATES=(
    "https://docker.1ms.run"
    "https://docker.m.daocloud.io"
    "https://docker.1panel.live"
    "https://hub.rat.dev"
    "https://docker.nju.edu.cn"
    "https://mirror.ccs.tencentyun.com"   # 腾讯云机器内网专用，非腾讯云会失败
)

# 允许用环境变量追加自己的专属加速器：
#   DOCKER_MIRROR=https://xxxx.mirror.aliyuncs.com sudo -E bash scripts/setup-docker-cn.sh
if [ -n "${DOCKER_MIRROR:-}" ]; then
    CANDIDATES=("$DOCKER_MIRROR" "${CANDIDATES[@]}")
    echo "      已把你指定的 $DOCKER_MIRROR 排在最前面"
fi

# 只测 /v2/ 端点是不够的：有的站能返回元数据，实际镜像层却重定向到
# CloudFront 之类的国外 CDN，照样拉不下来。所以这里直接拿显式前缀真拉一次
# hello-world（几十 KB），端到端验证。
WORKING=()
for m in "${CANDIDATES[@]}"; do
    host="${m#https://}"; host="${host#http://}"; host="${host%/}"
    printf "      测试 %-28s " "$host"

    if timeout 90 docker pull "${host}/library/hello-world" >/dev/null 2>&1; then
        echo -e "${C_GREEN}可用${C_OFF}"
        WORKING+=("$m")
        docker rmi "${host}/library/hello-world" >/dev/null 2>&1 || true
    else
        echo "拉取失败"
    fi
done

if [ ${#WORKING[@]} -eq 0 ]; then
    die "所有加速站都不通。

      最稳的办法是申请阿里云专属加速器（免费，需要阿里云账号）：
        1. 登录 https://cr.console.aliyun.com
        2. 左侧「镜像工具 → 镜像加速器」，复制你的专属地址
        3. 重新运行：
           DOCKER_MIRROR=https://你的ID.mirror.aliyuncs.com sudo -E bash $0

      如果这台机器就在阿里云/腾讯云上，用厂商的内网加速地址更快。

      注意：有的站能返回镜像元数据、看着像通的，但镜像层会重定向到
      CloudFront 等国外 CDN，实际拉不下来。所以这里用真实拉取来判断，
      而不是只 ping 一下接口。"
fi

# ---------------------------------------------------------------- 3 写配置
step "[3/4] 写入 /etc/docker/daemon.json..."

mkdir -p /etc/docker
[ -f /etc/docker/daemon.json ] && {
    cp /etc/docker/daemon.json "/etc/docker/daemon.json.bak.$(date +%s)"
    warn "原配置已备份为 /etc/docker/daemon.json.bak.*"
}

{
    printf '{\n  "registry-mirrors": [\n'
    for i in "${!WORKING[@]}"; do
        printf '    "%s"%s\n' "${WORKING[$i]}" "$([ $i -lt $((${#WORKING[@]}-1)) ] && echo ,)"
    done
    printf '  ],\n'
    printf '  "log-driver": "json-file",\n'
    printf '  "log-opts": { "max-size": "10m", "max-file": "3" }\n'
    printf '}\n'
} > /etc/docker/daemon.json

ok "已写入 ${#WORKING[@]} 个加速地址"
systemctl daemon-reload
systemctl restart docker || die "Docker 重启失败，检查 /etc/docker/daemon.json 语法"
sleep 3
ok "Docker 已重启"

# ---------------------------------------------------------------- 4 验证
step "[4/4] 拉取测试镜像验证..."
if timeout 120 docker pull hello-world >/dev/null 2>&1; then
    ok "拉取成功，加速可用"
    docker rmi hello-world >/dev/null 2>&1 || true
else
    die "仍然拉不动镜像。

      逐项排查：
        1. 服务器能上外网吗：curl -I https://mirrors.aliyun.com
        2. 看当前生效的加速地址：docker info | grep -A5 'Registry Mirrors'
        3. 换成阿里云专属加速器（见上一步的说明）"
fi

echo
echo "=================================================="
echo "  Docker 环境就绪"
echo
docker info 2>/dev/null | grep -A"${#WORKING[@]}" "Registry Mirrors" | sed 's/^/  /'
echo
echo "  接下来在项目目录里执行："
echo "    ./deploy.sh"
echo "=================================================="
