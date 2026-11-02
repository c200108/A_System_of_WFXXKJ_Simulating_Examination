#!/bin/sh
# 前端容器启动时由 nginx 镜像的 /docker-entrypoint.sh 自动执行（/docker-entrypoint.d/ 下）。
#
# 决定这次用 http 还是 https：
#   · .env 没填 HTTPS_PORT            → 什么都不做，用镜像里的默认配置（只开 80），和以前一模一样
#   · 填了 HTTPS_PORT，证书也在       → 换成 https.conf：开 443，80 上的网页跳到 https
#   · 填了 HTTPS_PORT，证书却找不到   → 打一句警告，先按 http 跑，别让整站起不来
#
# 证书在 /etc/nginx/ssl/（docker-compose.yml 把宿主机的 SSL_CERT_DIR 只读挂进来），
# 文件名固定是 fullchain.pem 和 key.pem。
#
# 开了 HTTPS_PORT 时还会在后台每隔 CERT_CHECK_INTERVAL 秒（默认 3600）看一眼证书：
# acme.sh 续期把文件换了、或者证书是后来才放进去的，就重新生成配置并 nginx -s reload。
# 所以续期之后什么都不用做，最多一小时内自动生效。

set -u

EXAM=/etc/nginx/exam
SSL=/etc/nginx/ssl
CONF=/etc/nginx/conf.d/default.conf
INTERVAL="${CERT_CHECK_INTERVAL:-3600}"

log() { echo "[exam-https] $*"; }

# 80 端口跳转到哪。PUBLIC_BASE_URL 是 https 的就跳到它（证书只认域名，学生用 IP 打开也该被
# 带到域名上）；否则跳到同一主机名的 https，对外端口不是 443 时带上端口。
https_origin() {
    case "${PUBLIC_BASE_URL:-}" in
        https://*)
            echo "$PUBLIC_BASE_URL" | sed 's#^\(https://[^/]*\).*#\1#'
            return ;;
    esac
    port="${HTTPS_PORT##*:}"          # 允许写成 0.0.0.0:443 这种带地址的
    if [ "$port" = "443" ]; then
        echo 'https://$host'
    else
        echo "https://\$host:$port"
    fi
}

# 当前状态的「指纹」：证书内容一变它就变，巡检靠它判断要不要 reload
state() {
    if [ -s "$SSL/fullchain.pem" ] && [ -s "$SSL/key.pem" ]; then
        echo "on:$(cat "$SSL/fullchain.pem" "$SSL/key.pem" | md5sum | cut -c1-32)"
    else
        echo "missing"
    fi
}

apply() {
    case "$1" in
        on:*)
            sed "s#__HTTPS_ORIGIN__#$(https_origin)#" "$EXAM/https.conf" > "$CONF"
            if nginx -t -q 2>/dev/null; then
                log "HTTPS 已启用：443 用 $SSL 里的证书，80 上的网页跳到 $(https_origin)"
                return 0
            fi
            # 证书和私钥不配套、文件坏了 …… 宁可退回 http 也别让整站起不来
            log "警告：证书配置没通过 nginx -t（证书和私钥不配套、文件坏了……）："
            nginx -t 2>&1 | sed 's/^/    /'
            cp "$EXAM/http.conf" "$CONF"
            return 1
            ;;
        *)
            log "警告：.env 填了 HTTPS_PORT，但证书目录里没有 fullchain.pem 和 key.pem"
            log "      检查 .env 里的 SSL_CERT_DIR 指对了没有（宿主机上那个目录挂到了容器的 $SSL）"
            cp "$EXAM/http.conf" "$CONF"
            return 1
            ;;
    esac
}

watch_certs() {
    last="$1"
    while sleep "$INTERVAL"; do
        now="$(state)"
        [ "$now" = "$last" ] && continue
        # 等几秒再看一次：acme.sh 是先写私钥再写证书，正好撞在中间的话两个文件不配套
        sleep 10
        [ "$(state)" = "$now" ] || continue
        log "证书有变化，重新加载"
        cp "$CONF" /tmp/exam-default.conf.bak
        if apply "$now"; then
            nginx -s reload && last="$now"
            continue
        fi
        case "$last" in
            on:*)
                # 新证书有问题时，原来那套还在 nginx 内存里好好地服务着 —— 别降成 http，
                # 配置文件放回去、不 reload，下一轮再看
                cp /tmp/exam-default.conf.bak "$CONF"
                log "继续用原来的证书，$INTERVAL 秒后再检查"
                ;;
            *)
                nginx -s reload && last="$now"
                ;;
        esac
    done
}

if [ -z "${HTTPS_PORT:-}" ]; then
    [ -s "$SSL/fullchain.pem" ] && log "提示：证书目录里有证书，但 .env 没填 HTTPS_PORT，所以没开 HTTPS"
    exit 0
fi

cur="$(state)"
apply "$cur" || log "先按 http 跑，证书弄好后最多 $INTERVAL 秒自动切到 https（或者 docker compose restart frontend）"
watch_certs "$cur" &
