#!/usr/bin/env bash
# 部署初始化：生成 .env 并填入随机密钥，然后自检。
#
#   chmod +x deploy-init.sh && ./deploy-init.sh
#
# 密钥在本机随机生成，不来自任何模板，也不会进 Git（.env 已被 .gitignore 排除）。
# 已存在 .env 时不会覆盖，避免把正在用的口令冲掉。

set -euo pipefail
cd "$(dirname "$0")"

echo "=================================================="
echo "   信息技术组卷台   部署初始化"
echo "=================================================="
echo

# 找一个真的能跑的 Python。Windows 商店的 python3 是个占位程序，
# 存在但一跑就失败；纯 Docker 部署的服务器则可能根本没装 Python。
# 自检是锦上添花，找不到就跳过，绝不能挡住部署。
PY=""
for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c "import sys" >/dev/null 2>&1; then
        PY="$c"
        break
    fi
done

run_check() {
    if [ -n "$PY" ]; then
        "$PY" backend/tools/check_deploy.py || true
    else
        echo "[提示] 这台机器上没有可用的 Python，跳过配置自检。"
        echo "       不影响 Docker 部署；想手动确认可在有 Python 的机器上跑："
        echo "       python backend/tools/check_deploy.py"
    fi
}

if [ -f .env ]; then
    echo "[跳过] .env 已经存在，不覆盖。"
    echo "       想重新生成就先备份再删除：mv .env .env.bak"
    echo
    echo "直接进入自检："
    echo
    run_check
    exit 0
fi

# ---------- 随机串生成：按可用工具挑一个 ----------
gen() {  # gen <长度>
    local n="$1"
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 $((n * 2)) | tr -dc 'A-Za-z0-9' | head -c "$n"
    elif [ -n "$PY" ]; then
        "$PY" -c "import secrets; print(secrets.token_urlsafe($n*2)[:$n])"
    else
        tr -dc 'A-Za-z0-9' < /dev/urandom | head -c "$n"
    fi
}

JWT="$(gen 48)"
DB_ROOT="$(gen 20)"
DB_PASS="$(gen 20)"
ADMIN_PW="$(gen 16)"

# ---------- 访问地址 ----------
echo "这台机器对外的访问地址是什么？"
echo "（直接回车用自动探测到的公网 IP；也可以填域名，如 exam.school.edu.cn）"
DETECTED="$(curl -s --max-time 5 https://api.ipify.org 2>/dev/null || echo '')"
read -r -p "地址 [${DETECTED:-手动输入}]: " HOST
HOST="${HOST:-$DETECTED}"
read -r -p "对外端口 [8080]: " PORT
PORT="${PORT:-8080}"

if [ -z "$HOST" ]; then
    echo "[提示] 没填地址，CORS_ORIGINS 先留 localhost，之后可在 .env 里改。"
    ORIGIN="http://localhost:${PORT}"
else
    ORIGIN="http://${HOST}:${PORT}"
fi

# ---------- 写 .env ----------
cat > .env <<EOF
# 由 deploy-init.sh 生成于 $(date '+%F %T')
# 这个文件含明文口令，不要提交进 Git，也不要发给别人。

MYSQL_ROOT_PASSWORD=${DB_ROOT}
MYSQL_DATABASE=exam
MYSQL_USER=exam
MYSQL_PASSWORD=${DB_PASS}

# 换掉它会让所有已登录的人重新登录，属于正常现象
JWT_SECRET=${JWT}

# 首次启动自动创建的管理员账号
ADMIN_USERNAME=admin
ADMIN_PASSWORD=${ADMIN_PW}

WEB_PORT=${PORT}
CORS_ORIGINS=${ORIGIN}
EOF

chmod 600 .env 2>/dev/null || true

echo
echo "=================================================="
echo "  .env 已生成，口令全部是随机的"
echo
echo "  管理员账号 : admin"
echo "  管理员密码 : ${ADMIN_PW}"
echo
echo "  ↑ 请立刻记下来。密码也存在 .env 里，但登录后请在系统里再改一次。"
echo "=================================================="
echo

run_check

echo
echo "接下来："
echo "  1. docker compose up -d --build"
echo "  2. 在云服务器安全组 / 防火墙放行 ${PORT} 端口"
echo "  3. 浏览器打开 ${ORIGIN}"
echo
echo "详细步骤见 docs/部署指南.md"
