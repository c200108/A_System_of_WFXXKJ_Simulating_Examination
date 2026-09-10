"""打字练习文本库。

文本原来写死在 config.yaml 里，现在挪进数据库：老师能在界面上增删改、
也能上传 txt 批量导入。config.yaml 里那份退化成「首次建库时的初始值」，
和知识范围、题型是同一个套路。
"""

import hashlib
import random
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import TypingText
from ..siteconfig import site

# txt 批量导入：一行一段；空行分隔的多行会被拼成一段（方便贴长文）
_BLANK_LINES = re.compile(r"\n\s*\n+")


def text_hash(content: str) -> str:
    """按去掉所有空白后的内容查重，避免同一段文字因为多个空格被重复导入。"""
    return hashlib.sha256(re.sub(r"\s+", "", content).encode("utf-8")).hexdigest()


def seed_from_config(db: Session) -> int:
    """把 config.yaml 里的内置文本灌进空库。已有数据就跳过，不覆盖老师的修改。"""
    if db.scalar(select(TypingText.id).limit(1)):
        return 0

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
            )
        )
        added += 1

    db.commit()
    return {"added": added, "skipped": skipped, "too_short": too_short}


def build_passage(db: Session, mode: str, difficulty: str) -> str:
    """随机洗牌拼几段成一篇长文，保证限时练习有足够内容，两次也不会完全一样。"""
    rows = db.scalars(
        select(TypingText.content).where(
            TypingText.mode == mode,
            TypingText.difficulty == difficulty,
            TypingText.is_active.is_(True),
        )
    ).all()
    if not rows:
        return ""

    pool = list(rows)
    random.shuffle(pool)
    lo, hi = (list(site.typing.passages_per_round) + [7, 9])[:2]
    count = min(len(pool), random.randint(min(lo, hi), max(lo, hi)))
    sep = " " if mode == "english" else ""
    return sep.join(pool[:count]).rstrip()
