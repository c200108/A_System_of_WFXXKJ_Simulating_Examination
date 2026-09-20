"""把题目配图变成桌面端能显示的样子。

## 为什么要转

题库里的配图基本都是 `.jpg`。学生端 exe 用的是 Tkinter，而 **Tkinter 只认
PNG 和 GIF，不认 JPEG** —— 直接把 jpg 塞进考试包，学生看到的是一道没有图的
带图题，等于没法做。

所以在服务器这边转：jpg → png，顺便缩到屏幕装得下的尺寸。转换放在服务端有两个
好处：**学生端保持零依赖**（不用为了解码 JPEG 往 exe 里塞一个图像库，体积和
出错面都省了），而且一张图只转一次，全机房共用同一份。

## Pillow 没装也不能崩

老部署上可能没有 Pillow。这时候**跳过转换、题目照出**，而不是让整场考试导不出来
—— 没有图的带图题已经够糟了，导不出包更糟。日志里会留一句。
"""

from __future__ import annotations

import io
from pathlib import Path

from ..config import settings

# 学生机分辨率低，题目区大约七百像素宽。转的时候就缩到位，
# 免得把几兆的原图塞进考试包，五十台机器一起下载
MAX_WIDTH = 700
MAX_HEIGHT = 520

# 减到多少色。256 色对图表、截图这类考试插图足够，体积能小一半还多
PALETTE = 256
# 减色结果超过这个大小才回头和原样 PNG 比一比（编码一次不便宜）
COMPARE_ABOVE = 150 * 1024

# Tkinter 原生就能显示的，不用转
NATIVE = {".png", ".gif"}


def _pillow():
    try:
        from PIL import Image
        return Image
    except ImportError:
        return None


def local_path(image_url: str) -> Path | None:
    """把 `/uploads/images/xxx.jpg` 换成磁盘上的真实路径。

    只接受 `/uploads/` 开头的相对地址 —— 题目里的图都是本系统上传的。
    外链（http://…）不下载：考试机可能连不上外网，而且考试时去拉外部资源
    本来就不该发生。
    """
    url = str(image_url or "").strip()
    if not url.startswith("/uploads/"):
        return None
    rel = url[len("/uploads/"):].split("?")[0]
    if not rel or ".." in rel:
        return None
    path = Path(settings.upload_dir) / rel
    return path if path.is_file() else None


def as_png(image_url: str) -> tuple[str, bytes] | None:
    """读出这张图，转成 Tkinter 认得的格式。返回 (放进包里的文件名, 内容)。

    转不了就返回 None —— 调用方照常出题，只是没有图。
    """
    path = local_path(image_url)
    if not path:
        return None
    suffix = path.suffix.lower()
    raw = path.read_bytes()

    if suffix in NATIVE:
        # 已经是 PNG/GIF：原样带走，**一个像素都不动**
        return path.name, raw

    image_mod = _pillow()
    if image_mod is None:
        return None                      # 没装 Pillow，这张图只能放弃

    try:
        with image_mod.open(io.BytesIO(raw)) as im:
            im = im.convert("RGB")
            im.thumbnail((MAX_WIDTH, MAX_HEIGHT))
            # **必须减色。** PNG 是无损格式，照片直接转过去会比原 JPEG 大一倍
            # ——实测四张图 194 KB 的 JPEG 变成 399 KB 的 PNG，一份考试包因此
            # 涨到 900 KB，五十个学生同时开考要传 45 MB。
            # 减到 256 色之后只剩 173 KB，比原图还小；考试插图基本是图表和
            # 截图，肉眼看不出差别。
            small = im.convert("P", palette=image_mod.ADAPTIVE, colors=PALETTE)
            buf = io.BytesIO()
            small.save(buf, format="PNG", optimize=True)
            out = buf.getvalue()

            # 万一减色反而更大（色块极多的图偶尔会），就用原样的 PNG。
            # 只在减色结果仍然偏大时才比一次 —— PNG 编码不便宜，
            # 小图上白编一遍是纯浪费
            if len(out) > COMPARE_ABOVE:
                plain = io.BytesIO()
                im.save(plain, format="PNG", optimize=True)
                if plain.tell() < len(out):
                    out = plain.getvalue()
        return path.stem + ".png", out
    except Exception:                                   # noqa: BLE001
        return None                      # 图坏了不能连累整场考试导不出来
