"""打字练习文本库。

文本原来写死在 config.yaml 里，现在挪进数据库：老师能在界面上增删改、
也能上传 txt 批量导入。config.yaml 里那份退化成「首次建库时的初始值」，
和知识范围、题型是同一个套路。

## 主题（2.15.0）

每段文本属于一个主题（信息生活、……）。学生取文本时**先在启用的主题里等概率随机挑一个，
再只在这个主题里抽几段拼成一篇**，绝不跨主题拼 —— 一篇读下来讲的是同一件事。
每次请求各自随机（不用固定种子），一个机房六十台同时取也是各取各的。
theme_id 为空的文本当内置的「信息生活」算。
"""

import hashlib
import random
import re

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import TypingText, TypingTheme
from ..siteconfig import site

# txt 批量导入：一行一段；空行分隔的多行会被拼成一段（方便贴长文）
_BLANK_LINES = re.compile(r"\n\s*\n+")

DEFAULT_THEME = "信息生活"
# 每次请求独立随机：用系统熵，不受谁在别处 random.seed() 影响
_rng = random.SystemRandom()


def default_theme_id(db: Session) -> int | None:
    """内置主题「信息生活」的 id；还没建（新库还没跑 seed）返回 None。"""
    return db.scalar(
        select(TypingTheme.id).where(TypingTheme.is_builtin.is_(True)).order_by(TypingTheme.id).limit(1)
    )


def ensure_default_theme(db: Session) -> int:
    """确保有内置主题「信息生活」，没归主题的文本归它。返回它的 id。迁移也做同样的事，
    这里是给 create_all 建出来的库（测试、全新部署）兜底的。"""
    tid = default_theme_id(db)
    if tid is None:
        row = db.scalar(select(TypingTheme).where(TypingTheme.name == DEFAULT_THEME))
        if row is None:
            row = TypingTheme(name=DEFAULT_THEME, is_enabled=True, sort_order=0, is_builtin=True)
            db.add(row)
        row.is_builtin = True
        db.flush()
        tid = row.id
    db.execute(update(TypingText).where(TypingText.theme_id.is_(None)).values(theme_id=tid))
    db.commit()
    return tid


def text_hash(content: str) -> str:
    """按去掉所有空白后的内容查重，避免同一段文字因为多个空格被重复导入。"""
    return hashlib.sha256(re.sub(r"\s+", "", content).encode("utf-8")).hexdigest()


def seed_from_config(db: Session) -> int:
    """把 config.yaml 里的内置文本灌进空库。已有数据就跳过，不覆盖老师的修改。"""
    if db.scalar(select(TypingText.id).limit(1)):
        return 0

    tid = ensure_default_theme(db)
    added = 0
    for mode, lib in (("english", site.typing.english), ("chinese", site.typing.chinese)):
        for difficulty, items in (lib or {}).items():
            for content in items:
                content = content.strip()
                if not content:
                    continue
                db.add(
                    TypingText(
                        mode=mode,
                        difficulty=difficulty,
                        content=content,
                        content_hash=text_hash(content),
                        source="内置",
                        theme_id=tid,
                    )
                )
                added += 1
    db.commit()
    return added


def parse_txt(raw: bytes, split: str = "line") -> list[str]:
    """解析上传的 txt。

    split="line"  一行一段（默认）。空行直接忽略。
    split="blank" 空行分段，段内换行折成空格 —— 贴整篇文章时用。

    刻意做成显式参数而不是自动判断：老师的文件里多一个空行是常事，
    靠"有没有空行"猜分段方式，会莫名其妙把几十行并成一大段。
    """
    for encoding in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("这个文件的编码认不出来，请另存为 UTF-8 或 GBK 再传")

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    if split == "blank":
        chunks = [re.sub(r"\s*\n\s*", " ", c).strip() for c in _BLANK_LINES.split(text)]
    else:
        chunks = [line.strip() for line in text.split("\n")]

    return [c for c in chunks if c]


def add_texts(
    db: Session,
    mode: str,
    difficulty: str,
    contents: list[str],
    source: str = "自定义",
    created_by: int | None = None,
    theme_id: int | None = None,
) -> dict:
    """批量入库，按内容哈希去重（库内已有的、以及本次文件内重复的都跳过）。"""
    existing = {h for (h,) in db.execute(select(TypingText.content_hash)).all()}
    seen: set[str] = set()
    added = 0
    skipped = 0
    too_short = 0

    for content in contents:
        content = content.strip()
        if len(content) < 5:  # 太短的练不出东西，多半是误传的空行或标题
            too_short += 1
            continue
        h = text_hash(content)
        if h in existing or h in seen:
            skipped += 1
            continue
        seen.add(h)
        db.add(
            TypingText(
                mode=mode,
                difficulty=difficulty,
                content=content,
                content_hash=h,
                source=source,
                created_by=created_by,
                theme_id=theme_id,
            )
        )
        added += 1

    db.commit()
    return {"added": added, "skipped": skipped, "too_short": too_short}


def build_passage(db: Session, mode: str, difficulty: str, rng=None) -> str:
    """拼一篇练习文：先挑主题，再在这个主题里随机抽几段。

    1. 候选主题 = 启用的、并且这个语言 + 难度下有启用文本的主题；
    2. 候选里**等概率**挑一个（不按段数加权：段多的主题不该老被抽到）；
    3. 只在这个主题里洗牌抽 passages_per_round 段；不够就有几段拼几段，**不拿别的主题凑**。
    """
    rng = rng or _rng
    rows = db.execute(
        select(TypingText.content, TypingText.theme_id).where(
            TypingText.mode == mode,
            TypingText.difficulty == difficulty,
            TypingText.is_active.is_(True),
        )
    ).all()
    if not rows:
        return ""

    default = default_theme_id(db)
    enabled = set(db.scalars(select(TypingTheme.id).where(TypingTheme.is_enabled.is_(True))))
    groups: dict = {}
    for content, tid in rows:
        tid = tid if tid is not None else default
        # 内置主题还没建的老库：没归主题的文本照样能用
        if tid in enabled or (tid is None and not enabled):
            groups.setdefault(tid, []).append(content)
    if not groups:
        return ""

    pool = list(groups[rng.choice(sorted(groups, key=lambda k: (k is None, k or 0)))])
    rng.shuffle(pool)
    lo, hi = (list(site.typing.passages_per_round) + [7, 9])[:2]
    count = min(len(pool), rng.randint(min(lo, hi), max(lo, hi)))
    sep = " " if mode == "english" else ""
    return sep.join(pool[:count]).rstrip()