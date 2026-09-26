import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.core.config import USER_RESET_PASSWORD
from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.security import get_current_user, get_db, hash_password
from backend.app.models.annotation import AnnotationDB
from backend.app.models.detection import DetectionResultDB
from backend.app.models.plot import PlotDB
from backend.app.models.user import UserDB

router = APIRouter(prefix="/admin", tags=["管理员"])
logger = logging.getLogger(__name__)


def _admin_only(user: UserDB):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")


@router.get("/users")
@limiter.limit("30/minute", key_func=get_user_key)
def list_users(
    request: Request,
    page: int = 1,
    limit: int = 20,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _admin_only(current_user)
    total = db.query(UserDB).count()
    users = db.query(UserDB).offset((page - 1) * limit).limit(limit).all()
    result = []
    for u in users:
        det_count = (
            db.query(DetectionResultDB)
            .filter(DetectionResultDB.user_id == u.id)
            .count()
        )
        result.append(
            {
                "id": u.id,
                "username": u.username,
                "role": u.role,
                "disabled": bool(u.disabled),
                "created_at": u.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if u.created_at
                else "",
                "detection_count": det_count,
            }
        )
    return {"code": 200, "data": result, "total": total, "page": page, "limit": limit}


@router.put("/users/{user_id}/toggle-status")
@limiter.limit("10/minute", key_func=get_user_key)
def toggle_user_status(
    request: Request,
    user_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _admin_only(current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能禁用自己")
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.disabled = 1 if user.disabled == 0 else 0
    db.commit()
    return {"code": 200, "msg": "状态已更新", "disabled": bool(user.disabled)}


@router.put("/users/{user_id}/password")
@limiter.limit("5/minute", key_func=get_user_key)
def reset_user_password(
    request: Request,
    user_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _admin_only(current_user)
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    new_pwd = USER_RESET_PASSWORD
    user.password_hash = hash_password(new_pwd)
    db.commit()
    logger.info("密码重置: admin=%s target_user=%s", current_user.username, user.username)
    return {"code": 200, "msg": "密码已重置"}


@router.delete("/users/{user_id}")
@limiter.limit("5/minute", key_func=get_user_key)
def delete_user(
    request: Request,
    user_id: int,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _admin_only(current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    user = db.query(UserDB).filter(UserDB.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.query(DetectionResultDB).filter(DetectionResultDB.user_id == user_id).delete()
    db.query(AnnotationDB).filter(AnnotationDB.user_id == user_id).delete()
    db.query(PlotDB).filter(PlotDB.user_id == user_id).delete()
    db.delete(user)
    db.commit()
    return {"code": 200, "msg": "用户及关联数据已删除"}
