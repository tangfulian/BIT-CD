from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, Header, HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_HOURS
from backend.app.models.database import SessionLocal
from backend.app.models.user import UserDB


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def get_current_user(authorization: str = Header(None)) -> UserDB:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未提供认证令牌")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="令牌无效")
    except JWTError:
        raise HTTPException(status_code=401, detail="令牌无效")
    db = SessionLocal()
    try:
        user = db.query(UserDB).filter(UserDB.username == username).first()
    finally:
        db.close()
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    if user.disabled:
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")
    return user


def get_optional_user(authorization: str = Header(None)) -> "UserDB | None":
    """游客可用的可选认证：有 token 则返回用户，无 token 返回 None。"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None
    db = SessionLocal()
    try:
        user = db.query(UserDB).filter(UserDB.username == username).first()
    finally:
        db.close()
    if user is None or user.disabled:
        return None
    return user


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
