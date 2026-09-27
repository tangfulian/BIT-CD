"""多时相序列的请求模型。"""
from typing import List

from pydantic import BaseModel, Field


class SeriesCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    location: str = ""
    lat_lng: str = ""
    # 地块面积（亩）。不填则速率只有 %/年 口径，没有亩/年。
    area_mu: float = Field(0.0, ge=0)


class SeriesRecordItem(BaseModel):
    detection_id: int
    # 该期的起止影像月份（YYYY-MM）。历史记录里批量检测产生的记录日期为空，
    # 必须在这里补上，否则无法参与时序排序。
    t1_time: str = ""
    t2_time: str = ""


class SeriesAttachRequest(BaseModel):
    records: List[SeriesRecordItem] = Field(..., min_length=1)
