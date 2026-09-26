import logging

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


def get_user_key(request: Request) -> str:
    """从 JWT 提取用户标识，未认证时回退到 IP"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            from jose import jwt
            from backend.app.core.config import SECRET_KEY, ALGORITHM

            token = auth.split(" ")[1]
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            if username:
                return "user:" + username
        except Exception:
            pass
    client = request.client
    return "ip:" + (client.host if client else "unknown")
