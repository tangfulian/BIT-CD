"""第三方登录（目前只有 GitHub）。

走 Authorization Code 流程：

1. 前端点按钮 → `GET /auth/github/authorize`
2. 生成随机 nonce，签名成 `state`；nonce 同时写进 httpOnly cookie
3. 302 到 GitHub 授权页
4. 用户同意后 GitHub 回跳 `GET /auth/github/callback?code=&state=`
5. 校验 `state` 的签名，并与 cookie 里的 nonce 比对 —— 光验签名只能证明
   `state` 是我们签的，证明不了**是这个浏览器**发起的；两者都比对才挡得住
   CSRF（攻击者把自己的 code 塞给别人）
6. 拿 code 换 access_token，再取 `/user`
7. 按 `(provider, provider_uid)` 找账号或新建，签发本站 JWT
8. 302 回前端，token 放在 URL **fragment** 里

用 fragment 而不是 query：fragment 不会发给服务器、不进 Referer。
它仍会留在浏览器历史里，所以前端读到后立刻 replaceState 清掉。

账号策略是**一律新建**，不按用户名合并。GitHub 用户名可以被别人注册，
按用户名自动合并等于把「注册同名 GitHub 号」变成「接管别人的本地账号」。
要合并只能在登录之后手动绑定。
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core import config as cfg
from backend.app.core.limiter import limiter
from backend.app.core.security import (
    ALGORITHM,
    SECRET_KEY,
    create_access_token,
    get_db,
    hash_password,
)
from backend.app.models.oauth import OAuthAccountDB
from backend.app.models.user import UserDB

router = APIRouter(prefix="/auth", tags=["第三方登录"])
logger = logging.getLogger(__name__)

_STATE_COOKIE = "oauth_state"
_STATE_TTL = timedelta(minutes=10)

_GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
_GITHUB_USER = "https://api.github.com/user"


class _OAuthError(Exception):
    """换 token 或取用户信息失败。消息只进日志，不回给浏览器。"""


# ---------------------------------------------------------------- state


def _make_state() -> tuple[str, str]:
    """返回 (nonce, 签名后的 state)。nonce 要单独写进 cookie。"""
    nonce = secrets.token_urlsafe(24)
    state = jwt.encode(
        {"n": nonce, "exp": datetime.now(timezone.utc) + _STATE_TTL},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return nonce, state


def _read_state(state: str) -> str | None:
    try:
        payload = jwt.decode(state, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    nonce = payload.get("n")
    return nonce if isinstance(nonce, str) else None


# ---------------------------------------------------------------- 地址


def _frontend_base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _redirect_uri(request: Request) -> str:
    return cfg.GITHUB_REDIRECT_URI or f"{_frontend_base(request)}/auth/github/callback"


def _back_to_frontend(request: Request, fragment: str) -> RedirectResponse:
    resp = RedirectResponse(f"{_frontend_base(request)}/#{fragment}", status_code=302)
    # state 是一次性的，无论成败都清掉
    resp.delete_cookie(_STATE_COOKIE, path="/")
    return resp


# ---------------------------------------------------------------- GitHub


def _exchange_code(code: str, redirect_uri: str) -> dict:
    with httpx.Client(timeout=15) as client:
        try:
            resp = client.post(
                _GITHUB_TOKEN,
                data={
                    "client_id": cfg.GITHUB_CLIENT_ID,
                    "client_secret": cfg.GITHUB_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as e:
            raise _OAuthError(f"换 token 请求失败: {e}") from e
        if resp.status_code != 200:
            raise _OAuthError(f"换 token 返回 {resp.status_code}: {resp.text[:200]}")

        payload = resp.json()
        access_token = payload.get("access_token")
        if not access_token:
            raise _OAuthError(
                f"没有 access_token: {payload.get('error_description') or payload.get('error')}"
            )

        try:
            user_resp = client.get(
                _GITHUB_USER,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                    # GitHub 的 API 对缺少 User-Agent 的请求直接 403
                    "User-Agent": "BIT-CD",
                },
            )
        except httpx.HTTPError as e:
            raise _OAuthError(f"取用户信息失败: {e}") from e
        if user_resp.status_code != 200:
            raise _OAuthError(f"取用户信息返回 {user_resp.status_code}")
        return user_resp.json()


# ---------------------------------------------------------------- 账号


def _unique_username(db: Session, base: str) -> str:
    """GitHub 用户名可能和已有本地账号重名。撞了就加后缀，**绝不合并**。"""
    base = (base or "").strip()[:32] or "github"
    if not db.query(UserDB).filter(UserDB.username == base).first():
        return base
    i = 1
    while db.query(UserDB).filter(UserDB.username == f"{base}-gh{i}").first():
        i += 1
    return f"{base}-gh{i}"


def _resolve_user(db: Session, provider_uid: str, gh_login: str) -> UserDB:
    acct = (
        db.query(OAuthAccountDB)
        .filter(
            OAuthAccountDB.provider == "github",
            OAuthAccountDB.provider_uid == provider_uid,
        )
        .first()
    )
    if acct:
        user = db.query(UserDB).filter(UserDB.id == acct.user_id).first()
        if user:
            return user
        # 绑定指向了一个被删掉的用户：清掉这条悬空绑定，按新用户重走一遍
        logger.warning("GitHub 绑定指向的用户不存在，清理: user_id=%s", acct.user_id)
        db.delete(acct)
        db.commit()

    user = UserDB(
        username=_unique_username(db, gh_login),
        # 随机口令 + 丢弃：这个账号只能通过 GitHub 登录，密码登录无从匹配
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role="user",
    )
    db.add(user)
    try:
        db.flush()
        db.add(
            OAuthAccountDB(
                provider="github", provider_uid=provider_uid, user_id=user.id
            )
        )
        db.commit()
    except IntegrityError:
        # 并发的首次登录：另一个请求已经建好了，退回去用它的
        db.rollback()
        acct = (
            db.query(OAuthAccountDB)
            .filter(
                OAuthAccountDB.provider == "github",
                OAuthAccountDB.provider_uid == provider_uid,
            )
            .first()
        )
        if not acct:
            raise
        user = db.query(UserDB).filter(UserDB.id == acct.user_id).first()
        if not user:
            raise
        return user
    db.refresh(user)
    return user


# ---------------------------------------------------------------- 路由


@router.get("/providers")
def list_providers():
    """前端据此决定显示哪些第三方按钮 —— 没配就别给一个点了就报错的按钮。"""
    return {"code": 200, "data": {"github": cfg.GITHUB_OAUTH_ENABLED}}


@router.get("/github/authorize")
@limiter.limit("20/minute")
def github_authorize(request: Request):
    if not cfg.GITHUB_OAUTH_ENABLED:
        raise HTTPException(status_code=503, detail="GitHub 登录未配置")

    nonce, state = _make_state()
    query = urlencode(
        {
            "client_id": cfg.GITHUB_CLIENT_ID,
            "redirect_uri": _redirect_uri(request),
            "scope": "read:user",
            "state": state,
            "allow_signup": "true",
        }
    )
    resp = RedirectResponse(f"{_GITHUB_AUTHORIZE}?{query}", status_code=302)
    # SameSite=Lax：GitHub 回跳是顶层 GET 导航，Lax 下 cookie 会带上，
    # 而跨站的 POST 不会 —— 正好是我们要的。线上是 http，所以不能加 secure。
    resp.set_cookie(
        _STATE_COOKIE,
        nonce,
        max_age=int(_STATE_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        path="/",
    )
    return resp


@router.get("/github/callback")
def github_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    if error:
        logger.info("GitHub 授权被拒绝: %s", error)
        return _back_to_frontend(request, "oauth_error=denied")

    nonce = _read_state(state)
    cookie = request.cookies.get(_STATE_COOKIE)
    if not nonce or not cookie or not secrets.compare_digest(nonce, cookie):
        logger.warning("GitHub 回调 state 校验失败")
        return _back_to_frontend(request, "oauth_error=state")

    if not code:
        return _back_to_frontend(request, "oauth_error=missing_code")

    try:
        gh_user = _exchange_code(code, _redirect_uri(request))
    except _OAuthError as e:
        logger.warning("GitHub 登录失败: %s", e)
        return _back_to_frontend(request, "oauth_error=github")

    gh_id = gh_user.get("id")
    if gh_id is None:
        logger.warning("GitHub /user 没有返回 id")
        return _back_to_frontend(request, "oauth_error=github")

    user = _resolve_user(db, str(gh_id), gh_user.get("login") or "")
    if user.disabled:
        return _back_to_frontend(request, "oauth_error=disabled")

    token = create_access_token({"sub": user.username, "role": user.role})
    logger.info("GitHub 登录成功: github=%s → 本站账号 %s", gh_user.get("login"), user.username)
    return _back_to_frontend(request, f"oauth_token={token}")
