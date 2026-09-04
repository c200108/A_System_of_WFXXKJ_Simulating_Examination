#!/usr/bin/env bash
# 裸机引导：全新 Ubuntu 22.04 上，从什么都没有到系统跑起来。
#
# 新机器上直接跑（不需要先 clone 仓库）：
#
#   curl -fsSL https://raw.githubusercontent.com/c200108/A_System_of_WFXXKJ_Simulating_Examination/main/scripts/bootstrap.sh | sudo bash
#
# GitHub 拉不动的话，先手动把仓库弄到机器上，再执行：
#
#   sudo bash scripts/bootstrap.sh
#
# 依次做：装 git → 拿代码 → 装 Docker 并配国内镜像 → 一键部署。
# 每一步都可重复执行，中断了重跑即可。

set -uo pipefail

REPO="https://github.com/c200108/A_System_of_WFXXKJ_Simulating_Examination.git"
DIR_NAME="A_System_of_WFXXKJ_Simulating_Examination"
INSTALL_ROOT="${INSTALL_ROOT:-/opt}"

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YEL='\033[33m'; C_RED='\033[31m'; C_OFF='\033[0m'
step() { printf "\n${C_CYAN}%s${C_OFF}\n" "$1"; }
ok()   { printf "      ${C_GREEN}%s${C_OFF}\n" "$1"; }
warn() { printf "      ${C_YEL}%s${C_OFF}\n" "$1"; }
die()  { printf "\n${C_RED}[失败] %s${C_OFF}\n\n" "$1"; exit 1; }

[ "$(id -u)" = "0" ] || die "需要 root，请用 sudo 运行。"

echo "=================================================="
echo "   信息技术组卷台   裸机引导（Ubuntu / Debian）"
echo "=================================================="

# ---------------------------------------------------------------- 1 代码
step "[1/3] 获取项目代码..."

# 已经在项目目录里跑的话直接用当前目录
if [ -f "./docker-compose.yml" ] && [ -d "./backend" ]; then
    PROJECT_DIR="$(pwd)"
    ok "就在项目目录里，直接使用：$PROJECT_DIR"
elif [ -d "${INSTALL_ROOT}/${DIR_NAME}/.git" ]; then
    PROJECT_DIR="${INSTALL_ROOT}/${DIR_NAME}"
    ok "已存在，尝试更新：$PROJECT_DIR"
    git -C "$PROJECT_DIR" pull --ff-only 2>/dev/null || warn "更新失败（网络？），用现有代码继续"
else
    command -v git >/dev/null 2>&1 || {
        warn "没有 git，安装中"
        apt-get update -qq && apt-get install -y -qq git >/dev/null || die "git 安装失败，先确认 apt 源可用"
    }
    mkdir -p "$INSTALL_ROOT"
    step_ok=0
    for i in 1 2 3; do
        echo "      第 $i 次 clone..."
        if git clone --depth 1 "$REPO" "${INSTALL_ROOT}/${DIR_NAME}"; then step_ok=1; break; fi
        sleep 5
    done
    [ "$step_ok" = 1 ] || die "clone 失败三次。GitHub 在国内不稳，两个办法：
      · 挂代理后重试
      · 在能上网的机器上下载 ZIP，传到这台机器解压，然后进目录执行：
        sudo bash scripts/bootstrap.sh"
    PROJECT_DIR="${INSTALL_ROOT}/${DIR_NAME}"
    ok "代码已放到 $PROJECT_DIR"
fi

cd "$PROJECT_DIR" || die "进不去项目目录"

# ---------------------------------------------------------------- 2 Docker
step "[2/3] 准备 Docker 环境..."
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1 \
   && docker info 2>/dev/null | grep -q "Registry Mirrors"; then
    ok "Docker 与镜像加速都已就绪，跳过"
else
    bash scripts/setup-docker-cn.sh || die "Docker 环境准备失败，看上面的提示。"
fi

# ---------------------------------------------------------------- 3 部署
step "[3/3] 部署系统..."
chmod +x deploy.sh
# deploy.sh 会问访问地址和端口，这里保持交互
bash deploy.sh

echo
echo "项目目录：$PROJECT_DIR"
echo "以后升级：cd $PROJECT_DIR && git pull && docker compose up -d --build"
