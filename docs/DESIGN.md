# BIT_CD 黑土地遥感变化检测系统 —— 设计文档

> 版本: v1.1 | 日期: 2026-05-29

---

## 1. 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (SPA - Vanilla JS)               │
│  index.html → main.js → 15 Pages + Chatbot Widget        │
│  ECharts | AMap | jsPDF | html2canvas                    │
└─────────────────┬───────────────────────────────────────┘
                  │ HTTP (JWT Bearer Token)
┌─────────────────▼───────────────────────────────────────┐
│               后端 (FastAPI + Uvicorn)                    │
│  11 Routers → Services → SQLAlchemy ORM                   │
│  Rate Limit (slowapi) | CORS | Static Files              │
└────────┬──────────────────────┬─────────────────────────┘
         │                      │
┌────────▼────────┐  ┌──────────▼────────────┐
│   SQLite        │  │  外部 API              │
│   (SQLAlchemy)  │  │  DashScope (Qwen)      │
│                 │  │  高德地图 (逆地理编码)   │
└─────────────────┘  │  Browser Use (Agent)   │
                     └───────────────────────┘
```

### 技术选型理由

| 组件 | 选择 | 理由 |
|------|------|------|
| 前端框架 | 原生 JS (ES Modules) | 无框架依赖，轻量 (< 2MB)，SPA 模式 |
| 后端框架 | FastAPI | 异步支持，自动 OpenAPI 文档，类型安全 |
| 数据库 ORM | SQLAlchemy 2.0 | 成熟稳定，支持 SQLite/PostgreSQL 双后端 |
| 深度学习 | PyTorch 2.x | 主流框架，预训练模型丰富 |
| AI 模型 | DashScope 千问 | 阿里云生态，OpenAI 兼容接口 |
| 地图 | 高德 JS API 2.0 | 国内地图服务，逆地理编码 |
| 图表 | ECharts 5.5.0 | 功能全面，主题定制 |
| 浏览器自动化 | browser-use 0.12 | 开源免费，Playwright 底层 |

---

## 2. 前端设计

### 2.1 整体布局

```
┌──────────┬──────────────────────────────────────┐
│ Sidebar  │  Main Content (.main-content)        │
│ 268px    │                                      │
│ fixed    │  ┌──────────────────────────────┐    │
│          │  │  Page Header (h1 + subtitle)  │    │
│  Logo    │  ├──────────────────────────────┤    │
│  Nav × 15│  │                              │    │
│          │  │  Page Content                │    │
│  Footer  │  │  (15 pages, only 1 active)   │    │
│          │  │                              │    │
│          │  └──────────────────────────────┘    │
│          │                                      │
│          │  ┌──────────┐                        │
│          │  │ Chatbot  │  (fixed, bottom-right) │
│          │  │ Widget   │                        │
│          │  └──────────┘                        │
└──────────┴──────────────────────────────────────┘
```

### 2.2 路由设计

采用 **data-page 属性映射**，无 URL 路由（纯 SPA 内部切换）：

```javascript
// navigator.js 核心逻辑
switchPage(page) {
  // 1. 移除所有 .nav-item.active
  // 2. 移除所有 .page-content.active
  // 3. 激活 document.getElementById("page-" + page)
  // 4. 触发页面特定的渲染/清理
}
```

15 个页面按 `data-page` 属性映射到 `#page-{name}` DOM 元素。

### 2.3 状态管理

轻量级全局状态对象 `state` (state.js)，无 Vuex/Redux：

- `currentUserRole` — 当前用户角色
- `chatHistory` — AI 对话上下文
- `batchResult` — 批量检测结果
- 其他模块内部自行管理状态（History._currentPage, Detector._currentResult 等）

### 2.4 国际化

纯 JSON 字典映射，零依赖：

```
locales/zh-CN.js → 中文键值对
locales/en.js    → 英文键值对
i18n.js          → t(key, ...args) 查询 + MutationObserver 自动翻译
```

HTML 使用 `data-i18n="key"` 属性标记需翻译元素，JS 使用 `I18n.t('key')`。

### 2.5 主题系统

CSS 自定义属性双主题方案：

```css
:root { --primary: #2c5e44; --bg-main: #f6f4f0; ... }
[data-theme="dark"] { --primary: #4ea877; --bg-main: #121a14; ... }
```

切换时修改 `<html data-theme="dark|light">`，所有组件自动适配。

### 2.6 组件通信

EventBus 发布/订阅模式 (eventBus.js)：

| 事件 | 触发者 | 监听者 |
|------|--------|--------|
| `lang-change` | I18n | 各模块刷新文案 |
| `navigate` | Notify | Navigator 切换页面 |
| `auth-change` | Auth | 各模块权限控制 |

---

## 3. 后端设计

### 3.1 分层架构

```
Routers (HTTP 层) → Services (业务逻辑) → Models (数据访问)
                         ↓
                   外部 API 调用 (DashScope, AMap, Browser Use)
```

### 3.2 数据库模型

```
┌──────────┐     ┌────────────────────┐     ┌──────────┐
│  UserDB   │1───*│  DetectionResultDB  │1───*│ AnnotationDB│
│  users    │     │  detection_results  │     │ annotations │
└──────────┘     └────────────────────┘     └──────────┘
       │
       │1───*  PlotDB (plots)
```

**UserDB** (users): id, username, password_hash, role (user/admin), disabled, created_at
**DetectionResultDB** (detection_results): id, user_id, model, threshold, ratio, change_pixel, total_pixel, lat_lng, location, change_type, t1_time, t2_time, ai_change_type, ai_confidence, mask_url, heat_url, fusion_url, score_url, image_pair_hash, created_at
**PlotDB** (plots): id, user_id, name, province, city, lat_lng, area, land_type, crop_type, data_source, change_type, t1_time, t2_time, created_at, updated_at
**AnnotationDB** (annotations): id, detection_id, user_id, annotation_data (JSON: base64 掩膜), created_at, updated_at

### 3.3 鉴权流程

```
注册: username + password + captcha → bcrypt hash → users 表
登录: username + password → 验证 bcrypt → JWT (HS256, 24h)
请求: Authorization: Bearer <token> → get_current_user() → UserDB
```

### 3.4 AI 服务设计

```
ai_service.py
  ├─ chat()            → DashScope qwen-turbo (通用对话)
  ├─ analyze_result()  → qwen-turbo (结构化分析报告)
  └─ classify_change() → qwen-turbo (6 分类)

agent_service.py
  ├─ _build_llm()         → qwen-vl-plus (视觉主模型)
  ├─ _build_fallback_llm()→ qwen-plus (文本备用)
  ├─ _launch_chrome()     → 手动启动 Chromium + CDP
  └─ execute_agent()      → BrowserProfile → Agent.run()
```

### 3.5 检测服务设计

```
detect_service.py
  ├─ run_detection()      → CDEvaluator 单模型推理
  ├─ compare_models()     → 多模型并行推理
  ├─ rethreshold()        → 阈值重应用
  ├─ compute_metrics()    → TP/FP/TN/FN → P/R/F1/IoU
  └─ compute_ndvi()       → (NIR-R)/(NIR+R)
```

MD5 缓存键 = `md5(t1_path + t2_path + model + threshold)`，结果存储于 `results/` 目录。

模型加载使用 `weights_only=False`（自定义架构不兼容安全加载模式，checkpoint 来自可信源）。

历史记录返回时通过 `_rewrite_url()` 将数据库中旧域名的 URL 重写为当前请求地址，确保结果图可访问。

### 3.6 安全设计

| 措施 | 实现 |
|------|------|
| 密码存储 | bcrypt (cost=12) |
| 令牌 | JWT HS256，24 小时过期 |
| 接口限流 | slowapi，全部接口覆盖（登录 5/分、注册 3/分、检测 10/分、Agent 3/分 等） |
| CORS | 白名单域名 + /results 静态文件 CORS 头注入（回显请求 Origin，不 fallback 到 `*`） |
| 请求体大小 | 50MB 中间件校验，防止大文件攻击 |
| SQL 注入 | SQLAlchemy ORM 参数化查询 |
| 文件上传 | 仅允许 image/jpeg/png/tiff/bmp，限制 10MB |
| Agent 限流 | 3 次/分钟，单次最长 10 分钟 |
| 日志安全 | 生产日志级别 INFO，避免泄露请求体中的敏感信息 |
| 密码重置 | API 响应不包含明文密码，由管理员口头告知 |

---

## 4. 深度学习模型设计

### 4.1 统一推理框架

所有模型实现 `CDEvaluator` 接口 (basic_model.py)：

```python
class CDEvaluator:
    def __init__(self, net_G, checkpoint_path, device)
    def _to_tensor(self, img_path) → Tensor
    def _detect(self, t1_path, t2_path, threshold) → score_map, mask
```

### 4.2 BIT 模型结构 (默认推荐)

```
T1 Image ──→ ResNet18 (4 stages) ──→ Tokenize + Position Embed ──┐
                                                                   ├──→ Transformer Decoder (8层) ──→ SegHead → Score Map
T2 Image ──→ ResNet18 (4 stages) ──→ Tokenize + Position Embed ──┘
```

ResNet18 在 ImageNet 预训练，Transformer Decoder 学习双时相差异特征。

### 4.3 模型权重

| 模型 | 预训练权重路径 |
|------|--------------|
| BIT | `checkpoints/BIT_LEVIR/best_ckpt.pt` |
| DIFF | 无需权重（像素差分基线） |
| FC_SIAM_DIFF | `checkpoints/FC_SIAM_DIFF/best_ckpt.pt` |
| SNUNET | `checkpoints/SNUNET/best_ckpt.pt` |
| CHANGEFORMER | `checkpoints/CHANGEFORMER/best_ckpt.pt` |
| AFCF3D | `checkpoints/AFCF3D/best_ckpt.pt` |
| BIT_LuojiaSET | `checkpoints/BIT_LuojiaSET/best_ckpt.pt` |

---

## 5. Agent 浏览器操控设计

### 5.1 架构

```
用户指令 → POST /agent/execute → agent_service.execute_agent()
    ├─ _launch_chrome() → chromium --remote-debugging-port=N
    ├─ ChatOpenAI(qwen-vl-plus) + ChatOpenAI(qwen-plus, fallback)
    ├─ BrowserProfile(cdp_url) → Agent(task, llm, browser_profile)
    └─ agent.run(max_steps=25) → {success, final_result, screenshots}
```

### 5.2 关键设计决策

| 决策 | 理由 |
|------|------|
| 手动启动 Chrome + CDP | browser-use 内置 launch 跨平台兼容性差，手动管理更可控 |
| 跨平台 Chrome 路径 | `os.environ.get("LOCALAPPDATA")` 动态适配 Windows/Linux/Docker |
| qwen-vl-plus + qwen-plus fallback | 视觉模型看截图，文本模型保证结构化输出 |
| 持久化 user_data_dir | 保留登录 Cookie，避免重复登录 |
| max_steps=25，timeout=600s | 平衡任务完整性与资源消耗 |
| 前端 600s AbortController | 匹配后端超时 |

---

## 6. 部署架构

### 生产环境（阿里云 ECS）
```
阿里云 ECS (1.6GB RAM, CentOS)
├─ Docker + docker-compose
├─ bitcd-app 容器 (FastAPI + Uvicorn, port 8000, HTTP)
├─ 2GB swap (缓解内存压力)
├─ ufw 防火墙 (仅开放 22/80/443/8000)
└─ SQLite (容器内持久化卷)
```

### Docker 模式
```
docker-compose up → bitcd-app (FastAPI + Uvicorn, 内嵌 StaticFiles, SQLite)
```

### 本地开发模式
```
python api.py                    # 后端 :8000
npx live-server frontend --port=5500  # 前端 :5500
```

### HTTP 限制说明

当前服务器仅支持 HTTP（无域名无法配置 HTTPS 证书）。以下浏览器 API 需要安全上下文（HTTPS 或 localhost）：
- **File System Access API** (`window.showDirectoryPicker`) — 用于文件夹批量选择

前端已做降级处理：在 HTTP 环境下隐藏文件夹选择按钮，显示文字提示。本地开发时使用 `localhost` 不受影响。
