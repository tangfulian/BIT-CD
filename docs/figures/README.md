# 架构图的源码

`docs/ARCHITECTURE.md` 里那两张图是**脚本画的**，不是手摆的。

| 文件 | 作用 |
|---|---|
| `diagram_kit.py` | 绘图原语（框 / 分组 / 箭头 / 标题带）+ 配色 |
| `sys_arch.py` | 系统架构图 —— 请求链路 + 支撑两条带 |
| `biz_arch.py` | 业务架构图 —— 2 行 × 4 模块 × 6 功能点 |
| `make_visio.py` | 录制上面两个脚本的图元，重放进 Visio 生成 `.vsdx` |
| `out/` | 产物：`.vsdx` + 两种 PNG |

## 怎么改

```bash
# 只改排版、看效果（不开 Visio，秒出）
python sys_arch.py        # -> out/系统架构图_预览.png
python biz_arch.py        # -> out/业务架构图_预览.png

# 定稿后生成 Visio 源文件
python make_visio.py
```

坐标一律用**厘米**，画布尺寸就是 Visio 页面尺寸 —— 脚本里写的数字和 Visio 里
量到的一一对应，不用换算。

改内容只需要动 `sys_arch.py` / `biz_arch.py` 里那两个列表。

## 依赖

- Python：`matplotlib`、`pywin32`
- **本机装了 Visio**（`make_visio.py` 走 COM 驱动它）
- 工具库在项目根目录的 `Visio工具箱/`（**未入库**，见 `.gitignore` ——
  它是从另一个论文项目抽出来的，笔记里有那个项目的内部信息）。
  本仓库对它的 `visio_emit.py` 做了两处中文适配：文本宽度按 CJK 两倍计、
  `Char.AsianFont` 单独设成微软雅黑。细节写在那两个函数的注释里。

没有 Visio 也不影响：两个 `*_arch.py` 能独立跑出 PNG 预览，只是生成不了 `.vsdx`。

## 两个约定

**1. `_预览.png` 不是交付物。** 它是 matplotlib 的快速预览，字体由系统决定；
Visio 里的实际渲染以 `*_Visio导出.png` 为准。文档嵌的是后者。

**2. 别再手工编辑 `.vsdx`。** 它的每个形状都是脚本生成的，手工改完下次重跑就没了。
要改就改 Python。
