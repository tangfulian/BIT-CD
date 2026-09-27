"""灾害定损的请求模型。

除 detection_id 外全部可选：不传即回落到 disaster_service 里的示例默认值，
响应会回显实际采用了哪些值（含 assumptions 清单）。
"""
from typing import Dict, Optional

from pydantic import BaseModel, Field


class DisasterAssessRequest(BaseModel):
    detection_id: int
    # 地块总面积（亩）。各级受灾面积按像素占比从这里摊派。
    area_mu: float = Field(0.0, ge=0)
    crop_type: str = ""
    location: str = ""
    change_type: str = ""

    # 以下均为假设参数，None 表示采用默认示例值
    yield_per_mu: Optional[float] = Field(None, ge=0)
    price_per_kg: Optional[float] = Field(None, ge=0)
    loss_rates: Optional[Dict[str, float]] = None
    grade_bounds: Optional[Dict[str, float]] = None
    survey_costs: Optional[Dict[str, float]] = None


class DisasterNarrativeRequest(DisasterAssessRequest):
    """说明草稿沿用与测算完全相同的入参。

    刻意让服务端按同样参数重算一遍，而不是信任前端回传的测算结果 ——
    否则喂给模型的数字可能与系统实际算出的不一致，草稿就成了另一个来源。
    """
