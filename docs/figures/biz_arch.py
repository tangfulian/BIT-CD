# -*- coding: utf-8 -*-
"""黑土地遥感变化检测系统 —— 业务架构图。

两行 × 四模块，每模块 2 列 × 3 行的功能点；左侧绿列标出这一行是什么。
底部一行写清三种角色的可见范围 —— 这个系统有游客/用户/管理员三档权限，
不说清楚的话「有 15 个页面」会被误读成「谁都能看 15 个页面」。

由 make_visio.py 录制并重放进 Visio；单独运行则输出 PNG 预览。
"""

import os

from diagram_kit import (C, FS, band, box, canvas)

W, H = 44.0, 22.6

fig, ax = canvas(W, H)

# ---------------------------------------------------------------- 标题
band(ax, 0.8, 20.6, 42.4, 1.6, "黑土地遥感变化检测系统 · 业务架构")

ROW_H = 7.4
ROWS = [
    (12.2, "检测业务", "#2F7D46", [
        ("数据准备", [
            "地块信息配置", "地块档案管理", "经纬度定位",
            "作物与地类", "面积与权属", "地图选点",
        ]),
        ("变化检测", [
            "单张检测", "批量检测", "多模型对比",
            "阈值实时调节", "Otsu 自动阈值", "影像配准检查",
        ]),
        ("结果管理", [
            "检测历史", "结果并排对比", "变化区域标注",
            "掩膜 / 热力图", "报告导出", "单条记录删除",
        ]),
        ("时序与定损", [
            "多时相序列", "变化速率拟合", "灾害定损测算",
            "受灾分级", "经济损失估算", "人工查勘对比",
        ]),
    ]),
    (3.2, "智能与系统", "#1F5F8B", [
        ("AI 能力", [
            "AI Agent 对话", "自然语言指令", "变化类型分类",
            "分析报告生成", "定损说明草稿", "浏览器操控通道",
        ]),
        ("模型能力", [
            "模型清单", "批量模型评估", "阈值扫描曲线",
            "敏感性 / 特异性", "权重可用性", "系统运行状态",
        ]),
        ("数据可视化", [
            "数据看板", "检测地图", "NDVI 查看",
            "变化趋势图", "类型分布统计", "大屏展示",
        ]),
        ("账户与系统", [
            "个人中心", "用户管理", "登录与注册",
            "权限角色", "中英双语切换", "明暗双主题",
        ]),
    ]),
]

ROLE_W = 3.6
GAP = 1.2
MOD_W = (42.0 - ROLE_W - GAP - 3 * GAP) / 4.0     # 8.4

for row_y, role, role_color, modules in ROWS:
    # 左侧角色列
    box(ax, 1.0, row_y, ROLE_W, ROW_H, role, C["role_fc"], C["role_ec"],
        tc=C["role_text"], fs=12.0, bold=True, round_=0.2)

    for mi, (head, feats) in enumerate(modules):
        gx = 1.0 + ROLE_W + GAP + mi * (MOD_W + GAP)

        # 模块外框（浅底，把这一组圈起来）
        box(ax, gx, row_y, MOD_W, ROW_H, "", C["group_fc"], C["group_ec"],
            round_=0.18, ls="--", z=1)

        # 模块头
        box(ax, gx + 0.25, row_y + ROW_H - 1.6, MOD_W - 0.5, 1.3, head,
            C["head_fc"], C["head_ec"], tc=C["head_text"], fs=FS + 1.4,
            bold=True, round_=0.12)

        # 功能点 2 列 × 3 行
        cw = (MOD_W - 0.5 - 0.3) / 2.0
        ch, cgap = 1.30, 0.32
        top = row_y + ROW_H - 1.6 - 0.45          # 网格上沿
        for k, name in enumerate(feats):
            r, c = divmod(k, 2)
            box(ax, gx + 0.25 + c * (cw + 0.3),
                top - (r + 1) * ch - r * cgap,
                cw, ch, name, C["item_fc"], C["item_ec"],
                tc=C["item_text"], fs=FS, round_=0.10)

# ---------------------------------------------------------------- 角色可见范围
FOOT_Y, FOOT_H = 0.8, 1.4
box(ax, 1.0, FOOT_Y, 42.0, FOOT_H, "", C["group_fc"], C["group_ec"],
    round_=0.16, z=1)
roles = [
    ("游客", "仅「单张检测」1 页 · 3 次额度"),
    ("普通用户", "全部检测与分析功能，数据仅本人可见"),
    ("管理员", "额外拥有用户管理 · 可查看全站记录"),
]
seg = 42.0 / 3
for i, (who, what) in enumerate(roles):
    sx = 1.0 + i * seg
    if i:
        ax.plot([sx, sx], [FOOT_Y + 0.22, FOOT_Y + FOOT_H - 0.22],
                color=C["group_ec"], linewidth=1.0, zorder=2)
    ax.text(sx + seg / 2, FOOT_Y + FOOT_H / 2, "%s —— %s" % (who, what),
            ha="center", va="center", fontsize=FS, color=C["text"], zorder=3)

# ---------------------------------------------------------------- 预览 PNG
# matplotlib 快速预览，改图时不必开 Visio。交付物是 out/业务架构图.vsdx，
# 实际渲染以 out/业务架构图_Visio导出.png 为准。
_d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(_d, exist_ok=True)
_p = os.path.join(_d, "业务架构图_预览.png")
fig.savefig(_p, dpi=110, facecolor="white")
print("预览已写出:", _p)
