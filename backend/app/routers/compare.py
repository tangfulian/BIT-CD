import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.core.timefmt import to_local
from backend.app.models.detection import DetectionResultDB
from backend.app.models.user import UserDB
from backend.app.services.record_access import rewrite_url

router = APIRouter(tags=["对比"])
logger = logging.getLogger(__name__)


@router.get("/compare")
@limiter.limit("20/minute", key_func=get_user_key)
def compare_results(
    request: Request,
    id1: int = Query(...),
    id2: int = Query(...),
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    r1 = db.query(DetectionResultDB).filter(DetectionResultDB.id == id1).first()
    r2 = db.query(DetectionResultDB).filter(DetectionResultDB.id == id2).first()
    if not r1 or not r2:
        raise HTTPException(status_code=404, detail="检测记录未找到")
    if current_user.role != "admin" and (
        r1.user_id != current_user.id or r2.user_id != current_user.id
    ):
        raise HTTPException(status_code=403, detail="无权访问")

    base_url = str(request.base_url).rstrip("/")

    def _format(r):
        # URL 必须重写、时间必须转东八区 —— 这两条约定收在 record_access 与
        # core/timefmt 里。本文件原先各写了一份，于是同一个系统里结果对比页的
        # 图片可能裂（库里存的是检测当时的绝对地址，服务器换过域名就失效）、
        # 时间比其他页面早 8 小时。history.py 与 series.py 都已接过去。
        return {
            "id": r.id,
            "model": r.model,
            "threshold": r.threshold,
            "ratio": r.ratio,
            "change_pixel": r.change_pixel,
            "total_pixel": r.total_pixel,
            "lat_lng": r.lat_lng or "",
            "location": r.location or "",
            "change_type": r.change_type or "",
            "t1_time": r.t1_time or "",
            "t2_time": r.t2_time or "",
            "ai_change_type": r.ai_change_type or "",
            "ai_confidence": r.ai_confidence or 0.0,
            "mask": rewrite_url(base_url, r.mask_url),
            "heat": rewrite_url(base_url, r.heat_url),
            "fusion": rewrite_url(base_url, r.fusion_url),
            "time": to_local(r.created_at),
        }

    return {"code": 200, "data": {"result1": _format(r1), "result2": _format(r2)}}
