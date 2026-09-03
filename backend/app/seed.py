"""首次启动时初始化：管理员账号 + 知识范围/题型字典。可重复执行。"""

from sqlalchemy import select

from .config import settings
from .constants import ALL_TYPES, DICT_SCOPE, DICT_TYPE, SCOPES
from .database import SessionLocal
from .models import DictItem, User
from .security import hash_password


def seed() -> None:
    db = SessionLocal()
    try:
        if not db.scalar(select(User).where(User.username == settings.admin_username)):
            db.add(
                User(
                    username=settings.admin_username,
                    password_hash=hash_password(settings.admin_password),
                    name=settings.admin_name,
                    role="admin",
                )
            )
            print(f"[seed] 已创建管理员 {settings.admin_username}")

        for i, name in enumerate(SCOPES):
            if not db.scalar(
                select(DictItem).where(
                    DictItem.category == DICT_SCOPE, DictItem.name == name
                )
            ):
                db.add(DictItem(category=DICT_SCOPE, name=name, sort_order=i))

        for i, name in enumerate(ALL_TYPES):
            if not db.scalar(
                select(DictItem).where(DictItem.category == DICT_TYPE, DictItem.name == name)
            ):
                db.add(DictItem(category=DICT_TYPE, name=name, sort_order=i))

        db.commit()
        print("[seed] 字典初始化完成")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
