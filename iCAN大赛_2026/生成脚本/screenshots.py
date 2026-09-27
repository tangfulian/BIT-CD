# -*- coding: utf-8 -*-
"""Playwright 截图：登录页 + 关闭弹窗后的公开页面"""
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8000"
OUT = ".claude/iCAN_out/assets"

pages = [("single", "ui_single.png"), ("dashboard", "ui_dashboard.png"),
         ("status", "ui_status.png"), ("history", "ui_history.png")]

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()

    page.goto(BASE + "/", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1200)
    # 尝试关闭登录弹窗
    try:
        page.click("#authOverlayClose", timeout=3000)
        page.wait_for_timeout(800)
    except Exception as e:
        print("关闭弹窗跳过:", e)

    for name, fname in pages:
        try:
            page.eval_on_selector_all(".nav-item", "els => els.forEach(e => e.classList.remove('active'))")
            page.eval_on_selector_all(".page-content", "els => els.forEach(e => e.classList.remove('active'))")
            page.eval_on_selector(f'button[data-page="{name}"]', "e => e.classList.add('active')")
            page.eval_on_selector(f'#page-{name}', "e => e.classList.add('active')")
            page.wait_for_timeout(1200)
            page.screenshot(path=f"{OUT}/{fname}", full_page=False)
            print(f"截图完成: {fname}")
        except Exception as e:
            print(f"截图失败 {name}:", e)

    b.close()
