# -*- coding: utf-8 -*-
"""Generate an A4-PORTRAIT cover matching the text pages.

Layout (A4 210x297mm, 2480x3508 px):
  top    - competition info on the design's dark green
  middle - the complete "全域智监" calligraphy + subtitle cropped from the
           original artwork (crop box chosen wide enough to never cut strokes),
           followed by the terraced-field photo
  bottom - team members and date
"""
import fitz, pathlib, sys, io
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageFilter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")
OUT_PNG = BASE / "项目计划书图片" / "封面.png"
F = "C:/Windows/Fonts/"

W, H = 2480, 3508                      # A4 竖版 @300dpi×0.5

# ---------- 素材 1：封面设计稿 ----------
doc = fitz.open(str(BASE / "项目计划书封面.pdf"))
pix = doc[0].get_pixmap(matrix=fitz.Matrix(3, 3))
art = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)   # 2880 x 1620

# 副标题（"基于人工智能的卫星遥感动态变化监测系统"）比"全域智监"四字更宽，
# 裁切框必须按副标题的宽度取，否则两端会被切断；左右各留 80px 余量
TITLE_BOX = (80, 165, 2800, 840)       # 宽 2720, 高 675
title_block = art.crop(TITLE_BOX)
th = int(title_block.size[1] * W / title_block.size[0])
title_block = title_block.resize((W, th), Image.LANCZOS)
print(f"标题块: {title_block.size[0]}x{title_block.size[1]}  (裁自 {TITLE_BOX})")

# 深绿底色：取标题块上方一行像素的中位数，避免采到装饰高光
row = [art.getpixel((x, 160)) for x in range(400, 2500, 50)]
DARKGREEN = tuple(sorted(c[i] for c in row)[len(row) // 2] for i in range(3))
print(f"采样底色: {DARKGREEN}")

# ---------- 素材 2：梯田照片（与正文背景同源）----------
photo = Image.open(BASE / "背景.png").convert("RGB")

TOP_H, BOT_H = 360, 420
PHOTO_H = H - TOP_H - th - BOT_H
print(f"分区: 顶 {TOP_H} + 标题 {th} + 照片 {PHOTO_H} + 底 {BOT_H} = {TOP_H+th+PHOTO_H+BOT_H}")

pw, ph = photo.size
target_r = W / PHOTO_H
if pw / ph > target_r:
    nw = int(ph * target_r)
    photo = photo.crop(((pw - nw) // 2, 0, (pw - nw) // 2 + nw, ph))
else:
    nh = int(pw / target_r)
    photo = photo.crop((0, (ph - nh) // 2, pw, (ph - nh) // 2 + nh))
photo = photo.resize((W, PHOTO_H), Image.LANCZOS)

# ---------- 组装 ----------
canvas = Image.new("RGB", (W, H), DARKGREEN)
canvas.paste(title_block, (0, TOP_H))
canvas.paste(photo, (0, TOP_H + th))

# ---------- 叠加设计稿中的卫星 ----------
# 亮度分析：卫星（含光环）在 y 984~1564、大片云海在 y 1380~1560。
# 若把云海一起裁进来，卫星会被白色淹没；故只取卫星本体及上方深绿区域，再放大。
SAT_BOX = (1050, 995, 1900, 1370)           # 850 x 375：完整包住太阳能板与光环上缘
sat = art.crop(SAT_BOX)
BW = 1700                                    # 放大到 1700px（约 2 倍），卫星成为视觉主体
BH = int(sat.size[1] * BW / sat.size[0])
sat = sat.resize((BW, BH), Image.LANCZOS)

grad_v = Image.new("L", (BW, BH), 255)
dv = ImageDraw.Draw(grad_v)
for i in range(150):
    a = int(255 * (i / 150) ** 1.6)
    dv.line([(0, i), (BW, i)], fill=a)
    dv.line([(0, BH - 1 - i), (BW, BH - 1 - i)], fill=a)

grad_h = Image.new("L", (BW, BH), 255)
dh = ImageDraw.Draw(grad_h)
for i in range(240):
    a = int(255 * (i / 240) ** 1.6)
    dh.line([(i, 0), (i, BH)], fill=a)
    dh.line([(BW - 1 - i, 0), (BW - 1 - i, BH)], fill=a)

mask = ImageChops.darker(grad_v, grad_h)     # 四边同时柔化

# 裁切框内带进了两块云海（左下、右上），在绿色梯田上会呈突兀的白斑，用半透明深绿盖掉
ov = Image.new("RGBA", sat.size, (0, 0, 0, 0))
od = ImageDraw.Draw(ov)
CLOUD_MASK = (45, 88, 55, 215)
od.ellipse((0, 430, 450, 780), fill=CLOUD_MASK)          # 左下云斑
od.ellipse((1130, 340, 1510, 700), fill=CLOUD_MASK)      # 右上云斑
ov = ov.filter(ImageFilter.GaussianBlur(70))
sat = Image.alpha_composite(sat.convert("RGBA"), ov).convert("RGB")

sat_y = TOP_H + th + int(PHOTO_H * 0.35)     # 再往下放，位于照片区偏下
canvas.paste(sat, ((W - BW) // 2, sat_y), mask)
print(f"卫星: {BW}x{BH} @ y={sat_y}")

d = ImageDraw.Draw(canvas)

f_contest = ImageFont.truetype(F + "msyhbd.ttc", 66)
f_info = ImageFont.truetype(F + "msyh.ttc", 46)
f_team = ImageFont.truetype(F + "msyhbd.ttc", 58)
f_date = ImageFont.truetype(F + "msyh.ttc", 44)
WHITE, LIGHT = (255, 255, 255), tuple(min(255, c + 150) for c in DARKGREEN)


def ctext(text, font, y, fill):
    d.text(((W - d.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)


ctext("中国国际大学生创新大赛（2026）", f_contest, 62, WHITE)
ctext("赛道：国家级产业赛道　组别：成果转化组", f_info, 178, LIGHT)

ctext("汤福连    刘芮仲    于欣欣    张珏枫", f_team, H - BOT_H + 120, WHITE)
ctext("2026 年 9 月", f_date, H - BOT_H + 222, LIGHT)

canvas.save(OUT_PNG)

# ---------- 导出 A4 竖版 PDF ----------
jpg_out = OUT_PNG.with_suffix(".jpg")
canvas.save(jpg_out, "JPEG", quality=88, dpi=(300, 300))
pdf_out = OUT_PNG.with_suffix(".pdf")
pdoc = fitz.open()
pg = pdoc.new_page(width=210 / 25.4 * 72, height=297 / 25.4 * 72)
pg.insert_image(pg.rect, filename=str(jpg_out))
pdoc.save(str(pdf_out), deflate=True, garbage=4)
pdoc.close()

print(f"输出: {OUT_PNG.name}  {canvas.size[0]}x{canvas.size[1]} px")
print(f"输出: {pdf_out.name}  A4 竖版 210×297 mm（与正文页一致）")
