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

echo "[start] 执行数据库迁移"
alembic upgrade head

echo "[start] 初始化管理员与字典"
python -m app.seed

echo "[start] 启动服务"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers
