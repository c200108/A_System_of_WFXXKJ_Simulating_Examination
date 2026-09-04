import os
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import settings

IS_SQLITE = settings.database_url.startswith("sqlite")

connect_args: dict = {}
engine_kwargs: dict = {"pool_pre_ping": True}

if IS_SQLITE:
    connect_args = {"check_same_thread": False}
    # SQLite 不会自己建目录，先把 data/ 建出来，否则 alembic 第一次就连不上
    db_file = settings.database_url.split("///", 1)[-1]
    if db_file and db_file != ":memory:":
        os.makedirs(os.path.dirname(os.path.abspath(db_file)), exist_ok=True)
else:
    # MySQL 默认 8 小时后掐掉空闲连接，pool_recycle 要小于它，
    # 否则夜里没人用、第二天早上第一个请求会拿到一条已经断掉的连接。
    engine_kwargs.update(pool_size=10, max_overflow=20, pool_recycle=3600)

engine = create_engine(settings.database_url, connect_args=connect_args, **engine_kwargs)


if IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _tune_sqlite(dbapi_conn, _record):
        """WAL 让读写不再互相阻塞，busy_timeout 让并发写排队而不是直接报错。

        不开这两项时，一个学生在交卷判分（要读题），另一个学生的写入就得干等。
        """
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=10000")
        cur.execute("PRAGMA foreign_keys=ON")  # SQLite 默认不校验外键，显式打开
        cur.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
