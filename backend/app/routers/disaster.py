"""农业灾害定损接口。

三个端点：参数默认值、定损测算、说明草稿。

分工上刻意把"算钱"和"写字"分开：
  /disaster/assess     纯确定性算术，不调用任何外部服务，结果可复现
  /disaster/narrative  调大模型写说明草稿，失败不影响金额

这样即使 AI 不可用，定损金额照样算得出来 —— 金额不该依赖一个会抖动的服务。
"""
import logging

import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.models.detection import DetectionResultDB
from backend.app.models.user import UserDB
from backend.app.schemas.disaster import (
    DisasterAssessRequest,
    DisasterNarrativeRequest,
)
from backend.app.services import ai_service
from backend.app.services.detect_service import load_score_map
from backend.app.services.disaster_service import (
    DEFAULT_CROP_PARAMS,
    DEFAULT_GRADE_BOUNDS,
    DEFAULT_LOSS_RATES,
    DEFAULT_SURVEY_COSTS,
    IMAGE_DISCLAIMER,
    SURVEY_COST_REFERENCE,
    assess,
    build_narrative_prompt,
    ensure_draft_label,
)

router = APIRouter(tags=["灾害定损"])
logger = logging.getLogger(__name__)

# 分级下界必须递增，否则分级区间会重叠或倒挂，得出的统计没有意义
_BOUND_ORDER = ("moderate", "severe", "total")


def _url_to_path(url: str) -> str:
    """从结果 URL 提取文件系统路径（与 detect.py 同一约定）"""
    return f"results/{url.rsplit('/', 1)[-1]}"


def _get_detection(detection_id: int, current_user: UserDB, db: Session):
    """取本人记录。

    不属于本人的记录与不存在的记录返回同一个 404 —— 否则等于告诉了调用方
    "这条记录存在，只是不归你"，可被用来探测他人记录数。
    """
    record = db.query(DetectionResultDB).filter(
        DetectionResultDB.id == detection_id,
        DetectionResultDB.user_id == current_user.id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="检测记录不存在")
    if not record.score_url:
        # /detect/compare 建的记录与部分旧记录没有概率图，无法分级
        raise HTTPException(
            status_code=400,
            detail="该记录缺少概率图（score_map），无法定损；请用单张检测重新生成",
        )
    return record


def _validated_bounds(bounds):
    """校验分级下界严格递增，返回 (生效值, 错误信息)。"""
    merged = dict(DEFAULT_GRADE_BOUNDS)
    if bounds:
        for key in _BOUND_ORDER:
            if bounds.get(key) is not None:
                merged[key] = float(bounds[key])
    values = [merged[k] for k in _BOUND_ORDER]
    if values != sorted(values) or len(set(values)) != len(values):
        return None, f"分级下界必须严格递增，当前为 {values}"
    if any(v <= 0 or v > 1 for v in values):
        return None, "分级下界必须落在 0–1 之间"
    return merged, ""


def _run_assess(payload: DisasterAssessRequest, current_user: UserDB, db: Session):
    """共用测算流程：取记录 → 读概率图 → 校验 → 计算。"""
    record = _get_detection(payload.detection_id, current_user, db)

    bounds, err = _validated_bounds(payload.grade_bounds)
    if err:
        raise HTTPException(status_code=400, detail=err)

    try:
        score_map = load_score_map(_url_to_path(record.score_url))
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail="该记录的概率图文件已丢失，无法定损"
        )

    # 掩膜取记录已保存的那一份（用户界面上看到的就是它），
    # 而不是从概率图重新阈值化 —— 后者经 8bit 量化后可能与保存的掩膜有细微出入，
    # 会让定损面积与用户看到的变化区域对不上。
    mask_path = _url_to_path(record.mask_url) if record.mask_url else None
    change_mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE) if mask_path else None
    if change_mask is None:
        # 掩膜缺失时退回按概率图重建，至少还能算，并在响应里说明
        logger.warning("掩膜文件缺失，改用概率图按阈值 %s 重建", record.threshold)
        change_mask = (score_map > record.threshold).astype(np.uint8) * 255

    # 作物参数：显式传入优先，否则用该作物的示例值
    crop = DEFAULT_CROP_PARAMS.get(payload.crop_type, {})
    yield_per_mu = (
        payload.yield_per_mu if payload.yield_per_mu is not None
        else crop.get("yield_per_mu", 0.0)
    )
    price_per_kg = (
        payload.price_per_kg if payload.price_per_kg is not None
        else crop.get("price_per_kg", 0.0)
    )

    result = assess(
        score_map,
        change_mask,
        area_mu=payload.area_mu,
        yield_per_mu=yield_per_mu,
        price_per_kg=price_per_kg,
        loss_rates=payload.loss_rates,
        grade_bounds=bounds,
        survey_costs=payload.survey_costs,
    )
    result["detection"] = {
        "id": record.id,
        "model": record.model,
        "threshold": record.threshold,
        "ratio": record.ratio,
        "change_pixel": record.change_pixel,
        "total_pixel": record.total_pixel,
        "location": record.location or payload.location,
        "change_type": record.change_type or payload.change_type,
        "t1_time": record.t1_time,
        "t2_time": record.t2_time,
        "crop_type": payload.crop_type,
    }
    # 系统算出的与假设的必须能一眼分开，前端据此分区展示
    result["measured"] = {
        "change_pixel": record.change_pixel,
        "total_pixel": record.total_pixel,
        "ratio": record.ratio,
        "threshold": record.threshold,
    }
    result["disclaimer"] = (
        "受灾等级由模型变化置信度分级得到，是「变化强度」的代理，"
        "不是实测减产率；减产比例、亩产、单价均为假设参数。"
        "本测算结果不作为理赔依据，需实地抽样核验。"
    )
    return result


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
        result = _run_assess(payload, current_user, db)
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
        result = _run_assess(payload, current_user, db)
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
