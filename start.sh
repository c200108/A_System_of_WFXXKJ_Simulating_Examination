#!/usr/bin/env bash
# 信息技术组卷台 —— Linux / macOS 启动脚本
# 和 Windows 上的「一键启动.bat」做同样的事，步骤一一对应。
#
#   chmod +x start.sh   # 只需一次
#   ./start.sh
#
# 用哪个数据库由 backend/.env 里的 DATABASE_URL 决定，本脚本不关心。

set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"
VENV="$ROOT/backend/.venv/bin"

echo "=================================================="
echo "        信息技术组卷台   启动中"
echo "=================================================="
echo

# ---------- 环境检查 ----------
if ! command -v python3 >/dev/null 2>&1; then
    echo "[错误] 没找到 python3，请先安装 Python 3.10 以上版本。"
    exit 1
fi
PYV=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
if [ "$(printf '%s\n3.10\n' "$PYV" | sort -V | head -1)" != "3.10" ]; then
    echo "[错误] Python 版本是 $PYV，需要 3.10 以上。"
    exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
    echo "[错误] 没找到 npm，请先安装 Node.js 18 以上版本。"
    exit 1
fi

# ---------- 1/6 虚拟环境 ----------
echo "[1/6] 准备后端运行环境..."
[ -x "$VENV/python" ] || python3 -m venv backend/.venv

# ---------- 2/6 后端依赖 ----------
echo "[2/6] 安装后端依赖..."
"$VENV/python" -m pip install --disable-pip-version-check -q -r backend/requirements.txt

[ -f backend/.env ] || cp backend/.env.example backend/.env

# ---------- 3/6 数据库 ----------
echo "[3/6] 初始化数据库..."
cd backend
mkdir -p data
if ! "$VENV/python" -m tools.ensure_db; then
    echo
    echo "       数据库没准备好，原因见上面一行。修好后重新运行本脚本。"
    exit 1
fi
"$VENV/python" -m alembic upgrade head
"$VENV/python" -m app.seed

# ---------- 4/6 原题库 ----------
echo "[4/6] 导入原题库..."
if [ -f data/.migrated ]; then
    echo "      已经导过了，跳过。"
else
    "$VENV/python" -m tools.migrate_from_html && echo ok > data/.migrated
fi
cd "$ROOT"

# ---------- 5/6 前端依赖 ----------
echo "[5/6] 安装前端依赖..."
if [ -d frontend/node_modules ]; then
    echo "      已安装，跳过。"
else
    (cd frontend && npm install)
fi

# ---------- 6/6 起服务 ----------
echo "[6/6] 启动服务..."
cleanup() {
    echo
    echo "正在停止服务..."
    kill "${BACK_PID:-}" "${FRONT_PID:-}" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "已停止。"
}
trap cleanup EXIT INT TERM

(cd backend && "$VENV/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
BACK_PID=$!
(cd frontend && npm run dev) &
FRONT_PID=$!

sleep 6
echo
echo "=================================================="
echo "  启动完成"
echo
echo "  使用地址：http://localhost:5173"
echo "  接口文档：http://127.0.0.1:8000/docs"
echo "  默认账号：见 backend/.env 里的 ADMIN_USERNAME / ADMIN_PASSWORD"
echo
echo "  按 Ctrl+C 停止两个服务。"
echo "=================================================="

# 有图形界面就顺手打开浏览器
if command -v xdg-open >/dev/null 2>&1; then xdg-open http://localhost:5173 >/dev/null 2>&1 || true
elif command -v open >/dev/null 2>&1; then open http://localhost:5173 || true
fi

wait
