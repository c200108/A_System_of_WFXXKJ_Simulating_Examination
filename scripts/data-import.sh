#!/usr/bin/env bash
# 把 data-export.sh 导出的文件夹还原到一台全新的 Ubuntu 服务器上。
#
#   sudo bash scripts/data-import.sh ~/exam-data
#
# 前提：这台机器已经装好 docker，且项目代码已经放到位（解压或 git clone 都行）。
# 没装 docker 的话先跑 scripts/setup-docker-cn.sh。
#
# 做的事：
#   1. 用导出的口令生成 .env —— 口令必须和导出时一致，否则连不上还原出来的库；
#   2. 起数据库容器，等它真的能应答；
#   3. 把 SQL 灌进去；
#   4. 还原配图和 config.yaml；
#   5. 起全部服务，按 MANIFEST 核对行数。
#
# **会覆盖目标库的同名数据库**，所以一上来就要你确认。

set -uo pipefail

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YEL='\033[33m'; C_RED='\033[31m'; C_OFF='\033[0m'
step() { printf "\n${C_CYAN}%s${C_OFF}\n" "$1"; }
ok()   { printf "      ${C_GREEN}✓ %s${C_OFF}\n" "$1"; }
warn() { printf "      ${C_YEL}! %s${C_OFF}\n" "$1"; }
die()  { printf "\n${C_RED}[失败] %s${C_OFF}\n\n" "$1"; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || die "进不去项目目录 $ROOT"

SRC="${1:-}"
[ -n "$SRC" ] || die "用法：sudo bash $0 <导出的文件夹>"
SRC="$(cd "$SRC" 2>/dev/null && pwd)" || die "找不到目录：${1}"

echo "=================================================="
echo "   还原数据到本机"
echo "=================================================="
echo "  项目目录：$ROOT"
echo "  数据来源：$SRC"

# ---------------------------------------------------------------- 0 检查
step "[1/7] 检查来源文件..."
for f in database.sql.gz uploads.tar.gz config.yaml env.secrets; do
    [ -s "$SRC/$f" ] || die "缺少 $f，这个目录不像是 data-export.sh 导出的"
done
gzip -t "$SRC/database.sql.gz" || die "database.sql.gz 损坏，重新导一份"
tar tzf "$SRC/uploads.tar.gz" >/dev/null || die "uploads.tar.gz 损坏"
ok "四个文件齐全，压缩包完整"

[ -f "$ROOT/docker-compose.yml" ] || die "当前目录不是项目根目录（没有 docker-compose.yml）"
command -v docker >/dev/null 2>&1 || die "没装 docker，先跑 scripts/setup-docker-cn.sh"
docker compose version >/dev/null 2>&1 || die "docker compose 不可用（需要 v2）"

if [ -s "$SRC/MANIFEST.txt" ]; then
    echo
    sed -n '1,8p' "$SRC/MANIFEST.txt" | sed 's/^/      /'
fi

# ---------------------------------------------------------------- 1 确认
step "[2/7] 确认操作..."
EXISTING=""
if [ -n "$(docker compose ps -q db 2>/dev/null)" ]; then
    EXISTING="（注意：本机 db 容器正在运行，里面的同名数据库会被覆盖）"
fi
echo "      即将把上面这份数据还原到本机。$EXISTING"
echo "      还原会覆盖本机数据库里的同名库，操作不可撤销。"
echo
read -r -p "      确认请输入「还原」两个字：" ANSWER
[ "$ANSWER" = "还原" ] || die "已取消，什么都没动"

# ---------------------------------------------------------------- 2 .env
step "[3/7] 准备 .env..."
# 口令必须沿用导出时那一套：MySQL 数据卷里的账号是建库时定死的，
# 换一套口令就连不上还原出来的库。
if [ -f "$ROOT/.env" ]; then
    cp "$ROOT/.env" "$ROOT/.env.bak-$(date +%Y%m%d-%H%M%S)"
    warn "已有 .env，备份为 .env.bak-*"
fi

[ -f "$ROOT/.env.example" ] || die "缺少 .env.example"
cp "$ROOT/.env.example" "$ROOT/.env"

# 把导出的口令逐行覆盖进去。用 awk 整行替换，不用 sed 的 s///：
# 口令里可能有 / & | 之类的字符，当分隔符会把命令搞坏。
while IFS= read -r line; do
    case "$line" in \#*|"") continue ;; esac
    key="${line%%=*}"
    [ -n "$key" ] || continue
    awk -v k="$key" -v full="$line" '
        BEGIN { done = 0 }
        $0 ~ "^[[:space:]]*" k "[[:space:]]*=" && !done { print full; done = 1; next }
        { print }
        END { if (!done) print full }
    ' "$ROOT/.env" > "$ROOT/.env.tmp" && mv "$ROOT/.env.tmp" "$ROOT/.env"
done < "$SRC/env.secrets"

chmod 600 "$ROOT/.env"
# shellcheck disable=SC1091
. "$ROOT/scripts/lib-env.sh" || die "找不到 scripts/lib-env.sh"
load_env_file "$ROOT/.env" || die "读不了 $ROOT/.env"

DB_USER="${MYSQL_USER:?"env.secrets 里缺 MYSQL_USER"}"
DB_PASS="${MYSQL_PASSWORD:?"env.secrets 里缺 MYSQL_PASSWORD"}"
DB_NAME="${MYSQL_DATABASE:-exam}"
ok ".env 已生成，口令沿用导出时那一套"

# ---------------------------------------------------------------- 3 起数据库
step "[4/7] 启动数据库并等它就绪..."
docker compose up -d db || die "数据库容器起不来，看 docker compose logs db"

READY=0
for i in $(seq 1 60); do
    if docker compose exec -T db mysqladmin ping -u"$DB_USER" -p"$DB_PASS" --silent >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 2
    [ $((i % 10)) -eq 0 ] && echo "      还在等数据库初始化（已等 $((i * 2)) 秒）..."
done
[ "$READY" = 1 ] || die "等了 2 分钟数据库还没起来，看 docker compose logs db"
ok "数据库已就绪"

# ---------------------------------------------------------------- 4 灌数据
step "[5/7] 导入数据..."
docker compose exec -T db mysql -u"$DB_USER" -p"$DB_PASS" --default-character-set=utf8mb4 \
    -e "CREATE DATABASE IF NOT EXISTS \`$DB_NAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" \
    >/dev/null 2>&1 || die "建库失败，口令可能不对"

# mysqldump 出来的 SQL 自带 DROP TABLE IF EXISTS，直接灌即可覆盖
if ! gunzip -c "$SRC/database.sql.gz" | docker compose exec -T db mysql \
        -u"$DB_USER" -p"$DB_PASS" --default-character-set=utf8mb4 "$DB_NAME" 2>"$ROOT/.import_err"; then
    printf "%s\n" "$(cat "$ROOT/.import_err")" >&2
    rm -f "$ROOT/.import_err"
    die "导入失败，上面是原始报错"
fi
rm -f "$ROOT/.import_err"
ok "SQL 已导入"

# ---------------------------------------------------------------- 5 文件
step "[6/7] 还原配图与配置..."
mkdir -p "$ROOT/data"
rm -rf "$ROOT/data/uploads"
tar xzf "$SRC/uploads.tar.gz" -C "$ROOT/data" || die "解开 uploads 失败"
mkdir -p "$ROOT/data/uploads"
ok "配图与导入原件已还原（$(find "$ROOT/data/uploads" -type f 2>/dev/null | wc -l) 个文件）"

cp "$SRC/config.yaml" "$ROOT/config.yaml" || die "复制 config.yaml 失败"
ok "config.yaml 已还原"

# ---------------------------------------------------------------- 6 起服务并核对
step "[7/7] 启动全部服务并核对数据..."
docker compose up -d --build || die "服务起不来，看 docker compose logs"

# 后端启动时会跑 alembic upgrade head。导入的库如果是旧版本，这一步会把它升上来。
HEALTHY=0
for i in $(seq 1 60); do
    if curl -fsS -m 3 "http://127.0.0.1:${WEB_PORT:-8080}/api/health" >/dev/null 2>&1; then
        HEALTHY=1
        break
    fi
    sleep 2
done
if [ "$HEALTHY" = 1 ]; then
    ok "服务已就绪"
else
    warn "健康检查没通过，可能还在构建。稍后看 docker compose logs backend"
fi

echo
echo "      --- 行数核对（左：本机现在  右：导出时）---"
MISMATCH=0
CHECKED=0
for t in questions users students exams exam_submissions typing_records typing_texts; do
    now="$(docker compose exec -T db mysql -u"$DB_USER" -p"$DB_PASS" -N -B "$DB_NAME" \
           -e "SELECT COUNT(*) FROM $t" 2>/dev/null | tr -d '\r')"
    # 用 sed 而不是 grep -oP：-P 在非 UTF-8 的 locale 下会直接罢工
    # （报 "-P supports only unibyte and UTF-8 locales"），
    # 那样每张表都"查不到期望值"，核对静悄悄地全被跳过。
    want="$(sed -n "s/^$t=\([0-9][0-9]*\)\$/\1/p" "$SRC/MANIFEST.txt" 2>/dev/null | head -1)"

    if [ -z "$want" ]; then
        printf "      %-18s %-8s ${C_YEL}（清单里没有，没核对）${C_OFF}\n" "$t" "${now:-?}"
    elif [ "$now" = "$want" ]; then
        printf "      ${C_GREEN}%-18s %-8s = %s${C_OFF}\n" "$t" "$now" "$want"
        CHECKED=$((CHECKED + 1))
    else
        printf "      ${C_RED}%-18s %-8s ≠ %s${C_OFF}\n" "$t" "${now:-?}" "$want"
        MISMATCH=1
        CHECKED=$((CHECKED + 1))
    fi
done

echo
echo "=================================================="
if [ "$CHECKED" = 0 ]; then
    # 一张表都没比成，就绝不能说"对得上" —— 那是最容易让人放心地丢数据的一句话
    echo -e "  ${C_RED}还原跑完了，但一张表都没能核对${C_OFF}"
    echo "  可能是 MANIFEST.txt 格式不对，或数据库查询没返回结果。"
    echo "  务必手工进系统看一眼题目数和学生数再投入使用。"
elif [ "$MISMATCH" = 0 ]; then
    echo "  还原完成，核对的 $CHECKED 张表行数全部对得上"
else
    echo -e "  ${C_YEL}还原完成，但有表的行数对不上${C_OFF}"
    echo "  常见原因：导出后源库又有人操作过；或导入中途报了错。"
    echo "  拿 $SRC/MANIFEST.txt 和上面的数字逐行比对确认。"
fi
echo
echo "  访问地址：http://本机IP:${WEB_PORT:-8080}"
echo "      学生平台  /          教师后台  /js"
echo
echo "  账号沿用原服务器的，密码也没变。"
echo "=================================================="
