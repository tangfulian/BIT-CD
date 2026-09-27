import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user
from backend.app.models.user import UserDB
from backend.app.schemas.agent import AgentExecuteRequest
from backend.app.services.agent_service import execute_agent

router = APIRouter(prefix="/agent", tags=["AI Agent"])
logger = logging.getLogger(__name__)


@router.post("/execute")
@limiter.limit("3/minute", key_func=get_user_key)
async def agent_execute(
    request: Request,
    body: AgentExecuteRequest,
    current_user: UserDB = Depends(get_current_user),
):
    # Agent 会驱动真实浏览器并以管理员身份操作前端，属高权限功能：
    # 此前仅要求登录（任意注册用户即可调用），现限定管理员
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Agent 功能仅限管理员使用")
    try:
        result = await execute_agent(body.instruction, body.max_steps)
        return {"code": 200, **result}
    except Exception as e:
        logger.exception("Agent执行失败: %s", e)
        # 不回 str(e)：browser-use 的异常常带 base_url、模型名与服务器路径。
        # 全局异常处理器（main.py）刻意只给异常类名，这里保持同一口径。
        return {
            "code": 500,
            "success": False,
            "final_result": None,
            "total_steps": 0,
            "duration_seconds": 0,
            "screenshots": [],
            "visited_urls": [],
            "errors": [f"执行失败（{type(e).__name__}），详情见服务端日志"],
        }
