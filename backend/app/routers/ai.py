import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.models.detection import DetectionResultDB
from backend.app.models.user import UserDB
from backend.app.schemas.common import ChatRequest
from backend.app.schemas.detection import (
    ClassifyChangeRequest,
    DetectAIAnalysisRequest,
    UpdateChangeTypeRequest,
)
from backend.app.services.ai_service import chat, classify_change

router = APIRouter(prefix="/ai", tags=["AI"])
logger = logging.getLogger(__name__)

SYSTEM_CHAT_PROMPT = (
    "你是「东北黑土地变化检测智能系统」的专属AI助手，你的职责是："
    "1. 解答用户关于黑土地保护、遥感变化检测、系统操作的相关问题；"
    "2. 语言专业严谨，通俗易懂，只回答和农业遥感、黑土地保护、本系统相关的内容；"
    "3. 禁止回答和本领域无关的问题，引导用户回到系统相关的话题。"
)

SYSTEM_ANALYSIS_PROMPT = (
    "你是东北黑土地保护与遥感变化检测领域的国家级顶级专家，深耕黑土地治理领域20年，"
    "精通东北四省区黑土地保护政策、水土保持技术、耕地质量提升方案。"
    "你必须严格基于用户提供的检测数据、地块精准信息，完成专业、精准、定制化的解读，"
    "绝对禁止输出通用套话，必须贴合地块的实际情况。"
    "你的解读必须严格遵循以下结构，语言专业严谨，符合农业农村部黑土地保护规范，字数控制在400-600字："
    "1. 检测结果精准概述：必须明确提到地块所在省市、双时相时间、影像数据源、检测模型精度、变化类型、变化面积占比，量化说明变化严重程度；"
    "2. 变化成因针对性分析：必须结合地块的耕地类型、种植模式、所在区域的气候地理特征，分析该变化产生的核心原因，禁止泛泛而谈；"
    "3. 定制化治理与保护建议：必须结合变化类型、所在区域、种植作物，给出3-4条可落地、符合当地实际的治理措施，必须贴合东北黑土地保护的主流技术规范。"
)


@router.post("/chat")
@limiter.limit("10/minute", key_func=get_user_key)
async def ai_chat(request: Request, chat_req: ChatRequest, current_user=Depends(get_current_user)):
    try:
        # dashscope SDK 是同步阻塞调用（网络往返数秒），移入线程池
        reply = await run_in_threadpool(chat, chat_req.user_input, chat_req.history, SYSTEM_CHAT_PROMPT)
        return {"code": 200, "reply": reply}
    except Exception as e:
        logger.error("AI聊天失败: %s", e)
        return {"code": 500, "error": str(e), "reply": "AI服务异常"}


@router.post("/analysis-detect-result")
@limiter.limit("5/minute", key_func=get_user_key)
async def ai_analysis(request: Request, analysis_req: DetectAIAnalysisRequest, current_user=Depends(get_current_user)):
    user_input = f"地块位置：{analysis_req.location}，变化类型：{analysis_req.change_type}..."
    try:
        analysis = await run_in_threadpool(chat, user_input, [], SYSTEM_ANALYSIS_PROMPT)
        return {"code": 200, "analysis": analysis}
    except Exception as e:
        logger.error("AI分析失败: %s", e)
        return {"code": 500, "error": str(e), "analysis": "AI解读失败"}


@router.post("/classify-change")
@limiter.limit("10/minute", key_func=get_user_key)
async def ai_classify_change(
    request: Request,
    classify_req: ClassifyChangeRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        result = await run_in_threadpool(
            lambda: classify_change(
                change_ratio=classify_req.change_ratio,
                change_pixel=classify_req.change_pixel,
                total_pixel=classify_req.total_pixel,
                threshold=classify_req.threshold,
                location=classify_req.location,
                land_type=classify_req.land_type,
                crop_type=classify_req.crop_type,
                t1_time=classify_req.t1_time,
                t2_time=classify_req.t2_time,
            )
        )
        change_type = result.get("change_type", "")
        confidence = result.get("confidence", 0.0)
        reasoning = result.get("reasoning", "")

        # 如果提供了 detection_id，持久化 AI 分类结果
        if classify_req.detection_id > 0:
            detection = db.query(DetectionResultDB).filter(
                DetectionResultDB.id == classify_req.detection_id,
                DetectionResultDB.user_id == current_user.id,
            ).first()
            if detection:
                detection.ai_change_type = change_type
                detection.ai_confidence = confidence
                db.commit()
                logger.info("AI分类已保存: detection_id=%s type=%s conf=%.2f",
                            classify_req.detection_id, change_type, confidence)

        return {
            "code": 200,
            "change_type": change_type,
            "confidence": confidence,
            "reasoning": reasoning,
        }
    except Exception as e:
        logger.error("AI分类失败: %s", e)
        return {"code": 500, "error": str(e)}


@router.post("/update-change-type")
@limiter.limit("10/minute", key_func=get_user_key)
async def update_change_type(
    request: Request,
    req: UpdateChangeTypeRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    detection = db.query(DetectionResultDB).filter(
        DetectionResultDB.id == req.detection_id,
        DetectionResultDB.user_id == current_user.id,
    ).first()
    if not detection:
        raise HTTPException(status_code=404, detail="检测记录不存在")
    detection.change_type = req.change_type
    db.commit()
    return {"code": 200, "msg": "更新成功"}
