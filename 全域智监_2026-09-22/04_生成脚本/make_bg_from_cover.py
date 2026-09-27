# -*- coding: utf-8 -*-
"""Crop text-free regions of the cover artwork into A4-proportioned page backgrounds."""
import fitz, pathlib, sys, io
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")
OUTDIR = BASE / "项目计划书图片"
F = "C:/Windows/Fonts/"

# 渲染封面原稿（无大赛信息条的那一版）
doc = fitz.open(str(BASE / "项目计划书封面.pdf"))
pix = doc[0].get_pixmap(matrix=fitz.Matrix(3, 3))
cover = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
W, H = cover.size
print(f"封面渲染: {W} x {H}")

A4 = 210 / 297          # 0.7071
TW, TH = 1240, 1754     # 输出（A4 @150dpi）

# 候选裁切区（依据亮像素密度分析，避开标题/副标题/卫星/云海）
# 干净区：x0-720 与 x2160-2880 的上半部（亮像素<4%）
CROPS = {
    "左侧梯田": (0, 332, 720, 1350),          # 左下：深色梯田，无文字
    "右侧梯田": (2160, 0, 2880, 1018),        # 右上：梯田 + 云纹装饰
}


def prep(im, alpha):
    """裁剪 -> A4 比例 -> 提亮降饱和 -> 与白底混合"""
    w, h = im.size
    if w / h > A4:                       # 太宽，裁两侧
        nw = int(h * A4)
        im = im.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:                                # 太高，裁上下
        nh = int(w / A4)
        im = im.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    im = im.resize((TW, TH), Image.LANCZOS)
    im = ImageEnhance.Brightness(im).enhance(1.15)
    im = ImageEnhance.Color(im).enhance(0.65)
    return Image.blend(Image.new("RGB", (TW, TH), (255, 255, 255)), im, alpha)


made = []
for name, box in CROPS.items():
    for alpha, tag in ((0.12, "12"), (0.18, "18")):
        v = prep(cover.crop(box), alpha)
        fn = OUTDIR / f"背景{name}{tag}.png"
        v.save(fn)
        made.append((f"{name} {int(alpha*100)}%", v))
        print(f"  生成 {fn.name}")

# 对比图：现有背景 vs 新候选
existing = Image.open(OUTDIR / "背景淡12.png").resize((TW, TH), Image.LANCZOS)
items = [("现用（背景.png 12%）", existing)] + made
tw, th = 300, 424
strip = Image.new("RGB", (tw * len(items) + 16 * (len(items) - 1), th + 34), (255, 255, 255))
sd = ImageDraw.Draw(strip)
f = ImageFont.truetype(F + "msyh.ttc", 20)
for i, (label, im) in enumerate(items):
    x = i * (tw + 16)
    strip.paste(im.resize((tw, th), Image.LANCZOS), (x, 30))
    sd.text((x + tw / 2 - sd.textlength(label, font=f) / 2, 5), label, font=f, fill=(40, 40, 40))
strip.save(BASE / ".claude" / "bg_options.png")
print("对比图: .claude/bg_options.png")
