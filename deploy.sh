#!/usr/bin/env bash
# 一键部署（Linux / macOS）。Windows 请双击「一键部署.bat」。
#
#   chmod +x deploy.sh && ./deploy.sh
#
# 从检查 Docker 到验证业务链路全程自动。可重复执行：
# 已有 .env 不会被覆盖，重跑相当于「重新构建并重启」。

set -uo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YEL='\033[33m'; C_RED='\033[31m'; C_OFF='\033[0m'
step() { printf "\n${C_CYAN}%s${C_OFF}\n" "$1"; }
ok()   { printf "      ${C_GREEN}%s${C_OFF}\n" "$1"; }
warn() { printf "      ${C_YEL}%s${C_OFF}\n" "$1"; }
die()  { printf "\n${C_RED}[失败] %s${C_OFF}\n\n" "$1"; exit 1; }

echo "=================================================="
echo "      信息技术组卷台   一键部署"
echo "=================================================="

# ---------------------------------------------------------------- 1 Docker
step "[1/6] 检查 Docker..."
command -v docker >/dev/null 2>&1 || die "这台机器没装 Docker。
      安装：curl -fsSL https://get.docker.com | sh
      装完把当前用户加进 docker 组：sudo usermod -aG docker \$USER
      然后重新登录再跑本脚本。"

docker info >/dev/null 2>&1 || die "Docker 已安装但没运行（或当前用户没权限）。
      启动：sudo systemctl start docker
      权限：sudo usermod -aG docker \$USER  然后重新登录"

docker compose version >/dev/null 2>&1 || die "缺少 docker compose 插件（v2）。
      安装：sudo bash scripts/setup-docker-cn.sh  （国内服务器用这个）"
ok "Docker 就绪  $(docker --version | sed 's/Docker version //')"

# 国内服务器直连 Docker Hub 基本拉不动，先确认镜像源是通的，
# 免得等构建到一半才失败、白等好几分钟。
if docker info 2>/dev/null | grep -q "Registry Mirrors"; then
    ok "已配置镜像加速  $(docker info 2>/dev/null | grep -A1 'Registry Mirrors' | tail -1 | tr -d ' ')"
elif [ -n "${REGISTRY:-}" ]; then
    ok "使用指定的镜像仓库  $REGISTRY"
else
    warn "没有配置镜像加速，将直连 Docker Hub"
    warn "国内服务器多半拉不动。若下一步卡住或超时，先跑："
    warn "  sudo bash scripts/setup-docker-cn.sh"
fi

# ---------------------------------------------------------------- 2 配置
step "[2/6] 准备配置文件..."

gen() {  # gen <长度>：只用不易混淆的字符，抄写时不会把 0/O、1/l 搞错
    local n="$1"
    LC_ALL=C tr -dc 'a-km-zA-HJ-NP-Z2-9' < /dev/urandom | head -c "$n"
}

# .env.example 里的这些值公开在 GitHub 上，出现即等于没有密码
env_defaults_found() {
    local bad=""
    for k in JWT_SECRET ADMIN_PASSWORD MYSQL_ROOT_PASSWORD MYSQL_PASSWORD; do
        local v
        v="$(grep -E "^\s*${k}\s*=" .env | head -1 | cut -d= -f2- | tr -d ' \r')"
        case "$v" in
            change_this_*|please-change-*|change-me-in-production|admin123|exam_pwd|root_pwd|你的密码)
                bad="$bad $k" ;;
        esac
    done
    echo "$bad"
}

ADMIN_PW=""
NEED_GENERATE=1

if [ -f .env ]; then
    BAD="$(env_defaults_found)"
    if [ -z "$BAD" ]; then
        ok ".env 已存在且口令已自定义，沿用现有配置"
        NEED_GENERATE=0
    else
        warn "现有 .env 里这几项还是示例默认值：${BAD}"
        warn "这些值公开在 GitHub 上，用它们部署等于没有密码。"
        echo
        read -r -p "  重新生成一份随机口令？旧文件会备份为 .env.bak  [Y/n]: " ANS
        case "$ANS" in
            n|N) die "已取消。请手工改好 .env 里的这几项后再运行。" ;;
        esac
        mv .env .env.bak
        ok "旧配置已备份为 .env.bak"
    fi
fi

if [ "$NEED_GENERATE" = 1 ]; then
    echo
    echo "  这台机器对外的访问地址是什么？"
    echo "  · 有公网 IP 就填 IP，例如 203.0.113.10"
    echo "  · 有域名就填域名，例如 exam.school.edu.cn"
    echo "  · 回车则尝试自动探测公网 IP"
    DETECTED="$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || true)"
    read -r -p "  地址 [${DETECTED:-localhost}]: " HOST_ADDR
    HOST_ADDR="${HOST_ADDR:-${DETECTED:-localhost}}"
    while true; do
        read -r -p "  对外端口 [8080]: " PORT
        PORT="${PORT:-8080}"
        # 必须是纯数字且在合法范围。手滑多打一个字母，docker compose 要到
        # 构建阶段才会报 invalid hostPort，白等好几分钟，所以这里当场拦下。
        if [[ "$PORT" =~ ^[0-9]+$ ]] && [ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ]; then
            break
        fi
        warn "「$PORT」不是合法端口，请填 1-65535 的纯数字"
    done

    ADMIN_PW="$(gen 16)"
    cat > .env <<EOF
# 由 deploy.sh 生成于 $(date '+%F %T')
# 本文件含明文口令，不要提交进 Git，也不要发给别人。

MYSQL_ROOT_PASSWORD=$(gen 20)
MYSQL_DATABASE=exam
MYSQL_USER=exam
MYSQL_PASSWORD=$(gen 20)

# 换掉它会让所有已登录的人重新登录，属于正常现象
JWT_SECRET=$(gen 48)

ADMIN_USERNAME=admin
ADMIN_PASSWORD=${ADMIN_PW}

WEB_PORT=${PORT}
CORS_ORIGINS=http://${HOST_ADDR}:${PORT}
EOF
    chmod 600 .env
    ok "已生成 .env，所有口令都是随机的"
fi

# shellcheck disable=SC1091
set -a; . ./.env; set +a
WEB_PORT="${WEB_PORT:-8080}"

if ! [[ "$WEB_PORT" =~ ^[0-9]+$ ]] || [ "$WEB_PORT" -lt 1 ] || [ "$WEB_PORT" -gt 65535 ]; then
    die ".env 里的 WEB_PORT 是「${WEB_PORT}」，不是合法端口（要 1-65535 的纯数字）。

      编辑 .env，把 WEB_PORT 改对，并且**把 CORS_ORIGINS 结尾的端口一起改成同一个值**。
      例如两处都用 8080：

        nano .env

      改完重新运行本脚本。"
fi

# ---------------------------------------------------------------- 3 端口
step "[3/6] 检查端口 ${WEB_PORT}..."
if command -v ss >/dev/null 2>&1 && ss -ltn 2>/dev/null | grep -q ":${WEB_PORT} "; then
    warn "端口 ${WEB_PORT} 已被占用"
    warn "若不是本系统的容器，请改 .env 里的 WEB_PORT 换一个端口再重来"
else
    ok "端口空闲"
fi

# ---------------------------------------------------------------- 4 构建
step "[4/6] 构建并启动（首次要下载约 1GB，需要几分钟）..."
echo "      国内网络拉镜像容易中断，失败会自动重试。"

BUILT=0
BUILD_LOG="$(mktemp)"
trap 'rm -f "$BUILD_LOG"' EXIT

for i in 1 2 3; do
    echo
    echo "      第 $i 次尝试..."
    if docker compose up -d --build 2>&1 | tee "$BUILD_LOG" | sed 's/^/        /'; then
        BUILT=1; break
    fi

    # 有些失败重试一百次也没用，识别出来就别白等。
    # 最典型的是镜像加速站的域名已经不存在了（站点关停），DNS 直接解析失败。
    if grep -q "no such host" "$BUILD_LOG"; then
        DEAD="$(grep -o 'lookup [^ ]*' "$BUILD_LOG" | head -1 | cut -d' ' -f2)"
        die "镜像加速站 ${DEAD:-（见上面日志）} 的域名解析不了，这个站已经没了。

      国内公共加速站关停很频繁，换一个：

        sudo bash scripts/setup-docker-cn.sh

      它会逐个实测候选站，只写入真正能用的，并备份你现有的 daemon.json。

      要手动指定也行：

        sudo tee /etc/docker/daemon.json > /dev/null <<'"'"'EOF'"'"'
        { \"registry-mirrors\": [\"https://docker.1ms.run\"] }
        EOF
        sudo systemctl restart docker"
    fi

    if grep -qE "unauthorized|authentication required" "$BUILD_LOG"; then
        die "镜像仓库要求认证，多半是加速站限制了匿名拉取。换一个：
        sudo bash scripts/setup-docker-cn.sh"
    fi

    [ "$i" -lt 3 ] && { warn "这次没成功，10 秒后重试"; sleep 10; }
done
[ "$BUILT" = 1 ] || die "镜像构建失败，试了 3 次。

      国内服务器最常见的原因是拉不动 Docker Hub。跑这个脚本会自动
      装好 Docker 并逐个实测国内加速站，只写入真正能用的：

        sudo bash scripts/setup-docker-cn.sh

      如果加速站全都不通（现在关停很频繁），申请一个阿里云专属加速器
      （免费，需账号，在 https://cr.console.aliyun.com 的「镜像加速器」里），
      然后：

        DOCKER_MIRROR=https://你的ID.mirror.aliyuncs.com sudo -E bash scripts/setup-docker-cn.sh

      要是那个站只能当仓库前缀用、当不了透明加速器，就改用：

        REGISTRY=那个站的域名 ./deploy.sh"
ok "容器已启动"

# ---------------------------------------------------------------- 5 等待就绪
step "[5/6] 等待服务就绪（首次启动要建库、导题库，约 1 分钟）..."
READY=0
for i in $(seq 1 60); do
    sleep 3
    STATE="$(docker compose ps --format '{{.Service}}={{.Health}}' 2>/dev/null | tr '\n' ' ')"
    case "$STATE" in *backend=healthy*) READY=1; break;; esac
    [ $((i % 5)) -eq 0 ] && echo "      仍在启动... ($((i*3)) 秒)  $STATE"
done
if [ "$READY" != 1 ]; then
    echo
    echo "      后端一直没有就绪，最后 25 行日志："
    docker compose logs backend --tail=25 2>&1 | sed 's/^/        /'
    die "服务启动失败，请把上面的日志发给维护者。"
fi
ok "后端健康检查通过"

# ---------------------------------------------------------------- 6 验证
step "[6/6] 验证业务链路..."
BASE="http://localhost:${WEB_PORT}"

if curl -fs --max-time 15 "$BASE/api/health" >/dev/null 2>&1; then
    ok "接口健康"
else
    die "接口不通，检查：docker compose logs backend"
fi

TOKEN="$(curl -fs --max-time 20 -X POST "$BASE/api/auth/login" \
    -d "username=${ADMIN_USERNAME}&password=${ADMIN_PASSWORD}" 2>/dev/null \
    | sed -n 's/.*"access_token":"\([^"]*\)".*/\1/p')"
if [ -n "$TOKEN" ]; then
    ok "管理员登录成功"
    TOTAL="$(curl -fs --max-time 20 "$BASE/api/questions/stats" \
        -H "Authorization: Bearer $TOKEN" 2>/dev/null \
        | sed -n 's/.*"total":\([0-9]*\).*/\1/p')"
    ok "题库 ${TOTAL:-?} 题"
    [ "${TOTAL:-0}" = "0" ] && warn "题库是空的。要搬旧机器数据见 docs/部署指南.md 第四节"
else
    warn "登录验证没通过，但服务已经起来了，可以先手动打开页面看看。"
fi

# ---------------------------------------------------------------- 完成
PUBLIC_URL="$(echo "${CORS_ORIGINS:-$BASE}" | cut -d, -f1)"
echo
echo "=================================================="
echo "  部署完成"
echo
echo "  本机访问   ：$BASE"
[ "$PUBLIC_URL" != "$BASE" ] && echo "  对外访问   ：$PUBLIC_URL"
echo "  接口文档   ：$BASE/docs"
echo
echo "  管理员账号 ：${ADMIN_USERNAME}"
if [ -n "$ADMIN_PW" ]; then
    printf "  管理员密码 ：${C_YEL}%s${C_OFF}\n" "$ADMIN_PW"
    echo
    echo "  ↑ 请立刻记下来。密码也存在 .env 里，登录后请在系统里再改一次。"
else
    echo "  管理员密码 ：见 .env 里的 ADMIN_PASSWORD"
fi
echo "=================================================="
echo
echo "  还要做的两件事："
echo "    1. 要让外网访问，在云服务器安全组 / 防火墙放行 ${WEB_PORT} 端口"
echo "       Ubuntu: sudo ufw allow ${WEB_PORT}/tcp"
echo "    2. 把备份加进 crontab，部署当天就设好："
echo "       0 2 * * * ${ROOT}/backup/backup.sh >> /var/log/exam-backup.log 2>&1"
echo
echo "  常用命令（在项目目录下）："
echo "    docker compose ps                看状态"
echo "    docker compose logs -f backend   看日志"
echo "    docker compose down              停止（数据不丢）"
echo
echo "  完整说明见 docs/部署指南.md"
echo
