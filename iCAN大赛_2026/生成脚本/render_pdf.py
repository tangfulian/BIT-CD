"""Render report.html -> report.pdf via Playwright Chromium."""
import pathlib
from playwright.sync_api import sync_playwright

BASE = pathlib.Path(r"d:\A汤福连的比赛与实验\BIT_CD\.claude\iCAN_out")
html_path = BASE / "report.html"
out_path = BASE / "report.pdf"
url = html_path.resolve().as_uri()

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(url, wait_until="networkidle", timeout=120_000)
    # give images a moment
    page.wait_for_timeout(1500)
    page.pdf(
        path=str(out_path),
        format="A4",
        print_background=True,
        margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
    )
    browser.close()

size_mb = out_path.stat().st_size / (1024 * 1024)
print(f"PDF saved: {out_path}")
print(f"Size: {size_mb:.2f} MB")
