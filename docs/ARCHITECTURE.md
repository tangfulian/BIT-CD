# 系统架构

黑土地遥感变化检测系统的整体设计。面向要读懂这个仓库的人 —— 新人、
接手的人、以及三个月后的自己。

> 本文讲**结构与理由**。想跑起来看 [README](../README.md)，
> Agent 部分另见 [AGENT.md](AGENT.md)。

---

## 一、系统是什么

上传同一地块的前后两期遥感影像，输出变化区域与统计；在此基础上提供多模型
对比、多时相趋势、灾害定损与 AI 解读。

后端 FastAPI，前端原生 JavaScript 单页应用（**无构建步骤**），模型侧 PyTorch。

### 业务架构

![业务架构图](figures/out/业务架构图_Visio导出.png)

功能分成两行八模块，每个功能点对应导航里的一个页面或页面内的一个能力。
**底部那行标的是三种角色的可见范围，最容易踩的是「游客只放行『单张检测』1 页」**
—— 做浏览器端自动化时必须先建认证会话，否则只能看到 1 个页面，
看起来像「页面全挂了」。

---

## 二、整体架构

![系统架构图](figures/out/系统架构图_Visio导出.png)

上图分两条带：**上带是请求链路**（客户端 → 前端 → 接入层 → 后端服务 → AI 与模型），
**下带是支撑**（部署与运维 / 数据存储 / 文件与权重 / 外部依赖）。

> 图是**脚本画的，不是手摆的**。源码在 [`figures/`](figures/)：
> `sys_arch.py` 定义系统架构、`biz_arch.py` 定义业务架构、`diagram_kit.py` 是绘图原语，
> `make_visio.py` 把两者重放成 Visio 原生 `.vsdx`。
> **改 Python 重跑，图和代码一起变** —— 不需要手工维护第二份元素清单。

**为什么前端没有构建步骤**：这个项目的部署环境不总是能跑 Node。用原生
ES Modules + 自托管依赖（`frontend/vendor/`），整个前端就是一堆静态文件，
拷过去就能用。代价是没有打包优化，但换来了「不依赖任何 CDN、断网也能开」。

---

## 三、后端分层

```
backend/app/
  core/       7 个    配置、鉴权、限流、验证码、时间、日志、LLM 预算
  models/     6 个    SQLAlchemy 表定义
  schemas/    6 个    Pydantic 入参出参
  routers/   13 个    接口层（49 个端点）
  services/  12 个    业务逻辑
```

**分层的实际约束**：`routers/` 只做参数校验与权限判断，业务逻辑一律在
`services/`。

**最明显的例外是 `routers/detect.py`（492 行）** —— 其余模块都在 250 行以内，
它一个顶两个，同时承担了一部分编排。属于历史遗留，改动时注意别再往里堆。

### 各 routers 的端点分布

| 模块 | 端点数 | 职责 |
|---|:---:|---|
| `detect` | 12 | 单张/批量检测、模型清单、NDVI、配准检查、评估 |
| `series` | 6 | 多时相序列的增删查、趋势 |
| `auth` | 5 | 登录、注册、验证码、改密 |
| `admin` | 4 | 用户管理（**admin 专属**） |
| `ai` | 4 | 对话、分析报告、变化分类 |
| `plot` | 4 | 地块档案 |
| `disaster` | 3 | 定损测算、参数、草稿 |
| `history` | 3 | 检测记录的查/删/清空 |
| `agent` | 2 | Agent 两条通道（见 [AGENT.md](AGENT.md)） |
| `amap` | 2 | 逆地理编码、IP 定位 |
| `annotation` | 2 | 变化区域的标注 |
| `compare` | 1 | 两条记录的并排对比 |
| `status` | 1 | 模型信息、运行时长、资源、请求统计 |

---

## 四、数据模型

五张表，关系很简单：

```
users ──┬──< detection_results ──┬──< annotations
        │                        │
        │                        └── series_id ──> image_series
        │
        └──< plots
```

| 表 | 关键字段 | 说明 |
|---|---|---|
| `users` | `username` / `password_hash` / `role` | 角色只有 `admin` 与 `user` |
| `detection_results` | `ratio` / `change_pixel` / `lat_lng` / `mask_url` … | **`ratio` 存的是百分数**（已 ×100），不是 0~1 小数 |
| `image_series` | 多时相序列 | 一条序列把多期检测串起来 |
| `plots` | 地块档案 | 经纬度、面积、作物 |
| `annotations` | 人工标注 | 挂在某条检测记录上 |

**关于 `ratio` 的单位**：这是本项目最容易踩的坑。`detect_service.py` 里
`change_pixel / total_pixel * 100` 已经乘过 100，所以全站直接 `ratio + '%'`
即可 —— **任何地方再乘一次 100 都是 bug**（个人中心曾经就这样，显示的
「平均变化率」放大了一百倍）。

---

## 五、鉴权与权限

**技术栈**：JWT（`python-jose`）签发 + `bcrypt` 存口令。令牌放
`localStorage`，24 小时过期。

两个依赖项决定接口的准入：

| | 行为 |
|---|---|
| `get_current_user` | 无有效令牌 → 401 |
| `get_optional_user` | 无令牌也能过，返回 `None`（用于游客可用的接口） |

**权限面**（`role != "admin"` 的检查点）：

- `admin` —— 整个用户管理模块
- `agent` —— **仅浏览器通道**（`/agent/execute`）
- `annotation` / `compare` / `history` —— 不是「仅 admin」，而是
  **「本人或 admin」**，即普通用户只能碰自己的数据

**Agent 两条通道权限不同的理由**写在 `routers/agent.py` 的 docstring 里，
值得一读：浏览器通道会以管理员身份驱动真实 Chrome，属高权限；工具通道
全程以调用者本人的身份执行，能做的事与用户自己点界面完全相同，**因此
不构成提权**，所以只要登录即可。

---

## 六、检测流水线

### 模型注册表

7 个模型在 `detection_pipeline.py` 的 `SUPPORTED_MODELS` 注册：

| ID | 是否需要权重 |
|---|---|
| `DIFF` | **否** —— 像素级差分基准 |
| `BIT` · `FC_SIAM_DIFF` · `SNUNET` · `CHANGEFORMER` · `AFCF3D` · `BIT_LuojiaSET` | 是 |

### 「可用」≠「已注册」

`detect_service.is_model_available()` 区分三态：

```
注册表里没有        → False
不需要权重（DIFF）  → True
需要权重但磁盘没有  → False   ← 调用时才 503
```

**这是一个刻意的设计**：注册了但没下权重文件的模型，如果照常列给用户，
用户选完只会撞一个 503。所以提供查询接口给出**真实能力清单**，前端只列
真正能用的。

### 权重不随仓库分发

放到 `checkpoints/<模型ID>/best_ckpt.pt` 即被识别。缺权重的模型**显式失败**：
`get_model()` 抛 `ModelNotAvailableError`，接口返回 503 并说明缺哪个文件。

早期版本是「退回随机/ImageNet 初始化继续跑」—— 能出结果但明显变差，而且
以 HTTP 200 静默返回，前端与用户无从分辨。现在改成硬失败，理由写在
`ModelNotAvailableError` 的类注释里。

### 预处理归一化必须与训练一致

这是本项目最隐蔽的一类 bug：**归一化错了不会有任何报错**。模型照样输出一张
看起来正常的 0~1 概率图，只是整片区域被判成变化。

- 走 `scripts/train.py` → `core.utils.get_loaders` → `datasets.CD_dataset`
  训练出来的模型，归一化是 `mean=std=0.5`（输入落在 [-1,1]），见
  `datasets/data_utils.py` 的 `CDDataAugmentation.transform`。
- `AFCF3D` 有自己的训练流程与推理分支，ImageNet 统计量对它是正确的。

所以 `detect_service._build_transform(model_type)` 是**按模型选**的，
不再全局共用一份。`detect_change`、`evaluate_models`、`evaluate_scan`
三处都必须走它 —— 评估页以前也共用错的那份，会直接污染模型指标。

2026-10 实测（30 个 SYSU-CD 样本、阈值 0.5，变化率与真值的平均绝对误差）：

| 模型 | ImageNet 统计量 | `mean=std=0.5` |
|---|---:|---:|
| BIT（epoch 97） | 36.6 个百分点，28/30 样本高估 >1.5× | **2.8 个百分点，2/30** |
| AFCF3D | 1.2 个百分点（本来就对） | — |

---

## 七、前端结构

单个 `index.html` 承载 15 个页面容器（`.page-content`），靠
`.nav-item[data-page]` 切换，**不是路由** —— 没有 URL 变化，刷新回到默认页。

```
frontend/js/
  main.js        启动顺序、模块初始化
  navigator.js   页面切换（含游客只放行 single 一页的门槛）
  state.js       全局状态        eventBus.js   模块间通信
  api.js         接口封装         auth.js       登录态与游客额度
  detector.js    单张检测         batchDetector.js  批量
  history.js     历史             compare.js    对比
  evaluator.js   模型评估         timeline.js   时序
  bigscreen.js   数据看板         status.js     系统状态
  disaster.js    灾害定损         agent.js      Agent 面板
  mapViewer.js   地图             landInfo.js   地块档案
  ndviViewer.js  NDVI             reportGenerator.js  报告导出
  i18n.js + locales/             中英双语
```

**游客门槛**在 `navigator.js`：`Auth.isGuest() && page !== 'single'` ——
**游客只能看「单张检测」一页**，其余 14 页被登录遮罩拦住。做自动化测试
时必须先建认证会话。

---

## 八、外部依赖

| 依赖 | 用途 | 缺失时 |
|---|---|---|
| LLM（默认 DeepSeek） | 变化分类、分析报告、定损草稿、Agent | AI 相关功能降级，其余正常 |
| 高德地图 | 逆地理编码、地图底图 | 地图页降级 |
| 第三方 JS 库 | ECharts / jsPDF / html2canvas / GeoTIFF | **已自托管**，无外部依赖 |

前端第三方库全部在 `frontend/vendor/`，**不依赖任何 CDN**。
Service Worker 的预缓存清单与之同步，断网也能打开。

### LLM 是可换的

三个消费方（`ai_service` / `agent_service` / `tool_agent_service`）都走
**OpenAI 兼容端点**，不绑定任何专有 SDK。服务商、密钥、模型名全部来自
环境变量，换家只改 `.env`。

另有一道**按天累计的调用预算**（`core/llm_budget.py`）—— 端点限流是按分钟
的，拦不住「每 20 秒发一次的循环」那种一天跑掉几千次的失控。

---

## 九、部署

```bash
cp .env.example .env       # 填各项
DEPLOY_HOST=your.server bash deploy.sh
```

Docker Compose 起容器，默认 SQLite（走 PostgreSQL 另配 `DATABASE_URL`）。

**数据库迁移用 Alembic**，`init_db()` 在启动时自动执行。两个迁移都写了
`downgrade()`，所以回滚路径是通的。

---

## 十、这份文档没覆盖的

- **Agent 的两条通道与 7 个工具** —— 见 [AGENT.md](AGENT.md)
- 前端各页面的交互细节 —— 看 `frontend/js/` 对应模块
- 模型网络结构 —— 看 `models/`（从 AFCF3D-Net 等项目引入，非本项目所写）
