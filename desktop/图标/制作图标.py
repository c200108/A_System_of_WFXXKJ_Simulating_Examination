# -*- coding: utf-8 -*-
r"""把校徽做成 exe 的图标：校徽 + 信息科技的电路环。

    python 制作图标.py                 用 图标/校徽.png 生成 考试客户端.ico
    python 制作图标.py --src 别的.png  换一张源图

**要什么**：`图标/校徽.png` —— 学校那枚圆形徽章，越大越清楚越好（建议 ≥512），
背景白的、米色的、透明的都行，脚本会自己洗干净。

**做成什么样**：徽章原样摆中间（学校的东西不改），外面套一圈深蓝电路环 ——
环上有节点和走线，右下角一枚芯片角标。这样既是这所学校的，又一眼看出是
信息科技考试用的。

**为什么小尺寸单独画**：16×16 的任务栏图标只有 256 个像素，校徽上的楼、字、
年份全糊成一团红 —— 48×48 也一样糊。所以 48 及以下换成"红环 + 芯片"的简笔版，
64 起才用校徽。ico 本来就允许每个尺寸放不一样的图。

    16 / 24 / 32 / 48    红环 + 芯片        任务栏、Alt+Tab、资源管理器中图标
    64 / 128 / 256       校徽 + 电路环      大图标、属性页、桌面快捷方式
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
RED = (214, 32, 25)            # 校徽那个红
NAVY = (23, 58, 110)           # 电路环的深蓝：印在白底上够沉，缩小也不糊
CYAN = (0, 150, 199)           # 节点高光
BG = (255, 255, 255, 0)        # 透明底，贴在深色任务栏上也干净

SIZES = (256, 128, 64, 48, 32, 24, 16)
BIG = 1024                     # 先画大的再缩，边缘才干净


# ================================================================ 洗底
def clean_badge(src: Path, size: int) -> Image.Image:
    """把徽章抠出来：去掉底色，只留线条，摆进一个正方形里。

    判据是"离底色有多远"，**不是"有多亮"**：这枚徽章的底是米色带噪点的
    （约 200,200,150），红线条是 (224,0,0)。按亮度切的话，米色只比红色亮一点，
    切出来会留一层带噪点的脏底；按"离底色的距离"切，米色归零、红线全留。

    底色不写死，取图里最常见的那个颜色 —— 学校哪天换成蓝底金字的徽章，
    这段不用改。
    """
    im = Image.open(src).convert("RGBA")

    # ① 先裁掉四周的空白
    grey = im.convert("RGB").convert("L")
    box = ImageChops.invert(grey).point(lambda v: 255 if v > 24 else 0).getbbox()
    if box:
        im = im.crop(box)

    # ② 摆正成正方形（长边为准，居中）
    side = max(im.size)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2), im)
    im = sq.resize((size, size), Image.LANCZOS)

    # ③ 按"离底色多远"算透明度
    rgb = im.convert("RGB")
    bg = _background(rgb, im.getchannel("A"))
    alpha = _distance_mask(rgb, bg)
    # 原图本来就有透明区的话，取两者更小的那个，别把透明处又涂回来
    alpha = ImageChops.darker(alpha, im.getchannel("A"))
    out = Image.new("RGBA", im.size, (0, 0, 0, 0))
    out.paste(rgb, (0, 0), alpha)
    return out


def _background(rgb: Image.Image, a: Image.Image) -> tuple:
    """底色：取**最外圈那一环**的中位颜色。

    不能用"图里最常见的颜色"——这枚徽章的红线条又粗又多，统计下来红比米色还
    常见，于是把红当成底色抠掉，留下一张空壳。踩过这个坑。

    圆形徽章的最外圈按定义就是底：那儿不会有图案，只有底色（或者透明）。
    """
    w, h = rgb.size
    cx, cy, R = w / 2, h / 2, min(w, h) / 2
    px, pa = rgb.load(), a.load()
    reds, greens, blues = [], [], []
    for i in range(720):                       # 沿着圆周取样，每 0.5 度一个
        ang = math.radians(i * 0.5)
        for f in (0.93, 0.955, 0.98):
            x = int(cx + math.cos(ang) * R * f)
            y = int(cy + math.sin(ang) * R * f)
            if 0 <= x < w and 0 <= y < h and pa[x, y] >= 128:
                r, g, b = px[x, y]
                reds.append(r), greens.append(g), blues.append(b)
    if not reds:
        return (255, 255, 255)
    mid = lambda v: sorted(v)[len(v) // 2]     # noqa: E731
    return (mid(reds), mid(greens), mid(blues))


def _distance_mask(rgb: Image.Image, bg: tuple, soft: int = 34) -> Image.Image:
    """离底色越远越不透明。soft 是"这点差别不算数"的宽容度，用来吃掉噪点。"""
    r, g, b = rgb.split()
    out = Image.new("L", rgb.size, 0)
    px_r, px_g, px_b = r.load(), g.load(), b.load()
    px_o = out.load()
    for y in range(rgb.height):
        for x in range(rgb.width):
            d = (abs(px_r[x, y] - bg[0]) + abs(px_g[x, y] - bg[1])
                 + abs(px_b[x, y] - bg[2])) // 2
            px_o[x, y] = 0 if d <= soft else min(255, (d - soft) * 3)
    return out.filter(ImageFilter.MedianFilter(3))          # 噪点去掉


# ================================================================ 电路环
def circuit_ring(size: int, r_in: float, r_out: float, nodes: int = 12) -> Image.Image:
    """一圈电路：环 + 等距节点 + 从节点往里伸的短走线。"""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = size / 2
    w = max(2, int(size * 0.012))

    d.ellipse([c - r_out, c - r_out, c + r_out, c + r_out], outline=NAVY, width=w)
    d.ellipse([c - r_in, c - r_in, c + r_in, c + r_in], outline=NAVY, width=w)

    for i in range(nodes):
        a = math.radians(i * 360 / nodes - 90)
        ca, sa = math.cos(a), math.sin(a)
        # 走线：从外环往里伸一截就停，不要拉满 —— 拉满了像齿轮，不像电路
        r_mid = r_in + (r_out - r_in) * 0.45
        d.line([c + ca * r_mid, c + sa * r_mid, c + ca * r_out, c + sa * r_out],
               fill=NAVY, width=w)
        # 节点：压在外环上，隔一个换个颜色，看着像焊点
        rr = size * (0.022 if i % 2 == 0 else 0.016)
        x, y = c + ca * r_out, c + sa * r_out
        d.ellipse([x - rr, y - rr, x + rr, y + rr],
                  fill=NAVY if i % 2 == 0 else CYAN)
    return im


def chip(size: int, box: float) -> Image.Image:
    """一枚芯片：圆角方块 + 四边引脚 + 中间的方孔。信息科技最好认的符号。"""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = size / 2
    half = box / 2
    pin = box * 0.17
    w = max(2, int(size * 0.016))

    for i in range(3):
        off = -box * 0.28 + i * box * 0.28
        d.line([c + off, c - half - pin, c + off, c - half], fill=NAVY, width=w)
        d.line([c + off, c + half, c + off, c + half + pin], fill=NAVY, width=w)
        d.line([c - half - pin, c + off, c - half, c + off], fill=NAVY, width=w)
        d.line([c + half, c + off, c + half + pin, c + off], fill=NAVY, width=w)

    d.rounded_rectangle([c - half, c - half, c + half, c + half],
                        radius=box * 0.16, fill=NAVY)
    inner = box * 0.3
    d.rounded_rectangle([c - inner, c - inner, c + inner, c + inner],
                        radius=box * 0.08, fill=(255, 255, 255, 255))
    return im


# ================================================================ 组装
def big_icon(src: Path) -> Image.Image:
    """大尺寸用的：校徽原样在中间，外面套电路环。"""
    im = Image.new("RGBA", (BIG, BIG), BG)
    c = BIG / 2
    # 白底圆盘：徽章本身是线条画，贴在深色任务栏上没有底会散
    ImageDraw.Draw(im).ellipse([c - BIG * 0.485, c - BIG * 0.485,
                                c + BIG * 0.485, c + BIG * 0.485],
                               fill=(255, 255, 255, 255))
    im.alpha_composite(circuit_ring(BIG, BIG * 0.415, BIG * 0.468, nodes=12))
    badge = clean_badge(src, int(BIG * 0.80))
    im.alpha_composite(badge, (int(c - badge.width / 2), int(c - badge.height / 2)))
    return im


def small_icon() -> Image.Image:
    """16~32 用的简笔版：环 + 芯片。校徽缩到这个尺寸只剩一团红。"""
    im = Image.new("RGBA", (BIG, BIG), BG)
    c = BIG / 2
    d = ImageDraw.Draw(im)
    d.ellipse([c - BIG * 0.47, c - BIG * 0.47, c + BIG * 0.47, c + BIG * 0.47],
              fill=(255, 255, 255, 255), outline=RED, width=int(BIG * 0.055))
    im.alpha_composite(chip(BIG, BIG * 0.44))
    return im


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

    big = big_icon(src)
    small = small_icon()
    big.resize((512, 512), Image.LANCZOS).save(HERE / "预览-大.png")
    small.resize((512, 512), Image.LANCZOS).save(HERE / "预览-小.png")

    frames = []
    for s in SIZES:
        # 48 以下一律用简笔版：校徽缩到 48 只剩一团糊掉的红，认不出是什么。
        # ico 允许每个尺寸放不一样的图，就是为了这个
        base = big if s >= 64 else small
        one = base.resize((s, s), Image.LANCZOS)
        if s <= 32:                     # 缩得太狠会发灰，锐一下
            one = one.filter(ImageFilter.SHARPEN)
        frames.append(one)
    frames[0].save(args.out, format="ICO",
                   sizes=[(s, s) for s in SIZES], append_images=frames[1:])

    # PyInstaller 只吃 .ico；程序里给 Tk 窗口设图标用 PNG 更省事，一起出一份
    big.resize((256, 256), Image.LANCZOS).save(HERE / "考试客户端.png")
    print(f"做好了：{args.out}")
    print(f"  预览：{HERE / '预览-大.png'}（64 及以上用这张）")
    print(f"        {HERE / '预览-小.png'}（48 及以下用这张）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
