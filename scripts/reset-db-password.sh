#!/usr/bin/env bash
# 把数据卷里那个旧数据库的口令，改成当前 .env 里的口令。
#
# 什么时候用：删掉项目目录重新部署之后，deploy.sh 生成了一份新的随机口令，
# 但数据卷 exam-system_db_data 还是旧的 —— MySQL 只在第一次初始化时采用
# MYSQL_PASSWORD，之后完全不看，所以后端连不上，部署卡在
#   dependency failed to start: container exam-system-backend-1 is unhealthy
#
# 做法：用 --skip-grant-tables 起一个**临时** mysqld（不开网络，只走容器内的
# socket），先整库导出一份 SQL 留底，再把 root 和应用账号的口令改成 .env 里的值。
#
#   bash scripts/reset-db-password.sh
#
# 【前提】旧 .env 确实找不回来了。能找回来就直接放回去，那样什么都不用动 ——
#         找回来省事得多，见 deploy.sh 停下来时打印的三条路。

set -uo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YEL='\033[33m'; C_RED='\033[31m'; C_OFF='\033[0m'
step() { printf "\n${C_CYAN}%s${C_OFF}\n" "$1"; }
ok()   { printf "      ${C_GREEN}%s${C_OFF}\n" "$1"; }
warn() { printf "      ${C_YEL}%s${C_OFF}\n" "$1"; }
die()  { printf "\n${C_RED}[失败] %s${C_OFF}\n\n" "$1"; exit 1; }

VOLUME="exam-system_db_data"
TMP_NAME="exam-pwreset"

# shellcheck source=scripts/lib-env.sh
. "$ROOT/scripts/lib-env.sh"

echo "=================================================="
echo "      重设数据库口令（保留原有数据）"
echo "=================================================="

# ---------------------------------------------------------------- 检查
step "[1/6] 检查前提..."
command -v docker >/dev/null 2>&1 || die "这台机器没装 Docker。"
docker info >/dev/null 2>&1 || die "Docker 没运行，或当前用户没权限。"
[ -f .env ] || die "项目根目录没有 .env。请先跑一次 ./deploy.sh 生成，再回来跑本脚本。"
docker volume inspect "$VOLUME" >/dev/null 2>&1 \
    || die "找不到数据卷 $VOLUME。没有旧数据库要救，直接跑 ./deploy.sh 就行。"

load_env_file "$ROOT/.env"
: "${MYSQL_ROOT_PASSWORD:?.env 里没有 MYSQL_ROOT_PASSWORD}"
: "${MYSQL_PASSWORD:?.env 里没有 MYSQL_PASSWORD}"
DB_NAME="${MYSQL_DATABASE:-exam}"
DB_USER="${MYSQL_USER:-exam}"
IMAGE="${REGISTRY:-docker.io}/library/mysql:8.0"
ok "数据卷在，.env 读到了，目标账号：${DB_USER} / 库：${DB_NAME}"

echo
warn "这个操作会修改数据卷里的账号口令。数据本身不动，但仍请确认。"
read -r -p "  确认继续？输入「确认」再回车： " ANS
[ "$ANS" = "确认" ] || die "已取消，什么都没动。"

# ---------------------------------------------------------------- 停服务
step "[2/6] 停掉正在运行的容器..."
# 必须停 —— 两个 mysqld 同时开同一份数据文件会把数据写坏
docker compose down --remove-orphans >/dev/null 2>&1 || true
docker rm -f "$TMP_NAME" >/dev/null 2>&1 || true
ok "已停止"

cleanup() {
    docker rm -f "$TMP_NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# ---------------------------------------------------------------- 临时库
step "[3/6] 用免密模式启动一个临时数据库..."
# --skip-networking：只开容器内的 socket，这段时间里外面连不进来
docker run --rm -d --name "$TMP_NAME" \
    -v "${VOLUME}:/var/lib/mysql" \
    "$IMAGE" \
    mysqld --skip-grant-tables --skip-networking >/dev/null \
    || die "临时容器起不来。镜像 $IMAGE 在本机有吗？docker images | grep mysql"

printf "      等它就绪"
READY=0
for _ in $(seq 1 60); do
    if docker exec "$TMP_NAME" mysql -u root -e "SELECT 1" >/dev/null 2>&1; then
        READY=1; break
    fi
    printf "."
    sleep 2
done
echo
[ "$READY" = 1 ] || die "临时数据库 120 秒内没就绪。看日志：docker logs $TMP_NAME"
ok "临时数据库已就绪（免密）"

# ---------------------------------------------------------------- 先备份
step "[4/6] 先整库导出一份备份..."
BACKUP_DIR="/opt/exam-backups"
mkdir -p "$BACKUP_DIR" 2>/dev/null || BACKUP_DIR="$ROOT"
STAMP="$(date '+%Y%m%d-%H%M%S')"
DUMP="${BACKUP_DIR}/exam-改口令前-${STAMP}.sql.gz"

# 改口令之前先留底：万一下一步出意外，这份还能还原。
# 免密模式下 mysqldump 不需要口令，正好趁这个时候导。
if docker exec "$TMP_NAME" mysqldump -u root \
        --databases "$DB_NAME" --single-transaction --routines --events 2>/dev/null \
        | gzip > "$DUMP"; then
    SIZE="$(du -h "$DUMP" 2>/dev/null | cut -f1)"
    if [ -s "$DUMP" ]; then
        chmod 600 "$DUMP" 2>/dev/null || true
        ok "备份已存到 $DUMP （${SIZE}）"
    else
        rm -f "$DUMP"
        die "导出来是个空文件，不敢往下走。看看库名对不对：
      docker exec $TMP_NAME mysql -u root -e 'SHOW DATABASES'"
    fi
else
    rm -f "$DUMP"
    die "备份失败，已停在这里，没有改任何口令。"
fi

# ---------------------------------------------------------------- 改口令
step "[5/6] 改口令..."
# --skip-grant-tables 下权限表没加载，ALTER USER 会报错，
# 所以先 FLUSH PRIVILEGES 把权限表读进来再改。
SQL=$(cat <<SQLEOF
FLUSH PRIVILEGES;
ALTER USER 'root'@'localhost' IDENTIFIED BY '${MYSQL_ROOT_PASSWORD}';
CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${MYSQL_PASSWORD}';
ALTER USER '${DB_USER}'@'%' IDENTIFIED BY '${MYSQL_PASSWORD}';
GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'%';
FLUSH PRIVILEGES;
SQLEOF
)
# 口令从标准输入喂进去，不写进命令行 —— 命令行参数在 ps 里人人可见
if ! printf '%s\n' "$SQL" | docker exec -i "$TMP_NAME" mysql -u root 2>/tmp/pwreset.err; then
    warn "$(cat /tmp/pwreset.err 2>/dev/null | head -5)"
    die "改口令失败。数据没动，备份在 $DUMP"
fi
ok "root 和 ${DB_USER} 的口令都已改成 .env 里的值"

# ---------------------------------------------------------------- 起服务
step "[6/6] 关掉临时库，重新起服务..."
docker stop "$TMP_NAME" >/dev/null 2>&1 || true
# 等它把数据完全落盘再走，不然下一个 mysqld 会看到没关干净的文件
sleep 3
trap - EXIT

docker compose up -d --build || die "启动失败。看日志：docker compose logs --tail=60"

printf "      等后端起来"
for _ in $(seq 1 40); do
    if docker compose ps backend 2>/dev/null | grep -q "healthy"; then
        echo; ok "后端健康检查通过，口令已经对上了"
        echo
        echo "      备份留在：$DUMP"
        echo "      之后升级只要 git pull && docker compose up -d --build，"
        echo "      千万别再删项目目录 —— .env 一没，这套麻烦就得重来一遍。"
        exit 0
    fi
    printf "."
    sleep 5
done
echo
warn "后端 200 秒内还没健康。看日志找原因："
echo "      docker compose logs backend --tail=60"
exit 1
