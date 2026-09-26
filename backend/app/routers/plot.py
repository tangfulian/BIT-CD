import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db
from backend.app.models.plot import PlotDB
from backend.app.models.user import UserDB
from backend.app.schemas.plot import PlotCreate, PlotOut, PlotUpdate

router = APIRouter(prefix="/plots", tags=["地块管理"])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[PlotOut])
@limiter.limit("30/minute", key_func=get_user_key)
def list_plots(
    request: Request,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plots = (
        db.query(PlotDB)
        .filter(PlotDB.user_id == current_user.id)
        .order_by(PlotDB.updated_at.desc())
        .all()
    )
    return [_plot_to_out(p) for p in plots]


@router.post("", response_model=PlotOut)
@limiter.limit("20/minute", key_func=get_user_key)
def create_plot(
    request: Request,
    data: PlotCreate,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plot = PlotDB(
        user_id=current_user.id,
        name=data.name,
        province=data.province,
        city=data.city,
        lat_lng=data.lat_lng,
        area=data.area,
        land_type=data.land_type,
        crop_type=data.crop_type,
        data_source=data.data_source,
        change_type=data.change_type,
        t1_time=data.t1_time,
        t2_time=data.t2_time,
    )
    db.add(plot)
    db.commit()
    db.refresh(plot)
    logger.info("地块创建: user=%s name=%s", current_user.username, data.name)
    return _plot_to_out(plot)


@router.put("/{plot_id}", response_model=PlotOut)
@limiter.limit("20/minute", key_func=get_user_key)
def update_plot(
    request: Request,
    plot_id: int,
    data: PlotUpdate,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plot = (
        db.query(PlotDB)
        .filter(PlotDB.id == plot_id, PlotDB.user_id == current_user.id)
        .first()
    )
    if not plot:
        raise HTTPException(status_code=404, detail="地块不存在")
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(plot, key, value)
    plot.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plot)
    logger.info("地块更新: user=%s id=%s", current_user.username, plot_id)
    return _plot_to_out(plot)


@router.delete("/{plot_id}")
@limiter.limit("20/minute", key_func=get_user_key)
def delete_plot(
    request: Request,
    plot_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plot = (
        db.query(PlotDB)
        .filter(PlotDB.id == plot_id, PlotDB.user_id == current_user.id)
        .first()
    )
    if not plot:
        raise HTTPException(status_code=404, detail="地块不存在")
    db.delete(plot)
    db.commit()
    logger.info("地块删除: user=%s id=%s", current_user.username, plot_id)
    return {"code": 200, "msg": "地块已删除"}


def _plot_to_out(p: PlotDB) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "province": p.province or "",
        "city": p.city or "",
        "lat_lng": p.lat_lng or "",
        "area": p.area or 0,
        "land_type": p.land_type or "",
        "crop_type": p.crop_type or "",
        "data_source": p.data_source or "",
        "change_type": p.change_type or "",
        "t1_time": p.t1_time or "",
        "t2_time": p.t2_time or "",
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
