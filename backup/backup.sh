#!/usr/bin/env bash
# 每天备份数据库和上传目录，保留最近 30 天。
#
# 加到宿主机 crontab（路径按实际存放位置改）：
#   0 2 * * * /opt/A_System_of_WFXXKJ_Simulating_Examination/backup/backup.sh >> /var/log/exam-backup.log 2>&1
#
# 设计要点：备份脚本最怕「以为备好了其实是空文件」，所以这里每一步都验证，
# 任何一步失败立刻非 0 退出，绝不打印「备份完成」。

set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

# cron 的环境变量几乎是空的，必须自己把 .env 读进来。
# 不读的话下面会退回 .env.example 里的默认密码，认证失败却又被管道吞掉。
if [ -f "$ROOT/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    . "$ROOT/.env"
    set +a
else
    echo "[错误] 找不到 $ROOT/.env，无法取得数据库口令" >&2
    exit 1
fi

DB_USER="${MYSQL_USER:?".env 里缺 MYSQL_USER"}"
DB_PASS="${MYSQL_PASSWORD:?".env 里缺 MYSQL_PASSWORD"}"
DB_NAME="${MYSQL_DATABASE:-exam}"

DATE="$(date +%F_%H%M)"
OUT="$ROOT/backup"
mkdir -p "$OUT"

# ---------- 数据库 ----------
SQL_TMP="$OUT/.db_${DATE}.sql"
if ! docker compose exec -T db mysqldump \
        -u"$DB_USER" -p"$DB_PASS" \
        --single-transaction --default-character-set=utf8mb4 \
        "$DB_NAME" > "$SQL_TMP" 2>"$OUT/.dump_err"; then
    echo "[错误] mysqldump 失败：$(cat "$OUT/.dump_err")" >&2
    rm -f "$SQL_TMP" "$OUT/.dump_err"
    exit 1
fi

# 认证失败时 mysqldump 可能只吐几行注释就退出，光看退出码不够，还要看内容
if ! grep -q "CREATE TABLE" "$SQL_TMP"; then
    echo "[错误] 导出的 SQL 里没有建表语句，备份无效（口令不对？库是空的？）" >&2
    rm -f "$SQL_TMP" "$OUT/.dump_err"
    exit 1
fi

gzip -c "$SQL_TMP" > "$OUT/db_${DATE}.sql.gz"
rm -f "$SQL_TMP" "$OUT/.dump_err"

# ---------- 上传目录（题目配图，不在数据库里）----------
if [ -d "$ROOT/data/uploads" ]; then
    tar czf "$OUT/uploads_${DATE}.tar.gz" -C "$ROOT/data" uploads
else
    echo "[提示] 没有 data/uploads 目录，跳过配图备份"
fi

# ---------- 清理与汇报 ----------
find "$OUT" -name '*.gz' -mtime +30 -delete

DB_SIZE="$(du -h "$OUT/db_${DATE}.sql.gz" | cut -f1)"
echo "[$(date '+%F %T')] 备份完成"
echo "  数据库 : backup/db_${DATE}.sql.gz  ($DB_SIZE)"
[ -f "$OUT/uploads_${DATE}.tar.gz" ] && \
    echo "  配图   : backup/uploads_${DATE}.tar.gz  ($(du -h "$OUT/uploads_${DATE}.tar.gz" | cut -f1))"
echo "  现存备份 $(find "$OUT" -name '*.gz' | wc -l) 份"
