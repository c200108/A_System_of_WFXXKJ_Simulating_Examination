#!/usr/bin/env bash
# 把本机的全部数据导到一个文件夹，供以后在别的机器上还原。
#
#   sudo bash scripts/data-export.sh              # 导到项目下的 exam-data/
#   sudo bash scripts/data-export.sh /mnt/u盘     # 导到指定位置
#
# 导出的内容：
#   tables/*.jsonl   每张表一个文件，一行一条记录（学生、教师、题库、成绩、
#                    班级、反馈、打字记录、系统设置……一张不落）
#   meta.json        导出时间、迁移版本、每张表有哪些列和多少行
#   uploads.tar.gz   题目配图和导入的 Excel 原件
#   config.yaml      平台配置
#   settings.env     端口、对外地址、镜像源（**不含任何口令**）
#
# ============================ 两条设计原则 ============================
#
# 1）**只导数据，不导表结构。**
#    老版本用 mysqldump，导出的 SQL 带着 CREATE TABLE，还原时会把目标库的结构
#    倒退成导出那天的样子。表结构应该由目标库那份代码说了算，不该由一份旧备份
#    倒着覆盖回去。改成只导数据之后，老备份能直接导进新版本系统：新加的列取
#    默认值，删掉的列跳过并报出来。
#
# 2）**不导口令。**
#    老版本会把 .env 里的口令导进 env.secrets，还原时按到新机器上。这是错的：
#    MySQL 的口令存在数据卷里、只在第一次建库时采用，新部署的卷用的是它自己
#    生成的那套。硬按旧口令上去只会连不上 —— 这个坑踩过一整天，见
#    docs/数据还原排障.md。所以这里只导端口、对外地址这些非机密设置。

set -uo pipefail

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YEL='\033[33m'; C_RED='\033[31m'; C_OFF='\033[0m'
step() { printf "\n${C_CYAN}%s${C_OFF}\n" "$1"; }
ok()   { printf "      ${C_GREEN}✓ %s${C_OFF}\n" "$1"; }
warn() { printf "      ${C_YEL}! %s${C_OFF}\n" "$1"; }
die()  { printf "\n${C_RED}[失败] %s${C_OFF}\n\n" "$1"; exit 1; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || die "进不去项目目录 $ROOT"

OUT="${1:-$ROOT/exam-data}"

echo "=================================================="
echo "   导出全部数据"
echo "=================================================="
echo "  项目目录：$ROOT"
echo "  导出到  ：$OUT"

# ---------------------------------------------------------------- 1 检查
step "[1/5] 检查环境..."
command -v docker >/dev/null 2>&1 || die "没装 docker"
docker compose version >/dev/null 2>&1 || die "docker compose 不可用（需要 v2）"
[ -f "$ROOT/docker-compose.yml" ] || die "当前目录不是项目根目录"
[ -n "$(docker compose ps -q backend 2>/dev/null)" ] \
    || die "backend 容器没在运行。先 docker compose up -d 再导出。"
ok "docker 就绪，后端容器在运行"
# 脚本是宿主机上的文件，git pull 就更新了；但 tools/*.py 是**打进镜像**的
# （backend/Dockerfile 里 COPY . .，没有挂载源码）。只 pull 不重建的话，
# 新脚本会去调容器里还不存在的模块，报一句 "No module named tools.xxx"，
# 看不出是怎么回事。这里提前认出来，把该敲的命令直接给出来。
if ! docker compose exec -T backend python -c "import tools.export_data" >/dev/null 2>&1; then
    die "容器里的后端代码还是旧的，没有 tools/export_data.py。
      拉了新代码之后要重建镜像才生效：

        docker compose up -d --build

      等后端变成 healthy（docker compose ps）再回来跑本脚本。"
fi

mkdir -p "$OUT" || die "建不了目录 $OUT"
OUT="$(cd "$OUT" && pwd)"

# ---------------------------------------------------------------- 2 数据
step "[2/5] 导出数据表..."
# 在容器里导到 /tmp，再拷出来 —— 不依赖宿主机和容器之间有共享目录
docker compose exec -T backend rm -rf /tmp/data-export >/dev/null 2>&1
if ! docker compose exec -T backend python -m tools.export_data /tmp/data-export; then
    die "导出失败，上面是原始报错"
fi

rm -rf "$OUT/tables" "$OUT/meta.json"
CID="$(docker compose ps -q backend)"
docker cp "$CID:/tmp/data-export/tables" "$OUT/tables" >/dev/null || die "拷不出 tables 目录"
docker cp "$CID:/tmp/data-export/meta.json" "$OUT/meta.json" >/dev/null || die "拷不出 meta.json"
docker compose exec -T backend rm -rf /tmp/data-export >/dev/null 2>&1

# 宁可失败也不要产出一个看似成功的空备份
[ -s "$OUT/meta.json" ] || die "meta.json 是空的，备份无效"
COUNT="$(ls -1 "$OUT/tables"/*.jsonl 2>/dev/null | wc -l)"
[ "$COUNT" -ge 5 ] || die "只导出了 $COUNT 张表，太少了，八成没导成"
ok "$COUNT 张表已导出（$(du -sh "$OUT/tables" | cut -f1)）"

# ---------------------------------------------------------------- 3 文件
step "[3/5] 导出题目配图与导入原件..."
if [ -d "$ROOT/data/uploads" ] && [ -n "$(ls -A "$ROOT/data/uploads" 2>/dev/null)" ]; then
    tar czf "$OUT/uploads.tar.gz" -C "$ROOT/data" uploads || die "打包 uploads 失败"
    ok "配图已打包（$(du -h "$OUT/uploads.tar.gz" | cut -f1)）"
else
    tar czf "$OUT/uploads.tar.gz" -C "$ROOT" --files-from /dev/null || die "建空包失败"
    warn "uploads 目录是空的，打了个空包"
fi

# ---------------------------------------------------------------- 4 配置
step "[4/5] 导出配置..."
cp "$ROOT/config.yaml" "$OUT/config.yaml" || die "复制 config.yaml 失败"
ok "config.yaml 已导出"

# 只导非机密的部署设置。口令一概不导 —— 新机器用它自己那套。
{
    echo "# 从 $(hostname) 于 $(date '+%F %T') 导出"
    echo "# 只有部署设置，**没有任何口令**。还原时可选择性套用。"
    grep -E '^[[:space:]]*(REGISTRY|WEB_PORT|CORS_ORIGINS|PUBLIC_BASE_URL)[[:space:]]*=' \
        "$ROOT/.env" 2>/dev/null
} > "$OUT/settings.env"
ok "端口和对外地址已导出到 settings.env（不含口令）"

# ---------------------------------------------------------------- 5 清单
step "[5/5] 生成清单..."
{
    echo "昌邑市实验中学信息科技教学平台 —— 数据导出清单"
    echo "导出时间 : $(date '+%F %T')"
    echo "来源主机 : $(hostname)"
    echo
    echo "--- 各表行数（还原后拿这个核对）---"
    docker compose exec -T backend python -c "
import json, sys
meta = json.load(open('/dev/stdin', encoding='utf-8'))
for name, info in sorted(meta['表'].items()):
    print(f\"{name}={info['行数']}\")
" < "$OUT/meta.json" 2>/dev/null || python3 -c "
import json
meta = json.load(open('$OUT/meta.json', encoding='utf-8'))
for name, info in sorted(meta['表'].items()):
    print(f\"{name}={info['行数']}\")
"
} > "$OUT/MANIFEST.txt"
ok "清单已生成"

echo
echo "=================================================="
echo "  导出完成：$OUT"
du -sh "$OUT" | sed 's/^/  总大小：/'
echo
echo "  还原到别的机器："
echo "    1. 那台机器上先正常部署好（git clone + ./deploy.sh），确认能打开"
echo "    2. 把整个 $(basename "$OUT") 目录拷过去"
echo "    3. sudo bash scripts/data-import.sh /路径/$(basename "$OUT")"
echo
echo "  这份备份**不含口令**，新机器沿用它自己的 .env，不会再出现口令对不上。"
echo "=================================================="
