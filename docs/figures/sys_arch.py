# -*- coding: utf-8 -*-
"""黑土地遥感变化检测系统 —— 系统架构图。

画布 44 x 30 cm，直接用厘米坐标，与 Visio 页面一一对应。
分两条带：上带是请求链路（客户端 → 前端 → 接入 → 后端 → AI），
下带是支撑（部署 / 存储 / 文件 / 外部依赖）。

由 make_visio.py 录制并重放进 Visio；单独运行则输出 PNG 预览。
"""

import os

from diagram_kit import (C, FS, arrow, band, canvas, group,
                         line, stack_centered)

W, H = 44.0, 30.0

fig, ax = canvas(W, H)

# ---------------------------------------------------------------- 标题
band(ax, 0.8, 27.9, 42.4, 1.7, "黑土地遥感变化检测系统 · 系统架构")

# ---------------------------------------------------------------- 上带：请求链路
B1_Y, B1_H = 16.6, 10.2          # 容器下沿 / 高度
ROW_H, ROW_GAP = 1.50, 0.36
B1_TOP = B1_Y + B1_H
B1_MID = B1_Y + B1_H / 2

cols = [
    # (x, w, 标题, 副标题, [条目])
    (1.0, 4.4, "客户端", "浏览器访问", [
        "桌面浏览器",
        "移动浏览器",
        "无需安装",
    ]),
    (6.8, 10.6, "前端应用", "浏览器内 · 原生 ES Modules · 无构建步骤", [
        "单页入口 index.html · 15 个页面容器",
        "视图模块 js/*.js（按功能拆分）",
        "中英双语 i18n · 明暗双主题",
        "Service Worker 预缓存 · 断网可用",
        "vendor/ 自托管（ECharts / jsPDF / html2canvas / GeoTIFF）",
    ]),
    (18.8, 6.6, "接入层", "FastAPI · 同源", [
        "静态资源同源挂载",
        "JWT 鉴权",
        "游客可选鉴权",
        "接口限流",
        "每日 LLM 调用预算",
    ]),
    (26.8, 8.2, "后端服务", "FastAPI", [
        "接口层 routers · 13 模块 / 49 端点",
        "业务层 services · 12 模块",
        "检测流水线 · 变化计算",
        "AI 服务 · Agent 双通道",
        "灾害定损 · 时序趋势拟合",
    ]),
    (36.4, 6.6, "AI 与模型", "能力层", [
        "LLM · DeepSeek（可换服务商）",
        "变化类型分类 · 报告生成",
        "Agent · browser-use + Playwright",
        "模型 · PyTorch（7 种网络）",
        "权重 checkpoints/（未部署时如实降级）",
    ]),
]

for x, w, title, sub, items in cols:
    group(ax, x, B1_Y, w, B1_H, title, sub)
    stack_centered(ax, x + 0.3, B1_Y, B1_TOP, w - 0.6, ROW_GAP, ROW_H,
                   items, C["item_fc"], C["item_ec"], tc=C["item_text"])

# 链路箭头
for x0, x1 in ((5.4, 6.8), (17.4, 18.8), (25.4, 26.8), (35.0, 36.4)):
    arrow(ax, (x0, B1_MID), (x1, B1_MID))
ax.text(18.1, B1_MID + 0.55, "同源 fetch", ha="center", va="center",
        fontsize=FS - 1.2, color=C["muted"], zorder=5)

# ---------------------------------------------------------------- 下带：支撑
B2_Y, B2_H = 1.6, 11.2
B2_TOP = B2_Y + B2_H

sub_cols = [
    (1.0, 8.4, "部署与运维", "交付方式", [
        "Docker Compose 部署",
        "前端静态同源分发",
        "环境变量配置 .env",
        "Service Worker 离线缓存",
        "日志 logs/app.log",
    ]),
    (10.8, 11.6, "数据存储", "SQLAlchemy · SQLite / PostgreSQL", [
        "默认 SQLite，可切 PostgreSQL",
        "users · 账号与角色",
        "detection_results · 检测记录与结果路径",
        "plots · 地块档案",
        "image_series · 多时相序列 / annotations · 标注",
    ]),
    (23.8, 9.4, "文件与权重", "results/ · 不入库", [
        "掩膜 / 热力图 / 融合图 / 概率图",
        "T2 影像（重调阈值重建融合图要用）",
        "checkpoints/ · 模型权重",
        "uploads/ · Agent 附件落盘",
        "vendor/ · 自托管第三方库",
    ]),
    (34.6, 8.4, "外部依赖", "可选 / 可替换", [
        "LLM 服务商 · OpenAI 兼容端点",
        "高德地图 JS API",
        "第三方库全部自托管",
        "无外部 CDN 依赖",
    ]),
]

for x, w, title, sub, items in sub_cols:
    group(ax, x, B2_Y, w, B2_H, title, sub)
    stack_centered(ax, x + 0.3, B2_Y, B2_TOP, w - 0.6, ROW_GAP, ROW_H,
                   items, C["blue_fc"], C["blue_ec"], tc=C["blue_text"])

# ---------------------------------------------------------------- 上带 → 下带
#
# 落点要避开分组标题：标题水平居中在 y = B2_TOP + 0.62，箭头若竖着插在
# 组的中线上，箭头尖正好压住标题文字。下面每个落点都刻意偏到标题两侧。
GAP_TOP = B1_Y            # 16.6
GAP_BOT = B2_TOP          # 12.8
LBL_Y = GAP_BOT + 2.4     # 标签统一放在标题上方，避开 y=13.42 的标题行


def note(x, text):
    ax.text(x, LBL_Y, text, ha="center", va="center",
            fontsize=FS - 1.0, color=C["muted"], zorder=5)


# 后端 → 数据存储（斜线，落在组内偏右，避开居中的「数据存储」标题）
arrow(ax, (28.0, GAP_TOP), (20.5, GAP_BOT))
note(23.6, "SQLAlchemy 读写")

# 后端 → 文件与权重（竖直，走组内右侧）
arrow(ax, (32.0, GAP_TOP), (32.0, GAP_BOT))
note(30.4, "结果落盘")

# AI 与模型 → 外部依赖（竖直，走组内右侧）
arrow(ax, (42.0, GAP_TOP), (42.0, GAP_BOT))
note(40.2, "调用 LLM / 地图")

# 前端 → 部署（虚线，落在组内偏右）
line(ax, (9.5, GAP_TOP), (8.2, GAP_BOT + 1.1), ls="--")
arrow(ax, (8.2, GAP_BOT + 1.1), (8.2, GAP_BOT))
note(11.0, "静态分发")

# ---------------------------------------------------------------- 预览 PNG
# 这是 matplotlib 的快速预览，用来改图时不必开 Visio。
# **它不是交付物** —— Visio 里的实际渲染以 out/系统架构图_Visio导出.png 为准
# （导出方式见 make_visio.py 的说明；两者的排版一致，但字体由 Visio 决定）。
_d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(_d, exist_ok=True)
_p = os.path.join(_d, "系统架构图_预览.png")
fig.savefig(_p, dpi=110, facecolor="white")
print("预览已写出:", _p)
