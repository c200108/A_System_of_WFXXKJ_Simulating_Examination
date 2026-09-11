#!/usr/bin/env bash
# 把这套系统的全部数据导出到一个专属文件夹，拷走就能在别的服务器上还原。
#
#   sudo bash scripts/data-export.sh              # 导到 ./exam-data/
#   sudo bash scripts/data-export.sh /mnt/u盘     # 导到指定位置
#
# 导出的内容：
#   database.sql.gz  整个 MySQL 库（题库、账号、学生、成绩、反馈、更新日志……）
#   uploads.tar.gz   题目配图和导入的 Excel 原件
#   config.yaml      平台配置（平台名称、知识范围、打字文本……）
#   env.secrets      .env 里的口令，**含明文密码，注意保管**
#   MANIFEST.txt     导出时间、版本、各表行数，还原后拿来核对
#
# 设计上的一条原则：**宁可失败也不要产出一个看似成功的空备份**。
# 每一步都验证产物有没有内容，任何一步不对就立刻退出，绝不打印"导出完成"。

set -uo pipefail

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YEL='\033[33m'; C_RED='\033[31m'; C_OFF='\033[0m'
step() { printf "\n${C_CYAN}%s${C_OFF}\n" "$1"; }
ok()   { printf "      ${C_GREEN}✓ %s${C_OFF}\n" "$1"; }
warn() { printf "      ${C_YEL}! %s${C_OFF}\n" "$1"; }
die()  { printf "\n${C_RED}[失败] %s${C_OFF}\n\n" "$1"; exit 1; }

# 项目根目录：脚本在 scripts/ 下，往上一层
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || die "进不去项目目录 $ROOT"

OUT_BASE="${1:-$ROOT/exam-data}"
STAMP="$(date +%Y%m%d-%H%M%S)"

echo "=================================================="
echo "   导出全部数据"
echo "=================================================="
echo "  项目目录：$ROOT"
echo "  导出到  ：$OUT_BASE"

# ---------------------------------------------------------------- 0 前置检查
step "[1/6] 检查环境..."
command -v docker >/dev/null 2>&1 || die "没装 docker"
[ -f "$ROOT/.env" ] || die "找不到 $ROOT/.env，无法取得数据库口令"
[ -f "$ROOT/docker-compose.yml" ] || die "找不到 docker-compose.yml，确认在项目根目录"

# cron 或 sudo 环境里变量是空的，必须自己读 .env。
# 用 load_env_file 而不是 source：口令里带 & | ; 空格时 source 会当成 shell 语法。
# shellcheck disable=SC1091
. "$ROOT/scripts/lib-env.sh" || die "找不到 scripts/lib-env.sh"
load_env_file "$ROOT/.env" || die "读不了 $ROOT/.env"

DB_USER="${MYSQL_USER:?".env 里缺 MYSQL_USER"}"
DB_PASS="${MYSQL_PASSWORD:?".env 里缺 MYSQL_PASSWORD"}"
DB_NAME="${MYSQL_DATABASE:-exam}"

if [ -z "$(docker compose ps -q db 2>/dev/null)" ]; then
    die "db 容器没在运行。先 docker compose up -d db 再导出。"
fi
ok "docker 和 .env 都就位，数据库容器在运行"

mkdir -p "$OUT_BASE" || die "建不了目录 $OUT_BASE"
OUT="$OUT_BASE"

# ---------------------------------------------------------------- 1 数据库
step "[2/6] 导出数据库..."
SQL_TMP="$OUT/.database.sql.tmp"

# --routines --events --triggers：把存储过程一起带走，将来加了也不会漏
# --single-transaction：不锁表，导出期间学生照常答题
# --set-gtid-purged=OFF：新库不是同一个复制拓扑，带 GTID 会导不进去
if ! docker compose exec -T db mysqldump \
        -u"$DB_USER" -p"$DB_PASS" \
        --single-transaction --quick \
        --routines --events --triggers \
        --default-character-set=utf8mb4 \
        --set-gtid-purged=OFF \
        "$DB_NAME" > "$SQL_TMP" 2>"$OUT/.dump_err"; then
    printf "%s\n" "$(cat "$OUT/.dump_err")" >&2
    rm -f "$SQL_TMP" "$OUT/.dump_err"
    die "mysqldump 失败，上面是原始报错"
fi

# 认证失败时 mysqldump 可能只吐几行注释就退出，光看退出码不够
if ! grep -q "CREATE TABLE" "$SQL_TMP"; then
    rm -f "$SQL_TMP" "$OUT/.dump_err"
    die "导出的 SQL 里没有建表语句，备份无效（口令不对？库是空的？）"
fi

TABLES="$(grep -c "^CREATE TABLE" "$SQL_TMP")"
gzip -c "$SQL_TMP" > "$OUT/database.sql.gz" || die "压缩失败"
rm -f "$SQL_TMP" "$OUT/.dump_err"
ok "数据库已导出（$TABLES 张表，$(du -h "$OUT/database.sql.gz" | cut -f1)）"

# ---------------------------------------------------------------- 2 上传目录
step "[3/6] 导出题目配图与导入原件..."
if [ -d "$ROOT/data/uploads" ] && [ -n "$(ls -A "$ROOT/data/uploads" 2>/dev/null)" ]; then
    tar czf "$OUT/uploads.tar.gz" -C "$ROOT/data" uploads || die "打包 uploads 失败"
    ok "已导出（$(find "$ROOT/data/uploads" -type f | wc -l) 个文件，$(du -h "$OUT/uploads.tar.gz" | cut -f1)）"
else
    # 建个空包，还原脚本就不用分两种情况处理
    tar czf "$OUT/uploads.tar.gz" -T /dev/null
    warn "data/uploads 是空的，生成了空包"
fi

# ---------------------------------------------------------------- 3 配置
step "[4/6] 导出配置..."
cp "$ROOT/config.yaml" "$OUT/config.yaml" || die "复制 config.yaml 失败"
ok "config.yaml 已导出"

# .env 里有明文口令，单独放并且只给 root 读
{
    echo "# 从 $(hostname) 于 $(date '+%F %T') 导出"
    echo "# 含明文口令，请妥善保管；还原时 data-import.sh 会读它"
    grep -E '^[[:space:]]*(MYSQL_|JWT_SECRET|ADMIN_)' "$ROOT/.env" 2>/dev/null
} > "$OUT/env.secrets"
chmod 600 "$OUT/env.secrets"
ok "口令已导出到 env.secrets（权限 600）"

# ---------------------------------------------------------------- 4 清单
step "[5/6] 统计各表行数..."
COUNTS="$(docker compose exec -T db mysql -u"$DB_USER" -p"$DB_PASS" \
    --default-character-set=utf8mb4 -N -B "$DB_NAME" 2>/dev/null <<'SQL'
SELECT CONCAT(table_name, '=', table_rows)
FROM information_schema.tables
WHERE table_schema = DATABASE()
ORDER BY table_name;
SQL
)"

# information_schema.table_rows 对 InnoDB 只是估算，关键几张表实点一遍
EXACT="$(docker compose exec -T db mysql -u"$DB_USER" -p"$DB_PASS" \
    --default-character-set=utf8mb4 -N -B "$DB_NAME" 2>/dev/null <<'SQL'
SELECT CONCAT('questions=', (SELECT COUNT(*) FROM questions));
SELECT CONCAT('users=', (SELECT COUNT(*) FROM users));
SELECT CONCAT('students=', (SELECT COUNT(*) FROM students));
SELECT CONCAT('exams=', (SELECT COUNT(*) FROM exams));
SELECT CONCAT('exam_submissions=', (SELECT COUNT(*) FROM exam_submissions));
SELECT CONCAT('typing_records=', (SELECT COUNT(*) FROM typing_records));
SELECT CONCAT('typing_texts=', (SELECT COUNT(*) FROM typing_texts));
SQL
)"

{
    echo "昌邑市实验中学信息科技教学平台 —— 数据导出清单"
    echo "导出时间 : $(date '+%F %T')"
    echo "来源主机 : $(hostname)"
    echo "数据库名 : $DB_NAME"
    echo "表数量   : $TABLES"
    echo "迁移版本 : $(docker compose exec -T db mysql -u"$DB_USER" -p"$DB_PASS" -N -B "$DB_NAME" \
                     -e 'SELECT version_num FROM alembic_version' 2>/dev/null | tr -d '\r')"
    echo
    echo "--- 关键表精确行数（还原后拿这个核对）---"
    echo "$EXACT" | tr -d '\r'
    echo
    echo "--- 全部表（估算值，仅供参考）---"
    echo "$COUNTS" | tr -d '\r'
} > "$OUT/MANIFEST.txt"
ok "清单已写入 MANIFEST.txt"

# ---------------------------------------------------------------- 5 自检
step "[6/6] 校验导出结果..."
FAIL=0
for f in database.sql.gz uploads.tar.gz config.yaml env.secrets MANIFEST.txt; do
    if [ ! -s "$OUT/$f" ]; then
        warn "$f 不存在或是空的"
        FAIL=1
    fi
done
[ "$FAIL" = 0 ] || die "导出结果不完整，别拿这份去还原"

gzip -t "$OUT/database.sql.gz" || die "database.sql.gz 压缩包损坏"
tar tzf "$OUT/uploads.tar.gz" >/dev/null || die "uploads.tar.gz 压缩包损坏"
ok "压缩包完整性校验通过"

# 留一份带时间戳的副本，避免下次导出直接把这份覆盖掉
cp "$OUT/MANIFEST.txt" "$OUT/MANIFEST-$STAMP.txt"

echo
echo "=================================================="
echo "  导出完成"
echo
ls -1sh "$OUT"/database.sql.gz "$OUT"/uploads.tar.gz "$OUT"/config.yaml \
        "$OUT"/env.secrets "$OUT"/MANIFEST.txt | sed 's/^/    /'
echo
echo "  整个文件夹拷到新服务器，然后在新服务器上执行："
echo "      sudo bash scripts/data-import.sh /路径/$(basename "$OUT")"
echo
echo "  注意：env.secrets 里是明文口令，别放进 Git，也别发微信群。"
echo "=================================================="
