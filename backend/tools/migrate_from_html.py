"""把现有单文件 HTML 里的 BANK_BASE（341 道题 + base64 图片）迁进数据库。

用法（在 backend 目录下）：
    python -m tools.migrate_from_html                 # 默认读 legacy/信息技术组卷台.html
    python -m tools.migrate_from_html 别的文件.html   # 也可以指定路径

做三件事：
1. 抠出 `const BANK_BASE = [...]` 这行 JSON；
2. base64 图片落成 uploads/images/*.png 文件，数据库只存路径；
3. 按题干哈希去重后写入 questions / options，重复执行不会产生重复数据。
"""

import base64
import json
import os
import re
import sys
import uuid

from sqlalchemy import select

from app.config import settings
from app.database import SessionLocal
from app.models import Option, Question
from app.services.importer import stem_hash

DATA_URL_RE = re.compile(r"^data:image/(?P<ext>[a-zA-Z0-9.+-]+);base64,(?P<body>.+)$", re.S)

# 老版本 HTML 归档在项目根的 legacy/ 目录，不传参数就读它
DEFAULT_HTML = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "legacy",
    "信息技术组卷台.html",
)


def extract_bank(html_path: str) -> list[dict]:
    with open(html_path, encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("const BANK_BASE"):
                raw = stripped.split("=", 1)[1].strip().rstrip(";")
                return json.loads(raw)
    raise SystemExit("在这个 HTML 里没找到 BANK_BASE，请确认文件正确。")


def save_image(data_url: str, images_dir: str) -> str | None:
    m = DATA_URL_RE.match(data_url.strip())
    if not m:
        return data_url if data_url.startswith("http") else None
    ext = m.group("ext").lower()
    ext = {"jpeg": "jpg", "svg+xml": "svg"}.get(ext, ext)
    name = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(images_dir, exist_ok=True)
    with open(os.path.join(images_dir, name), "wb") as f:
        f.write(base64.b64decode(m.group("body")))
    return f"/uploads/images/{name}"


def main() -> None:
    html_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HTML
    if not os.path.exists(html_path):
        raise SystemExit(f"找不到文件：{html_path}")
    print(f"读取：{html_path}")

    bank = extract_bank(html_path)
    images_dir = os.path.join(settings.upload_dir, "images")
    db = SessionLocal()
    added = skipped = images = 0
    try:
        existing = {h for (h,) in db.execute(select(Question.stem_hash)).all()}
        for item in bank:
            stem = (item.get("q") or "").strip()
            if not stem:
                continue
            h = stem_hash(stem)
            if h in existing:
                skipped += 1
                continue
            existing.add(h)

            image_url = None
            if item.get("img"):
                image_url = save_image(item["img"], images_dir)
                if image_url:
                    images += 1

            q = Question(
                code=item.get("id"),
                type=item.get("t") or "选择题",
                stem=stem,
                stem_hash=h,
                answer=item.get("a") or "",
                scope=item.get("k") or "",
                source=item.get("s") or "原卷",
                image_url=image_url,
            )
            for i, pair in enumerate(item.get("o") or []):
                if len(pair) >= 2:
                    q.options.append(Option(label=pair[0], content=pair[1], sort_order=i))
            db.add(q)
            added += 1
        db.commit()
    finally:
        db.close()

    print(f"迁移完成：新增 {added} 题，跳过重复 {skipped} 题，落地图片 {images} 张。")


if __name__ == "__main__":
    main()
