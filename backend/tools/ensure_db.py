"""启动前的数据库准备：连不上就说清楚为什么，库不存在就建出来。

alembic 只会建表，不会建库。用 MySQL 时如果那个 database 还不存在，
直接 upgrade 会抛一句很难懂的 1049 错误。这个脚本把这一步接管掉，
并且把常见的失败原因翻译成人话。

启动脚本会先调用它；也可以手动跑：
    cd backend && .venv\\Scripts\\python.exe -m tools.ensure_db
"""

import sys

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.config import settings


def _die(msg: str) -> None:
    print(msg)
    sys.exit(1)


def ensure() -> None:
    url = make_url(settings.database_url)

    if url.get_backend_name() == "sqlite":
        # 目录由 app.database 建，这里连一下确认文件可写
        create_engine(settings.database_url).connect().close()
        print(f"[db] SQLite 就绪：{url.database}")
        return

    db_name = url.database
    if not db_name:
        _die("[db] DATABASE_URL 里没写数据库名，形如 .../exam?charset=utf8mb4")

    # 先连到服务器本身（不指定 database），才能执行 CREATE DATABASE。
    # 注意必须用空字符串：URL.set() 把 None 当成"这一项不改"，传 None 是无效的。
    server_url = url.set(database="")
    try:
        server = create_engine(server_url, pool_pre_ping=True)
        conn = server.connect()
    except Exception as exc:
        text_ = str(exc)
        if "Access denied" in text_:
            _die(
                f"[db] 数据库用户名或密码不对：{url.username}@{url.host}\n"
                f"     去 backend/.env 改 DATABASE_URL 里的密码。"
            )
        if "Can't connect" in text_ or "Connection refused" in text_ or "timed out" in text_:
            _die(
                f"[db] 连不上数据库服务器 {url.host}:{url.port or 3306}\n"
                f"     MySQL 服务没启动？Windows 上用管理员 cmd 执行：net start MySQL84\n"
                f"     （服务名以你本机实际安装的为准）"
            )
        _die(f"[db] 连接数据库失败：{exc}")

    with conn:
        if url.get_backend_name() == "mysql":
            # utf8mb4 必须显式指定，否则中文题干可能存不进去或排序不对
            conn.execute(
                text(
                    f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                    f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                )
            )
            conn.commit()
        elif url.get_backend_name() == "postgresql":
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_name}
            ).scalar()
            if not exists:
                conn.execute(text("COMMIT"))
                conn.execute(text(f'CREATE DATABASE "{db_name}" ENCODING \'UTF8\''))

    print(f"[db] {url.get_backend_name()} 就绪：{url.host}/{db_name}")


if __name__ == "__main__":
    ensure()
