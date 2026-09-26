import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.models.detection import DetectionResultDB
from backend.app.models.user import UserDB

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

    def _format(r):
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
            "mask": r.mask_url,
            "heat": r.heat_url,
            "fusion": r.fusion_url,
            "time": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
        }

    return {"code": 200, "data": {"result1": _format(r1), "result2": _format(r2)}}
