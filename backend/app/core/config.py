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
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
AMAP_WEB_KEY = os.getenv("AMAP_WEB_KEY")
AMAP_API_BASE = "https://restapi.amap.com/v3"

# --- AI Agent（Browser Use 操控前端） ---
AGENT_FRONTEND_URL = os.getenv("AGENT_FRONTEND_URL", "http://localhost:5500")
AGENT_USERNAME = os.getenv("AGENT_USERNAME", "admin")
# 不再需要 AGENT_PASSWORD：Agent 改为直接签发 token 并经 CDP 注入 localStorage
# （见 agent_service._inject_auth），不再走「用账号密码登录表单」的老路。
# 原先这里会读取 AGENT_PASSWORD，未设置时生成随机值并打警告——但那个值从来没有
# 被任何代码读过，只会让每次启动都刷一条无意义的警告。故整块移除。
AGENT_BROWSER_HEADLESS = os.getenv("AGENT_BROWSER_HEADLESS", "true").lower() == "true"
AGENT_MAX_STEPS = int(os.getenv("AGENT_MAX_STEPS", "15"))

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
