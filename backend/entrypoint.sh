#!/bin/sh
set -e

echo "[start] 等待数据库就绪..."
python - <<'PY'
import time, sys
from sqlalchemy import create_engine, text
from app.config import settings

for i in range(60):
    try:
        create_engine(settings.database_url).connect().execute(text("SELECT 1"))
        print("[start] 数据库连上了")
        break
    except Exception as e:
        print(f"[start] 第 {i+1} 次重试：{e.__class__.__name__}")
        time.sleep(2)
else:
    sys.exit("数据库连不上，检查 DATABASE_URL")
PY

echo "[start] 准备数据库"
python -m tools.ensure_db

echo "[start] 执行数据库迁移"
alembic upgrade head

echo "[start] 初始化管理员与字典"
python -m app.seed

# 全新部署时把 legacy/ 里那份原题库灌进去；库里已有题目则原样不动，
# 所以从备份恢复的实例不会被影响，重启也不会重复导入。
echo "[start] 检查题库"
python -m tools.migrate_from_html --if-empty

echo "[start] 启动服务"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
