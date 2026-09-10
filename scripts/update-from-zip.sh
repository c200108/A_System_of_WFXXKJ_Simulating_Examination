#!/usr/bin/env bash
# 用下载的 ZIP 更新部署（服务器连不上 GitHub 时用这个）。
#
#   sudo bash scripts/update-from-zip.sh ~/新下载的.zip
#
# 为什么要脚本：手工「删旧目录 → 解压新的」有三个必踩的坑 ——
#   1. .env 跟着旧目录一起没了。里面的数据库口令是卷初始化时定死的，
#      重新生成一份新的，后端就连不上库了；
#   2. data/uploads/ 里的题目配图一起没了，题目还在但图裂了；
#   3. GitHub 的 ZIP 解压出来带 -main 后缀，目录名一变，compose 的项目名
#      和数据卷名跟着变，数据库看起来就"空了"。
#      （这条现在由 docker-compose.yml 里的 name: exam-system 兜住了）
#
# 本脚本把这三件事都接管掉：先备份，替换目录，再把配置和上传目录还回去。

set -uo pipefail

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YEL='\033[33m'; C_RED='\033[31m'; C_OFF='\033[0m'
step() { printf "\n${C_CYAN}%s${C_OFF}\n" "$1"; }
ok()   { printf "      ${C_GREEN}%s${C_OFF}\n" "$1"; }
warn() { printf "      ${C_YEL}%s${C_OFF}\n" "$1"; }
die()  { printf "\n${C_RED}[失败] %s${C_OFF}\n\n" "$1"; exit 1; }

ZIP="${1:-}"
# 部署目录固定不变。目录名一直保持一致，是这套流程能重复跑的前提。
TARGET="${EXAM_DIR:-/opt/exam-system}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="/opt/exam-backups"

[ "$(id -u)" = "0" ] || die "需要 root：sudo bash $0 <zip文件>"
[ -n "$ZIP" ] || die "用法：sudo bash $0 ~/下载的.zip"
[ -f "$ZIP" ] || die "找不到文件：$ZIP"
command -v unzip >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq unzip; }

echo "=================================================="
echo "   从 ZIP 更新部署"
echo "=================================================="
echo "  目标目录：$TARGET"
echo "  ZIP 文件：$ZIP"

# ---------------------------------------------------------------- 1 备份
step "[1/5] 备份现有配置与数据..."
mkdir -p "$BACKUP_DIR"

HAS_OLD=0
if [ -d "$TARGET" ]; then
    HAS_OLD=1
    [ -f "$TARGET/.env" ] || die "$TARGET 下没有 .env，这不像是有效的部署目录。
      确认 EXAM_DIR 指对了，或首次部署请直接用 deploy.sh。"

    cp "$TARGET/.env" "$BACKUP_DIR/env-$STAMP"
    ok "已备份 .env → $BACKUP_DIR/env-$STAMP"

    if [ -d "$TARGET/data/uploads" ]; then
        tar czf "$BACKUP_DIR/uploads-$STAMP.tar.gz" -C "$TARGET/data" uploads
        ok "已备份 data/uploads → $BACKUP_DIR/uploads-$STAMP.tar.gz"
    fi

    # config.yaml 只备份、不还原：新版本常会加字段（比如 site、typing.time_limits），
    # 把旧文件盖回去反而会缺键或触发启动校验。留一份是为了让你能 diff 出自己改过什么。
    if [ -f "$TARGET/config.yaml" ]; then
        cp "$TARGET/config.yaml" "$BACKUP_DIR/config-$STAMP.yaml"
        ok "已备份 config.yaml → $BACKUP_DIR/config-$STAMP.yaml"
    fi

    # 数据库在 docker 卷里，不在目录中，本身不受影响；但升级前留一份更稳妥。
    # 用 ps -q 判断而不是 grep "Up"：compose 各版本的 STATUS 文案不一样
    # （有的写 Up 2 hours，有的写 running），按文案匹配迟早会漏判。
    if [ -n "$(docker compose -f "$TARGET/docker-compose.yml" ps -q db 2>/dev/null)" ]; then
        if bash "$TARGET/backup/backup.sh" >/dev/null 2>&1; then
            # backup.sh 把产物写在 $TARGET/backup/ 下，而 $TARGET 待会儿要被改名，
            # 最后又会提示你删掉旧目录 —— 不搬出来的话，这份库备份会跟着一起没。
            DUMP="$(find "$TARGET/backup" -name 'db_*.sql.gz' -newermt '-10 minutes' | sort | tail -1)"
            if [ -n "$DUMP" ]; then
                cp "$DUMP" "$BACKUP_DIR/db-$STAMP.sql.gz"
                ok "数据库已备份 → $BACKUP_DIR/db-$STAMP.sql.gz（$(du -h "$BACKUP_DIR/db-$STAMP.sql.gz" | cut -f1)）"
            else
                warn "备份跑完了但没找到 db_*.sql.gz，请手工确认 $TARGET/backup/"
            fi
        else
            warn "数据库备份没成功，继续更新（数据在 docker 卷里，不会被本脚本删掉）"
            warn "但没有备份就更新是有风险的，介意的话现在 Ctrl+C，手工跑一次 backup/backup.sh"
        fi
    else
        warn "db 容器没在运行，跳过数据库备份（数据仍在 docker 卷里，不受影响）"
    fi
else
    warn "$TARGET 不存在，按首次部署处理"
fi

# ---------------------------------------------------------------- 2 解压
step "[2/5] 解压新版本..."
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
unzip -q "$ZIP" -d "$TMP" || die "解压失败，文件可能不完整"

# GitHub 的 ZIP 会多一层 xxx-main/，自动往里找到真正的项目根
SRC="$TMP"
if [ ! -f "$SRC/docker-compose.yml" ]; then
    SRC="$(find "$TMP" -maxdepth 2 -name docker-compose.yml -printf '%h\n' | head -1)"
fi
[ -n "$SRC" ] && [ -f "$SRC/docker-compose.yml" ] || die "ZIP 里找不到 docker-compose.yml，确认下载的是项目仓库"
ok "项目根：${SRC#$TMP/}"

# ---------------------------------------------------------------- 3 替换
step "[3/5] 替换目录..."
if [ "$HAS_OLD" = 1 ]; then
    mv "$TARGET" "$TARGET.old-$STAMP" || die "旧目录改名失败，什么都没动，原样还在 $TARGET"
    ok "旧目录改名为 $(basename "$TARGET.old-$STAMP")（确认没问题后可删）"
fi
# 这一步失败最要命：旧目录已经改名，新的又没放上去。所以失败就地回滚。
if ! mv "$SRC" "$TARGET"; then
    if [ "$HAS_OLD" = 1 ]; then
        mv "$TARGET.old-$STAMP" "$TARGET" && warn "已回滚到旧版本"
    fi
    die "新目录就位失败（$SRC → $TARGET）"
fi

# ---------------------------------------------------------------- 4 还原
step "[4/5] 还原配置与上传目录..."
if [ "$HAS_OLD" = 1 ]; then
    cp "$BACKUP_DIR/env-$STAMP" "$TARGET/.env"
    chmod 600 "$TARGET/.env"
    ok ".env 已还原（数据库口令保持不变，能连上原来的库）"

    if [ -d "$TARGET.old-$STAMP/data/uploads" ]; then
        mkdir -p "$TARGET/data"
        cp -r "$TARGET.old-$STAMP/data/uploads" "$TARGET/data/"
        ok "题目配图与导入原件已还原（$(find "$TARGET/data/uploads" -type f | wc -l) 个文件）"
    fi

    # config.yaml 用的是新版本那份。如果你在服务器上改过它（平台名称、
    # 知识范围、打字文本……），这里把差异指出来，别让改动无声无息地没掉。
    if ! diff -q "$BACKUP_DIR/config-$STAMP.yaml" "$TARGET/config.yaml" >/dev/null 2>&1; then
        warn "config.yaml 和你原来那份不一样，已改用新版本的。"
        warn "  想看差在哪：diff $BACKUP_DIR/config-$STAMP.yaml $TARGET/config.yaml"
        warn "  确认后把自己的改动手工挪回去，然后 docker compose restart backend"
    fi
else
    warn "首次部署：稍后 deploy.sh 会引导你生成 .env"
fi

# ---------------------------------------------------------------- 5 重建
step "[5/5] 重新构建并启动..."
cd "$TARGET" || die "进不去 $TARGET"
chmod +x deploy.sh scripts/*.sh backup/*.sh 2>/dev/null || true
bash deploy.sh

echo
echo "=================================================="
echo "  更新完成"
echo
echo "  旧目录：$TARGET.old-$STAMP"
echo "  确认新版本一切正常后再删：sudo rm -rf $TARGET.old-$STAMP"
echo
echo "  备份（在 $TARGET 之外，删旧目录不影响）："
ls -1sh "$BACKUP_DIR"/*-"$STAMP"* 2>/dev/null | sed 's/^/    /'
echo
echo "  题库、成绩、账号都在 docker 卷 exam-system_db_data 里，本次没动过。"
echo "  验一下：题库页题目数、考试页成绩条数和更新前对得上就没问题。"
echo "=================================================="
