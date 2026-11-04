"""首次启动时初始化：管理员账号 + 知识范围/题型字典。可重复执行。

知识范围和题型的来源是 config.yaml：
- bank.sync_on_start = false（默认）：只补数据库里还没有的项，
  界面上手工加的、改的都保留 —— 日常以界面为准；
- bank.sync_on_start = true：每次启动都以配置文件为准，
  配置里没有的项会被停用 —— 想用文件管一切时才打开。
"""

from sqlalchemy import select

from . import clock
from .config import settings
from .constants import DICT_SCOPE, DICT_TYPE
from .database import SessionLocal
from .models import AppMeta, DictItem, ExamSubmission, User
from .security import hash_password
from .changelog_seed import seed_changelog
from .services.exam import settle_submission
from .services.supplement import seed_supplement
from .services.typing_texts import ensure_default_theme, seed_from_config
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


def _settle_old_submissions(db) -> int:
    """2.10.0 起操作题检查点全过给满分、全没过给 0 分，算评完。老答卷补一遍，只补一次。"""
    if db.get(AppMeta, "auto_settle_v1"):
        return 0
    n = sum(1 for sub in db.scalars(select(ExamSubmission)) if settle_submission(sub))
    db.add(AppMeta(key="auto_settle_v1", value=clock.now().isoformat(sep=" ")))
    db.commit()
    return n


def seed(supplement: bool = True) -> None:
    """supplement=False 不补补充题：测试要从一个空题库起步，组卷才算得准。"""
    db = SessionLocal()
    try:
        # 最先做：服务器时钟校正值改了，已有记录的时间一起挪（见 app/clock.py）。
        # 赶在下面建任何新记录之前 —— 不然新记录会被多挪一次
        moved = clock.rebase(db)
        if moved:
            print(f"[seed] 时钟校正改成 {site.time.offset_hours:+g} 小时，已有记录的时间挪了 {moved:+g} 小时")

        n = _settle_old_submissions(db)
        if n:
            print(f"[seed] {n} 份老答卷里检查点全过 / 全没过的操作题已自动定分")

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
        ensure_default_theme(db)  # 内置主题「信息生活」，没归主题的文本归它

        # 补充题跟着代码走：库里没有就补上（按题干查重，老师删了的不会再冒出来）
        n = seed_supplement(db) if supplement else 0
        db.commit()
        if n:
            print(f"[seed] 补充题新增 {n} 道")

        # 更新日志按内容去重，可反复执行；新版本追加到 changelog_seed.py 即可
        n = seed_changelog(db)
        if n:
            print(f"[seed] 更新日志新增 {n} 条")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
