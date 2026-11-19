#!/usr/bin/env bash
# 主机助手：替网页做「导入备份」「一键更新」这两件**只能在宿主机上做**的事。
#
# 不用手工跑。scripts/host-agent-install.sh 把它装成 systemd 服务：
# 网页（后端容器）在 data/host-jobs/queue/ 放一张单子，systemd 马上拉起本脚本接单。
#
# 只认三种动作，单子里的内容只当数据用：
#
#   import         导入 exam-data：DATA_IMPORT_YES=1 bash scripts/data-import.sh <任务目录>/exam-data，
#                  再重建后端、前端容器（网站会有一小会儿打不开）
#   update-github  一键更新：**先比版本**（GitHub 上 main 的提交号 / 更新日志里的版本号和本机的比），
#                  已经是最新就到此为止、不下载；不是最新才从 GitHub 下载 main 压缩包到任务目录，
#                  然后照手工升级的三步走 ——
#                    cd 到 zip 所在目录
#                    unzip -p <zip> '*/scripts/update-from-zip.sh' > u.sh
#                    bash u.sh <zip>
#   update-zip     同上，只是 zip 是网页上传的
#
# **压缩包文件名不写死**：下载的按 GitHub 给的名字存（一般是
# A_System_of_WFXXKJ_Simulating_Examination-main.zip），上传的按原文件名存；
# 执行时在任务目录里找那个 .zip，叫什么都行。
#
# 进度和完整输出写回任务目录（status.json、log.txt），网页隔几秒读一次。
# 一次只做一件：flock 锁着，两个升级同时跑会把代码目录搅乱。

set -uo pipefail

# systemd 拉起的服务没有 HOME 这个环境变量：git 于是读不到 /root/.gitconfig 里 setup-github-cn.sh
# 配的加速（url.<加速地址>.insteadOf），问 GitHub 提交号的 git ls-remote 只好直连 github.com，
# 国内服务器连不上 → 每次都「查不到 GitHub 上的版本，照常下载更新」（下载那步自己读配置文件，所以照样下得下来）。
# 命令行里手动跑 git 有 HOME，所以 clone 一直是好的。（2.24.0）
if [ -z "${HOME:-}" ]; then
    HOME="$(getent passwd "$(id -u)" 2>/dev/null | cut -d: -f6)"
    export HOME="${HOME:-/root}"
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOBS="$ROOT/data/host-jobs"
QUEUE="$JOBS/queue"
REPO_ZIP_URL="${UPDATE_ZIP_URL:-https://github.com/c200108/A_System_of_WFXXKJ_Simulating_Examination/archive/refs/heads/main.zip}"
REPO_GIT_URL="${UPDATE_GIT_URL:-https://github.com/c200108/A_System_of_WFXXKJ_Simulating_Examination.git}"
REPO_API_URL="${UPDATE_API_URL:-https://api.github.com/repos/c200108/A_System_of_WFXXKJ_Simulating_Examination/commits/main}"
REPO_SEED_URL="${UPDATE_SEED_URL:-https://raw.githubusercontent.com/c200108/A_System_of_WFXXKJ_Simulating_Examination/main/backend/app/changelog_seed.py}"
# 本机现在跑的是哪个提交：每次升级成功后从压缩包注释里取出来记在这里（GitHub 的压缩包注释就是提交号）
DEPLOYED="$JOBS/deployed-commit"

[ "$(id -u)" = "0" ] || { echo "主机助手要用 root 跑（由 systemd 拉起）"; exit 1; }
mkdir -p "$QUEUE" "$JOBS/jobs"

exec 9> "$JOBS/agent.lock"
flock -n 9 || exit 0          # 已经有一个在干活了，它干完会再看一遍队列

now() { date '+%F %T'; }

write_status() {   # $1 目录 $2 状态 $3 说明 $4 开始时间 $5 结束时间
    local msg="${3//\\/\\\\}"; msg="${msg//\"/\\\"}"
    printf '{"status": "%s", "message": "%s", "started_at": "%s", "finished_at": "%s"}\n' \
        "$2" "$msg" "$4" "${5:-}" > "$1/status.json.tmp" && mv -f "$1/status.json.tmp" "$1/status.json"
}

wait_healthy() {
    local i state
    for i in $(seq 1 60); do
        sleep 3
        state="$(docker compose ps --format '{{.Service}}={{.Health}}' 2>/dev/null | tr '\n' ' ')"
        case "$state" in *backend=healthy*) echo "      后端已就绪：$state"; return 0;; esac
        [ $((i % 5)) -eq 0 ] && echo "      等后端启动... $((i*3)) 秒  $state"
    done
    return 1
}

# ---------------------------------------------------------------- 动作
do_import() {   # $1 任务目录
    local src="$1/exam-data"
    [ -s "$src/meta.json" ] || { echo "任务目录里没有 exam-data/meta.json"; return 1; }
    cd "$ROOT" || return 1
    DATA_IMPORT_YES=1 bash "$ROOT/scripts/data-import.sh" "$src" || return 1
    echo
    echo "== 重建容器（网站会有一小会儿打不开）=="
    docker compose up -d --force-recreate backend frontend 2>&1 | sed 's/^/      /'
    wait_healthy || { docker compose logs backend --tail=30 2>&1 | sed 's/^/      /'; return 1; }
}

# 宿主机配过 GitHub 加速（setup-github-cn.sh 写的 git insteadOf）就顺着用
mirror_urls() {
    local cfg line from to
    for cfg in /root/.gitconfig /etc/gitconfig /home/*/.gitconfig; do
        [ -f "$cfg" ] || continue
        git config -f "$cfg" --get-regexp '^url\..*\.insteadof$' 2>/dev/null | while read -r line from; do
            to="${line#url.}"; to="${to%.insteadof}"; to="${to%.insteadOf}"
            case "$REPO_ZIP_URL" in "$from"*) echo "${to}${REPO_ZIP_URL#"$from"}";; esac
        done
    done
}

# ---------------------------------------------------------------- 先比版本
# 更新日志里的全部版本号（排好序的一串），本机代码和 GitHub 上的各取一份比
seed_versions() { grep -oE '^        "[0-9]+\.[0-9]+\.[0-9]+",$' | tr -d ' ",' | sort -u | tr '\n' ' '; }
server_version() { tr ' ' '\n' | grep -E '^2\.' | sort -t. -k1,1n -k2,2n -k3,3n | tail -1; }

remote_commit() {   # GitHub 上 main 的提交号；git 会顺着 setup-github-cn.sh 配的加速走
    local sha=""
    if command -v git >/dev/null 2>&1; then
        sha="$(timeout 40 git ls-remote "$REPO_GIT_URL" refs/heads/main 2>/dev/null | cut -c1-40)"
    fi
    if [ -z "$sha" ]; then
        sha="$(curl -fsS --connect-timeout 15 --max-time 30 -H 'Accept: application/vnd.github.sha' "$REPO_API_URL" 2>/dev/null | head -c 40)"
    fi
    case "$sha" in *[!0-9a-f]*|"") echo "";; *) echo "$sha";; esac
}

remote_versions() {
    local url
    for url in "$REPO_SEED_URL" $(REPO_ZIP_URL="$REPO_SEED_URL" mirror_seed_urls | sort -u); do
        # 先存下来再判：写成 curl | seed_versions 的话，curl 失败了管道照样「成功」，返回一个空串
        local body got
        body="$(curl -fsS --connect-timeout 15 --max-time 40 "$url" 2>/dev/null)" || continue
        got="$(echo "$body" | seed_versions)"
        [ -n "$got" ] && { echo "$got"; return 0; }
    done
    return 1
}

mirror_seed_urls() {   # raw.githubusercontent.com 也可能配了加速
    local cfg line from to
    for cfg in /root/.gitconfig /etc/gitconfig /home/*/.gitconfig; do
        [ -f "$cfg" ] || continue
        git config -f "$cfg" --get-regexp '^url\..*\.insteadof$' 2>/dev/null | while read -r line from; do
            to="${line#url.}"; to="${to%.insteadof}"; to="${to%.insteadOf}"
            case "$REPO_SEED_URL" in "$from"*) echo "${to}${REPO_SEED_URL#"$from"}";; esac
        done
    done
}

# 已经是最新返回 0（并在任务目录里留 uptodate 记号），不是最新或比不出来返回 1（接着下载升级）
check_latest() {   # $1 任务目录
    local local_sha remote_sha lv rv lsv rsv
    local_sha="$(head -c 40 "$DEPLOYED" 2>/dev/null)"
    lv="$(seed_versions < "$ROOT/backend/app/changelog_seed.py" 2>/dev/null)"
    lsv="$(echo "$lv" | server_version)"
    echo "== 先检查版本 =="
    echo "      本机：服务端 ${lsv:-?}${local_sha:+，提交 ${local_sha:0:7}}"
    remote_sha="$(remote_commit)"
    if [ -n "$remote_sha" ] && [ -n "$local_sha" ]; then
        echo "      GitHub：提交 ${remote_sha:0:7}"
        if [ "$remote_sha" = "$local_sha" ]; then
            echo "      已经是最新版本（提交号一致），不用下载更新。"
            printf '%s' "${lsv}" > "$1/uptodate"
            return 0
        fi
        echo "      有新提交，开始更新。"
        return 1
    fi
    # 本机还没记过提交号（这个功能之前升级的）或者问不到提交号：退回比更新日志里的版本号
    rv="$(remote_versions)" || rv=""
    rsv="$(echo "$rv" | server_version)"
    if [ -n "$rv" ] && [ -n "$lv" ]; then
        echo "      GitHub：服务端 ${rsv:-?}${remote_sha:+，提交 ${remote_sha:0:7}}"
        if [ "$rv" = "$lv" ]; then
            echo "      已经是最新版本（版本号一致），不用下载更新。"
            printf '%s' "${lsv}" > "$1/uptodate"
            [ -n "$remote_sha" ] && printf '%s\n' "$remote_sha" > "$DEPLOYED"
            return 0
        fi
        echo "      有新版本，开始更新。"
        return 1
    fi
    echo "      查不到 GitHub 上的版本，照常下载更新。"
    return 1
}

download_zip() {   # 在当前目录（任务目录）里下载，文件名用 GitHub 给的
    local url
    command -v curl >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq curl; }
    for url in "$REPO_ZIP_URL" $(mirror_urls | sort -u); do
        echo "      下载：$url"
        rm -f ./*.zip
        # -J 按服务器给的文件名存（GitHub 给的是 仓库名-main.zip）
        if curl -fL --retry 2 --connect-timeout 20 --max-time 900 -sS -O -J "$url"; then
            local got; got="$(ls -t ./*.zip 2>/dev/null | head -1)"
            if [ -n "$got" ] && unzip -tq "$got" >/dev/null 2>&1; then
                echo "      已下载：$(basename "$got")（$(du -h "$got" | cut -f1)）"
                return 0
            fi
            echo "      下下来的文件不完整，换一个地址"
        fi
    done
    echo "从 GitHub 下载失败。国内服务器可以先 sudo bash scripts/setup-github-cn.sh 配加速，"
    echo "或者在网页上改用「上传压缩包更新」：在自己电脑上下载 main 压缩包再传上来。"
    return 1
}

do_update() {   # $1 任务目录 $2 是否先下载（1/0）
    cd "$1" || return 1                         # 1. 进到 zip 所在的目录
    if [ "$2" = 1 ]; then
        check_latest "$1" && return 0
        download_zip || return 1
    fi
    local zip; zip="$(ls -t ./*.zip 2>/dev/null | head -1)"
    [ -n "$zip" ] || { echo "任务目录里找不到 .zip"; return 1; }
    zip="$(basename "$zip")"                    # 文件名不写死：下载的、上传的叫什么都行
    command -v unzip >/dev/null 2>&1 || { apt-get update -qq && apt-get install -y -qq unzip; }
    echo "      压缩包：$zip"
    # 2. 从 zip 里取出升级脚本，存成 u.sh
    unzip -p "$zip" '*/scripts/update-from-zip.sh' > u.sh
    [ -s u.sh ] || { echo "压缩包里没有 scripts/update-from-zip.sh，不是在线版项目的 main 压缩包"; return 1; }
    # 记下压缩包是哪个提交（GitHub 打的压缩包注释就是 40 位提交号），升级成功了写进 deployed-commit
    local sha; sha="$(unzip -z "$zip" 2>/dev/null | tail -n +2 | tr -cd '0-9a-f' | head -c 40)"
    # 3. 运行升级脚本（部署目录直接告诉它，不用它去猜）
    EXAM_DIR="$ROOT" bash u.sh "$zip" || return 1
    if [ "${#sha}" = 40 ]; then printf '%s\n' "$sha" > "$DEPLOYED"; else rm -f "$DEPLOYED"; fi
}

run_job() {   # $1 任务号 $2 动作
    local id="$1" action="$2" dir="$JOBS/jobs/$1" started rc
    [ -f "$dir/job.json" ] || return 0
    started="$(now)"
    write_status "$dir" running "正在执行" "$started"
    # 圆括号：子 shell 里 cd、exit 都不影响外面接着接单
    (
        echo "==== $(now) 开始：$action（任务 $id）===="
        case "$action" in
            import)        do_import "$dir" ;;
            update-github) do_update "$dir" 1 ;;
            update-zip)    do_update "$dir" 0 ;;
            *)             echo "不认识的动作：$action"; false ;;
        esac
        rc=$?
        echo
        echo "==== $(now) 结束，退出码 $rc ===="
        exit $rc
    ) >> "$dir/log.txt" 2>&1
    rc=$?
    if [ "$rc" = 0 ] && [ -f "$dir/uptodate" ]; then
        write_status "$dir" ok "已经是最新版本（服务端 $(cat "$dir/uptodate")），不用更新" "$started" "$(now)"
    elif [ "$rc" = 0 ]; then
        write_status "$dir" ok "完成" "$started" "$(now)"
    else
        write_status "$dir" failed "没做成，看日志最后几行" "$started" "$(now)"
    fi
    # 压缩包、解开的数据用完就删，任务目录只留单子和日志（备份另有 /opt/exam-backups 和回滚点）
    rm -rf "$dir/exam-data" "$dir"/*.zip "$dir/u.sh" 2>/dev/null
    # 只留最近 20 个任务
    ls -1d "$JOBS/jobs"/*/ 2>/dev/null | sort | head -n -20 | xargs -r rm -rf
}

# ---------------------------------------------------------------- 接单
while :; do
    q="$(ls -1A "$QUEUE" 2>/dev/null | sort | head -1)"
    [ -n "$q" ] || break
    action="$(head -c 32 "$QUEUE/$q" 2>/dev/null | tr -cd 'a-z-')"
    rm -f "$QUEUE/$q"
    case "$q" in *[!A-Za-z0-9_-]*) continue;; esac     # 任务号只许这些字符，防路径穿越
    run_job "$q" "$action"
done
