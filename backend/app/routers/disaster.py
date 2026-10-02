"""农业灾害定损接口。

三个端点：参数默认值、定损测算、说明草稿。

分工上刻意把"算钱"和"写字"分开：
  /disaster/assess     纯确定性算术，不调用任何外部服务，结果可复现
  /disaster/narrative  调大模型写说明草稿，失败不影响金额

这样即使 AI 不可用，定损金额照样算得出来 —— 金额不该依赖一个会抖动的服务。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.models.user import UserDB
from backend.app.schemas.disaster import (
    DisasterAssessRequest,
    DisasterNarrativeRequest,
)
from backend.app.services import ai_service
# 编排（取记录、读概率图、校验、组响应）已下沉到 disaster_assessment，
# 因为工具通道需要在没有 HTTP 请求的情况下复用同一套语义。
# 纯计算仍在 disaster_service —— 那个模块只依赖 numpy，不受影响。
from backend.app.services.disaster_assessment import run_assess
from backend.app.services.disaster_service import (
    DEFAULT_CROP_PARAMS,
    DEFAULT_GRADE_BOUNDS,
    DEFAULT_LOSS_RATES,
    DEFAULT_SURVEY_COSTS,
    IMAGE_DISCLAIMER,
    SURVEY_COST_REFERENCE,
    build_narrative_prompt,
    ensure_draft_label,
)

router = APIRouter(tags=["灾害定损"])
logger = logging.getLogger(__name__)


@router.get("/disaster/params")
@limiter.limit("30/minute", key_func=get_user_key)
async def get_params(
    request: Request,
    current_user: UserDB = Depends(get_current_user),
):
    """返回全部默认参数及其来源说明。

    来源说明是必给的：这些数值是示例参考值，不是本系统的实测结论，
    使用者需要知道每个数是怎么来的才谈得上替换。
    """
    return JSONResponse(content={
        "code": 200,
        "crop_params": DEFAULT_CROP_PARAMS,
        "loss_rates": DEFAULT_LOSS_RATES,
        "grade_bounds": DEFAULT_GRADE_BOUNDS,
        "survey_costs": DEFAULT_SURVEY_COSTS,
        "survey_cost_ranges": {
            "manual_per_mu": list(SURVEY_COST_REFERENCE["manual_per_mu"]),
            "remote_per_mu": list(SURVEY_COST_REFERENCE["remote_per_mu"]),
            "manual_days": SURVEY_COST_REFERENCE["manual_days"],
            "remote_days": SURVEY_COST_REFERENCE["remote_days"],
        },
        "source_note": SURVEY_COST_REFERENCE["source_note"],
    })


@router.post("/disaster/assess")
@limiter.limit("20/minute", key_func=get_user_key)
async def assess_disaster(
    request: Request,
    payload: DisasterAssessRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """定损测算。纯算术，不调用大模型。"""
    try:
        result = run_assess(payload, current_user, db)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return JSONResponse(content={"code": 200, "result": result})


@router.post("/disaster/narrative")
@limiter.limit("5/minute", key_func=get_user_key)
async def disaster_narrative(
    request: Request,
    payload: DisasterNarrativeRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成定损说明草稿。

    按与测算完全相同的入参在服务端重算一遍，而不是采信前端回传的结果 ——
    否则喂给模型的数字可能和系统实际算出的不一致，草稿就成了第二个来源。

    草稿区分为独立字段（draft / draft_label / uses_image / image_disclaimer），
    前端据字段渲染固定横幅而不是解析模型文本：模型既编不出也删不掉这些字段。
    """
    try:
        result = run_assess(payload, current_user, db)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    prompt = build_narrative_prompt(
        result,
        location=result["detection"]["location"],
        change_type=result["detection"]["change_type"],
        crop_type=result["detection"]["crop_type"],
    )

    try:
        text = ai_service.draft_disaster_note(prompt)
    except Exception as exc:
        # 与 /ai/* 一致：不抛 500，返回可读原因。
        # 定损金额已在 assess 里算好，草稿失败不应连累它。
        logger.warning("定损说明草稿生成失败: %s", exc)
        return JSONResponse(content={
            "code": 500,
            "error": f"说明草稿生成失败：{exc}",
            "hint": "定损测算结果不受影响，可稍后重试",
        })

    return JSONResponse(content={
        "code": 200,
        "draft": ensure_draft_label(text),
        "draft_label": "AI 草稿，需人工复核",
        "uses_image": False,
        "image_disclaimer": IMAGE_DISCLAIMER,
        "note": "草稿中的每个数字都应能在测算表中找到，请逐项核对",
    })
