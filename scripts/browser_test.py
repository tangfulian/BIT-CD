"""浏览器端验证：批量检测 / 地图底图 / 导出报表。

这三块只能靠真浏览器验 —— 批量是前端循环调 /detect，地图靠高德 JS SDK 渲染，
导出是 jsPDF/html2canvas 在浏览器里生成的。接口测试覆盖不到。

登录态靠注入 localStorage 的三个键，不走 /login：它强制校验验证码，
脚本认不出图（这正是 smoke_test.py 长期静默失效的原因，那边踩过一次）。

用法：
    python api.py                     # 另开一个终端
    python scripts/browser_test.py

会造 1~2 条检测记录，跑完自动删掉。

两个踩过的坑，改这个文件前先读：
  1. **拦截请求必须用 context.route，不能用 page.route** —— 本项目注册了
     Service Worker，SW 发出的请求绕过 page.route，表现为「明明拦了却生效」。
  2. **在 add_init_script 里改 window.indexedDB.open 不生效** —— 实测
     hasOwnProperty 仍是 false、调用照常不抛错。想制造 IndexedDB 写失败，
     要替换模块导出的方法：`(await import('/js/indexedDB.js')).BatchStore.saveTask`
     —— ES 模块导出是同一个对象，batchDetector 里拿到的就是它。
"""

import json
import os
import pathlib
import sqlite3
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from backend.app.core.security import create_access_token    # noqa: E402

from playwright.sync_api import sync_playwright              # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

URL = os.getenv("BITCD_BASE", "http://127.0.0.1:8000") + "/"
DB = ROOT / "blackland.db"
RESULTS = ROOT / "results"
TOKEN = create_access_token({"sub": "admin", "role": "admin"})
SEED = ("localStorage.setItem('auth_token', " + json.dumps(TOKEN) + ");"
        "localStorage.setItem('login_user', 'admin');"
        "localStorage.setItem('login_user_role', 'admin');")

# 制造 IndexedDB 写失败（见文件头坑 2）
BREAK_IDB = """
async () => {
  const m = await import('/js/indexedDB.js');
  m.BatchStore.saveTask = () => Promise.reject(new Error('IndexedDB 已被测试禁用'));
  return typeof m.BatchStore.saveTask;
}
"""

OK, BAD = 0, []


def check(label, cond, detail=""):
    global OK
    if cond:
        OK += 1
        print(f"  PASS  {label}")
    else:
        BAD.append(label)
        print(f"  FAIL  {label}   {detail}")


def rec_ids():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    return sorted(r[0] for r in c.execute("select id from detection_results"))


def make_pair(tmp, n):
    np.random.seed(np.random.randint(1 << 30))
    a = Image.fromarray(np.random.randint(0, 255, (256, 256, 3), dtype=np.uint8))
    b = np.array(a.copy()).astype(np.int16)
    b[60:160, 60:160] = np.clip(b[60:160, 60:160] + 90, 0, 255)
    p1, p2 = tmp / f"pair{n}_t1.png", tmp / f"pair{n}_t2.png"
    a.save(p1)
    Image.fromarray(b.astype(np.uint8)).save(p2)
    return p1, p2


def run_batch(browser, pairs, break_idb):
    ctx = browser.new_context(accept_downloads=True)
    page = ctx.new_page()
    page.add_init_script(SEED)
    console = []
    page.on("console", lambda m: console.append(m.text))

    page.goto(URL, wait_until="load")
    page.wait_for_timeout(1500)
    page.click('[data-page="batch"]')
    page.wait_for_timeout(600)

    if break_idb:
        page.evaluate(BREAK_IDB)

    page.select_option("#batch_model", "DIFF")
    page.set_input_files("#batch_t1", [str(a) for a, _ in pairs])
    page.set_input_files("#batch_t2", [str(b) for _, b in pairs])
    page.click("#batchStart")
    page.wait_for_selector("#batchSummaryBar:not(.hidden)", timeout=180_000)
    page.wait_for_timeout(1500)

    out = {
        "ctx": ctx, "page": page, "console": console,
        "total": page.text_content("#batchSumTotal"),
        "done": page.text_content("#batchSumDone"),
        "failed": page.text_content("#batchSumFailed"),
        "rows": page.eval_on_selector_all("#batchTableBody tr", "e => e.length"),
        "toasts": page.eval_on_selector_all(".toast", "e => e.map(x => x.textContent.trim())"),
    }
    return out


def main():
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="bitcd_browser_"))
    pairs = [make_pair(tmp, 0), make_pair(tmp, 1)]
    before = rec_ids()

    with sync_playwright() as p:
        browser = p.chromium.launch()

        print("=== 批量检测（IndexedDB 正常）===")
        a = run_batch(browser, pairs, break_idb=False)
        print(f"  总数={a['total']} 完成={a['done']} 失败={a['failed']} 表格行={a['rows']}")
        check("2 组全部完成、无失败",
              a["total"] == "2" and a["done"] == "2" and a["failed"] == "0", a)
        check("结果表渲染出 2 行", a["rows"] == 2, a["rows"])
        check("没有误报「进度无法保存」（持久化正常）",
              not any("无法保存" in t for t in a["toasts"]), a["toasts"])

        print("\n=== 导出报表 ===")
        page = a["page"]
        for btn, name, magic in (("#batchExport", "CSV", None),
                                 ("#batchExportPDF", "PDF", b"%PDF-")):
            try:
                with page.expect_download(timeout=90_000) as dl:
                    page.click(btn)
                d = dl.value
                path = pathlib.Path(d.path())
                size = path.stat().st_size if path.exists() else 0
                print(f"  {name}: {d.suggested_filename}  {size} 字节")
                check(f"{name} 下载成功且非空", size > 0, size)
                if magic:
                    check(f"{name} 是有效文件（以 {magic.decode()} 开头）",
                          path.read_bytes()[:5] == magic, path.read_bytes()[:8])
                elif name == "CSV":
                    text = path.read_text(encoding="utf-8", errors="replace")
                    check("CSV 带 UTF-8 BOM（Excel 打开中文不乱码）",
                          text.startswith("﻿"), repr(text[:8]))
                    print(f"  表头: {text.lstrip(chr(0xFEFF)).splitlines()[0][:90]}")
            except Exception as e:
                check(f"{name} 触发下载", False, f"{type(e).__name__}: {e}")
        a["ctx"].close()

        print("\n=== 批量检测（IndexedDB 写入失败）===")
        b = run_batch(browser, pairs, break_idb=True)
        print(f"  总数={b['total']} 完成={b['done']} 失败={b['failed']}")
        check("写失败不阻断检测流程", b["total"] == "2" and b["done"] == "2", b)
        check("★ 提示「进度无法保存」（这是静默降级修复的验收点）",
              any("无法保存" in t for t in b["toasts"]), b["toasts"])
        check("提示只出现一次，连续两张图不刷屏",
              sum(1 for t in b["toasts"] if "无法保存" in t) == 1, b["toasts"])
        check("失败原因进了 console（便于排查）",
              any("队列持久化失败" in c for c in b["console"]), b["console"][:3])
        b["ctx"].close()

        print("\n=== 地图 ===")
        ctx = browser.new_context()
        page = ctx.new_page()
        page.add_init_script(SEED)
        page.goto(URL, wait_until="load")
        page.wait_for_timeout(1200)
        page.click('[data-page="mapviewer"]')
        page.wait_for_timeout(5000)

        info = page.evaluate("""() => {
          const el = document.getElementById('mapviewerMap');
          const hint = document.getElementById('mapEmptyHint');
          const r = el ? el.getBoundingClientRect() : null;
          return {
            amapDefined: typeof AMap !== 'undefined',
            kids: el ? Array.from(el.children).map(c => c.tagName + '.' + (c.className || '')) : [],
            canvas: el ? el.querySelectorAll('canvas').length : 0,
            rect: r ? [Math.round(r.width), Math.round(r.height)] : null,
            hintVisible: hint ? getComputedStyle(hint).display !== 'none' : null,
            invalidDomain: !!window.__AMAP_INVALID_DOMAIN__,
          };
        }""")
        print("  " + json.dumps(info, ensure_ascii=False))
        check("AMap SDK 已加载", info["amapDefined"])
        check("容器有尺寸（没被折叠成 0 高）",
              bool(info["rect"]) and info["rect"][0] > 100 and info["rect"][1] > 100,
              info["rect"])
        check("AMap 接管了容器（注入了自己的子节点）", len(info["kids"]) > 0, info["kids"])
        check("画布已创建", info["canvas"] > 0, info)
        check("没有 INVALID_USER_DOMAIN（域名白名单问题）", not info["invalidDomain"], info)
        ctx.close()

        browser.close()

    new = sorted(set(rec_ids()) - set(before))
    print(f"\n=== 清理 ===\n  本轮新增记录: {new}")
    if new:
        c = sqlite3.connect(DB)
        rows = list(c.execute(
            "select id, mask_url, heat_url, fusion_url, score_url from detection_results "
            f"where id in ({','.join('?' * len(new))})", new))
        for r in rows:
            for u in r[1:]:
                if u:
                    f = RESULTS / u.rsplit("/", 1)[-1]
                    if f.exists():
                        f.unlink()
        c.executemany("delete from detection_results where id=?", [(i,) for i in new])
        c.commit()
        print(f"  已删除 {len(rows)} 条记录及其文件")

    print(f"\n{'=' * 52}\n{OK} passed, {len(BAD)} failed")
    for x in BAD:
        print("  -", x)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
