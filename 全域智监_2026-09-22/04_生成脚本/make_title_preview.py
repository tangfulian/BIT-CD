# -*- coding: utf-8 -*-
"""Preview of the title page (扉页) with the competition info block."""
from PIL import Image, ImageDraw, ImageFont
import pathlib, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD")
F = "C:/Windows/Fonts/"

W, H = 1240, 1754
bg = Image.open(BASE / "项目计划书图片" / "背景淡12.png").resize((W, H), Image.LANCZOS)
d = ImageDraw.Draw(bg)

f_contest = ImageFont.truetype(F + "msyhbd.ttc", 31)   # \large\heiti
f_info = ImageFont.truetype(F + "msyh.ttc", 25)        # \normalsize
f_title = ImageFont.truetype(F + "msyhbd.ttc", 40)     # \LARGE\heiti
f_sub = ImageFont.truetype(F + "msyhbd.ttc", 31)       # \large\heiti
f_author = ImageFont.truetype(F + "msyh.ttc", 30)

DARK, TEXT = (27, 67, 50), (43, 43, 43)
MUTED = (80, 85, 80)


def center(text, font, y, fill):
    d.text(((W - d.textlength(text, font=font)) / 2, y), text, font=font, fill=fill)
    return y + font.size + 12


y = 300
y = center("中国国际大学生创新大赛（2026）", f_contest, y, DARK)
y += 10
y = center("项目赛道：新农科", f_info, y, TEXT)
y = center("产业命题赛道：哈尔滨航天恒星数据系统科技有限公司", f_info, y, TEXT)
y = center("命题名称：时序遥感大模型与多源数据协同的农业灾害智能监测及定损 Agent 系统", f_info, y, TEXT)

y += 60
y = center("基于人工智能的黑土地遥感动态变化监测系统", f_title, y, DARK)
y += 8
y = center("项目计划书（创意策划方案）", f_sub, y, DARK)

y += 180
y = center("汤福连    刘芮仲    于欣欣    张珏枫", f_author, y, TEXT)
y += 6
y = center("2026 年 9 月 22 日", f_info, y, MUTED)

bg.save(BASE / ".claude" / "title_preview.png")
print("扉页预览: .claude/title_preview.png")
