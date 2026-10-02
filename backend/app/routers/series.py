"""多时相影像序列接口。

一个序列是同一地块的 N 期观测。期次本身仍是普通的检测记录，只是多挂了
series_id 与 phase_index，因此检测、结果图、重调阈值这些能力全部复用，
本模块只负责「把记录组织成序列」与「对序列做趋势分析」。

归属校验一律照 disaster.py 的做法：不属于本人的资源与不存在的资源返回
同一个 404，避免泄露存在性。
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.models.detection import DetectionResultDB
from backend.app.models.series import ImageSeriesDB
from backend.app.models.user import UserDB
from backend.app.schemas.series import SeriesAttachRequest, SeriesCreate
# 序列的取用与趋势编排已下沉到 series_trend，使工具通道能共用同一套语义 ——
# 两份实现必然漂移。导入时改名，本文件既有的调用点一行都不用动。
# parse_month 这里仍在直接用（attach_records 校期次日期）。
from backend.app.services.record_access import find_owned_detection, rewrite_url
from backend.app.services.series_service import parse_month
from backend.app.services.series_trend import (
    get_owned_series as _get_series,
    ordered_members as _ordered_members,
    trend_for_series,
)

router = APIRouter(tags=["时序序列"])
logger = logging.getLogger(__name__)


def _record_payload(rec: DetectionResultDB, base_url: str) -> dict:
    """序列成员的对外表示。

    URL 必须先重写再返回：库里存的是**检测当时**的绝对地址，服务器换过
    域名/IP、或曾经用 127.0.0.1 访问过，旧记录里就是过期主机名。
    history.py 早就为此打过补丁，而这里一直漏着 —— 结果是同一份数据在
    历史页显示正常、在时序页整片裂图，排查时会往错误方向找。
    """
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
        "mask": rewrite_url(base_url, rec.mask_url),
        "heat": rewrite_url(base_url, rec.heat_url),
        "fusion": rewrite_url(base_url, rec.fusion_url),
        "score": rewrite_url(base_url, rec.score_url),
    }


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
    base_url = str(request.base_url).rstrip("/")
    return JSONResponse(content={
        "code": 200,
        "series": {
            "id": series.id,
            "name": series.name,
            "location": series.location or "",
            "lat_lng": series.lat_lng or "",
            "area_mu": series.area_mu or 0,
        },
        "records": [_record_payload(r, base_url) for r in members],
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
        rec = find_owned_detection(db, current_user.id, item.detection_id)
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
    # 编排整段下沉到 series_trend —— 工具通道要在没有 HTTP 的情况下复用同一套
    # 语义。查库与最小二乘拟合都是同步阻塞的，放进线程池避免阻塞事件循环。
    trend = await run_in_threadpool(trend_for_series, series_id, current_user, db)
    return JSONResponse(content={"code": 200, "trend": trend})
