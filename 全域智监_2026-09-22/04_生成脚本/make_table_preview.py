# -*- coding: utf-8 -*-
"""Render a preview of the GF-2 official-parameter table as it will appear on the page."""
from PIL import Image, ImageDraw, ImageFont
import pathlib, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")
F = "C:/Windows/Fonts/"

HEAD = ["参数类别", "技术指标", "对本项目的支撑作用"]
ROWS = [
    ["发射与轨道", "2014 年 8 月 19 日发射；太阳同步回归轨道，轨道高度 631 km，回归周期 69 天",
     "成像光照条件稳定、重访规律，保障多时相影像可比"],
    ["空间分辨率", "星下点全色 0.8 m、多光谱 3.2 m",
     "亚米级成像可清晰分辨地块边界、植被覆盖度与侵蚀沟等细部特征"],
    ["成像幅宽", "45 km（两台相机组合）", "单景覆盖范围大，减少区域监测所需的影像拼接与重访次数"],
    ["侧摆与重访", "侧摆能力 ±35°，侧摆条件下重访周期约 5 天", "支撑“周级”动态监测的频次要求"],
    ["载荷谱段", "全色 0.45–0.90 μm；多光谱：蓝 0.45–0.52、绿 0.52–0.59、红 0.63–0.69、近红外 0.77–0.89 μm",
     "覆盖植被与土壤诊断光谱区间，支持植被指数计算与地力指标反演"],
    ["定位精度", "无地面控制点时约 50 m（CE90）", "保障多时相影像几何配准精度，减少配准误差引起的伪变化"],
    ["数据供给", "国产民用高分辨率卫星，产品成熟稳定", "数据来源自主可控，保障长时序监测档案的连续性"],
]
NOTE = "注：表中参数依据高分二号卫星官方公布数据整理。"

W, H = 1240, 1650
bg = Image.open(BASE / "项目计划书图片" / "背景淡12.png").resize((W, H), Image.LANCZOS)
d = ImageDraw.Draw(bg)

f_h2 = ImageFont.truetype(F + "msyhbd.ttc", 34)
f_cap = ImageFont.truetype(F + "msyh.ttc", 23)
f_tb = ImageFont.truetype(F + "msyh.ttc", 22)
f_th = ImageFont.truetype(F + "msyhbd.ttc", 22)

GREEN, TEXT, LINE = (45, 106, 79), (43, 43, 43), (120, 130, 120)

x0, y = 105, 90
d.text((x0, y), "2.GF-2卫星的核心技术优势", font=f_h2, fill=GREEN)
y += 58
d.text((x0, y), "……上述参数与数据保障条件彼此配合，共同支撑起从影像获取到变化检测的完整链路。"
                 "表 1 汇总了 GF-2 的主要技术参数及其对本项目的支撑作用。", font=f_cap, fill=TEXT)
y += 50
y_cap = y
y += 34

TOTAL = W - 210
RATIO = [2.6, 5.6, 5.8]
cols = [TOTAL * r / sum(RATIO) for r in RATIO]
PAD = 10


def wrap(text, font, maxw):
    lines, cur = [], ""
    for ch in text:
        if d.textlength(cur + ch, font=font) <= maxw:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def row_height(cells, font):
    n = 1
    for txt, cw in zip(cells, cols):
        n = max(n, len(wrap(txt, font, cw - 2 * PAD)))
    return n * 30 + 2 * PAD


d.text((x0 + TOTAL / 2 - 268, y_cap), "表 1  高分二号（GF-2）卫星主要技术参数及其对本项目的支撑",
       font=f_cap, fill=TEXT)

hh = row_height(HEAD, f_th)
d.rectangle([(x0, y), (x0 + TOTAL, y + hh)], outline=LINE, width=2)
cx = x0
for i, (h, cw) in enumerate(zip(HEAD, cols)):
    lines = wrap(h, f_th, cw - 2 * PAD)
    ty = y + PAD + (hh - 2 * PAD - len(lines) * 30) / 2
    for ln in lines:
        d.text((cx + cw / 2 - d.textlength(ln, font=f_th) / 2, ty), ln, font=f_th, fill=TEXT)
        ty += 30
    if i:
        d.line([(cx, y), (cx, y + hh)], fill=LINE, width=2)
    cx += cw
y += hh

for cells in ROWS:
    rh = row_height(cells, f_tb)
    d.rectangle([(x0, y), (x0 + TOTAL, y + rh)], outline=LINE, width=2)
    cx = x0
    for i, (txt, cw) in enumerate(zip(cells, cols)):
        lines = wrap(txt, f_tb, cw - 2 * PAD)
        ty = y + PAD + (rh - 2 * PAD - len(lines) * 30) / 2
        for ln in lines:
            if i == 0:
                d.text((cx + cw / 2 - d.textlength(ln, font=f_tb) / 2, ty), ln, font=f_tb, fill=TEXT)
            else:
                d.text((cx + PAD, ty), ln, font=f_tb, fill=TEXT)
            ty += 30
        if i:
            d.line([(cx, y), (cx, y + rh)], fill=LINE, width=2)
        cx += cw
    y += rh

y += 8
d.text((x0, y), NOTE, font=f_cap, fill=(90, 95, 90))

bg.crop((0, 0, W, y + 60)).save(BASE / ".claude" / "table_preview.png")
print("表格预览: .claude/table_preview.png")
