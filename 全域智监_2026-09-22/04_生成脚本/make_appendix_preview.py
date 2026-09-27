# -*- coding: utf-8 -*-
"""Preview of Appendix A (GF-2 official parameters)."""
from PIL import Image, ImageDraw, ImageFont
import pathlib, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")
F = "C:/Windows/Fonts/"

T1_HEAD = ["参数项", "技术指标", "说明"]
T1 = [
    ["发射时间", "2014 年 8 月 19 日", "于太原卫星发射中心发射"],
    ["轨道类型", "太阳同步回归轨道", "降交点地方时约上午 10:30"],
    ["轨道高度", "631 km", "兼顾覆盖范围与成像分辨率"],
    ["回归周期", "69 天", "不侧摆成像时的全球覆盖周期"],
    ["侧摆能力", "±35°", "具备快速姿态机动能力"],
    ["重访周期", "侧摆条件下约 5 天", "满足“周级”动态监测的频次需求"],
    ["全色分辨率", "星下点 0.8 m", "我国首颗分辨率优于 1 m 的民用光学遥感卫星"],
    ["多光谱分辨率", "星下点 3.2 m", "与全色影像融合后提升地类判别能力"],
    ["成像幅宽", "45 km", "由两台相机拼接实现"],
    ["定位精度", "无地面控制点时约 50 m（CE90）", "保障多时相影像的几何配准精度"],
]
T1_NOTE = "注：表中“星下点”指卫星垂直投影点处的成像分辨率，为载荷实际成像指标；相机标称指标为全色 1 m、多光谱 4 m。"

T2_HEAD = ["谱段", "波长范围", "主要用途"]
T2 = [
    ["全色", "0.45–0.90 μm", "提供高分辨率灰度影像，用于地块边界、田埂与侵蚀沟等几何细节判读"],
    ["蓝", "0.45–0.52 μm", "水体识别与大气校正，辅助地表反射率反演"],
    ["绿", "0.52–0.59 μm", "表征植被反射特征，用于作物长势与植被覆盖监测"],
    ["红", "0.63–0.69 μm", "叶绿素吸收波段，与近红外组合可计算 NDVI 等植被指数"],
    ["近红外", "0.77–0.89 μm", "对植被与土壤水分敏感，用于植被覆盖度与土壤有机质反演"],
]

W, H = 1240, 2100
bg = Image.open(BASE / "项目计划书图片" / "背景淡12.png").resize((W, H), Image.LANCZOS)
d = ImageDraw.Draw(bg)

f_h1 = ImageFont.truetype(F + "msyhbd.ttc", 40)
f_h2 = ImageFont.truetype(F + "msyhbd.ttc", 30)
f_cap = ImageFont.truetype(F + "msyh.ttc", 23)
f_tb = ImageFont.truetype(F + "msyh.ttc", 21)
f_th = ImageFont.truetype(F + "msyhbd.ttc", 21)
f_note = ImageFont.truetype(F + "msyh.ttc", 20)

GREEN, DARK, TEXT, LINE, MUTED = (45, 106, 79), (27, 67, 50), (43, 43, 43), (120, 130, 120), (100, 105, 100)

MARGIN = 105
TOTAL = W - 2 * MARGIN
PAD = 9
LH = 29


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


def draw_table(x0, y, ratio, head, rows, caption):
    cols = [TOTAL * r / sum(ratio) for r in ratio]
    d.text((x0 + TOTAL / 2 - d.textlength(caption, font=f_cap) / 2, y), caption, font=f_cap, fill=TEXT)
    y += 36

    def rheight(cells, font):
        n = 1
        for txt, cw in zip(cells, cols):
            n = max(n, len(wrap(txt, font, cw - 2 * PAD)))
        return n * LH + 2 * PAD

    hh = rheight(head, f_th)
    d.rectangle([(x0, y), (x0 + TOTAL, y + hh)], outline=LINE, width=2)
    cx = x0
    for i, (h, cw) in enumerate(zip(head, cols)):
        lines = wrap(h, f_th, cw - 2 * PAD)
        ty = y + PAD + (hh - 2 * PAD - len(lines) * LH) / 2
        for ln in lines:
            d.text((cx + cw / 2 - d.textlength(ln, font=f_th) / 2, ty), ln, font=f_th, fill=TEXT)
            ty += LH
        if i:
            d.line([(cx, y), (cx, y + hh)], fill=LINE, width=2)
        cx += cw
    y += hh

    for cells in rows:
        rh = rheight(cells, f_tb)
        d.rectangle([(x0, y), (x0 + TOTAL, y + rh)], outline=LINE, width=2)
        cx = x0
        for i, (txt, cw) in enumerate(zip(cells, cols)):
            lines = wrap(txt, f_tb, cw - 2 * PAD)
            ty = y + PAD + (rh - 2 * PAD - len(lines) * LH) / 2
            for ln in lines:
                if i == 0:
                    d.text((cx + cw / 2 - d.textlength(ln, font=f_tb) / 2, ty), ln, font=f_tb, fill=TEXT)
                else:
                    d.text((cx + PAD, ty), ln, font=f_tb, fill=TEXT)
                ty += LH
            if i:
                d.line([(cx, y), (cx, y + rh)], fill=LINE, width=2)
            cx += cw
        y += rh
    return y


y = 90
d.text((MARGIN, y), "附录 A　高分二号（GF-2）卫星技术参数", font=f_h1, fill=DARK)
y += 58
d.line([(MARGIN, y), (W - MARGIN, y)], fill=GREEN, width=4)
y += 34
d.text((MARGIN, y), "本附录汇总高分二号（GF-2）卫星的公开技术参数，作为正文第七章“项目技术的支撑”的资料性补充，"
                    "表中参数依据该卫星官方公布数据整理。", font=f_cap, fill=TEXT)
y += 52

d.text((MARGIN, y), "A.1 平台与载荷主要参数", font=f_h2, fill=GREEN)
y += 48
y = draw_table(MARGIN, y, [3.4, 5.4, 4.6], T1_HEAD, T1, "表 A-1  高分二号（GF-2）卫星平台与载荷主要参数")
y += 8
d.text((MARGIN, y), T1_NOTE, font=f_note, fill=MUTED)
y += 64

d.text((MARGIN, y), "A.2 谱段设置与主要用途", font=f_h2, fill=GREEN)
y += 48
y = draw_table(MARGIN, y, [2.4, 3.4, 7.6], T2_HEAD, T2, "表 A-2  高分二号（GF-2）卫星谱段设置及本项目用途")

bg.crop((0, 0, W, y + 70)).save(BASE / ".claude" / "appendix_preview.png")
print("附录预览: .claude/appendix_preview.png")
