# -*- coding: utf-8 -*-
"""画架构图的公共原语。

坐标单位一律用**厘米**，画布就是 Visio 页面的实际尺寸 —— 这样脚本里写的
数字和 Visio 里的尺寸一一对应，改起来不用换算。

只使用 visio_emit 支持的那几种图元：
    FancyBboxPatch -> 矩形（圆角由 rounding_size 决定）
    FancyArrowPatch -> 带箭头的线
    Line2D / LineCollection -> 纯线
    Text -> 文本框
刻意**不用 Rectangle 和 Polygon**：visio_emit 会把每 3 个 Rectangle/Polygon
编成一个名为 box3d 的组（那是给论文里的立体方块用的），在我的图里只会把
任意三个框莫名编在一起，用户在 Visio 里一拆就散。用 FancyBboxPatch 可以绕开。
"""

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt                      # noqa: E402
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch   # noqa: E402

# 预览 PNG 里的中文字体。只影响 PNG；写进 Visio 的字体由 visio_emit 控制。
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
matplotlib.rcParams["axes.unicode_minus"] = False

# ---------------------------------------------------------------- 配色
C = {
    "band":      "#1F4E5F",   # 标题带
    "band_text": "#FFFFFF",
    "group_fc":  "#F7FBFD",   # 分组容器
    "group_ec":  "#8FC4D8",
    "group_lbl": "#2E7D9A",
    "head_fc":   "#FFE9B8",   # 模块头
    "head_ec":   "#D9AE55",
    "head_text": "#7A5210",
    "item_fc":   "#E8F6EC",   # 功能块
    "item_ec":   "#8FCBA4",
    "item_text": "#1F6B3B",
    "role_fc":   "#CDEFD4",   # 角色列
    "role_ec":   "#7FC48F",
    "role_text": "#175C31",
    "blue_fc":   "#E7F0FB",   # 客户端 / 数据块
    "blue_ec":   "#9CBFE8",
    "blue_text": "#1B4F87",
    "arrow":     "#7A8A99",
    "text":      "#1F2937",
    "muted":     "#5B6B7A",
}

FS = 8.0        # 功能块字号
FS_TITLE = 19.0
FS_GROUP = 10.0
FS_HEAD = 9.5


def canvas(w, h):
    """建一张 w x h 厘米的画布，返回 (fig, ax)。"""
    fig, ax = plt.subplots(figsize=(w / 2.54, h / 2.54))
    ax.set_xlim(0, w)
    ax.set_ylim(0, h)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    return fig, ax


def box(ax, x, y, w, h, text, fc, ec, tc=None, fs=FS, bold=False,
        round_=0.12, lw=1.0, ls="-", z=2, ha="center"):
    """一个矩形 + 居中的文字。x,y 是左下角。"""
    if round_ and round_ > 0:
        style = "round,pad=0,rounding_size=%.4f" % round_
    else:
        style = "square,pad=0"
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle=style,
        facecolor=fc, edgecolor=ec, linewidth=lw, linestyle=ls, zorder=z,
        mutation_aspect=1))
    if text:
        tx = x + w / 2 if ha == "center" else x + 0.25
        ax.text(tx, y + h / 2, text, ha=ha, va="center",
                fontsize=fs, color=tc or C["text"],
                fontweight="bold" if bold else "normal", zorder=z + 1,
                linespacing=1.35)


def group(ax, x, y, w, h, title=None, sub=None, z=1):
    """虚线分组容器。title 画在容器**上方**（所以调用方要留出高度）。"""
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.22",
        facecolor=C["group_fc"], edgecolor=C["group_ec"],
        linewidth=1.1, linestyle="--", zorder=z))
    if title:
        ax.text(x + w / 2, y + h + 0.62, title, ha="center", va="center",
                fontsize=FS_GROUP, color=C["group_lbl"], fontweight="bold",
                zorder=z + 1)
    if sub:
        ax.text(x + w / 2, y + h + 0.22, sub, ha="center", va="center",
                fontsize=FS_GROUP - 2.2, color=C["muted"], zorder=z + 1)


def band(ax, x, y, w, h, text, fc=None, tc=None, fs=FS_TITLE, z=4):
    """顶部标题带。"""
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.18",
        facecolor=fc or C["band"], edgecolor="none", zorder=z))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=tc or C["band_text"], fontweight="bold",
            zorder=z + 1)


def arrow(ax, p1, p2, color=None, lw=1.4, style="-|>", ls="-", z=3, rad=0.0):
    """带箭头的连线。rad 非 0 时画成弧线（绕行用）。"""
    ax.add_patch(FancyArrowPatch(
        p1, p2, arrowstyle=style, mutation_scale=11,
        color=color or C["arrow"], linewidth=lw, linestyle=ls,
        zorder=z, shrinkA=0, shrinkB=0,
        connectionstyle="arc3,rad=%.2f" % rad))


def line(ax, p1, p2, color=None, lw=1.4, ls="-", z=3):
    """纯线，无箭头。"""
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color=color or C["arrow"],
            linewidth=lw, linestyle=ls, zorder=z, solid_capstyle="butt")


def stack(ax, x, y0, y1, w, gap, h, items, fc, ec, tc=None, fs=FS, z=2,
          round_=0.10):
    """在 y0..y1 之间垂直居中摞一行等高小框。

    **items[0] 在最上面** —— 按阅读顺序给列表即可。最早写的版本是从下往上
    摞的，结果每组的条目上下颠倒（写的第一个跑到了最底下），很难一眼看出来。
    """
    total = len(items) * h + (len(items) - 1) * gap
    cy = y0 + (y1 - y0 - total) / 2 + total - h    # 最上面那个框的下沿
    for t in items:
        box(ax, x, cy, w, h, t, fc, ec, tc=tc, fs=fs, round_=round_, z=z)
        cy -= h + gap
    return cy + gap                                 # 最下面那个框的下沿


# 旧名，保留以免已有脚本报错
stack_centered = stack
