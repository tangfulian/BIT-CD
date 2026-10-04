# -*- coding: utf-8 -*-
"""验证本轮修复是否真正生效（端到端行为，而非仅语法正确）"""
import os, sys, io, pathlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
ROOT = pathlib.Path(r"D:\BIT_CD")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ["DATABASE_URL"] = "sqlite:///./verify_tmp.db"

ok = fail = 0


def check(name, cond, extra=""):
    global ok, fail
    if cond:
        print(f"  ✓ {name}")
        ok += 1
    else:
        print(f"  ✗ {name}  {extra}")
        fail += 1


print("=== 1. 权重缺失的模型必须显式失败 ===")
from backend.app.services.detect_service import get_model, ModelNotAvailableError
for m in ("FC_SIAM_DIFF", "SNUNET", "CHANGEFORMER"):
    try:
        get_model(m)
        check(f"{m} 抛出 ModelNotAvailableError", False, "—— 仍然静默返回了模型！")
    except ModelNotAvailableError as e:
        check(f"{m} 抛出 ModelNotAvailableError", True)
    except Exception as e:
        check(f"{m} 抛出 ModelNotAvailableError", False, f"—— 抛的是 {type(e).__name__}: {e}")

print()
print("=== 2. 有权重的模型仍能正常加载 ===")
try:
    check("BIT 模型加载成功", get_model("BIT") is not None)
except Exception as e:
    check("BIT 模型加载成功", False, f"—— {type(e).__name__}: {e}")

print()
print("=== 3. 生产环境的验证码校验确实生效（未因放宽字段而失效）===")
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.models.database import Base, engine
from backend.app.core import captcha as cap_mod
from PIL import Image
import numpy as np

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
client = TestClient(create_app(), raise_server_exceptions=False)  # 让未处理异常以 500 响应呈现，便于断言


def login(username, password):
    """取验证码并登录（测试环境直接从内存存储读答案）"""
    d = client.get("/captcha").json()["data"]
    cid = d["captcha_id"]
    return cid, cap_mod._store[cid][0]


cid, _ = login("x", "y")
r = client.post("/login", json={"username": "nobody", "password": "whatever1",
                                "captcha_id": cid, "captcha_answer": "WRONG"})
check("错误的验证码被拒绝（生产校验有效）", r.status_code == 400, f"—— {r.status_code}")
cid, _ = login("x", "y")
r = client.post("/login", json={"username": "nobody", "password": "whatever1"})
check("不传验证码被拒绝", r.status_code == 400, f"—— {r.status_code}")

cid, ans = login("v", "v")
r = client.post("/register", json={"username": "vuser", "password": "verify12345",
                                   "captcha_id": cid, "captcha_answer": ans})
check("正确验证码可注册", r.status_code == 200, f"—— {r.status_code} {r.text[:80]}")

cid, ans = login("v", "v")
r = client.post("/login", json={"username": "vuser", "password": "verify12345",
                                "captcha_id": cid, "captcha_answer": ans})
H = {"Authorization": f"Bearer {r.json()['token']}"} if r.status_code == 200 else {}
check("正确验证码可登录", r.status_code == 200, f"—— {r.status_code}")

print()
print("=== 4. HTTP 行为：无权重模型 → 503；非法输入 → JSON 错误 ===")
img = Image.fromarray(np.random.randint(0, 255, (128, 128, 3), dtype=np.uint8))
def buf():
    b = io.BytesIO(); img.save(b, "PNG"); b.seek(0); return b

r = client.post("/detect", headers=H, data={"model": "SNUNET", "threshold": "0.5"},
                files={"img1": ("a.png", buf(), "image/png"), "img2": ("b.png", buf(), "image/png")})
check("无权重模型返回 503（而非 200 + 噪声结果）", r.status_code == 503,
      f"—— 实际 {r.status_code}: {r.text[:90]}")
if r.status_code == 503:
    print(f"      响应：{r.json()}")

r = client.post("/detect", headers=H, data={"model": "BIT", "threshold": "0.5"},
                files={"img1": ("a.txt", b"not an image", "text/plain"),
                       "img2": ("b.txt", b"not an image", "text/plain")})
ct = r.headers.get("content-type", "")
check("非法图片返回结构化 JSON 错误（而非裸 500 文本）",
      r.status_code >= 400 and "json" in ct, f"—— {r.status_code}, {ct}")
if r.status_code >= 400 and "json" in ct:
    print(f"      响应：{str(r.json())[:120]}")

r = client.post("/detect", headers=H, data={"model": "BIT", "threshold": "0.5"},
                files={"img1": ("a.png", buf(), "image/png"), "img2": ("b.png", buf(), "image/png")})
check("正常路径仍可用（BIT + 合法图片返回 200）", r.status_code == 200,
      f"—— {r.status_code}: {r.text[:90]}")

print()
print(f"结果：{ok} 项通过，{fail} 项失败")
for f in (ROOT / "verify_tmp.db", ROOT / "tests" / "test_bitcd.db"):
    if f.exists():
        try: f.unlink()
        except Exception: pass
sys.exit(1 if fail else 0)
