# -*- coding: utf-8 -*-
"""把两张架构图重放进 Visio，生成原生 .vsdx。

    python make_visio.py                # 两张都做
    python make_visio.py 系统架构图      # 只做一张（调试用）

原理见 Visio工具箱/README.md 的「路线 A」：先跑图脚本、在 Axes 层录下每个
图元，再重放进 Visio。好处是**图和代码永远同步** —— 改脚本、重跑，vsdx 跟着变，
不需要手工维护第二份元素清单。

产出：
    out/系统架构图.vsdx
    out/业务架构图.vsdx

字体：拉丁走 Arial、中文走微软雅黑。visio_emit 原本把 Char.AsianFont 也设成
Times New Roman，中文会被 Windows 字体链接兜到宋体上去；本仓库已改为分开设置。

注意（README 3.1）：**别用 COM 的 ExportAsFixedFormat 导 PDF**，文字会糊。
要 PDF 就在 Visio 里「文件 → 导出 → 创建 PDF/XPS」。
"""

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
TOOLBOX = HERE.parent.parent / "Visio工具箱"

sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TOOLBOX))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import figrecord as R      # noqa: E402
import visio_emit as E     # noqa: E402

FIGS = [
    ("系统架构图", "sys_arch.py"),
    ("业务架构图", "biz_arch.py"),
]

OUT = HERE / "out"
EMB = HERE / "_embed"


def main():
    if not TOOLBOX.is_dir():
        print("找不到 Visio 工具箱:", TOOLBOX)
        return 1

    only = set(sys.argv[1:])
    OUT.mkdir(exist_ok=True)

    for name, script in FIGS:
        if only and name not in only:
            continue
        src = HERE / script
        print(".. 录制 %s" % script)
        log, g = R.record(str(src), want_globals=True)
        W, H = g["W"], g["H"]
        print("   %d 个图元，页面 %.1f x %.1f cm" % (len(log), W, H))

        dst = OUT / (name + ".vsdx")
        n = E.emit(log, W, H, str(dst), str(EMB),
                   latin_font="Arial", cjk_font="微软雅黑")
        print("OK  %s   %d 图元 -> %d 个 Visio 对象" % (dst, len(log), n))

    return 0


if __name__ == "__main__":
    sys.exit(main())
