"""首次启动时初始化：管理员账号 + 知识范围/题型字典。可重复执行。

知识范围和题型的来源是 config.yaml：
- bank.sync_on_start = false（默认）：只补数据库里还没有的项，
  界面上手工加的、改的都保留 —— 日常以界面为准；
- bank.sync_on_start = true：每次启动都以配置文件为准，
  配置里没有的项会被停用 —— 想用文件管一切时才打开。
"""

from sqlalchemy import select

from .config import settings
from .constants import DICT_SCOPE, DICT_TYPE
from .database import SessionLocal
from .models import DictItem, User
from .security import hash_password
from .changelog_seed import seed_changelog
from .services.typing_texts import seed_from_config
from .siteconfig import site


def _sync_dict(db, category: str, names: list[str], sync: bool) -> None:
    existing = {d.name: d for d in db.scalars(select(DictItem).where(DictItem.category == category))}

    for i, name in enumerate(names):
        item = existing.get(name)
        if item is None:
            db.add(DictItem(category=category, name=name, sort_order=i))
        elif sync:
            item.sort_order = i
            item.is_active = True

    if sync:
        # 配置里删掉的项停用（不物理删除，历史题目还引用着它）
        for name, item in existing.items():
            if name not in names and item.is_active:
                item.is_active = False
                print(f"[seed] 配置里已无「{name}」，停用（历史题目不受影响）")


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

        sync = site.bank.sync_on_start
        _sync_dict(db, DICT_SCOPE, site.bank.scopes, sync)
        _sync_dict(db, DICT_TYPE, site.bank.types, sync)

        db.commit()
        print("[seed] 字典初始化完成" + ("（已按配置文件同步）" if sync else ""))

        # 打字文本只在空库时从 config.yaml 灌一次，之后以界面上的修改为准
        n = seed_from_config(db)
        if n:
            print(f"[seed] 打字文本已导入 {n} 段")

        # 更新日志按内容去重，可反复执行；新版本追加到 changelog_seed.py 即可
        n = seed_changelog(db)
        if n:
            print(f"[seed] 更新日志新增 {n} 条")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
