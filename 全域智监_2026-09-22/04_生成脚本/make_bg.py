# -*- coding: utf-8 -*-
"""Prepare an A4-proportioned, lightened page background from 背景.png."""
from PIL import Image, ImageEnhance
import pathlib, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")
src = BASE / "背景.png"
out = BASE / "项目计划书图片"
out.mkdir(exist_ok=True)

im = Image.open(src).convert('RGB')
W, H = im.size
print(f"原图: {W} x {H}")

# 1) 居中裁剪到 A4 比例（210:297）
ratio = 210 / 297
if W / H > ratio:
    nw = int(H * ratio)
    im = im.crop(((W - nw) // 2, 0, (W - nw) // 2 + nw, H))
else:
    nh = int(W / ratio)
    im = im.crop((0, (H - nh) // 2, W, (H - nh) // 2 + nh))
print(f"A4 裁剪后: {im.size[0]} x {im.size[1]}")

# 2) 提高亮度、降低饱和，便于压住文字
im = ImageEnhance.Brightness(im).enhance(1.15)
im = ImageEnhance.Color(im).enhance(0.65)

# 3) 与白底混合得到不同浓度的淡化版本
ALPHAS = [(0.08, '07'), (0.12, '12'), (0.18, '18')]
white = Image.new('RGB', im.size, (255, 255, 255))
thumbs = []
for a, tag in ALPHAS:
    v = Image.blend(white, im, a)
    name = out / f"背景_淡{tag}.png"
    v.save(name)
    print(f"  生成 {name.name}  (不透明度 {int(a*100)}%)")
    thumbs.append((tag, v))

# 4) 三联对比图（缩略）
tw, th = 420, 594
strip = Image.new('RGB', (tw * len(thumbs) + 20 * (len(thumbs) - 1), th + 40), (255, 255, 255))
for i, (tag, v) in enumerate(thumbs):
    strip.paste(v.resize((tw, th), Image.LANCZOS), (i * (tw + 20), 40))
strip.save(BASE / ".claude" / "bg_compare.png")
print("对比图: .claude/bg_compare.png")
