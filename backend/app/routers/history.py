import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.models.detection import DetectionResultDB
from backend.app.models.user import UserDB
from backend.app.services.record_access import query_owned_records, rewrite_url

router = APIRouter(tags=["历史记录"])
logger = logging.getLogger(__name__)

CST = timezone(timedelta(hours=8))


def _to_local(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")


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
    base_url = str(request.base_url).rstrip("/")

    # is_admin 是这一次调用的**明确表态**，不再是查询的隐藏属性。
    # 工具通道调同一份查询时传 False —— Agent 历史上以 admin 身份运行，
    # 一旦默认放行，模型就能拿到全库所有用户的记录。
    query = query_owned_records(
        db, current_user.id, is_admin=current_user.role == "admin"
    )

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
            "mask": rewrite_url(base_url, r.mask_url),
            "heat": rewrite_url(base_url, r.heat_url),
            "fusion": rewrite_url(base_url, r.fusion_url),
            "score": rewrite_url(base_url, r.score_url) or "",
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
    """清空历史记录。

    ★ 管理员分支删的是**全库所有用户**的记录，不只是自己的。这是有意的
      ——管理员口径在本文件里一贯如此（列表、单条删除也都带旁路），且前端
      有二次确认（history.confirmClearAll）挡着，不是一键误触。

      但改动这里之前必须想清楚影响面：没有软删除、没有回收站、没有备份，
      一次请求即不可逆。相比之下 plot.py 全程按 user_id 过滤、没有旁路，
      两个模块口径不一致 —— 这是现状，不是遗漏，动它需要单独决定。
    """
    if current_user.role == "admin":
        db.query(DetectionResultDB).delete()
    else:
        db.query(DetectionResultDB).filter(
            DetectionResultDB.user_id == current_user.id
        ).delete()
    db.commit()
    logger.info("清空历史记录: user=%s", current_user.username)
    return {"code": 200, "msg": "已清空"}
