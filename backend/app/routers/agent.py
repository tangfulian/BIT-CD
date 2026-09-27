import logging
import os
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.models.user import UserDB
from backend.app.services.agent_service import execute_agent
from backend.app.services.tool_agent_service import MAX_TOOL_ROUNDS, execute_tool_agent

router = APIRouter(prefix="/agent", tags=["AI Agent"])
logger = logging.getLogger(__name__)

MAX_FILES = 10
MAX_FILE_SIZE = 10 * 1024 * 1024  # 单文件 10MB，与前端其余上传处一致
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def _safe_basename(name: str) -> str:
    """只取文件名部分，剥掉任何目录成分。

    上传的文件名完全由客户端提供，可能含 ../ 或绝对路径；这里只保留最后一段
    并剔除分隔符，确保落盘范围锁死在本次的临时目录内。
    """
    base = os.path.basename((name or "").replace("\\", "/"))
    base = base.replace("\x00", "").strip()
    return base or "file"


async def _save_uploads(files: list[UploadFile]) -> tuple[list[str], str | None]:
    """把上传的文件落到一次性临时目录，返回 (绝对路径列表, 目录)。

    目录由调用方在 finally 里删除 —— browser-use 不管理 available_file_paths
    里文件的生命周期，全由调用方负责，不删就会一直堆着。
    """
    real = [f for f in files if f is not None and (f.filename or "").strip()]
    if not real:
        return [], None
    if len(real) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"附件最多 {MAX_FILES} 个")

    upload_dir = tempfile.mkdtemp(prefix="agent_uploads_")
    paths: list[str] = []
    used: set[str] = set()

    for f in real:
        name = _safe_basename(f.filename)
        suffix = os.path.splitext(name)[1].lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的附件类型：{name}",
            )
        data = await f.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"附件 {name} 是空文件")
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"附件 {name} 超过 {MAX_FILE_SIZE // 1024 // 1024}MB",
            )
        # 重名加序号，避免后者覆盖前者
        stem, ext = os.path.splitext(name)
        final, n = name, 1
        while final in used:
            final = f"{stem}_{n}{ext}"
            n += 1
        used.add(final)

        path = os.path.join(upload_dir, final)
        with open(path, "wb") as fh:
            fh.write(data)
        paths.append(path)

    logger.info("Agent 附件已落盘: %d 个 -> %s", len(paths), upload_dir)
    return paths, upload_dir


@router.post("/execute")
@limiter.limit("3/minute", key_func=get_user_key)
async def agent_execute(
    request: Request,
    instruction: str = Form(..., min_length=1, max_length=2000),
    max_steps: int = Form(25, ge=5, le=100),
    files: list[UploadFile] = File(default=[]),
    current_user: UserDB = Depends(get_current_user),
):
    # Agent 会驱动真实浏览器并以管理员身份操作前端，属高权限功能：
    # 此前仅要求登录（任意注册用户即可调用），现限定管理员
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Agent 功能仅限管理员使用")

    upload_dir = None
    try:
        file_paths, upload_dir = await _save_uploads(files)
        result = await execute_agent(instruction, max_steps, file_paths)
        return {"code": 200, **result}
    except HTTPException:
        raise
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
    finally:
        if upload_dir:
            shutil.rmtree(upload_dir, ignore_errors=True)


@router.post("/execute-tools")
@limiter.limit("10/minute", key_func=get_user_key)
async def agent_execute_tools(
    request: Request,
    instruction: str = Form(..., min_length=1, max_length=2000),
    max_rounds: int = Form(MAX_TOOL_ROUNDS, ge=1, le=MAX_TOOL_ROUNDS),
    files: list[UploadFile] = File(default=[]),
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """工具调用通道：模型用 function calling 直接调服务层，不驱动浏览器。

    权限刻意比 /execute 低一档（只要登录，不要求 admin）。理由是这条通道的
    权限面严格更小：它全程以调用者本人的身份执行，不启用管理员旁路，没有
    Chrome、没有可执行任意 JS 的会话，能做的事与用户自己点界面完全相同，
    因此不构成提权。仍复用同一套附件落盘与白名单校验。
    """
    upload_dir = None
    try:
        file_paths, upload_dir = await _save_uploads(files)
        # 内部是网络往返 + CPU 推理，全是阻塞调用，必须离开事件循环
        result = await run_in_threadpool(
            execute_tool_agent,
            instruction=instruction,
            file_paths=file_paths,
            user=current_user,
            db=db,
            base_url=str(request.base_url).rstrip("/"),
            max_rounds=max_rounds,
        )
        return {"code": 200, **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("工具通道执行失败: %s", e)
        # 与 /execute 同一口径：不回 str(e)，避免把内部路径、模型名透给前端
        return {
            "code": 500,
            "success": False,
            "final_result": None,
            "total_steps": 0,
            "duration_seconds": 0,
            "screenshots": [],
            "visited_urls": [],
            "errors": [f"执行失败（{type(e).__name__}），详情见服务端日志"],
            "tool_trace": [],
        }
    finally:
        if upload_dir:
            shutil.rmtree(upload_dir, ignore_errors=True)
