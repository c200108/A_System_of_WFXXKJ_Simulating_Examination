"""部署前自检：把 .env 里还没改的默认值揪出来。

公网部署时最危险的失误是「装完能跑就不管了」，而 .env.example 里的
JWT_SECRET 和 ADMIN_PASSWORD 是公开在 GitHub 上的——不改等于没有密码。

只用标准库，不需要先装依赖，拿到新机器第一件事就能跑：

    python backend/tools/check_deploy.py          # 检查 Docker 部署用的根目录 .env
    python backend/tools/check_deploy.py backend/.env   # 检查直接运行用的 .env

退出码 0 = 可以部署，1 = 有必须修的问题。
"""

import os
import re
import secrets
import sys

# 这些值来自 .env.example / docker-compose 的默认值，公开可查，出现即致命
KNOWN_DEFAULTS = {
    "change_this_to_a_long_random_string",
    "please-change-this-to-a-long-random-string",
    "please-change-me",
    "change-me-in-production",
    "test-secret-not-used-in-production",
    "change_this_root_pwd",
    "change_this_user_pwd",
    "change_this_admin_pwd",
    "root_pwd",
    "exam_pwd",
    "admin123",
    "你的密码",
}

WEAK_PASSWORDS = {
    "123456", "12345678", "password", "admin", "root", "111111",
    "000000", "abc123", "qwerty", "1qaz2wsx", "88888888",
}

RED = "[严重]"
YEL = "[建议]"
GRN = "[通过]"


def load_env(path: str) -> dict:
    env = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else ".env"
    if not os.path.isfile(path):
        print(f"{RED} 找不到 {path}")
        print("       先执行：cp .env.example .env  （Windows: copy .env.example .env）")
        sys.exit(1)

    env = load_env(path)
    print(f"检查 {os.path.abspath(path)}\n")

    fatal, warn = [], []

    # ---- JWT 密钥 ----
    jwt = env.get("JWT_SECRET", "")
    if not jwt:
        fatal.append("JWT_SECRET 没有设置")
    elif jwt in KNOWN_DEFAULTS:
        fatal.append(
            "JWT_SECRET 还是示例里的默认值。这串东西公开在 GitHub 上，\n"
            "         任何人都能用它伪造管理员登录令牌，直接进你的系统。"
        )
    elif len(jwt) < 32:
        warn.append(f"JWT_SECRET 只有 {len(jwt)} 个字符，建议 32 位以上")
    else:
        print(f"{GRN} JWT_SECRET 已自定义（{len(jwt)} 字符）")

    # ---- 管理员密码 ----
    pwd = env.get("ADMIN_PASSWORD", "")
    if not pwd:
        fatal.append("ADMIN_PASSWORD 没有设置")
    elif pwd in KNOWN_DEFAULTS or pwd.lower() in WEAK_PASSWORDS:
        fatal.append(
            f"ADMIN_PASSWORD 是默认值或弱口令。公网上会被扫描器几分钟内爆破，\n"
            f"         对方拿到管理员权限后能看到全部题目和答案。"
        )
    elif len(pwd) < 8:
        warn.append(f"ADMIN_PASSWORD 只有 {len(pwd)} 位，公网部署建议 12 位以上")
    else:
        print(f"{GRN} ADMIN_PASSWORD 已自定义（{len(pwd)} 位）")

    # ---- 数据库密码 ----
    for key in ("MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD"):
        v = env.get(key)
        if v is None:
            continue
        if v in KNOWN_DEFAULTS or v.lower() in WEAK_PASSWORDS:
            fatal.append(f"{key} 是默认值或弱口令")
        elif len(v) < 8:
            warn.append(f"{key} 少于 8 位")
        else:
            print(f"{GRN} {key} 已自定义")

    # ---- 直接运行模式下的连接串 ----
    url = env.get("DATABASE_URL", "")
    if url:
        if url.startswith("sqlite"):
            warn.append("DATABASE_URL 指向 SQLite。多人同时使用建议换 MySQL")
        for bad in KNOWN_DEFAULTS:
            if bad in url:
                fatal.append(f"DATABASE_URL 里含有默认密码「{bad}」")
                break
        if url.startswith("mysql") and "charset=utf8mb4" not in url:
            fatal.append("MySQL 连接串缺少 ?charset=utf8mb4，中文题干会出问题")

    # ---- 对外地址 ----
    cors = env.get("CORS_ORIGINS", "")
    if cors and "localhost" in cors and "WEB_PORT" in env:
        warn.append(
            "CORS_ORIGINS 还写着 localhost。Docker 部署下前后端同源，通常不影响，\n"
            "         但改成真实访问地址更稳妥"
        )

    # ---- 汇总 ----
    print()
    for w in warn:
        print(f"{YEL} {w}")
    for f in fatal:
        print(f"{RED} {f}")

    if fatal:
        print(f"\n发现 {len(fatal)} 个必须修复的问题，修好再部署。")
        print("\n需要一串安全的随机密钥可以直接用这个（每次运行都不一样）：")
        print(f"  JWT_SECRET={secrets.token_urlsafe(48)}")
        sys.exit(1)

    print(f"\n检查通过{'（有 ' + str(len(warn)) + ' 条建议）' if warn else ''}。")
    print("\n公网部署还请确认这两件事，脚本查不了：")
    print("  1. HTTPS —— 现在是 http，密码和答案在网上是明文传输的")
    print("  2. 备案 —— 国内服务器对外提供网页服务需要 ICP 备案，")
    print("     很多云厂商未备案会封 80/443 端口")


if __name__ == "__main__":
    main()
