# -*- coding: utf-8 -*-
r"""把校徽做成 exe 的图标。两种样式，机房里两版 exe 各用一种。

    python 制作图标.py              两种都出
    python 制作图标.py --样式 金红   只出一种
    python 制作图标.py --样式 蓝红

    样式   大尺寸(≥64)   小尺寸(≤48)     源图          出到                 谁用
    金红   校徽原样      金盘+红环+芯片  校徽.png      考试客户端.ico       64 位 exe
    蓝红   校徽+电路环   红环+蓝芯片     校徽-线描.png 考试客户端-蓝红.ico  32 位 exe

**为什么留两版**：学校后来给了一枚自己做的徽章（金底红字，电路走线、芯片、
二进制都在里面），那枚用在 64 位上；更早那版是拿线描校徽自己套了一圈深蓝电路环
—— 老师要它留给 32 位。机房里两种 exe 并存，图标不一样，**拿到手不用看文件名
就知道是哪一份**（发错了的后果不对称：64 位那份在 32 位机器上根本起不来）。
配给谁在 build.py 的 `icon_for()`，改那儿。

**为什么小尺寸单独画**：16×16 的任务栏图标只有 256 个像素，徽章上的楼、英文、
二进制全糊成一团 —— 48×48 也一样糊。所以 48 及以下换成简笔版，64 起才用校徽。
ico 本来就允许每个尺寸放不一样的图。

    16 / 24 / 32 / 48    简笔版：环 + 芯片    任务栏、Alt+Tab、资源管理器中图标
    64 / 128 / 256       校徽               大图标、属性页、桌面快捷方式
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
RED = (214, 32, 25)            # 校徽那个红
GOLD = (236, 218, 148)         # 校徽的金底（从图里量的）
NAVY = (23, 58, 110)           # 电路环的深蓝：印在白底上够沉，缩小也不糊
CYAN = (0, 150, 199)           # 节点高光
WHITE = (255, 255, 255, 255)
BG = (255, 255, 255, 0)        # 透明底，贴在深色任务栏上也干净

SIZES = (256, 128, 64, 48, 32, 24, 16)
BIG = 1024                     # 先画大的再缩，边缘才干净
SS = 4                         # 金红那版先放大 4 倍画，缩回去边才平滑


# ================================================================ 金红：校徽原样
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


# ================================================================ 蓝红：洗底
def clean_badge(src: Path, size: int) -> Image.Image:
    """把徽章抠出来：去掉底色，只留线条，摆进一个正方形里。

    判据是"离底色有多远"，**不是"有多亮"**：这枚线描徽章的底是米色带噪点的
    （约 200,200,150），红线条是 (224,0,0)。按亮度切的话，米色只比红色亮一点，
    切出来会留一层带噪点的脏底；按"离底色的距离"切，米色归零、红线全留。

    底色不写死，从图里量 —— 学校哪天换成蓝底金字的徽章，这段不用改。
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


# ================================================================ 电路环 / 芯片
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


def chip(size: int, box: float, color: tuple, hole: tuple) -> Image.Image:
    """一枚芯片：圆角方块 + 四边引脚 + 中间的方孔。信息科技最好认的符号。

    两种样式共用这一枚，只是配色不同：金红那版红芯片开金孔（跟着校徽的金底），
    蓝红那版蓝芯片开白孔（跟着电路环的深蓝）。
    """
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = size / 2
    half = box / 2
    pin = box * 0.17
    w = max(2, int(size * 0.016))

    for i in range(3):
        off = -box * 0.28 + i * box * 0.28
        d.line([c + off, c - half - pin, c + off, c - half], fill=color, width=w)
        d.line([c + off, c + half, c + off, c + half + pin], fill=color, width=w)
        d.line([c - half - pin, c + off, c - half, c + off], fill=color, width=w)
        d.line([c + half, c + off, c + half + pin, c + off], fill=color, width=w)

    d.rounded_rectangle([c - half, c - half, c + half, c + half],
                        radius=box * 0.16, fill=color)
    inner = box * 0.3
    d.rounded_rectangle([c - inner, c - inner, c + inner, c + inner],
                        radius=box * 0.08, fill=hole)
    return im


# ================================================================ 两种样式
def style_gold(src: Path) -> tuple:
    """学校自己那枚徽章，原样。大图不加任何东西 —— 电路、芯片、二进制、code
    它自己都有，再往外套只会打架。小图退成"金盘 + 红环 + 芯片"，配色跟着校徽走，
    所以缩到 16 像素也还是"同一家的东西"。"""
    big = round_badge(src, BIG)

    small = Image.new("RGBA", (BIG, BIG), BG)
    c, r = BIG / 2, BIG * 0.47
    ImageDraw.Draw(small).ellipse([c - r, c - r, c + r, c + r], fill=GOLD + (255,),
                                  outline=RED, width=int(BIG * 0.06))
    small.alpha_composite(chip(BIG, BIG * 0.44, RED, GOLD + (255,)))
    return big, small


def style_navy(src: Path) -> tuple:
    """线描校徽 + 深蓝电路环：校徽原样摆中间（学校的东西不改），外面套一圈电路。
    既是这所学校的，又一眼看出是信息科技考试用的。"""
    big = Image.new("RGBA", (BIG, BIG), BG)
    c = BIG / 2
    # 白底圆盘：这版徽章是线条画，贴在深色任务栏上没有底会散
    ImageDraw.Draw(big).ellipse([c - BIG * 0.485, c - BIG * 0.485,
                                 c + BIG * 0.485, c + BIG * 0.485], fill=WHITE)
    big.alpha_composite(circuit_ring(BIG, BIG * 0.415, BIG * 0.468, nodes=12))
    badge = clean_badge(src, int(BIG * 0.80))
    big.alpha_composite(badge, (int(c - badge.width / 2), int(c - badge.height / 2)))

    small = Image.new("RGBA", (BIG, BIG), BG)
    r = BIG * 0.47
    ImageDraw.Draw(small).ellipse([c - r, c - r, c + r, c + r], fill=WHITE,
                                  outline=RED, width=int(BIG * 0.055))
    small.alpha_composite(chip(BIG, BIG * 0.44, NAVY, WHITE))
    return big, small


STYLES = {
    #  样式     画法    源图             出到                 预览前缀
    "金红": (style_gold, "校徽.png", "考试客户端.ico", "预览-金红"),
    "蓝红": (style_navy, "校徽-线描.png", "考试客户端-蓝红.ico", "预览-蓝红"),
}


# ================================================================ 组装
def make(style: str, src: Path, out: Path) -> int:
    draw, _, _, preview = STYLES[style]
    if not src.exists():
        print(f"[{style}] 没找到源图：{src}\n"
              f"        把徽章存成这个名字（越大越清楚越好，≥512 最佳）再跑一次。")
        return 1

    big, small = draw(src)
    big.resize((512, 512), Image.LANCZOS).save(HERE / f"{preview}-大.png")
    small.resize((512, 512), Image.LANCZOS).save(HERE / f"{preview}-小.png")

    frames = []
    for s in SIZES:
        # 48 以下一律用简笔版：校徽缩到 48 只剩一团糊，认不出是什么。
        # ico 允许每个尺寸放不一样的图，就是为了这个
        base = big if s >= 64 else small
        one = base.resize((s, s), Image.LANCZOS)
        if s <= 32:                     # 缩得太狠会发灰，锐一下
            one = one.filter(ImageFilter.SHARPEN)
        frames.append(one)
    frames[0].save(out, format="ICO",
                   sizes=[(s, s) for s in SIZES], append_images=frames[1:])

    # PyInstaller 只吃 .ico；另存一份 PNG 备用（网页端 favicon 之类）
    big.resize((256, 256), Image.LANCZOS).save(out.with_suffix(".png"))
    print(f"[{style}] 做好了：{out.name}")
    print(f"        预览 {preview}-大.png（64 及以上用这张）、"
          f"{preview}-小.png（48 及以下）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="校徽 → exe 图标")
    ap.add_argument("--样式", dest="style", choices=list(STYLES), default="",
                    help="只做一种；不写就两种都做")
    ap.add_argument("--src", default="", help="换一张源图（只在指定了 --样式 时有效）")
    ap.add_argument("--out", default="", help="换个输出路径（同上）")
    args = ap.parse_args()

    if args.style:
        _, src, out, _ = STYLES[args.style]
        return make(args.style, Path(args.src or HERE / src),
                    Path(args.out or HERE / out))
    if args.src or args.out:
        print("--src / --out 要配合 --样式 用：两种样式各有各的源图和出口。")
        return 2

    bad = 0
    for style, (_, src, out, _) in STYLES.items():
        bad |= make(style, HERE / src, HERE / out)
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
