import os
import secrets
import logging
from dotenv import load_dotenv

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
load_dotenv(os.path.join(_project_root, ".env"))

logger = logging.getLogger(__name__)

# --- JWT 密钥：未设置则随机生成（重启后 session 失效） ---
_jwt_secret = os.getenv("JWT_SECRET")
if not _jwt_secret:
    _jwt_secret = secrets.token_hex(32)
    logger.warning(
        "⚠️  JWT_SECRET 未设置！已生成随机值，服务重启后所有用户需重新登录。"
        "请在 .env 中设置 JWT_SECRET=<your-secret> 以持久化。"
    )
SECRET_KEY = _jwt_secret
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 24

# --- 管理员初始密码：仅首次创建 admin 用户时使用 ---
_admin_pwd = os.getenv("ADMIN_DEFAULT_PASSWORD")
if not _admin_pwd:
    _admin_pwd = secrets.token_urlsafe(12)
    logger.warning(
        "⚠️  ADMIN_DEFAULT_PASSWORD 未设置！已生成随机值，请妥善保存。"
        "请在 .env 中设置 ADMIN_DEFAULT_PASSWORD=<your-password>。"
    )
ADMIN_DEFAULT_PASSWORD = _admin_pwd

# --- 管理员重置用户密码时的默认密码 ---
_user_reset = os.getenv("USER_RESET_PASSWORD")
if not _user_reset:
    _user_reset = secrets.token_urlsafe(12)
    logger.warning(
        "⚠️  USER_RESET_PASSWORD 未设置！已生成随机值。"
        "请在 .env 中设置 USER_RESET_PASSWORD=<your-password>。"
    )
USER_RESET_PASSWORD = _user_reset

# --- 外部服务 API Key ---
AMAP_WEB_KEY = os.getenv("AMAP_WEB_KEY")
AMAP_API_BASE = "https://restapi.amap.com/v3"

# --- LLM 服务商（可切换，不需要改代码） ---
# 三个消费方（ai_service / agent_service / tool_agent_service）都从这里取值。
# 换服务商 = 改 .env 里的这几个变量，不用动任何 .py。
#
# 当前默认 DeepSeek。切换时务必注意**模型名与端点是绑定的**：
# 同一个服务商的不同端点，可用的模型 ID 可能不同，而且列模型的接口不一定
# 列全 —— 实测 DeepSeek 的 /models 只返回 deepseek-flash 与 deepseek-v4-pro，
# 但 deepseek-v4-flash 实际也能调。以真实调用为准，别信列表。
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
# 没有回退。曾经回退到 DASHSCOPE_API_KEY，但那带来一个隐患：LLM_API_KEY
# 被误删时会**静默**指回百炼，而此时若百炼已停缴，报错是 401 而不是
# 「配置缺了」，排查会绕远路。宁可缺了就明确报缺。
LLM_API_KEY = os.getenv("LLM_API_KEY")
# 文本用途：变化类型分类、分析报告、定损说明草稿
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-v4-flash")
# Agent 用途：需要**同时**支持视觉与 Function Calling。
# 实测 deepseek-v4-flash 两项都支持（deepseek-v4-pro 不支持视觉，别用）。
LLM_AGENT_MODEL = os.getenv("LLM_AGENT_MODEL", LLM_MODEL)
# Agent 备用模型：留空 = 不启用（browser_use 的 fallback_llm 允许为 None）。
# 有意义的是**跨服务商**的备用 —— 同一账号同一家会在限流/欠费时一起挂。
LLM_AGENT_FALLBACK_MODEL = os.getenv("LLM_AGENT_FALLBACK_MODEL", "")

# --- LLM 每日调用预算 ---
# 服务里已有一重防护，但都是**按请求**的：单请求超时、Agent 循环轮次上限、
# 端点限流（每分钟几次）。限流按分钟算，一个每 20 秒发一次的循环在它放开后
# 一天仍能跑掉几千次调用。
#
# 而这个项目的 LLM key 与开发者的 Claude Code **共用同一份额度** ——
# 一个失控的循环烧掉的是开发额度，不是「反正免费的测试额度」。
# 所以在限流之外再加一道按天累计的闸。
#
# 0 或负数 = 不限制。默认 500：正常演示一天用不到（一次检测 1 次分类调用，
# 一次 Agent 任务几次），但足以在几分钟内拦住跑飞的循环。
LLM_DAILY_CALL_LIMIT = int(os.getenv("LLM_DAILY_CALL_LIMIT", "500") or 0)

# --- AI Agent（Browser Use 操控前端） ---
# 默认 8000 而不是 5500：前端由本应用自己挂在 / 上（main.py 的 StaticFiles），
# 端口就是 uvicorn 的端口。5500 是 JetBrains IDE 预览的历史残留，没有任何服务
# 监听，用这个默认值会让 _inject_auth 的 page.goto 直接超时。
AGENT_FRONTEND_URL = os.getenv("AGENT_FRONTEND_URL", "http://localhost:8000")
AGENT_USERNAME = os.getenv("AGENT_USERNAME", "admin")
# 不再需要 AGENT_PASSWORD：Agent 改为直接签发 token 并经 CDP 注入 localStorage
# （见 agent_service._inject_auth），不再走「用账号密码登录表单」的老路。
# 原先这里会读取 AGENT_PASSWORD，未设置时生成随机值并打警告——但那个值从来没有
# 被任何代码读过，只会让每次启动都刷一条无意义的警告。故整块移除。
AGENT_BROWSER_HEADLESS = os.getenv("AGENT_BROWSER_HEADLESS", "true").lower() == "true"
# 此处曾有 AGENT_MAX_STEPS，已移除：全仓库只有 agent_service import 了它、
# 从未使用，步数实际由 /agent/execute 的表单参数决定（默认 25）。留着会让
# .env 里的设置看起来生效而实际无效——与上面 AGENT_PASSWORD 同一类问题。

# --- CORS：逗号分隔的允许来源列表，默认限制 localhost ---
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:63342,http://localhost:3000,http://127.0.0.1:8000"
).split(",")

# --- 数据库 ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./blackland.db")

def _is_sqlite(url: str) -> bool:
    return "sqlite" in url

ML_CONFIG = {
    "project_name": "test",
    "gpu_ids": "0",
    "checkpoint_root": "checkpoints",
    "output_folder": "samples/predict",
    "num_workers": 0,
    "dataset": "CDDataset",
    "data_name": "SYSU",
    "batch_size": 1,
    "split": "test",
    "img_size": 256,
    "n_class": 2,
    "net_G": "base_transformer_pos_s4_dd8",
    "checkpoint_name": "best_ckpt.pt",
    "backbone": "resnet18",
}

# 每个模型独立的配置（net_G / project_name / checkpoint_name）
MODEL_CONFIGS = {
    "BIT": {
        "net_G": "base_transformer_pos_s4_dd8",
        # 该权重实为 SYSU-CD 训练产物（与 checkpoints/test/best_ckpt.pt 内容完全一致，
        # 见训练日志 data_name: SYSU），目录名原为 BIT_LEVIR 属误标，已更正
        "project_name": "BIT_SYSU",
        "checkpoint_name": "best_ckpt.pt",
    },
    "DIFF": {
        "net_G": None,  # 像素差分，无需模型
        "project_name": None,
        "checkpoint_name": None,
    },
    "FC_SIAM_DIFF": {
        "net_G": "fc_siam_diff",
        "project_name": "FC_SIAM_DIFF",
        "checkpoint_name": "best_ckpt.pt",
    },
    "SNUNET": {
        "net_G": "snunet",
        "project_name": "SNUNET",
        "checkpoint_name": "best_ckpt.pt",
    },
    "CHANGEFORMER": {
        "net_G": "changeformer",
        "project_name": "CHANGEFORMER",
        "checkpoint_name": "best_ckpt.pt",
    },
    "AFCF3D": {
        "net_G": "afcf3d",          # 独立加载，不走 CDEvaluator
        "project_name": "AFCF3D",
        "checkpoint_name": "best_ckpt.pt",
    },
    "BIT_LuojiaSET": {
        "net_G": "base_transformer_pos_s4_dd8",
        "project_name": "BIT_LuojiaSET",
        "checkpoint_name": "best_ckpt.pt",
    },
}
