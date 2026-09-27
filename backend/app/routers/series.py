"""多时相影像序列接口。

一个序列是同一地块的 N 期观测。期次本身仍是普通的检测记录，只是多挂了
series_id 与 phase_index，因此检测、结果图、重调阈值这些能力全部复用，
本模块只负责「把记录组织成序列」与「对序列做趋势分析」。

归属校验一律照 disaster.py 的做法：不属于本人的资源与不存在的资源返回
同一个 404，避免泄露存在性。
"""
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.models.detection import DetectionResultDB
from backend.app.models.series import ImageSeriesDB
from backend.app.models.user import UserDB
from backend.app.schemas.series import SeriesAttachRequest, SeriesCreate
from backend.app.services.series_service import analyze_trend, build_intervals, parse_month

router = APIRouter(tags=["时序序列"])
logger = logging.getLogger(__name__)


def _get_series(series_id: int, current_user: UserDB, db: Session) -> ImageSeriesDB:
    series = db.query(ImageSeriesDB).filter(
        ImageSeriesDB.id == series_id,
        ImageSeriesDB.user_id == current_user.id,
    ).first()
    if not series:
        raise HTTPException(status_code=404, detail="序列不存在")
    return series


def _record_payload(rec: DetectionResultDB) -> dict:
    return {
        "detection_id": rec.id,
        "phase_index": rec.phase_index,
        "model": rec.model,
        "threshold": rec.threshold,
        "ratio": rec.ratio,
        "change_pixel": rec.change_pixel,
        "total_pixel": rec.total_pixel,
        "location": rec.location or "",
        "change_type": rec.change_type or "",
        "t1_time": rec.t1_time or "",
        "t2_time": rec.t2_time or "",
        "mask": rec.mask_url,
        "heat": rec.heat_url,
        "fusion": rec.fusion_url,
        "score": rec.score_url or "",
    }


def _ordered_members(series_id: int, db: Session):
    """取序列成员并按影像日期排序（不是按挂载顺序、更不是按检测时间）。"""
    members = db.query(DetectionResultDB).filter(
        DetectionResultDB.series_id == series_id
    ).all()
    members.sort(key=lambda r: (
        parse_month(r.t1_time) or parse_month(r.t2_time) or date.max
    ))
    return members


@router.post("/series")
@limiter.limit("20/minute", key_func=get_user_key)
async def create_series(
    request: Request,
    payload: SeriesCreate,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    series = ImageSeriesDB(
        user_id=current_user.id,
        name=payload.name.strip(),
        location=payload.location.strip(),
        lat_lng=payload.lat_lng.strip(),
        area_mu=payload.area_mu,
    )
    db.add(series)
    db.commit()
    db.refresh(series)
    return JSONResponse(content={
        "code": 200,
        "series": {"id": series.id, "name": series.name},
    })


@router.get("/series")
@limiter.limit("30/minute", key_func=get_user_key)
async def list_series(
    request: Request,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.query(ImageSeriesDB).filter(
        ImageSeriesDB.user_id == current_user.id
    ).order_by(ImageSeriesDB.created_at.desc()).all()

    data = []
    for s in rows:
        members = _ordered_members(s.id, db)
        data.append({
            "id": s.id,
            "name": s.name,
            "location": s.location or "",
            "area_mu": s.area_mu or 0,
            "member_count": len(members),
            "first_start": members[0].t1_time if members else "",
            "last_end": members[-1].t2_time if members else "",
        })
    return JSONResponse(content={"code": 200, "data": data})


@router.get("/series/{series_id}")
@limiter.limit("30/minute", key_func=get_user_key)
async def get_series(
    request: Request,
    series_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    series = _get_series(series_id, current_user, db)
    members = _ordered_members(series_id, db)
    return JSONResponse(content={
        "code": 200,
        "series": {
            "id": series.id,
            "name": series.name,
            "location": series.location or "",
            "lat_lng": series.lat_lng or "",
            "area_mu": series.area_mu or 0,
        },
        "records": [_record_payload(r) for r in members],
    })


@router.post("/series/{series_id}/records")
@limiter.limit("20/minute", key_func=get_user_key)
async def attach_records(
    request: Request,
    series_id: int,
    payload: SeriesAttachRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """把已有检测记录挂到序列上。

    日期冲突时**拒绝**而不是静默改写：记录上的 t1_time/t2_time 是既成事实，
    覆盖它等于篡改历史。要改日期就先去改那条记录本身。
    """
    _get_series(series_id, current_user, db)

    to_attach = []
    for item in payload.records:
        rec = db.query(DetectionResultDB).filter(
            DetectionResultDB.id == item.detection_id,
            DetectionResultDB.user_id == current_user.id,
        ).first()
        if not rec:
            raise HTTPException(
                status_code=404, detail=f"检测记录 {item.detection_id} 不存在"
            )
        if rec.series_id is not None and rec.series_id != series_id:
            raise HTTPException(
                status_code=400,
                detail=f"检测记录 {item.detection_id} 已属于另一个序列",
            )

        t1 = (item.t1_time or "").strip() or (rec.t1_time or "")
        t2 = (item.t2_time or "").strip() or (rec.t2_time or "")
        if parse_month(t1) is None or parse_month(t2) is None:
            raise HTTPException(
                status_code=400,
                detail=f"检测记录 {item.detection_id} 缺少有效日期，"
                       f"需形如 2024-05（当前 t1={t1 or '空'} t2={t2 or '空'}）",
            )
        # 记录本身已有日期且与传入不一致 → 拒绝
        if rec.t1_time and item.t1_time and rec.t1_time.strip() != item.t1_time.strip():
            raise HTTPException(
                status_code=400,
                detail=f"检测记录 {item.detection_id} 的起始日期已是 {rec.t1_time}，"
                       f"与所填 {item.t1_time} 冲突；请先修改该记录",
            )
        if rec.t2_time and item.t2_time and rec.t2_time.strip() != item.t2_time.strip():
            raise HTTPException(
                status_code=400,
                detail=f"检测记录 {item.detection_id} 的末期日期已是 {rec.t2_time}，"
                       f"与所填 {item.t2_time} 冲突；请先修改该记录",
            )
        to_attach.append((rec, t1, t2))

    for rec, t1, t2 in to_attach:
        rec.series_id = series_id
        # 只在记录原本为空时补写，已有值已在上面的校验中确认与传入一致
        if not rec.t1_time:
            rec.t1_time = t1
        if not rec.t2_time:
            rec.t2_time = t2

    # 必须先 flush：SessionLocal 配的是 autoflush=False，不 flush 的话
    # 下面按 series_id 的查询看不到刚赋的值，phase_index 会全是 None。
    db.flush()

    # phase_index 按影像日期重排 —— 挂载顺序不代表时间顺序
    members = _ordered_members(series_id, db)
    for idx, rec in enumerate(members):
        rec.phase_index = idx

    db.commit()
    return JSONResponse(content={
        "code": 200,
        "attached": len(to_attach),
        "member_count": len(members),
    })


@router.delete("/series/{series_id}")
@limiter.limit("20/minute", key_func=get_user_key)
async def delete_series(
    request: Request,
    series_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除序列本身，**只解除关联，不删检测记录**。

    检测记录是既有的工作成果，删序列不该连带把它们抹掉。
    """
    series = _get_series(series_id, current_user, db)
    for rec in db.query(DetectionResultDB).filter(
        DetectionResultDB.series_id == series_id
    ).all():
        rec.series_id = None
        rec.phase_index = None
    db.delete(series)
    db.commit()
    return JSONResponse(content={"code": 200, "msg": "序列已删除（检测记录保留）"})


@router.get("/series/{series_id}/trend")
@limiter.limit("20/minute", key_func=get_user_key)
async def series_trend(
    request: Request,
    series_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    series = _get_series(series_id, current_user, db)
    members = _ordered_members(series_id, db)

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

    intervals, skipped = build_intervals(records, area_mu=series.area_mu or 0.0)
    trend = analyze_trend(intervals, area_mu=series.area_mu or 0.0)
    trend["skipped"] = skipped
    trend["series"] = {"id": series.id, "name": series.name}
    return JSONResponse(content={"code": 200, "trend": trend})
