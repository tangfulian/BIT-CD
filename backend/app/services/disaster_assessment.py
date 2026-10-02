"""灾害定损的编排层。

分层：**纯计算在 disaster_service —— 那个模块只依赖 numpy，可以在任何地方
导入调用；本模块负责取记录、读概率图、校验参数，再把纯函数算出的结果组装
成响应体。** 两者刻意不合并：把 torch、SQLAlchemy、FastAPI 拖进纯计算模块，
会毁掉它「随处可调」这个性质。模块名不带 _service 后缀，正是为了和纯计算层
一眼区分开。

此前这四段逻辑压在 routers/disaster.py 里，后果是只有走 HTTP 才能定损，
工具通道无法复用同一套语义，而两份实现必然漂移。

错误语义刻意保持原样：不属于本人的记录与不存在的记录返回同一个 404，
否则等于告诉调用方「这条记录存在，只是不归你」，可被用来探测他人记录数。
工具层会把 HTTPException 收敛成一句模型能读的话，不把栈透出去。
"""
import logging

import cv2
import numpy as np
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models.user import UserDB
from backend.app.schemas.disaster import DisasterAssessRequest
from backend.app.services.detect_service import load_score_map
from backend.app.services.record_access import find_owned_detection, url_to_path
from backend.app.services.disaster_service import (
    DEFAULT_CROP_PARAMS,
    DEFAULT_GRADE_BOUNDS,
    assess,
)

logger = logging.getLogger(__name__)

# 分级下界必须递增，否则分级区间会重叠或倒挂，得出的统计没有意义
_BOUND_ORDER = ("moderate", "severe", "total")


def get_owned_detection(detection_id: int, current_user: UserDB, db: Session):
    """取本人记录；不存在、不属于本人、缺概率图都会在这里拦掉。

    查询谓词来自 record_access.find_owned_detection —— 不区分「不存在」与
    「不属于本人」，二者返回同一个 404，否则等于告诉调用方「这条存在，
    只是不归你」，可被用来探测他人记录数。文案留在本模块，因为「缺少概率图」
    是定损自己的契约。
    """
    record = find_owned_detection(db, current_user.id, detection_id)
    if not record:
        raise HTTPException(status_code=404, detail="检测记录不存在")
    if not record.score_url:
        # /detect/compare 建的记录与部分旧记录没有概率图，无法分级
        raise HTTPException(
            status_code=400,
            detail="该记录缺少概率图（score_map），无法定损；请用单张检测重新生成",
        )
    return record


def validated_bounds(bounds):
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


def run_assess(payload: DisasterAssessRequest, current_user: UserDB, db: Session) -> dict:
    """共用测算流程：取记录 → 读概率图 → 校验 → 计算。

    同步阻塞（读图 + 矩阵运算），调用方负责放进线程池。
    """
    record = get_owned_detection(payload.detection_id, current_user, db)

    bounds, err = validated_bounds(payload.grade_bounds)
    if err:
        raise HTTPException(status_code=400, detail=err)

    try:
        score_map = load_score_map(url_to_path(record.score_url))
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail="该记录的概率图文件已丢失，无法定损"
        )

    # 掩膜取记录已保存的那一份（用户界面上看到的就是它），
    # 而不是从概率图重新阈值化 —— 后者经 8bit 量化后可能与保存的掩膜有细微出入，
    # 会让定损面积与用户看到的变化区域对不上。
    mask_path = url_to_path(record.mask_url) if record.mask_url else None
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
