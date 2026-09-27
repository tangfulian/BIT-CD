# -*- coding: utf-8 -*-
"""Compose a simulated A4 page (background + heading + body + figure slot) so the
user can judge readability without compiling LaTeX."""
from PIL import Image, ImageDraw, ImageFont
import pathlib, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")
W, H = 1240, 1754          # A4 @150dpi
bg = Image.open(BASE / "项目计划书图片" / "背景_淡12.png").resize((W, H), Image.LANCZOS)
d = ImageDraw.Draw(bg)

F = "C:/Windows/Fonts/"
f_h1 = ImageFont.truetype(F + "msyhbd.ttc", 46)
f_h2 = ImageFont.truetype(F + "msyhbd.ttc", 34)
f_bd = ImageFont.truetype(F + "msyh.ttc", 25)
f_sm = ImageFont.truetype(F + "msyh.ttc", 22)

GREEN, DARK, TEXT, MUTED = (45, 106, 79), (27, 67, 50), (43, 43, 43), (120, 120, 120)

y = 120
d.text((105, y), "八、产品设计——模型、数据与系统三位一体", font=f_h1, fill=(27, 67, 50))
y += 62
d.line([(105, y), (W - 105, y)], fill=GREEN, width=4)
y += 40

d.text((105, y), "1.核心算法：BIT模型框架", font=f_h2, fill=GREEN)
y += 52

body = [
    "模型以改进的 ResNet18 为 CNN 骨干网络，对双时相输入影像进行特征提取，再通过",
    "语义分词器与双时序图像转换器，利用 Transformer 编码器捕捉全局时空上下文信息；",
    "最后通过解码器输出精细特征，经预测头生成最终的变化检测结果图，实现了高精度、",
    "低误判的黑土地变化检测。",
    "",
    "从数据流看，该框架可分为四个阶段：T1、T2 两个时刻的影像分别进入共享权重的",
    "ResNet18 骨干网络，得到两组空间分辨率逐级降低、通道数逐级增加的中间特征图；",
    "语义分词器对特征图做语义级压缩，将其转化为数量可控的语义 token 序列……",
]
for line in body:
    d.text((105, y), line, font=f_bd, fill=TEXT)
    y += 38

# 图片空位框
y += 24
d.rectangle([(105, y), (W - 105, y + 330)], outline=(150, 150, 150), width=2)
d.text((W // 2 - 120, y + 145), "【图片空位：image9.png】", font=f_sm, fill=MUTED)
y += 356
d.text((W // 2 - 140, y), "图 8-1  CNN 骨干网络特征提取拓扑结构", font=f_sm, fill=MUTED)

bg.save(BASE / ".claude" / "page_preview.png")
print("预览: .claude/page_preview.png")
