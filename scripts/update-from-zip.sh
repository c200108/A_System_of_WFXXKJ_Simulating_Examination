#!/usr/bin/env bash
# 用 GitHub 下载的 ZIP 原地升级服务器上的部署：数据不丢，数据库容器不停。
#
#   sudo bash scripts/update-from-zip.sh ~/A_System_of_WFXXKJ_Simulating_Examination-main.zip
#
# ZIP 就是 GitHub 仓库页 Code → Download ZIP 下来的那个，不用解压，直接给路径。
# 部署目录自动找（正在跑的 exam-system 容器记着它的目录），找不到用 /opt/exam-system；
# 要指定就 EXAM_DIR=/你的/目录 sudo -E bash scripts/update-from-zip.sh xxx.zip
#
# ---------------------------------------------------------------- 怎么做到的
# 数据在哪、怎么护着：
#   题库/成绩/账号/回收站   Docker 卷 exam-system_db_data   —— 不在目录里，本脚本根本不碰
#   配图/座次表/导入原件    data/uploads（挂进后端容器）    —— 同步时跳过，原地不动
#   数据库口令等            .env                            —— 同步时跳过，原地不动
#   平台名称、校徽等配置    config.yaml                     —— 原地不动，新版本多的配置项最后合进去
#
# 步骤：
#   1. 先备份（数据库在线导出，不停库）；
#   2. 解压到临时目录，**原地覆盖**代码（rsync，跳过上面那几样；新版本删掉的旧文件一并删掉）。
#      不能「旧目录改名、新目录放进去」：容器按路径挂着 data/uploads 和 config.yaml，
#      目录一换，正在跑的容器还连着旧目录，这期间老师上传的图片就落进旧目录、找不回来了；
#   3. 旧容器照常服务的同时构建新镜像 —— 构建失败就把代码还原成原样，线上一秒都不受影响；
#   4. 构建好了才 up -d：只换代码变了的后端、前端，数据库容器不重启。
#      网页会有十几秒打不开（新后端启动、自动跑数据库迁移），避开考试时段；
#   5. 等健康检查通过，再把 config.yaml 合上新版本多出来的配置项。
#
# 绝对不要 docker compose down -v —— 那是唯一会删掉数据库卷的命令。

set -uo pipefail

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YEL='\033[33m'; C_RED='\033[31m'; C_OFF='\033[0m'
step() { printf "\n${C_CYAN}%s${C_OFF}\n" "$1"; }
ok()   { printf "      ${C_GREEN}%s${C_OFF}\n" "$1"; }
warn() { printf "      ${C_YEL}%s${C_OFF}\n" "$1"; }
die()  { printf "\n${C_RED}[失败] %s${C_OFF}\n\n" "$1"; exit 1; }

ZIP="${1:-}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${EXAM_BACKUP_DIR:-/opt/exam-backups}"

[ "$(id -u)" = "0" ] || die "需要 root：sudo bash $0 <zip文件>"
[ -n "$ZIP" ] || die "用法：sudo bash $0 ~/下载的.zip"
[ -f "$ZIP" ] || die "找不到文件：$ZIP"
ZIP="$(cd "$(dirname "$ZIP")" && pwd)/$(basename "$ZIP")"
command -v unzip >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq unzip; }
command -v rsync >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq rsync; }
command -v rsync >/dev/null 2>&1 || die "装不上 rsync，手工装一下：apt-get install -y rsync"
docker compose version >/dev/null 2>&1 || die "缺少 docker compose 插件（v2）"

# ---------------------------------------------------------------- 找部署目录
# 正在跑的后端容器上记着 compose 项目目录 —— 比猜路径靠谱，目录叫什么都找得到
if [ -n "${EXAM_DIR:-}" ]; then
    TARGET="$EXAM_DIR"
else
    TARGET="$(docker inspect exam-system-backend-1 \
        --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' 2>/dev/null)"
    [ -n "$TARGET" ] && [ -f "$TARGET/docker-compose.yml" ] || TARGET="/opt/exam-system"
fi
TARGET="${TARGET%/}"

echo "=================================================="
echo "   从 ZIP 原地升级（数据库不停）"
echo "=================================================="
echo "  部署目录：$TARGET"
echo "  ZIP 文件：$ZIP"
echo "  备份目录：$BACKUP_DIR"

# 同步代码时**不碰**的东西：服务器自己的数据、口令、配置、备份产物、本地加的文件。
# 这几样在哪一层都跳过（仓库里没有叫 data 的目录，不会误伤代码）
PROTECT=(
    --exclude=.env
    --exclude=data/
    --exclude=/config.yaml
    --exclude=/exam-data/
    --exclude=*.sql
    --exclude=*.sql.gz
    --exclude=*.tar.gz
    --exclude=/backup/*.json
    --exclude=/.git/
    --exclude=/docker-compose.override.yml
    --exclude=/desktop/发布/
    --exclude=/desktop/build/
    --exclude=node_modules/
    --exclude=__pycache__/
)
# 「新版本里删掉的旧文件也跟着删」只在这些代码目录里做；部署目录最外层只覆盖、不删，
# 免得把你自己放在那儿的东西（.env.bak、笔记、别的脚本）删了
CODE_DIRS=(backend frontend scripts docs legacy desktop android backup)
# 旧代码打包备份时跳过的（tar 的写法）
TAR_SKIP=(--exclude=./.env --exclude=./data --exclude=./exam-data --exclude=./.git
          --exclude='*.sql' --exclude='*.sql.gz' --exclude='*.tar.gz' --exclude=node_modules
          --exclude=__pycache__ --exclude='./desktop/发布' --exclude='./desktop/build')

# ---------------------------------------------------------------- 首次部署：没有旧目录
if [ ! -f "$TARGET/docker-compose.yml" ]; then
    [ -e "$TARGET" ] && [ -n "$(ls -A "$TARGET" 2>/dev/null)" ] && \
        die "$TARGET 存在但不像部署目录（没有 docker-compose.yml），不敢动。确认 EXAM_DIR 指对了。"
    warn "$TARGET 还没有部署，按首次部署处理"
    TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
    unzip -q "$ZIP" -d "$TMP" || die "解压失败，文件可能不完整"
    SRC="$(find "$TMP" -maxdepth 2 -name docker-compose.yml -printf '%h\n' | head -1)"
    [ -n "$SRC" ] || die "ZIP 里找不到 docker-compose.yml，确认下载的是项目仓库"
    mkdir -p "$TARGET" && rsync -a "$SRC/" "$TARGET/" || die "复制失败"
    rm -rf "$TMP"; trap - EXIT
    cd "$TARGET" && chmod +x deploy.sh scripts/*.sh backup/*.sh 2>/dev/null
    exec bash deploy.sh
fi
[ -f "$TARGET/.env" ] || die "$TARGET 下没有 .env，这不像是正在用的部署目录。"
cd "$TARGET" || die "进不去 $TARGET"

# ---------------------------------------------------------------- 1 备份
step "[1/6] 备份（数据库在线导出，不停库）..."
mkdir -p "$BACKUP_DIR"
cp .env "$BACKUP_DIR/env-$STAMP" && chmod 600 "$BACKUP_DIR/env-$STAMP"
ok ".env → $BACKUP_DIR/env-$STAMP"
cp config.yaml "$BACKUP_DIR/config-$STAMP.yaml" 2>/dev/null && ok "config.yaml → $BACKUP_DIR/config-$STAMP.yaml"
if [ -d data/uploads ]; then
    tar czf "$BACKUP_DIR/uploads-$STAMP.tar.gz" -C data uploads && \
        ok "data/uploads → $BACKUP_DIR/uploads-$STAMP.tar.gz（$(find data/uploads -type f | wc -l) 个文件）"
fi
# 旧代码也留一份：新版本构建失败时原样还原，目录和正在跑的容器保持一致
tar czf "$BACKUP_DIR/code-$STAMP.tar.gz" "${TAR_SKIP[@]}" . 2>/dev/null \
    && ok "旧代码 → $BACKUP_DIR/code-$STAMP.tar.gz（升级失败时用来还原）" \
    || die "旧代码备份失败，什么都还没动"

if [ -n "$(docker compose ps -q db 2>/dev/null)" ]; then
    if bash backup/backup.sh >/dev/null 2>&1; then
        DUMP="$(find backup -name 'db_*.sql.gz' -newermt '-10 minutes' | sort | tail -1)"
        if [ -n "$DUMP" ]; then
            cp "$DUMP" "$BACKUP_DIR/db-$STAMP.sql.gz"
            ok "数据库 → $BACKUP_DIR/db-$STAMP.sql.gz（$(du -h "$BACKUP_DIR/db-$STAMP.sql.gz" | cut -f1)）"
        else
            warn "备份跑完了但没找到 db_*.sql.gz，请手工确认 $TARGET/backup/"
        fi
    else
        warn "数据库导出没成功（数据仍在 Docker 卷里，本脚本不会碰它）"
        warn "介意的话现在 Ctrl+C，手工跑一次 backup/backup.sh 看看原因；10 秒后继续"
        sleep 10
    fi
else
    warn "db 容器没在运行，跳过数据库导出（数据仍在 Docker 卷里，不受影响）"
fi

# 数据对账用：升级前后题目数、成绩数要对得上
count() {
    docker compose exec -T db sh -c \
        'mysql -N -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "'"$1"'" 2>/dev/null' 2>/dev/null | tr -d '\r'
}
BEFORE_Q="$(count 'SELECT COUNT(*) FROM questions')"
BEFORE_S="$(count 'SELECT COUNT(*) FROM exam_submissions')"
BEFORE_T="$(count 'SELECT COUNT(*) FROM typing_records')"
[ -n "$BEFORE_Q" ] && ok "升级前：题目 $BEFORE_Q，答卷 $BEFORE_S，打字成绩 $BEFORE_T"

# ---------------------------------------------------------------- 2 解压
step "[2/6] 解压新版本..."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
unzip -q "$ZIP" -d "$TMP" || die "解压失败，文件可能不完整（什么都还没动）"
# GitHub 的 ZIP 外面多一层 xxx-main/，往里找真正的项目根
SRC="$(find "$TMP" -maxdepth 2 -name docker-compose.yml -printf '%h\n' | head -1)"
[ -n "$SRC" ] && [ -f "$SRC/backend/Dockerfile" ] || die "ZIP 里找不到项目（docker-compose.yml / backend），确认下载的是在线版仓库"
[ -f "$SRC/scripts/update-from-zip.sh" ] || warn "这个 ZIP 里没有升级脚本，像是很老的版本，确认没下错"
cp "$SRC/config.yaml" "$BACKUP_DIR/config-new-$STAMP.yaml" 2>/dev/null
ok "项目根：${SRC#$TMP/}"

# ---------------------------------------------------------------- 3 原地覆盖代码
step "[3/6] 原地覆盖代码（.env、data/、config.yaml、备份文件原地不动）..."
SYNC_LOG="$TMP/rsync.log"
sync_code() {   # $1 = 新代码根目录
    local from="$1" rc=0 d
    : > "$SYNC_LOG"
    # 最外层：只覆盖，不删
    # -c 按内容比：只有内容真变了的才算「更新」，时间戳不同不算
    rsync -ac --itemize-changes "${PROTECT[@]}" "${CODE_DIRS[@]/#/--exclude=/}" \
        "$from/" "$TARGET/" >> "$SYNC_LOG" || rc=1
    # 代码目录：新版本删掉的文件一起删
    for d in "${CODE_DIRS[@]}"; do
        [ -d "$from/$d" ] || continue
        mkdir -p "$TARGET/$d"
        # 上面那几条带 / 开头的规则是从部署目录算的，进了子目录要按子目录再写一遍
        local extra=()
        [ "$d" = desktop ] && extra=(--exclude=/发布/ --exclude=/build/)
        [ "$d" = backup ] && extra=(--exclude=/*.json)
        rsync -ac --delete --itemize-changes "${PROTECT[@]}" ${extra[@]+"${extra[@]}"} \
            "$from/$d/" "$TARGET/$d/" >> "$SYNC_LOG" || rc=1
    done
    return $rc
}
sync_code "$SRC" || { rollback_code_now=1; }
if [ "${rollback_code_now:-0}" = 1 ]; then
    tar xzf "$BACKUP_DIR/code-$STAMP.tar.gz" -C "$TARGET" 2>/dev/null
    die "覆盖代码出错，已把旧代码解回去。旧代码备份：$BACKUP_DIR/code-$STAMP.tar.gz"
fi
# 只数文件（>f 新增/改了内容，*deleting 删掉的），目录不算
CHANGED="$(grep -cE '^(>f|\*deleting)' "$SYNC_LOG" || true)"
chmod +x deploy.sh scripts/*.sh backup/*.sh 2>/dev/null || true
ok "更新了 ${CHANGED:-0} 处文件（容器还在用旧版本照常服务）"

rollback_code() {
    warn "把代码还原成升级前的样子..."
    # 解开旧代码，再用它同步一遍：新版本新加的文件也一并删掉
    local OLD="$TMP/old-code"
    mkdir -p "$OLD"
    if tar xzf "$BACKUP_DIR/code-$STAMP.tar.gz" -C "$OLD" && sync_code "$OLD"; then
        ok "代码已还原，和正在跑的旧容器一致"
    else
        warn "自动还原没成功，手工还原：cd $TARGET && tar xzf $BACKUP_DIR/code-$STAMP.tar.gz"
    fi
}

# ---------------------------------------------------------------- 4 构建（旧容器照常服务）
step "[4/6] 构建新镜像（几分钟；这期间网站照常能用）..."
BUILT=0
for i in 1 2 3; do
    docker compose build 2>&1 | sed 's/^/        /'
    [ "${PIPESTATUS[0]}" = 0 ] && { BUILT=1; break; }
    [ "$i" -lt 3 ] && { warn "第 $i 次构建没成功，10 秒后重试"; sleep 10; }
done
if [ "$BUILT" != 1 ]; then
    rollback_code
    die "新版本构建失败（试了 3 次），线上还是旧版本、没受影响。
      国内服务器多半是拉不动镜像：sudo bash scripts/setup-docker-cn.sh 换个加速站再来。"
fi
ok "新镜像构建好了"

# ---------------------------------------------------------------- 5 切换（数据库不重启）
step "[5/6] 切换到新版本（网页会有十几秒打不开）..."
DB_BEFORE="$(docker compose ps -q db 2>/dev/null)"
docker compose up -d 2>&1 | sed 's/^/        /'
DB_AFTER="$(docker compose ps -q db 2>/dev/null)"
if [ -n "$DB_BEFORE" ] && [ "$DB_BEFORE" = "$DB_AFTER" ]; then
    ok "数据库容器没动（同一个容器，一直在跑）"
elif [ -n "$DB_BEFORE" ]; then
    warn "新版本改了数据库容器的配置，数据库容器重建了一次（数据在卷里，不受影响）"
fi

READY=0
for i in $(seq 1 60); do
    sleep 3
    STATE="$(docker compose ps --format '{{.Service}}={{.Health}}' 2>/dev/null | tr '\n' ' ')"
    case "$STATE" in *backend=healthy*) READY=1; break;; esac
    [ $((i % 5)) -eq 0 ] && echo "      新后端启动中（自动升级数据库结构）... $((i*3)) 秒  $STATE"
done
if [ "$READY" != 1 ]; then
    echo; echo "      新后端没起来，最后 30 行日志："
    docker compose logs backend --tail=30 2>&1 | sed 's/^/        /'
    die "新版本没起来。数据都在（数据库卷、data/uploads 都没动过）。
      退回旧版本（数据库结构的升级只加不删，旧版本照样能用）：
        cd $TARGET && tar xzf $BACKUP_DIR/code-$STAMP.tar.gz && docker compose up -d --build
      把上面的日志发给维护者。"
fi
ok "新后端健康检查通过，数据库结构已自动升级"

# ---------------------------------------------------------------- 6 合并配置、对账
step "[6/6] 合并 config.yaml、核对数据..."
# 你改过的值（平台名称、校徽、卷面结构……）全留着，新版本多出来的配置项连说明一起补进去。
# 合并工具在新版本的容器里：新版本那份 config.yaml 从标准输入喂进去
if [ -f "$BACKUP_DIR/config-new-$STAMP.yaml" ]; then
    MERGED="$(mktemp)"; MLOG="$(mktemp)"
    if docker compose exec -T backend sh -c \
            'cat > /tmp/config-new.yaml && python -m tools.merge_config /app/config.yaml /tmp/config-new.yaml' \
            < "$BACKUP_DIR/config-new-$STAMP.yaml" > "$MERGED" 2> "$MLOG" && [ -s "$MERGED" ]; then
        if ! cmp -s "$MERGED" config.yaml; then
            # 写回原文件而不是 mv：config.yaml 是单文件挂进容器的，换了 inode 容器里就看不见了
            cat "$MERGED" > config.yaml
            docker compose restart backend >/dev/null 2>&1
            ok "config.yaml：你原来的配置全部保留。$(tail -n 1 "$MLOG")（后端重启了一下）"
        else
            ok "config.yaml：没有新的配置项，原样保留"
        fi
    else
        warn "config.yaml 没合并成功，继续用你原来那份（程序对新配置项用默认值，照常能跑）"
        warn "  $(tail -n 1 "$MLOG")"
        warn "  新版本那份在 $BACKUP_DIR/config-new-$STAMP.yaml，需要时 diff 一下手工挪"
    fi
    rm -f "$MERGED" "$MLOG"
fi

AFTER_Q="$(count 'SELECT COUNT(*) FROM questions')"
AFTER_S="$(count 'SELECT COUNT(*) FROM exam_submissions')"
AFTER_T="$(count 'SELECT COUNT(*) FROM typing_records')"
if [ -n "$BEFORE_Q" ]; then
    if [ "$BEFORE_Q" = "$AFTER_Q" ] && [ "$BEFORE_S" = "$AFTER_S" ] && [ "$BEFORE_T" = "$AFTER_T" ]; then
        ok "数据对上了：题目 $AFTER_Q，答卷 $AFTER_S，打字成绩 $AFTER_T"
    else
        warn "数据条数有变化：题目 $BEFORE_Q→$AFTER_Q，答卷 $BEFORE_S→$AFTER_S，打字成绩 $BEFORE_T→$AFTER_T"
        warn "（升级期间正好有人交卷/练字会多出几条，是正常的；变少了就把 $BACKUP_DIR/db-$STAMP.sql.gz 留好，联系维护者）"
    fi
fi
[ -d data/uploads ] && ok "上传文件 $(find data/uploads -type f | wc -l) 个，原地没动"

echo
echo "=================================================="
echo "  升级完成"
echo
echo "  这次的备份（都在 $BACKUP_DIR，和部署目录分开）："
ls -1sh "$BACKUP_DIR"/*-"$STAMP"* 2>/dev/null | sed 's/^/    /'
echo
echo "  确认一两天没问题后可以清理：sudo rm $BACKUP_DIR/*-$STAMP*"
echo "=================================================="
