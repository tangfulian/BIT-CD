"""冒烟测试没覆盖的三块：地块档案 / 时序序列 / 灾害定损。

smoke_test.py 覆盖的是检测、评估、历史、标注、鉴权那一片；这三块当时排在
它之后，一直没人系统跑过。这里补上。

顺带验两类容易蒙混过去的地方：
  - **响应结构**：records 是挂在响应顶层还是嵌在 series 里，字段到底叫什么
    （写测试时全靠猜字段名会得到「看起来失败」的假信号，所以这里断言前先打印）
  - **数值自洽**：定损的受灾面积不得超过地块总面积；损失额不得超过「全部绝收」
    的上限。这类断言比「接口返回 200」有意义得多。

用法：
    python api.py                     # 另开一个终端
    python scripts/api_misc_test.py

会造一条检测记录、一个序列、一个地块，跑完全部删掉。
"""

import io
import json
import os
import pathlib
import random
import sys

import numpy as np
import requests
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)   # DATABASE_URL 是相对路径，必须站在项目根

from backend.app.core.security import create_access_token    # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE = os.getenv("BITCD_BASE", "http://127.0.0.1:8000")
H = {"Authorization": "Bearer " + create_access_token({"sub": "admin", "role": "admin"})}
HJ = {**H, "Content-Type": "application/json"}

OK, BAD = 0, []


def check(label, cond, detail=""):
    global OK
    if cond:
        OK += 1
        print(f"  PASS  {label}")
    else:
        BAD.append(label)
        print(f"  FAIL  {label}   {detail}")


def png(img):
    b = io.BytesIO()
    img.save(b, format="PNG")
    b.seek(0)
    return b.read()


def main():
    np.random.seed(random.randrange(1 << 30))   # 每轮图都不同，避开检测缓存
    a = Image.fromarray(np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8))
    b = np.array(a.copy()).astype(np.int16)
    b[80:180, 80:180] = np.clip(b[80:180, 80:180] + 90, 0, 255)
    files = {"img1": ("1.png", png(a), "image/png"),
             "img2": ("2.png", png(Image.fromarray(b.astype(np.uint8))), "image/png")}
    base = {"lat_lng": "125.3,43.8", "location": "测试地块",
            "change_type": "黑土层变薄退化", "t1_time": "2024-06", "t2_time": "2025-06"}

    made = {"records": [], "series": [], "plots": []}
    try:
        print("=== 地块档案 CRUD ===")
        # 注意前缀是 /plots（复数）。写成 /plot 会落到挂在 / 的 SPA 静态服务上，
        # 返回 405 而不是 404 —— 看起来像「路径对但方法错」，很能带偏排查方向。
        r = requests.post(f"{BASE}/plots", headers=HJ, timeout=30, json={
            "name": "__功能验证地块__", "area": 120,
            "crop_type": "玉米", "lat_lng": "125.3,43.8"})
        check("POST /plots", r.status_code in (200, 201), f"{r.status_code} {r.text[:120]}")
        pid = r.json().get("id") if r.status_code in (200, 201) else None
        if pid:
            made["plots"].append(pid)

        r = requests.get(f"{BASE}/plots", headers=H, timeout=30)
        check("GET /plots 列表含新建地块",
              r.status_code == 200 and any(p.get("id") == pid for p in r.json()))

        r = requests.put(f"{BASE}/plots/{pid}", headers=HJ, timeout=30,
                         json={"name": "__功能验证地块改名__", "area": 150})
        check("PUT /plots/{id} 更新生效",
              r.status_code == 200 and r.json().get("area") == 150, r.status_code)

        print("\n=== 造一条检测记录（序列与定损都要用）===")
        r = requests.post(f"{BASE}/detect", headers=H, timeout=240,
                          data={"model": "BIT", "threshold": 0.5, **base}, files=files)
        check("POST /detect", r.status_code == 200, f"{r.status_code} {r.text[:150]}")
        det = r.json().get("detection_id") if r.status_code == 200 else None
        if det:
            made["records"].append(det)

        print("\n=== 时序序列 ===")
        r = requests.post(f"{BASE}/series", headers=HJ, timeout=30, json={
            "name": "__功能验证序列__", "location": "测试地块", "area_mu": 120})
        check("POST /series", r.status_code == 200, f"{r.status_code} {r.text[:120]}")
        sid = (r.json().get("series") or {}).get("id") if r.status_code == 200 else None
        if sid:
            made["series"].append(sid)

        if sid and det:
            r = requests.post(f"{BASE}/series/{sid}/records", headers=HJ, timeout=30,
                              json={"records": [{"detection_id": det,
                                                 "t1_time": "2024-06", "t2_time": "2025-06"}]})
            check("POST /series/{id}/records 挂载", r.status_code == 200,
                  f"{r.status_code} {r.text[:150]}")

            r = requests.get(f"{BASE}/series/{sid}", headers=H, timeout=30)
            body = r.json() if r.status_code == 200 else {}
            check("GET /series/{id} 成功", r.status_code == 200)
            # records 在**响应顶层**，不在 series 里面
            got = len(body.get("records") or [])
            check("序列里确实有 1 条记录", got == 1,
                  f"实际 {got}；顶层键={list(body.keys())}")

            r = requests.get(f"{BASE}/series/{sid}/trend", headers=H, timeout=30)
            check("GET /series/{id}/trend", r.status_code == 200, r.status_code)
            if r.status_code == 200:
                t = r.json().get("trend") or {}
                check("趋势里有 1 个区间", t.get("interval_count") == 1, t)

        r = requests.post(f"{BASE}/series/999999/records", headers=HJ, timeout=30,
                          json={"records": [{"detection_id": det or 1}]})
        check("挂到不存在的序列返回 404", r.status_code == 404, r.status_code)

        print("\n=== 灾害定损 ===")
        check("GET /disaster/params", requests.get(
            f"{BASE}/disaster/params", headers=H, timeout=30).status_code == 200)

        if det:
            r = requests.post(f"{BASE}/disaster/assess", headers=HJ, timeout=60, json={
                "detection_id": det, "area_mu": 120, "crop_type": "玉米",
                "yield_per_mu": 500, "price_per_kg": 2.4})
            check("POST /disaster/assess", r.status_code == 200, r.text[:200])
            if r.status_code == 200:
                res = r.json()["result"]
                print("        数值字段: " + json.dumps(
                    {k: v for k, v in res.items() if not isinstance(v, (dict, list))},
                    ensure_ascii=False))

                tot = res.get("total_loss_yuan")
                cap = 120 * 500 * 2.4      # 全部绝收时的上界
                check(f"损失额是数值且不超过「全部绝收」上限 {cap:,.0f}",
                      isinstance(tot, (int, float)) and 0 <= tot <= cap + 1, tot)

                # 不能写 `res.get("area") or 0` —— 字段缺失时 0 <= 120 会假通过
                area = next((res[k] for k in res if "area" in k.lower()
                             and isinstance(res[k], (int, float))), None)
                check("存在数值型受灾面积且不超过地块总面积 120 亩",
                      area is not None and area <= 120 + 0.01, area)

            r = requests.post(f"{BASE}/disaster/assess", headers=HJ, timeout=30,
                              json={"detection_id": 999999, "area_mu": 10})
            check("定损不存在的记录返回 404", r.status_code == 404, r.status_code)

    finally:
        print("\n=== 清理 ===")
        for i in made["records"]:
            print("  删记录", i, requests.delete(
                f"{BASE}/history/{i}", headers=H, timeout=30).status_code)
        for i in made["series"]:
            print("  删序列", i, requests.delete(
                f"{BASE}/series/{i}", headers=H, timeout=30).status_code)
        for i in made["plots"]:
            print("  删地块", i, requests.delete(
                f"{BASE}/plots/{i}", headers=H, timeout=30).status_code)

    print(f"\n{'=' * 52}\n{OK} passed, {len(BAD)} failed")
    for x in BAD:
        print("  -", x)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
