"""Agent 七个工具的**实际执行**验证。

与另两个测试的分工，别重复劳动：
    eval_agent_intent.py   只测「模型会选哪个工具」，不执行，不碰数据
    agent_e2e_test.py      测编排层（含真实 LLM 往返）
    本文件                 绕过模型直调工具处理器 —— 确定性、不花 LLM 调用

重点不在「能不能跑通」，而在两条**安全边界**（这两条一旦破了，
工具通道就从「替你点按钮」变成「替你越权」）：

  1. run_detection 的附件事白名单 —— 严格逐字符命中，不做 normpath 宽容化
  2. get_detection / get_series_trend 的归属过滤 —— 读不到别人的记录

用法：
    python scripts/agent_tools_test.py

不需要先起服务（进程内直调）。会在库里建一条测试记录，跑完自动删掉。
"""

import io
import json
import os
import pathlib
import random
import sqlite3
import sys

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# DATABASE_URL 是相对路径 sqlite:///./blackland.db，必须站在项目根目录，
# 否则会静默连到另一个空库上，报「no such table: users」。
os.chdir(ROOT)

from backend.app.core.security import get_db                                  # noqa: E402
from backend.app.models.detection import DetectionResultDB                    # noqa: E402
from backend.app.models.user import UserDB                                    # noqa: E402
from backend.app.services.tool_agent_service import _run_tool                 # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

OK, BAD = 0, []


def check(label, cond, detail=""):
    global OK
    if cond:
        OK += 1
        print(f"  PASS  {label}")
    else:
        BAD.append(label)
        print(f"  FAIL  {label}   {detail}")


def call(name, args, ctx):
    """执行一个工具，返回 (是否成功, 解析后的结果)。"""
    success, text = _run_tool(name, args, ctx)
    try:
        return success, json.loads(text)
    except Exception:
        return success, text


def main():
    import tempfile

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="agent_tools_"))
    np.random.seed(random.randrange(1 << 30))
    img1 = Image.fromarray(np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8))
    arr = np.array(img1.copy()).astype(np.int16)
    arr[60:160, 60:160] = np.clip(arr[60:160, 60:160] + 90, 0, 255)
    p1, p2 = tmp / "t1.png", tmp / "t2.png"
    img1.save(p1)
    Image.fromarray(arr.astype(np.uint8)).save(p2)

    db = next(get_db())
    admin = db.query(UserDB).filter(UserDB.role == "admin").first()
    other = db.query(UserDB).filter(UserDB.role != "admin").first()
    if admin is None:
        print("库里没有管理员账号，先跑一次 python api.py 建库")
        return 1

    ctx = {"user": admin, "db": db, "base_url": "http://127.0.0.1:8000",
           "file_paths": [str(p1), str(p2)]}
    other_ctx = ({"user": other, "db": db, "base_url": "http://127.0.0.1:8000",
                  "file_paths": []} if other else None)
    print(f"admin={admin.username!r}(id={admin.id})   "
          f"非管理员={other.username if other else '（库里没有，跨用户用例将跳过）'}")

    created = []
    try:
        print("\n=== list_models ===")
        s, res = call("list_models", {}, ctx)
        check("执行成功", s, res)
        names = (res.get("available_models") or []) if isinstance(res, dict) else []
        check("返回非空清单", bool(names), res)
        check("只列真正可用的（未部署权重的三个不在内）",
              not ({"FC_SIAM_DIFF", "SNUNET", "CHANGEFORMER"} & set(names)), names)
        print(f"        可用: {names}")

        print("\n=== run_detection：附件事白名单（安全边界 1）===")
        s, res = call("run_detection",
                      {"image1": "/etc/passwd", "image2": str(p2), "model": "DIFF"}, ctx)
        check("白名单外的路径被拒", not s, res)
        check("拒绝理由可读",
              isinstance(res, dict) and "不在本次可用附件" in str(res.get("error")), res)

        s, res = call("run_detection",
                      {"image1": str(p1) + "/../t1.png", "image2": str(p2),
                       "model": "DIFF"}, ctx)
        check("带 ../ 的变体也被拒（不做 normpath 宽容化）", not s, res)

        s, res = call("run_detection",
                      {"image1": str(p1), "image2": str(p2), "model": "NO_SUCH"}, ctx)
        check("不存在的模型被拒", not s, res)

        print("\n=== run_detection：正常执行 ===")
        s, res = call("run_detection",
                      {"image1": str(p1), "image2": str(p2),
                       "model": "BIT", "threshold": 0.5}, ctx)
        check("执行成功", s, res)
        det_id = res.get("detection_id") if isinstance(res, dict) else None
        if det_id:
            created.append(det_id)
            print(f"        detection_id={det_id}")

        print("\n=== list_detections ===")
        s, res = call("list_detections", {"limit": 5}, ctx)
        check("执行成功", s, res)
        items = res.get("items") if isinstance(res, dict) else None
        check("能列到刚造的那条",
              bool(items) and any(r.get("detection_id") == det_id for r in items),
              res)

        print("\n=== get_detection：归属过滤（安全边界 2）===")
        s, res = call("get_detection", {"detection_id": det_id}, ctx)
        check("本人读自己的记录成功", s, res)
        check("不泄露地块面积/作物类型（描述里承诺过）",
              isinstance(res, dict)
              and "plot_area_mu" not in res and "crop_type" not in res, res)

        s, res = call("get_detection", {"detection_id": 999999}, ctx)
        check("不存在的 ID 报错", not s, res)

        if other_ctx:
            s, res = call("get_detection", {"detection_id": det_id}, other_ctx)
            check("★ 别的普通用户读不到这条记录（IDOR）", not s, res)
            print(f"        对方拿到: {json.dumps(res, ensure_ascii=False)[:110]}")
        else:
            print("        （库里没有非管理员账号，跨用户用例跳过）")

        print("\n=== assess_disaster ===")
        s, res = call("assess_disaster",
                      {"detection_id": det_id, "area_mu": 100,
                       "yield_per_mu": 500, "price_per_kg": 2.4}, ctx)
        check("参数齐全时成功", s, res)
        check("不误报警告", isinstance(res, dict) and "warning" not in res, res)
        if isinstance(res, dict):
            print(f"        total_loss_yuan={res.get('total_loss_yuan')}")

        s, res = call("assess_disaster",
                      {"detection_id": det_id, "yield_per_mu": 500,
                       "price_per_kg": 2.4}, ctx)
        check("★ 缺面积时必须告警（曾经漏查，会汇报「无损失」）",
              isinstance(res, dict) and "warning" in res
              and "地块总面积" in str(res.get("warning")), res)
        if isinstance(res, dict) and res.get("warning"):
            print(f"        warning: {res['warning'][:90]}")

        print("\n=== list_series / get_series_trend ===")
        s, res = call("list_series", {}, ctx)
        check("list_series 成功", s, res)
        s, res = call("get_series_trend", {"series_id": 999999}, ctx)
        check("不存在的序列报错", not s, res)

        s, res = call("list_series", {}, ctx)
        series = res.get("series") if isinstance(res, dict) else None
        if series:
            sid = series[0].get("id")
            s, res = call("get_series_trend", {"series_id": sid}, ctx)
            check(f"读自己的序列 {sid} 成功", s, res)
            if other_ctx:
                s, res = call("get_series_trend", {"series_id": sid}, other_ctx)
                check("★ 别的普通用户读不到这条序列（IDOR）", not s, res)
        else:
            print("        （当前没有序列，趋势读取用例跳过）")

    finally:
        print("\n=== 清理 ===")
        for i in created:
            row = db.query(DetectionResultDB).filter(DetectionResultDB.id == i).first()
            if row:
                for u in (row.mask_url, row.heat_url, row.fusion_url, row.score_url):
                    if u:
                        f = ROOT / "results" / u.rsplit("/", 1)[-1]
                        if f.exists():
                            f.unlink()
                db.delete(row)
                print(f"  删除记录 {i}")
        db.commit()
        db.close()

    print(f"\n{'=' * 52}\n{OK} passed, {len(BAD)} failed")
    for b in BAD:
        print("  -", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
