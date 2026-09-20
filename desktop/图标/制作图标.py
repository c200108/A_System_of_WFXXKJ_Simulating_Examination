# -*- coding: utf-8 -*-
r"""把校徽做成 exe 的图标。

    python 制作图标.py                 用 图标/校徽.png 生成 考试客户端.ico
    python 制作图标.py --src 别的.png  换一张源图

**要什么**：`图标/校徽.png` —— 学校那枚圆形徽章，越大越清楚越好（现在这张是
2000×2000）。白底、透明底都行，脚本把圆外面切成透明。

**做什么**：基本什么都不做 —— 这枚徽章本身就是"校徽 + 信息科技"（电路走线、
芯片、二进制、code 都在里面），再往外加东西只会打架。脚本只负责三件事：
切成圆形、切掉圆外的白边、按尺寸出 ico。

**为什么小尺寸单独画**：16×16 的任务栏图标只有 256 个像素，徽章上的楼、英文、
二进制全糊成一团 —— 48×48 也一样糊。所以 48 及以下换成"红环 + 芯片"的简笔版，
64 起才用校徽。ico 本来就允许每个尺寸放不一样的图。

    16 / 24 / 32 / 48    金盘 + 红环 + 芯片    任务栏、Alt+Tab、资源管理器中图标
    64 / 128 / 256       校徽原样            大图标、属性页、桌面快捷方式
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
RED = (214, 32, 25)            # 校徽那个红
GOLD = (236, 218, 148)         # 校徽的金底（从图里量的）
BG = (255, 255, 255, 0)        # 透明底，贴在深色任务栏上也干净

SIZES = (256, 128, 64, 48, 32, 24, 16)
BIG = 1024                     # 先画大的再缩，边缘才干净
SS = 4                         # 小尺寸那版先放大 4 倍画，缩回去边才平滑


# ================================================================ 校徽
def round_badge(src: Path, size: int) -> Image.Image:
    """把徽章裁成正方形、切成圆形，圆外透明。

    **不抠底色。** 这枚徽章的金底是设计的一部分，不是要去掉的背景 ——
    抠了只剩红线条飘在白底上，整个味道就没了。要做的只是把圆外面那圈白边切掉，
    否则贴在深色任务栏上会看见一个白方块。
    """
    im = Image.open(src).convert("RGBA")

    # ① 裁掉四周的白边（按"离白多远"找内容的外框）
    grey = im.convert("RGB").convert("L")
    box = ImageChops.invert(grey).point(lambda v: 255 if v > 12 else 0).getbbox()
    if box:
        im = im.crop(box)

    # ② 补成正方形，居中
    side = max(im.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2), im)

    # ③ 圆形遮罩。先按 4 倍画再缩，边缘才不是锯齿
    big = size * SS
    sq = sq.resize((big, big), Image.LANCZOS)
    mask = Image.new("L", (big, big), 0)
    # 往里收一点点：原图圆周上常有一圈灰白的毛边，连着切掉
    inset = big * 0.005
    ImageDraw.Draw(mask).ellipse([inset, inset, big - inset, big - inset], fill=255)
    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    out.paste(sq, (0, 0), mask)
    return out.resize((size, size), Image.LANCZOS)


# ================================================================ 小尺寸那版
def chip(d: ImageDraw.ImageDraw, c: float, box: float, w: int) -> None:
    """一枚芯片：圆角方块 + 四边引脚 + 中间的方孔。信息科技最好认的符号。"""
    half = box / 2
    pin = box * 0.17
    for i in range(3):
        off = -box * 0.28 + i * box * 0.28
        d.line([c + off, c - half - pin, c + off, c - half], fill=RED, width=w)
        d.line([c + off, c + half, c + off, c + half + pin], fill=RED, width=w)
        d.line([c - half - pin, c + off, c - half, c + off], fill=RED, width=w)
        d.line([c + half, c + off, c + half + pin, c + off], fill=RED, width=w)
    d.rounded_rectangle([c - half, c - half, c + half, c + half],
                        radius=box * 0.16, fill=RED)
    inner = box * 0.3
    d.rounded_rectangle([c - inner, c - inner, c + inner, c + inner],
                        radius=box * 0.08, fill=GOLD + (255,))


def small_icon() -> Image.Image:
    """16~48 用的简笔版：金盘 + 红环 + 芯片。

    配色跟着校徽走（金底红字），所以缩到 16 像素也还是"同一家的东西"。
    校徽本身在这个尺寸只剩一团糊掉的红金，认不出是什么。
    """
    im = Image.new("RGBA", (BIG, BIG), BG)
    d = ImageDraw.Draw(im)
    c = BIG / 2
    r = BIG * 0.47
    d.ellipse([c - r, c - r, c + r, c + r], fill=GOLD + (255,),
              outline=RED, width=int(BIG * 0.06))
    chip(d, c, BIG * 0.44, max(2, int(BIG * 0.016)))
    return im


# ================================================================ 组装
def main() -> int:
    ap = argparse.ArgumentParser(description="校徽 → exe 图标")
    ap.add_argument("--src", default=str(HERE / "校徽.png"), help="校徽原图")
    ap.add_argument("--out", default=str(HERE / "考试客户端.ico"))
    args = ap.parse_args()

    src = Path(args.src)
    if not src.exists():
        print(f"没找到校徽原图：{src}\n"
              f"把学校那枚徽章存成 {src}（越大越清楚越好，≥512 最佳）再跑一次。")
        return 1

    big = round_badge(src, BIG)
    small = small_icon()
    big.resize((512, 512), Image.LANCZOS).save(HERE / "预览-大.png")
    small.resize((512, 512), Image.LANCZOS).save(HERE / "预览-小.png")

    frames = []
    for s in SIZES:
        # 48 以下一律用简笔版：校徽缩到 48 只剩一团糊，认不出是什么。
        # ico 允许每个尺寸放不一样的图，就是为了这个
        base = big if s >= 64 else small
        one = base.resize((s, s), Image.LANCZOS)
        if s <= 32:                     # 缩得太狠会发灰，锐一下
            one = one.filter(ImageFilter.SHARPEN)
        frames.append(one)
    frames[0].save(args.out, format="ICO",
                   sizes=[(s, s) for s in SIZES], append_images=frames[1:])

    # PyInstaller 只吃 .ico；另存一份 PNG 备用（网页端 favicon 之类）
    big.resize((256, 256), Image.LANCZOS).save(HERE / "考试客户端.png")
    print(f"做好了：{args.out}")
    print(f"  预览：{HERE / '预览-大.png'}（64 及以上用这张）")
    print(f"        {HERE / '预览-小.png'}（48 及以下用这张）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
