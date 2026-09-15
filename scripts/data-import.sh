#!/usr/bin/env bash
# 把 data-export.sh 导出的数据还原到本机。
#
#   sudo bash scripts/data-import.sh /路径/exam-data
#
# 【前提】本机已经正常部署好了：git clone + ./deploy.sh 跑通、能打开页面。
#         这个脚本只往现成的系统里填数据，不负责把系统装起来。
#
# ============================ 和老版本的区别 ============================
#
# 老版本会重写 .env（把导出时的口令按上去）、会碰数据卷、会用一份旧 SQL 覆盖
# 表结构。那套设计导致了一连串难查的故障，见 docs/数据还原排障.md。
#
# 现在这版：
#   · **不碰 .env** —— 本机的口令、端口原样不动
#   · **不碰数据卷** —— 不会出现"口令和卷里的对不上"
#   · **不改表结构** —— 结构以本机为准，数据按列名对齐填进去
#
# 所以"原项目删掉、重新 clone 一份部署、再把数据导回来"这条路是通的，
# 而且备份比系统旧几个版本也能导（新加的列取默认值，删掉的列跳过并报出来）。
#
# 做的事：
#   1. 检查来源目录和本机状态
#   2. 先把本机现有数据导一份到「回滚点」，万一导错了能退回去
#   3. 试算：列出每张表要导多少行、有哪些版本差异
#   4. 让你确认，然后真导
#   5. 还原配图和 config.yaml
#   6. 重启后端，逐表核对行数

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

# ---------------------------------------------------------------- 1 检查
step "[1/6] 检查来源与本机状态..."
[ -d "$SRC/tables" ] || die "$SRC 里没有 tables 目录，这不像是 data-export.sh 导出的。
      如果是 2.4.7 之前的老备份（里面是 database.sql.gz），
      见 docs/数据还原排障.md 的「老备份怎么办」。"
[ -s "$SRC/meta.json" ] || die "缺少 meta.json，备份不完整"
COUNT="$(ls -1 "$SRC/tables"/*.jsonl 2>/dev/null | wc -l)"
[ "$COUNT" -ge 5 ] || die "只有 $COUNT 张表，这份备份不完整，不敢导"

command -v docker >/dev/null 2>&1 || die "没装 docker"
[ -n "$(docker compose ps -q backend 2>/dev/null)" ] \
    || die "backend 容器没在运行。先把系统正常部署起来：
      ./deploy.sh
      确认能打开页面之后，再回来跑这个脚本。"

# 后端健康才说明迁移跑完了、表结构是最新的 —— 这是按列名对齐的前提
if ! docker compose ps backend 2>/dev/null | grep -q "healthy"; then
    warn "backend 还不是 healthy，可能迁移没跑完"
    warn "建议先等它健康再导：docker compose ps"
fi
ok "来源有 $COUNT 张表，本机后端在运行"
# 脚本是宿主机上的文件，git pull 就更新了；但 tools/*.py 是**打进镜像**的
# （backend/Dockerfile 里 COPY . .，没有挂载源码）。只 pull 不重建的话，
# 新脚本会去调容器里还不存在的模块，报一句 "No module named tools.xxx"，
# 看不出是怎么回事。这里提前认出来，把该敲的命令直接给出来。
if ! docker compose exec -T backend python -c "import tools.import_data" >/dev/null 2>&1; then
    die "容器里的后端代码还是旧的，没有 tools/import_data.py。
      拉了新代码之后要重建镜像才生效：

        docker compose up -d --build

      等后端变成 healthy（docker compose ps）再回来跑本脚本。"
fi

if [ -s "$SRC/MANIFEST.txt" ]; then
    echo
    sed -n '1,4p' "$SRC/MANIFEST.txt" | sed 's/^/      /'
fi

# ---------------------------------------------------------------- 2 回滚点
step "[2/6] 先把本机现有数据备一份（回滚点）..."
ROLLBACK="$ROOT/exam-data-回滚点-$(date +%Y%m%d-%H%M%S)"
docker compose exec -T backend rm -rf /tmp/rollback >/dev/null 2>&1
if docker compose exec -T backend python -m tools.export_data /tmp/rollback >/dev/null 2>&1; then
    mkdir -p "$ROLLBACK"
    CID="$(docker compose ps -q backend)"
    docker cp "$CID:/tmp/rollback/tables" "$ROLLBACK/tables" >/dev/null 2>&1
    docker cp "$CID:/tmp/rollback/meta.json" "$ROLLBACK/meta.json" >/dev/null 2>&1
    docker compose exec -T backend rm -rf /tmp/rollback >/dev/null 2>&1
    ok "回滚点已存到 $(basename "$ROLLBACK")"
    echo "        导错了可以退回去：sudo bash scripts/data-import.sh $ROLLBACK"
else
    warn "回滚点没备成（库可能是空的），继续"
fi

# ---------------------------------------------------------------- 3 试算
step "[3/6] 试算：看看会导入什么..."
docker compose exec -T backend rm -rf /tmp/data-import >/dev/null 2>&1
CID="$(docker compose ps -q backend)"
docker cp "$SRC" "$CID:/tmp/data-import" >/dev/null || die "拷不进容器"

docker compose exec -T backend python -m tools.import_data /tmp/data-import \
    || die "试算失败，上面是原始报错。本机数据一个字都没动。"

# ---------------------------------------------------------------- 4 确认
step "[4/6] 确认操作..."
echo "      即将用上面这份数据**覆盖**本机数据库里的同名表。"
echo "      本机的 .env、端口、口令都不会动；表结构也不会动。"
echo
read -r -p "      确认请输入「还原」两个字：" ANSWER
[ "$ANSWER" = "还原" ] || {
    docker compose exec -T backend rm -rf /tmp/data-import >/dev/null 2>&1
    die "已取消，什么都没动"
}

step "[5/6] 导入数据..."
docker compose exec -T backend python -m tools.import_data /tmp/data-import --write \
    || die "导入失败，上面是原始报错。整个导入是一个事务，失败会整体回滚，
      本机数据还是原来的样子。"
docker compose exec -T backend rm -rf /tmp/data-import >/dev/null 2>&1

# ---------------------------------------------------------------- 5 文件
step "[6/6] 还原配图与配置，重启服务..."
if [ -s "$SRC/uploads.tar.gz" ]; then
    mkdir -p "$ROOT/data"
    rm -rf "$ROOT/data/uploads"
    tar xzf "$SRC/uploads.tar.gz" -C "$ROOT/data" 2>/dev/null || true
    mkdir -p "$ROOT/data/uploads"
    ok "配图已还原（$(find "$ROOT/data/uploads" -type f 2>/dev/null | wc -l) 个文件）"
fi

if [ -s "$SRC/config.yaml" ]; then
    cp "$ROOT/config.yaml" "$ROOT/config.yaml.bak-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
    cp "$SRC/config.yaml" "$ROOT/config.yaml" || warn "复制 config.yaml 失败"
    ok "config.yaml 已还原（原件备份为 config.yaml.bak-*）"
fi

# settings.env 里是端口和对外地址，不含口令。要不要套用由你决定 ——
# 新机器的地址多半和老机器不一样，自动套用反而会把页面打不开。
if [ -s "$SRC/settings.env" ]; then
    echo
    warn "备份里带着老机器的端口和对外地址，没有自动套用："
    grep -E '^[A-Z]' "$SRC/settings.env" 2>/dev/null | sed 's/^/        /'
    warn "本机要沿用的话自己改 .env，改完 docker compose up -d"
fi

docker compose restart backend >/dev/null 2>&1 || warn "重启后端失败，手动跑 docker compose restart backend"

echo
echo "=================================================="
echo "  还原完成"
echo
echo "  本机的 .env 没有被改动，口令和端口还是原来的。"
[ -d "$ROLLBACK" ] && echo "  回滚点：$ROLLBACK"
echo
echo "  打开页面确认一下题目数、学生数对不对得上。"
echo "=================================================="
