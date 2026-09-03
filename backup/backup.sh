#!/bin/sh
# 每天备份一次数据库和上传目录，保留最近 30 天。
# 用法：加到宿主机 crontab —— 0 2 * * * /opt/exam-system/backup/backup.sh
set -e
cd "$(dirname "$0")/.."

DATE=$(date +%F)
mkdir -p backup

docker compose exec -T db \
  mysqldump -u"${MYSQL_USER:-exam}" -p"${MYSQL_PASSWORD:-exam_pwd}" \
  --single-transaction --default-character-set=utf8mb4 "${MYSQL_DATABASE:-exam}" \
  | gzip > "backup/db_${DATE}.sql.gz"

tar czf "backup/uploads_${DATE}.tar.gz" -C data uploads

find backup -name '*.gz' -mtime +30 -delete
echo "备份完成：backup/db_${DATE}.sql.gz"
