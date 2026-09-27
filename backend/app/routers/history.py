import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.models.detection import DetectionResultDB
from backend.app.models.user import UserDB

router = APIRouter(tags=["历史记录"])
logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))


def _to_local(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")


def _rewrite_url(request: Request, url: str | None) -> str:
    """将数据库中可能存有旧域名(127.0.0.1)的 URL 重写为当前请求的正确地址"""
    if not url:
        return ""
    filename = url.rsplit("/", 1)[-1]
    if not filename:
        return url
    return f"{str(request.base_url).rstrip('/')}/results/{filename}"


@router.get("/history")
@limiter.limit("30/minute", key_func=get_user_key)
def get_user_history(
    request: Request,
    page: int = Query(1, ge=1),
    # 加上界：此前无上界，limit 传很大即可一次拉走全部记录。
    # 取 500 而非 100 —— 前端为「一次拉全、客户端分页筛选」的设计，
    # 上界过小会让它的 /history?limit=5000 直接 422，列表与看板双双空白。
    limit: int = Query(20, ge=1, le=500),
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(DetectionResultDB)
    if current_user.role != "admin":
        query = query.filter(DetectionResultDB.user_id == current_user.id)

    total = query.count()
    items = query.order_by(DetectionResultDB.created_at.desc()).offset((page - 1) * limit).limit(limit).all()

    data = [
        {
            "id": r.id,
            "model": r.model,
            "threshold": r.threshold,
            "ratio": r.ratio,
            "change_pixel": r.change_pixel,
            "total_pixel": r.total_pixel,
            "lat_lng": r.lat_lng,
            "location": r.location,
            "change_type": r.change_type,
            "t1_time": r.t1_time,
            "t2_time": r.t2_time,
            "mask": _rewrite_url(request, r.mask_url),
            "heat": _rewrite_url(request, r.heat_url),
            "fusion": _rewrite_url(request, r.fusion_url),
            "score": _rewrite_url(request, r.score_url) or "",
            "ai_change_type": r.ai_change_type or "",
            "ai_confidence": r.ai_confidence or 0.0,
            "time": _to_local(r.created_at),
        }
        for r in items
    ]
    return {"code": 200, "data": data, "total": total, "page": page, "limit": limit}


@router.delete("/history/{record_id}")
@limiter.limit("20/minute", key_func=get_user_key)
def delete_single_record(
    request: Request,
    record_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    record = (
        db.query(DetectionResultDB)
        .filter(DetectionResultDB.id == record_id)
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    if current_user.role != "admin" and record.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权删除此记录")
    db.delete(record)
    db.commit()
    logger.info("删除检测记录: user=%s id=%s", current_user.username, record_id)
    return {"code": 200, "msg": "已删除"}


@router.delete("/history")
@limiter.limit("3/minute", key_func=get_user_key)
def clear_all_history(
    request: Request,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role == "admin":
        db.query(DetectionResultDB).delete()
    else:
        db.query(DetectionResultDB).filter(
            DetectionResultDB.user_id == current_user.id
        ).delete()
    db.commit()
    logger.info("清空历史记录: user=%s", current_user.username)
    return {"code": 200, "msg": "已清空"}
