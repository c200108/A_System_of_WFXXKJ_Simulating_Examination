#!/usr/bin/env bash
# 装「主机助手」：装好后系统管理员能在网页上（我的账号 → 数据备份与系统更新）
# 导入备份数据、一键更新，不用再登服务器敲命令。
#
#   sudo bash scripts/host-agent-install.sh            # 装 / 重装（可以反复跑）
#   sudo bash scripts/host-agent-install.sh --remove   # 卸掉
#
# 装的是两个 systemd 单元：
#   exam-host-agent.path     盯着 data/host-jobs/queue/，网页放了单子就拉起下面这个
#   exam-host-agent.service  跑 scripts/host-agent.sh，做完就退出，不常驻
#
# deploy.sh 和 update-from-zip.sh 跑完会自动调本脚本，正常不用手工装；
# 老服务器第一次升级到 2.18.0 之前没有它，升级完就有了。

set -uo pipefail

C_GREEN='\033[32m'; C_YEL='\033[33m'; C_RED='\033[31m'; C_OFF='\033[0m'
ok()   { printf "      ${C_GREEN}✓ %s${C_OFF}\n" "$1"; }
warn() { printf "      ${C_YEL}! %s${C_OFF}\n" "$1"; }
die()  { printf "\n${C_RED}[失败] %s${C_OFF}\n\n" "$1"; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT=/etc/systemd/system/exam-host-agent
JOBS="$ROOT/data/host-jobs"

[ "$(id -u)" = "0" ] || die "需要 root：sudo bash $0"
command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ] \
    || die "这台机器没有 systemd，装不了主机助手。导入、更新照旧用命令行：
      sudo bash scripts/data-import.sh <exam-data 目录>
      sudo bash scripts/update-from-zip.sh <main 压缩包>"

if [ "${1:-}" = "--remove" ]; then
    systemctl disable --now exam-host-agent.path >/dev/null 2>&1
    rm -f "$UNIT.path" "$UNIT.service" "$JOBS/agent.json"
    systemctl daemon-reload
    ok "主机助手已卸掉（网页上的导入、一键更新会提示没装）"
    exit 0
fi

case "$ROOT" in *[[:space:]]*) die "项目目录 $ROOT 里有空格，systemd 不好处理，换个不带空格的目录";; esac
[ -f "$ROOT/docker-compose.yml" ] || die "$ROOT 不像项目目录（没有 docker-compose.yml）"

mkdir -p "$JOBS/queue" "$JOBS/jobs"
chmod 700 "$JOBS"

cat > "$UNIT.service" <<EOF
[Unit]
Description=信息科技教学平台 主机助手（网页上的导入备份、一键更新）
After=docker.service

[Service]
Type=oneshot
ExecStart=/bin/bash $ROOT/scripts/host-agent.sh
WorkingDirectory=$ROOT
# 升级要构建镜像，可能好几分钟，不设超时
TimeoutStartSec=0
EOF

cat > "$UNIT.path" <<EOF
[Unit]
Description=盯着 $JOBS/queue 等网页派活

[Path]
DirectoryNotEmpty=$JOBS/queue
MakeDirectory=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable exam-host-agent.path >/dev/null 2>&1
# 升级脚本里也会调本脚本，那时主机助手自己正在跑 —— 只启 path，不碰正在跑的 service
systemctl start exam-host-agent.path
systemctl is-active --quiet exam-host-agent.path || die "exam-host-agent.path 没起来：systemctl status exam-host-agent.path"

VER="$(grep -m1 -oE '"[0-9]+\.[0-9]+\.[0-9]+"' "$ROOT/backend/app/changelog_seed.py" 2>/dev/null | tr -d '"')"
printf '{"version": "%s", "installed_at": "%s", "project_dir": "%s"}\n' \
    "${VER:-}" "$(date '+%F %T')" "$ROOT" > "$JOBS/agent.json"
ok "主机助手已装好：系统管理员登录网页 →「我的账号」→「数据备份与系统更新」"
