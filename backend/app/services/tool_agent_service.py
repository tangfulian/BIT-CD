"""工具调用通道：模型用 function calling 直接调自家后端。

与 agent_service 的区别，以及为什么要有这一条：

    浏览器通道：模型 → 无障碍树 → 点按钮 → 前端 JS → 我们的 REST API
    本通道    ：模型 → function calling → 服务层（同一进程）

浏览器通道是在操作一个**我们自己写的网站**，而那个网站背后就是我们自己的
接口 —— 用它去点自己的按钮，等于绕了一整圈去按自家的键盘。本通道去掉
中间四层，代价是没有截图可看（那是浏览器通道才有的演示价值）。

安全边界（三条，改动前先想清楚）：

1. **工具参数里绝不出现 user_id。** 身份一律取自调用方的登录态，否则模型
   可以伪造归属，把检测写到别人名下、或读别人的记录。
2. **永不使用管理员旁路。** history.py 的查询在 role == "admin" 时会返回
   全库记录；而 Agent 历史上正是以 admin 身份跑的。工具层一律按 user_id
   过滤，管理员在工具通道里也只看得见自己的数据。
3. **文件路径必须逐字符命中白名单。** run_detection 收的是服务器本地路径，
   模型若能自由填，一句注入就能让它去读 /app/.env 之外的任意文件。
   只接受调用方已列出的附件路径。
"""
import json
import logging
import os
import time

import httpx
from sqlalchemy.orm import Session

from backend.app.core.config import DASHSCOPE_API_KEY
from backend.app.models.detection import DetectionResultDB
from backend.app.models.user import UserDB
from backend.app.services import detection_service
from backend.app.services.detect_service import model_availability

logger = logging.getLogger(__name__)

_DASHSCOPE_CHAT_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# 工具通道用 qwen3.7-plus：实测它同时具备视觉、Function Calling 与
# json_schema 严格模式，而 qwen-vl-plus 不支持 Function Calling。
_AGENT_MODEL = "qwen3.7-plus"
_LLM_TIMEOUT = 120.0
# 工具循环的轮次上限。每一轮都是一次完整的模型往返，放开会让一次请求
# 拖到几分钟；正常任务 2~3 轮就能收敛。
MAX_TOOL_ROUNDS = 8
# 单次工具结果回灌给模型的字符上限，防止列表类结果把上下文撑爆。
MAX_TOOL_RESULT_CHARS = 4000

SYSTEM_PROMPT = """你是东北黑土地变化检测系统的智能助手，通过调用工具帮用户完成任务。

规则：
1. 先想清楚用户要什么，再选择工具。不要臆造参数。
2. 用户说"用附件跑一次检测"时，附件路径已在下方列出，直接把路径填进工具参数。
   不要自己编造路径，也不要把路径改成别的形式。
3. 需要模型名但不确定有哪些可用时，先调 list_models。
4. 工具返回错误时，把错误原因原样告诉用户，不要反复重试同一个调用。
5. 拿到结果后用中文简洁汇报关键数字（变化比例、面积、数量等），不要罗列原始 JSON。
6. 你只能看见当前用户自己的数据。如果查询结果为空，如实说没有，不要推测。"""


def _tool_schemas(file_paths: list[str]) -> list[dict]:
    available = [n for n, ok in model_availability().items() if ok]
    return [
        {
            "type": "function",
            "function": {
                "name": "list_models",
                "description": "列出当前真正可用的变化检测模型。挑模型前先调它，不要凭空猜模型名。",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_detection",
                "description": (
                    "对一对双时相遥感影像运行变化检测，返回变化比例与变化像素数，"
                    "并把结果写入当前用户的检测历史。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image1": {
                            "type": "string",
                            "description": "前期（T1）影像的完整路径，必须是附件清单里列出的路径之一",
                        },
                        "image2": {
                            "type": "string",
                            "description": "后期（T2）影像的完整路径，必须是附件清单里列出的路径之一",
                        },
                        "model": {
                            "type": "string",
                            "enum": available,
                            "description": "检测模型。不确定就先调 list_models",
                        },
                        "threshold": {
                            "type": "number",
                            "description": "变化判定阈值，取值 0~1，默认 0.5。用户没指定就用 0.5",
                        },
                        "t1_time": {"type": "string", "description": "前期影像时相，如 2024-05，可为空"},
                        "t2_time": {"type": "string", "description": "后期影像时相，如 2024-09，可为空"},
                        "location": {"type": "string", "description": "地块位置描述，可为空"},
                    },
                    "required": ["image1", "image2", "model"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_detections",
                "description": "分页列出当前用户自己的检测历史记录，用于拿到 detection_id 或回顾历史。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "返回条数，1~50，默认 10"},
                        "model": {"type": "string", "description": "只看某个模型的记录，可为空"},
                    },
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_detection",
                "description": "按 detection_id 取一条检测记录的完整统计信息。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "detection_id": {"type": "integer", "description": "检测记录 ID"},
                    },
                    "required": ["detection_id"],
                },
            },
        },
    ]


def _attachment_block(file_paths: list[str]) -> str:
    """把附件清单拼进提示词。只给路径与文件名，不替模型判断哪张是前期。"""
    if not file_paths:
        return "\n\n【本次可用附件】无。用户若要求跑检测，先请他用附件上传影像。"
    lines = ["\n\n【本次可用附件】（run_detection 只能使用下列路径，不得改写）"]
    for p in file_paths:
        try:
            size = f"{os.path.getsize(p) / 1024:.1f} KB"
        except OSError:
            size = "大小未知"
        lines.append(f"  {p}   （文件名 {os.path.basename(p)}，{size}）")
    lines.append("哪张是前期、哪张是后期，以用户任务里的说明为准。")
    return "\n".join(lines)


class ToolError(Exception):
    """工具执行失败。消息会原样回灌给模型，所以要写成模型能理解、用户能看懂的话。"""


def _list_models(_args: dict, _ctx: dict) -> dict:
    availability = model_availability()
    available = [n for n, ok in availability.items() if ok]
    if not available:
        raise ToolError("当前没有任何模型权重已部署，无法执行检测。")
    return {"available_models": available, "default": "BIT" if "BIT" in available else available[0]}


def _run_detection(args: dict, ctx: dict) -> dict:
    allowed = ctx["file_paths"]
    for key in ("image1", "image2"):
        path = str(args.get(key) or "")
        # 逐字符比对，不做 normpath/realpath 之类的"宽容"处理：白名单要的是
        # 严格命中，宽容化等于给绕过留口子。
        if path not in allowed:
            raise ToolError(
                f"{key} 指定的路径不在本次可用附件里，拒绝执行。"
                f"可用附件只有：{allowed or '（无）'}"
            )

    try:
        threshold = float(args.get("threshold", 0.5))
    except (TypeError, ValueError):
        raise ToolError("threshold 必须是 0~1 之间的数字") from None
    if not 0.0 <= threshold <= 1.0:
        raise ToolError("threshold 必须在 0~1 之间")

    with open(args["image1"], "rb") as fh:
        img1_bytes = fh.read()
    with open(args["image2"], "rb") as fh:
        img2_bytes = fh.read()

    result = detection_service.run_detection(
        img1_bytes=img1_bytes,
        img2_bytes=img2_bytes,
        model=str(args.get("model") or "BIT"),
        threshold=threshold,
        base_url=ctx["base_url"],
        db=ctx["db"],
        # 身份来自调用方登录态，永远不接受模型传入的 user_id
        user_id=ctx["user"].id,
        t1_time=str(args.get("t1_time") or ""),
        t2_time=str(args.get("t2_time") or ""),
        location=str(args.get("location") or ""),
    )
    stats = result["stats"]
    # 刻意不回灌四张图的 URL：它们又长又没用，模型只会把它们抄进回答里。
    return {
        "detection_id": result["detection_id"],
        "model": result["model"],
        "msg": result["msg"],
        "change_ratio_percent": stats["ratio"],
        "change_pixel": stats["change_pixel"],
        "total_pixel": stats["total_pixel"],
        "threshold": stats["threshold"],
    }


def _list_detections(args: dict, ctx: dict) -> dict:
    try:
        limit = int(args.get("limit", 10))
    except (TypeError, ValueError):
        limit = 10
    # 上界强制收窄：HTTP 那边 limit 可到 500，是给前端"一次拉全"让步的，
    # 工具侧放这么大等于一次往模型上下文里灌 500 条记录。
    limit = max(1, min(limit, 50))

    query = ctx["db"].query(DetectionResultDB).filter(
        # 只按 user_id 过滤，不给管理员旁路：Agent 历史上以 admin 运行，
        # 一旦放行就会把全库用户的记录交给模型。
        DetectionResultDB.user_id == ctx["user"].id
    )
    model = str(args.get("model") or "").strip()
    if model:
        query = query.filter(DetectionResultDB.model == model)

    records = query.order_by(DetectionResultDB.id.desc()).limit(limit).all()
    return {
        "count": len(records),
        "items": [
            {
                "detection_id": r.id,
                "model": r.model,
                "threshold": r.threshold,
                "change_ratio_percent": r.ratio,
                "change_pixel": r.change_pixel,
                "total_pixel": r.total_pixel,
                "location": r.location or "",
                "t1_time": r.t1_time or "",
                "t2_time": r.t2_time or "",
                "change_type": r.change_type or "",
            }
            for r in records
        ],
        "note": "以上仅为当前用户自己的记录。" if records else "当前用户没有任何检测记录。",
    }


def _get_detection(args: dict, ctx: dict) -> dict:
    try:
        detection_id = int(args["detection_id"])
    except (KeyError, TypeError, ValueError):
        raise ToolError("detection_id 必须是整数") from None

    record = (
        ctx["db"]
        .query(DetectionResultDB)
        .filter(
            DetectionResultDB.id == detection_id,
            DetectionResultDB.user_id == ctx["user"].id,
        )
        .first()
    )
    if not record:
        # 不区分"不存在"与"不属于本人"，避免把他人记录的存在性透出去。
        raise ToolError(f"没有找到 ID 为 {detection_id} 的检测记录（或它不属于你）")

    return {
        "detection_id": record.id,
        "model": record.model,
        "threshold": record.threshold,
        "change_ratio_percent": record.ratio,
        "change_pixel": record.change_pixel,
        "total_pixel": record.total_pixel,
        "location": record.location or "",
        "lat_lng": record.lat_lng or "",
        "change_type": record.change_type or "",
        "ai_change_type": record.ai_change_type or "",
        "t1_time": record.t1_time or "",
        "t2_time": record.t2_time or "",
    }


_DISPATCH = {
    "list_models": _list_models,
    "run_detection": _run_detection,
    "list_detections": _list_detections,
    "get_detection": _get_detection,
}


def _post_chat(messages: list, tools: list) -> dict:
    if not DASHSCOPE_API_KEY:
        raise RuntimeError("未配置 DASHSCOPE_API_KEY，Agent 功能不可用")
    resp = httpx.post(
        _DASHSCOPE_CHAT_URL,
        headers={"Authorization": f"Bearer {DASHSCOPE_API_KEY}"},
        json={
            "model": _AGENT_MODEL,
            "messages": messages,
            "tools": tools,
            "temperature": 0.2,
        },
        timeout=_LLM_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"模型调用失败：HTTP {resp.status_code} {resp.text[:200]}")
    choices = resp.json().get("choices") or []
    if not choices:
        raise RuntimeError("模型返回了空响应")
    return choices[0].get("message") or {}


def _run_tool(name: str, args: dict, ctx: dict) -> tuple[bool, str]:
    """执行一个工具，返回 (是否成功, 回灌给模型的文本)。"""
    func = _DISPATCH.get(name)
    if func is None:
        return False, json.dumps({"error": f"没有名为 {name} 的工具"}, ensure_ascii=False)
    try:
        payload = func(args, ctx)
        text = json.dumps(payload, ensure_ascii=False, default=str)
    except ToolError as exc:
        return False, json.dumps({"error": str(exc)}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        # 工具内部异常（含 HTTPException）一律收敛成模型能读的一句话，
        # 不把栈或内部路径透给模型。
        logger.warning("工具 %s 执行失败: %s", name, exc)
        detail = getattr(exc, "detail", None) or str(exc)
        return False, json.dumps({"error": f"{detail}"}, ensure_ascii=False)

    if len(text) > MAX_TOOL_RESULT_CHARS:
        text = text[:MAX_TOOL_RESULT_CHARS] + "...（结果过长已截断）"
    return True, text


def execute_tool_agent(
    instruction: str,
    file_paths: list[str],
    user: UserDB,
    db: Session,
    base_url: str,
    max_rounds: int = MAX_TOOL_ROUNDS,
) -> dict:
    """跑一轮工具调用 Agent，返回与浏览器通道同构的响应。

    同步阻塞（内部是网络往返 + CPU 推理），调用方负责放进线程池。
    """
    started = time.monotonic()
    tools = _tool_schemas(file_paths)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + _attachment_block(file_paths)},
        {"role": "user", "content": instruction},
    ]
    ctx = {"user": user, "db": db, "base_url": base_url, "file_paths": list(file_paths)}

    trace: list[dict] = []
    errors: list[str] = []

    for _round in range(max_rounds):
        message = _post_chat(messages, tools)
        calls = message.get("tool_calls") or []

        if not calls:
            return {
                "success": True,
                "final_result": (message.get("content") or "").strip() or "（模型没有给出内容）",
                "total_steps": len(trace),
                "duration_seconds": round(time.monotonic() - started, 1),
                "screenshots": [],
                "visited_urls": [],
                "errors": errors,
                "tool_trace": trace,
            }

        # 必须把 assistant 这条带 tool_calls 的消息原样放回去，
        # 否则后续的 role:"tool" 消息没有可对应的调用 id，接口会拒。
        messages.append(message)
        for call in calls:
            func = call.get("function") or {}
            name = func.get("name") or ""
            try:
                args = json.loads(func.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            ok, text = _run_tool(name, args, ctx)
            trace.append(
                {
                    "tool": name,
                    "arguments": args,
                    "ok": ok,
                    "summary": text[:300],
                }
            )
            if not ok:
                errors.append(f"{name}: {text[:200]}")
            messages.append(
                {"role": "tool", "tool_call_id": call.get("id"), "content": text}
            )

    return {
        "success": False,
        "final_result": f"任务未能在 {max_rounds} 轮工具调用内完成，请把要求说得更具体一些。",
        "total_steps": len(trace),
        "duration_seconds": round(time.monotonic() - started, 1),
        "screenshots": [],
        "visited_urls": [],
        "errors": errors,
        "tool_trace": trace,
    }
