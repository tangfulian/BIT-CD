import logging
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.app.core.limiter import limiter
from backend.app.core.logging_config import setup_logging
from backend.app.models.database import init_db
from backend.app.models.user import UserDB
from backend.app.core.security import hash_password
from backend.app.core.config import ADMIN_DEFAULT_PASSWORD, ALLOWED_ORIGINS
from backend.app.models.database import SessionLocal
from backend.app.services.detect_service import ModelNotAvailableError

from backend.app.routers import (
    admin,
    agent,
    ai,
    amap,
    annotation,
    auth,
    compare,
    detect,
    history,
    plot,
    status,
)


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(title="黑土地变化检测+AI系统", version="1.0")
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    @app.exception_handler(ModelNotAvailableError)
    async def _model_unavailable(request: Request, exc: ModelNotAvailableError):
        """模型权重缺失：返回 503 并说明原因，避免把未训练网络的输出当结果展示"""
        logging.getLogger(__name__).warning("模型不可用: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"code": 503, "msg": str(exc), "detail": "model_not_deployed"},
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception(request: Request, exc: Exception):
        """兜底异常处理：统一为 JSON 结构，避免裸 500 文本响应前端无法解析"""
        logging.getLogger(__name__).exception(
            "未处理异常 %s %s", request.method, request.url.path
        )
        return JSONResponse(
            status_code=500,
            content={"code": 500, "msg": "服务器内部错误", "detail": type(exc).__name__},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 请求统计中间件
    _path_map = {
        "/detect": "detect", "/register": "register", "/login": "login",
        "/ai/chat": "chat", "/ai/analysis-detect-result": "analysis",
        "/agent/execute": "agent",
        "/amap/regeo": "regeo", "/history": "history", "/compare": "compare",
        "/recommend-threshold": "recommend",
        "/detect/compare": "compare-models", "/detect/rethreshold": "rethreshold",
        "/detect/otsu": "otsu", "/detect/ndvi": "ndvi",
        "/detect/check-registration": "registration",
        "/detect/area-stats": "area-stats", "/detect/export-geojson": "geojson",
        "/evaluate": "evaluate", "/annotation": "annotation",
        "/plots": "plots", "/admin": "admin", "/status": "status",
        "/profile": "profile", "/captcha": "captcha",
    }
    MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB

    @app.middleware("http")
    async def limit_upload_size(request: Request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > MAX_UPLOAD_SIZE:
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=413,
                    content={"detail": f"请求体过大，最大允许 {MAX_UPLOAD_SIZE // 1024 // 1024}MB"},
                )
        return await call_next(request)

    @app.middleware("http")
    async def count_middleware(request: Request, call_next):
        if request.method not in ("OPTIONS", "HEAD"):
            # 按路径长度降序匹配：否则 "/detect" 会抢先命中 "/detect/compare" 等子路由，
            # 使 compare-models / rethreshold / otsu / ndvi 等计数永远为 0
            for route, name in sorted(_path_map.items(), key=lambda kv: -len(kv[0])):
                if request.url.path.startswith(route):
                    status.count(name)
                    break
        return await call_next(request)

    os.makedirs("uploads", exist_ok=True)
    os.makedirs("results", exist_ok=True)
    os.makedirs("samples/predict", exist_ok=True)

    # 为 /results 静态文件添加 CORS 头（mounted app 不继承主 app 中间件）
    _results_app = StaticFiles(directory="results")
    async def _results_with_cors(scope, receive, send):
        if scope["type"] == "http":
            # 仅对白名单内的来源放行。/results 是 mounted app，不继承主 app 的 CORS 中间件，
            # 原先无条件回显请求方 Origin，等于对任意站点开放检测结果图
            _req_origin = b""
            for h_name, h_val in scope.get("headers", []):
                if h_name == b"origin":
                    try:
                        if h_val.decode() in ALLOWED_ORIGINS:
                            _req_origin = h_val
                    except Exception:
                        pass
                    break
            async def send_wrapper(message):
                if message["type"] == "http.response.start" and _req_origin:
                    headers = dict(message.get("headers", []))
                    headers[b"access-control-allow-origin"] = _req_origin
                    message["headers"] = list(headers.items())
                await send(message)
            await _results_app(scope, receive, send_wrapper)
        else:
            await _results_app(scope, receive, send)
    app.mount("/results", _results_with_cors, name="results")

    init_db()
    _init_admin()

    app.include_router(agent.router)
    app.include_router(auth.router)
    app.include_router(detect.router)
    app.include_router(history.router)
    app.include_router(ai.router)
    app.include_router(amap.router)
    app.include_router(compare.router)
    app.include_router(annotation.router)
    app.include_router(admin.router)
    app.include_router(status.router)
    app.include_router(plot.router)

    # 挂载前端静态文件（必须在所有 router include 之后，确保 API 路由优先匹配）
    frontend_dir = os.path.join(_project_root, "frontend")
    if os.path.isdir(frontend_dir):
        app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return app


def _init_admin():
    db = SessionLocal()
    admin = db.query(UserDB).filter(UserDB.username == "admin").first()
    if not admin:
        db.add(
            UserDB(
                username="admin",
                password_hash=hash_password(ADMIN_DEFAULT_PASSWORD),
                role="admin",
            )
        )
        db.commit()
    elif admin.role != "admin":
        admin.role = "admin"
        db.commit()
    db.close()


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
