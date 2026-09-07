#!/usr/bin/env bash
# 让国内服务器能正常 git pull GitHub。
#
#   bash scripts/setup-github-cn.sh
#
# 逐个实测国内 GitHub 加速服务，把能用的那个配成 git 的透明替换
# （url.<代理>.insteadOf），之后 git clone / pull / fetch 照常写 github.com 地址即可，
# 不用改任何命令，也不用改 remote。
#
# 和 Docker 镜像站一样，这类服务关停、限流很频繁，所以不写死某一个，而是当场测。
# 全都不通时会提示改用 Gitee 镜像（最稳）。

set -uo pipefail

REPO_PATH="c200108/A_System_of_WFXXKJ_Simulating_Examination"

C_CYAN='\033[36m'; C_GREEN='\033[32m'; C_YEL='\033[33m'; C_RED='\033[31m'; C_OFF='\033[0m'
step() { printf "\n${C_CYAN}%s${C_OFF}\n" "$1"; }
ok()   { printf "      ${C_GREEN}%s${C_OFF}\n" "$1"; }
warn() { printf "      ${C_YEL}%s${C_OFF}\n" "$1"; }
die()  { printf "\n${C_RED}[失败] %s${C_OFF}\n\n" "$1"; exit 1; }

command -v git >/dev/null 2>&1 || die "没装 git：sudo apt-get install -y git"

echo "=================================================="
echo "   GitHub 国内访问配置"
echo "=================================================="

# ---------------------------------------------------------------- 1 直连先试
step "[1/3] 先试直连 GitHub..."
if timeout 15 git ls-remote "https://github.com/${REPO_PATH}.git" HEAD >/dev/null 2>&1; then
    ok "直连就能用，不需要配代理"
    git config --global --unget-all url."https://github.com/".insteadOf 2>/dev/null || true
    echo
    echo "  直接用就行：git pull"
    exit 0
fi
warn "直连不通，开始找可用的加速服务"

# ---------------------------------------------------------------- 2 探测
step "[2/3] 逐个实测（每个最多 20 秒）..."

# 允许指定自己找到的加速地址：
#   GH_PROXY=https://xxx.com/https://github.com bash scripts/setup-github-cn.sh
CANDIDATES=(
    "https://ghproxy.net/https://github.com"
    "https://gh-proxy.com/https://github.com"
    "https://ghfast.top/https://github.com"
    "https://ghproxy.cc/https://github.com"
    "https://gh.llkk.cc/https://github.com"
)
[ -n "${GH_PROXY:-}" ] && CANDIDATES=("$GH_PROXY" "${CANDIDATES[@]}")

WORKING=""
for base in "${CANDIDATES[@]}"; do
    printf "      %-46s " "$base"
    # 用真实的 git 协议探测，不是只 ping 一下首页 ——
    # 有的站首页能开但 git 协议走不通
    if timeout 20 git ls-remote "${base}/${REPO_PATH}.git" HEAD >/dev/null 2>&1; then
        printf "${C_GREEN}可用${C_OFF}\n"
        WORKING="$base"
        break
    fi
    echo "不通"
done

[ -n "$WORKING" ] || die "所有加速服务都不通。

      改用 Gitee 镜像（最稳，国内直连）：
        1. 登录 https://gitee.com，新建仓库时选「从 GitHub 导入」
        2. 仓库设置里开启定时同步
        3. 服务器上把 remote 换成 Gitee 地址：
           git remote set-url origin https://gitee.com/你的用户名/仓库名.git

      或者自己找一个可用的加速地址后：
        GH_PROXY=https://那个地址/https://github.com bash $0"

# ---------------------------------------------------------------- 3 写配置
step "[3/3] 配置 git 透明替换..."

# 先清掉旧的，避免叠加多条指向已失效的服务
git config --global --unset-all url."https://github.com/".insteadOf 2>/dev/null || true
for old in $(git config --global --get-regexp '^url\..*\.insteadof' 2>/dev/null | awk '{print $1}'); do
    key="${old%.insteadof}"
    val="$(git config --global --get "${key}.insteadOf" 2>/dev/null || true)"
    [ "$val" = "https://github.com/" ] && git config --global --unset-all "${key}.insteadOf"
done

git config --global url."${WORKING}/".insteadOf "https://github.com/"
ok "已配置：github.com → ${WORKING}"

echo
echo "验证："
if timeout 25 git ls-remote "https://github.com/${REPO_PATH}.git" HEAD >/dev/null 2>&1; then
    ok "写 github.com 地址已经能通了"
else
    warn "验证没过，可能是刚才那个服务不稳定，重跑本脚本换一个"
fi

echo
echo "=================================================="
echo "  配置完成"
echo
echo "  之后 git clone / pull / fetch 照常写 github.com 地址即可。"
echo "  想取消：git config --global --unset-all url.\"${WORKING}/\".insteadOf"
echo "=================================================="
