"""时序趋势的编排层。

分层：纯计算在 series_service（parse_month / build_intervals / analyze_trend，
只依赖标准库，随处可调）；本模块负责取序列、校验归属、取成员记录、组装响应体。
两者刻意不合并 —— 模块名不带 _service 后缀，正是为了和纯计算层一眼区分。

此前这段逻辑压在 routers/series.py 的 series_trend 处理函数里，后果是只有走
HTTP 才能出趋势，工具通道无法复用同一套语义。
"""
import logging
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.models.detection import DetectionResultDB
from backend.app.models.series import ImageSeriesDB
from backend.app.models.user import UserDB
from backend.app.services.record_access import find_owned_series
from backend.app.services.series_service import (
    analyze_trend,
    build_intervals,
    parse_month,
)

logger = logging.getLogger(__name__)


def get_owned_series(series_id: int, current_user: UserDB, db: Session) -> ImageSeriesDB:
    """取本人序列。

    查询谓词来自 record_access.find_owned_series。不存在与不属于本人返回
    同一个 404 —— 不区分二者，避免泄露他人序列的存在性。
    """
    series = find_owned_series(db, current_user.id, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="序列不存在")
    return series


def ordered_members(series_id: int, db: Session):
    """取序列成员并按**影像日期**排序（不是按挂载顺序、更不是按检测时间）。

    ★ 只按 series_id 过滤，**不带 user_id** —— 调用方必须先做归属校验
      （get_owned_series），否则会跨用户读到别人的检测记录。
      这个契约靠调用顺序保证，不是靠这个函数自己。
    """
    members = db.query(DetectionResultDB).filter(
        DetectionResultDB.series_id == series_id
    ).all()
    members.sort(key=lambda r: (
        parse_month(r.t1_time) or parse_month(r.t2_time) or date.max
    ))
    return members


def trend_for_series(series_id: int, current_user: UserDB, db: Session) -> dict:
    """取一个序列的变化趋势。同步阻塞（查库 + 拟合），调用方负责放进线程池。

    返回体里的 caveats / skipped 必须原样透传给用户：caveats 说明了这套
    分析不外推未来、突变点是启发式而非统计检验；skipped 是日期缺失被剔除的
    记录，不能被当成「没有变化」。
    """
    # 顺序不能颠倒：ordered_members 不带 user_id 过滤
    series = get_owned_series(series_id, current_user, db)
    members = ordered_members(series_id, db)

    records = [{
        "detection_id": r.id,
        "t1_time": r.t1_time or "",
        "t2_time": r.t2_time or "",
        "ratio": r.ratio,
        "change_pixel": r.change_pixel,
        "total_pixel": r.total_pixel,
        "model": r.model,
        "change_type": r.change_type or "",
    } for r in members]

    area_mu = series.area_mu or 0.0
    intervals, skipped = build_intervals(records, area_mu=area_mu)
    trend = analyze_trend(intervals, area_mu=area_mu)
    trend["skipped"] = skipped
    trend["series"] = {"id": series.id, "name": series.name}
    return trend
