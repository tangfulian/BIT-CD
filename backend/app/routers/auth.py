import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.core.captcha import generate_captcha, verify_captcha
from backend.app.core.security import (
    create_access_token,
    get_current_user,
    get_db,
    hash_password,
    verify_password,
)
from backend.app.core.limiter import get_user_key, limiter
from backend.app.core.timefmt import to_local
from backend.app.models.detection import DetectionResultDB
from backend.app.models.plot import PlotDB
from backend.app.models.user import UserDB
from backend.app.schemas.user import UserLogin, UserRegister


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

router = APIRouter(tags=["认证"])
logger = logging.getLogger(__name__)


@router.get("/captcha")
@limiter.limit("30/minute")
def get_captcha(request: Request):
    return {"code": 200, "data": generate_captcha()}


@router.post("/register")
@limiter.limit("3/minute")
def register(request: Request, user: UserRegister, db: Session = Depends(get_db)):
    if not verify_captcha(user.captcha_id, user.captcha_answer):
        raise HTTPException(status_code=400, detail="验证码错误或已过期，请刷新后重试")
    if db.query(UserDB).filter(UserDB.username == user.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    hashed = hash_password(user.password)
    new_user = UserDB(username=user.username, password_hash=hashed, role="user")
    db.add(new_user)
    db.commit()
    logger.info("用户注册: %s", user.username)
    return {"code": 200, "msg": "注册成功"}


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, user: UserLogin, db: Session = Depends(get_db)):
    if not verify_captcha(user.captcha_id, user.captcha_answer):
        raise HTTPException(status_code=400, detail="验证码错误或已过期，请刷新后重试")
    db_user = db.query(UserDB).filter(UserDB.username == user.username).first()
    if not db_user or not verify_password(user.password, db_user.password_hash):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    if db_user.disabled:
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")
    access_token = create_access_token(data={"sub": db_user.username, "role": db_user.role})
    logger.info("用户登录: %s (role=%s)", db_user.username, db_user.role)
    return {
        "code": 200,
        "token": access_token,
        "username": db_user.username,
        "role": db_user.role,
    }


@router.get("/profile")
@limiter.limit("30/minute", key_func=get_user_key)
def get_profile(
    request: Request,
    current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)
):
    """获取个人中心数据"""
    detection_count = (
        db.query(DetectionResultDB).filter(DetectionResultDB.user_id == current_user.id).count()
    )
    plot_count = db.query(PlotDB).filter(PlotDB.user_id == current_user.id).count()

    # 平均变化率
    from sqlalchemy import func

    avg_result = (
        db.query(func.avg(DetectionResultDB.ratio))
        .filter(DetectionResultDB.user_id == current_user.id)
        .scalar()
    )
    avg_ratio = round(float(avg_result), 4) if avg_result else None

    # 最近活动
    last = (
        db.query(DetectionResultDB)
        .filter(DetectionResultDB.user_id == current_user.id)
        .order_by(DetectionResultDB.id.desc())
        .first()
    )
    last_active = to_local(last.created_at, "%Y-%m-%d %H:%M") if last else None

    return {
        "code": 200,
        "data": {
            "username": current_user.username,
            "role": current_user.role,
            "created_at": to_local(current_user.created_at, "%Y-%m-%d %H:%M"),
            "detection_count": detection_count,
            "plot_count": plot_count,
            "avg_ratio": avg_ratio,
            "last_active": last_active,
        },
    }


@router.put("/profile/change-password")
@limiter.limit("5/minute", key_func=get_user_key)
def change_password(
    request: Request,
    req: ChangePasswordRequest,
    current_user: UserDB = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码错误")
    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="新密码长度不能少于8位")
    current_user.password_hash = hash_password(req.new_password)
    db.commit()
    return {"code": 200, "msg": "密码修改成功"}
