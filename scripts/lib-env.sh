#!/usr/bin/env bash
# 读取 .env 的公共函数。被 data-export.sh / data-import.sh / backup.sh 共用。
#
# 为什么不直接 `set -a; . .env`：
#   docker compose 的 .env 不是 shell 脚本，值里出现 & | ; ( ) 空格都是合法的，
#   而 source 会把它们当成 shell 语法。一个 MYSQL_PASSWORD='p@ss&w0rd|x' 就能让
#   source 报一串 "command not found"，然后脚本以为"变量没配"退出 ——
#   更糟的情况是只读进半截，拿着残缺的口令去连库。
#
# 这里逐行解析，值一律当纯文本，不做任何 shell 展开。

# load_env_file <文件路径>
# 把文件里的 KEY=VALUE 逐个 export 出来。忽略注释行和空行。
load_env_file() {
    local file="$1" line key value
    [ -f "$file" ] || return 1

    while IFS= read -r line || [ -n "$line" ]; do
        # 去掉行尾的 \r，Windows 上编辑过的 .env 很常见
        line="${line%$'\r'}"
        # 跳过注释和空行
        case "$line" in ''|'#'*) continue ;; esac
        # 没有等号的行不是配置项
        case "$line" in *=*) ;; *) continue ;; esac

        key="${line%%=*}"
        value="${line#*=}"

        # 兼容 `export KEY=VALUE` 的写法
        key="${key#export }"
        # 去掉键两侧空白
        key="$(printf '%s' "$key" | tr -d '[:space:]')"
        [ -n "$key" ] || continue

        # 值两侧的成对引号去掉（compose 允许写也允许不写）
        case "$value" in
            \"*\") value="${value#\"}"; value="${value%\"}" ;;
            \'*\') value="${value#\'}"; value="${value%\'}" ;;
        esac

        # 关键：用 declare 赋值，值不经过任何 shell 解析
        export "$key=$value"
    done < "$file"
}
