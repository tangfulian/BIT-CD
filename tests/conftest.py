import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 必须在 import backend 之前设置：用独立的文件型 SQLite 测试库。
# 不能用 sqlite:///:memory: 另建 engine —— routers 中的 SessionLocal 是模块级绑定，
# 替换 db_module.SessionLocal 不会影响已导入的名字，业务代码仍会连到另一个（未建表的）
# 内存库，表现为 "no such table: users"。让应用自身的 engine 指向测试库才可靠。
_TEST_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_bitcd.db")
os.environ["DATABASE_URL"] = "sqlite:///" + _TEST_DB
# 固定"管理员重置用户密码"所用的常量：未设置时 config.py 会生成随机值，测试无法预期
os.environ.setdefault("USER_RESET_PASSWORD", "testreset123")

import pytest
from fastapi.testclient import TestClient

from backend.app.models.database import Base, SessionLocal, engine

# 显式导入全部模型模块，让 Base.metadata 在 setup_db 之前就完整。
# models/__init__.py 是空的，导入不会自动带出这些类；而 setup_db 是 autouse，
# 早于 client fixture 里对 backend.app.main 的导入，所以不能指望那时候已经注册。
# 少导一个的后果：create_all 建不出该表，且带外键的模型会抛
# NoReferencedTableError。alembic/env.py 出于同样原因维护着一份同样的清单。
import backend.app.models.user  # noqa: E402, F401
import backend.app.models.detection  # noqa: E402, F401
import backend.app.models.annotation  # noqa: E402, F401
import backend.app.models.plot  # noqa: E402, F401
import backend.app.models.series  # noqa: E402, F401


@pytest.fixture(autouse=True)
def setup_db():
    """每个用例都从干净的表结构开始"""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    """FastAPI TestClient"""
    from backend.app.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(client):
    """Register a test user and return Authorization header."""
    client.post("/register", json={"username": "testuser", "password": "testpass123"})
    resp = client.post("/login", json={"username": "testuser", "password": "testpass123"})
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_headers(client):
    """Register a user, promote to admin in DB, return admin auth headers."""
    client.post("/register", json={"username": "adminuser", "password": "testpass123"})
    db = SessionLocal()
    from backend.app.models.user import UserDB
    user = db.query(UserDB).filter(UserDB.username == "adminuser").first()
    if user:
        user.role = "admin"
        db.commit()
    db.close()
    resp = client.post("/login", json={"username": "adminuser", "password": "testpass123"})
    token = resp.json()["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def mock_ai_chat(monkeypatch):
    """Mock DashScope AI chat to return a fixed reply.

    收 *args/**kwargs 是刻意的：调用方若给 chat 传了新关键字参数（如 temperature），
    签名写死的假函数会 TypeError，而测试失败信息会指向假函数、掩盖真实原因。
    """
    def _fake_chat(user_input, history, system_prompt, *args, **kwargs):
        return "这是一条AI模拟回复。"
    monkeypatch.setattr("backend.app.routers.ai.chat", _fake_chat)
    monkeypatch.setattr("backend.app.services.ai_service.chat", _fake_chat)


@pytest.fixture(autouse=True)
def mock_amap_regeo(monkeypatch):
    """Mock AMap reverse geocode to return a fixed address."""
    async def _fake_regeo(longitude, latitude):
        return {
            "province": "黑龙江省",
            "city": "哈尔滨市",
            "district": "南岗区",
            "formatted_address": "黑龙江省哈尔滨市南岗区",
        }
    monkeypatch.setattr("backend.app.routers.amap.reverse_geocode", _fake_regeo)
    monkeypatch.setattr("backend.app.services.amap_service.reverse_geocode", _fake_regeo)


@pytest.fixture(autouse=True)
def mock_detect_service(monkeypatch):
    """Mock detect_change globally so no PyTorch model is loaded."""
    def _fake_detect_change(img1, img2, threshold, model_type, unique_id):
        import numpy as np
        sm = np.zeros((256, 256), dtype=np.float32)
        sm[50:100, 50:100] = 0.9
        mask = (sm > threshold).astype(np.uint8) * 255
        heatmap = np.zeros((256, 256, 3), dtype=np.uint8)
        fusion = np.zeros((256, 256, 3), dtype=np.uint8)
        stats = {"total_pixel": 65536, "change_pixel": 2500, "ratio": 3.81, "threshold": threshold}
        return sm, mask, heatmap, fusion, stats
    monkeypatch.setattr("backend.app.services.detect_service.detect_change", _fake_detect_change)
    monkeypatch.setattr(
        "backend.app.services.detect_service.recommend_threshold_from_images",
        lambda img1, img2: 0.35,
    )


@pytest.fixture
def detection_record(client, auth_headers):
    """Create a detection record via /detect and return the response."""
    resp = client.post(
        "/detect",
        files=[
            ("img1", ("t1.png", _fake_png_bytes(), "image/png")),
            ("img2", ("t2.png", _fake_png_bytes(), "image/png")),
        ],
        data={"model": "BIT", "threshold": 0.5},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    return resp.json()


def _fake_png_bytes():
    import io
    import numpy as np
    from PIL import Image
    arr = np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


@pytest.fixture(autouse=True)
def bypass_captcha(monkeypatch):
    """测试环境跳过图形验证码：register/login 会校验验证码，不绕过则全部 422"""
    import importlib
    from backend.app.core import captcha as captcha_mod
    monkeypatch.setattr(captcha_mod, "verify_captcha", lambda *a, **k: True)
    for name in ("auth", "admin"):
        try:
            mod = importlib.import_module(f"backend.app.routers.{name}")
            if hasattr(mod, "verify_captcha"):
                monkeypatch.setattr(mod, "verify_captcha", lambda *a, **k: True)
        except Exception:
            pass


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """每个用例前重置限流计数，避免跨用例累积触发 429"""
    from backend.app.core.limiter import limiter
    if not hasattr(limiter, "reset"):
        try:
            limiter._storage.reset()
        except Exception:
            pass
    else:
        limiter.reset()
    yield
