import asyncio
import logging
import os
import socket
from contextlib import suppress
from typing import Any

import aiohttp

from browser_use import Agent, BrowserProfile
from browser_use.llm import ChatOpenAI

from backend.app.core.config import (
    DASHSCOPE_API_KEY,
    AGENT_FRONTEND_URL,
    AGENT_USERNAME,
    AGENT_BROWSER_HEADLESS,
    AGENT_MAX_STEPS,
)
from backend.app.core.security import create_access_token

logger = logging.getLogger(__name__)

AGENT_SYSTEM_CONTEXT = """操控浏览器完成用户任务。

目标系统: {frontend_url}/index.html
功能: 变化检测、批量检测、检测历史、结果对比、AI分析

★ 登录态 ★ 系统已在浏览器中预置登录凭据，直接导航到 {frontend_url}/index.html
即可进入已登录状态（无需手动登录，也不要在页面里输入任何凭据）。

规则:
1. 页面加载后等待核心内容出现再操作
2. UI 为中文
3. 文件上传使用上传按钮
4. 最多滚动3次页面，拿到数据后立即 done 汇报
5. 用中文汇报结果，错误说明原因"""


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _get_chrome_path() -> str:
    import shutil
    import platform

    # Linux: system chromium or playwright-installed
    if platform.system() == "Linux":
        for name in ["chromium", "chromium-browser", "google-chrome"]:
            path = shutil.which(name)
            if path:
                return path
        for base in [os.path.expanduser("~/.cache/ms-playwright"), "/root/.cache/ms-playwright"]:
            if os.path.isdir(base):
                for root, _, files in os.walk(base):
                    if "chrome" in files and "chrome-linux" in root:
                        return os.path.join(root, "chrome")
        return "chromium"

    # Windows: search standard ms-playwright install locations
    if platform.system() == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        candidates = [
            os.path.join(local_app_data, "ms-playwright", "chromium-1223", "chrome-win64", "chrome.exe"),
            os.path.join(local_app_data, "ms-playwright", "chromium_headless_shell-1223", "chrome-headless-shell-win64", "chrome-headless-shell.exe"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        base = os.path.join(local_app_data, "ms-playwright")
        if os.path.isdir(base):
            for root, _, files in os.walk(base):
                for f in files:
                    if f == "chrome.exe" and "chrome-win64" in root.replace("\\", "/"):
                        return os.path.join(root, f)
        return "chrome"


def _build_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model="qwen-vl-plus",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=DASHSCOPE_API_KEY,
        temperature=0.2,
        reasoning_effort=None,
        dont_force_structured_output=False,
        max_retries=3,
    )


def _build_fallback_llm() -> ChatOpenAI:
    """备用 LLM（文本模型，结构化输出更稳定）"""
    return ChatOpenAI(
        model="qwen-plus",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key=DASHSCOPE_API_KEY,
        temperature=0.1,
        max_retries=2,
    )


async def _launch_chrome(headless: bool) -> tuple[asyncio.subprocess.Process, str]:
    """手动启动 Chromium 并返回 (process, cdp_url)。绕过 browser-use 内部启动在 Windows 上的兼容问题。"""
    chrome_path = _get_chrome_path()
    port = _find_free_port()
    # 持久化用户目录，保留登录态，避免每次重新登录
    user_data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "browser_profile")
    os.makedirs(user_data_dir, exist_ok=True)

    args = [
        chrome_path,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={user_data_dir}",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-sync",
        "--no-first-run",
        "--no-default-browser-check",
        f"--window-size=1280,900",
        "about:blank",
    ]
    if headless:
        args.insert(1, "--headless=new")

    # 仅当以 root 运行时才关闭沙箱（否则 Chromium 拒绝启动，容器场景常见）；
    # 非 root 环境保留沙箱，不无谓降低浏览器隔离强度
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        args.append("--no-sandbox")

    logger.info("启动Chrome: %s --remote-debugging-port=%d", chrome_path, port)

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    cdp_url = await _wait_for_cdp(port)
    logger.info("Chrome CDP已就绪: %s", cdp_url)
    return proc, cdp_url


async def _wait_for_cdp(port: int, timeout: float = 30) -> str:
    start = asyncio.get_event_loop().time()
    async with aiohttp.ClientSession() as session:
        while asyncio.get_event_loop().time() - start < timeout:
            with suppress(Exception):
                async with session.get(f"http://127.0.0.1:{port}/json/version") as resp:
                    if resp.status == 200:
                        return f"http://127.0.0.1:{port}/"
            await asyncio.sleep(0.2)
    raise TimeoutError(f"Chrome CDP 在 {timeout}s 内未就绪")


async def _inject_auth(cdp_url: str) -> None:
    """通过 CDP 直接向浏览器写入登录态。

    登录凭据由本机进程注入，**不写进发给第三方大模型的提示词** ——
    此前做法是把管理员 JWT 明文嵌在 task 里交给 DashScope，令牌会随
    提示词离开本机，且可能被服务端记录。
    """
    from playwright.async_api import async_playwright

    agent_jwt = create_access_token(data={"sub": AGENT_USERNAME, "role": "admin"})
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        try:
            ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            page = await ctx.new_page()
            await page.goto(f"{AGENT_FRONTEND_URL}/index.html",
                            wait_until="domcontentloaded", timeout=30000)
            await page.evaluate(
                "([t, u]) => { localStorage.setItem('auth_token', t);"
                " localStorage.setItem('login_user', u); }",
                [agent_jwt, AGENT_USERNAME],
            )
            await page.close()
            logger.info("Agent 登录态已注入浏览器")
        finally:
            await browser.close()


async def execute_agent(instruction: str, max_steps: int) -> dict[str, Any]:
    task = AGENT_SYSTEM_CONTEXT.format(frontend_url=AGENT_FRONTEND_URL)
    task += f"\n\n用户任务:\n{instruction}"

    proc = None
    cdp_url = None
    try:
        proc, cdp_url = await _launch_chrome(headless=AGENT_BROWSER_HEADLESS)
        await _inject_auth(cdp_url)
        llm = _build_llm()
        fallback_llm = _build_fallback_llm()
        browser_profile = BrowserProfile(
            cdp_url=cdp_url,
            # 不再关闭浏览器安全策略：指令由用户自由输入，叠加 disable_security
            # 等于把同源策略等防线一并撤掉，风险过高
            disable_security=False,
            window_size={"width": 1280, "height": 900},
            minimum_wait_page_load_time=1.0,
            wait_for_network_idle_page_load_time=2.0,
        )

        step_records: list[dict[str, Any]] = []

        agent = Agent(
            task=task,
            llm=llm,
            fallback_llm=fallback_llm,
            browser_profile=browser_profile,
            use_vision=True,
            flash_mode=False,
            max_failures=3,
            max_actions_per_step=5,
            step_timeout=180,
        )

        logger.info("Agent开始执行: max_steps=%d", max_steps)

        history = await asyncio.wait_for(
            agent.run(max_steps=max_steps),
            timeout=600,
        )

        screenshots = history.screenshots() or []
        valid_screenshots = [s for s in screenshots[-5:] if s is not None]

        logger.info(
            "Agent执行完毕: success=%s steps=%d duration=%.1fs",
            history.is_successful(),
            history.number_of_steps(),
            history.total_duration_seconds(),
        )

        raw_errors = history.errors() or []
        return {
            "success": history.is_successful() or False,
            "final_result": history.final_result(),
            "total_steps": history.number_of_steps(),
            "duration_seconds": round(history.total_duration_seconds(), 1),
            "screenshots": valid_screenshots,
            "visited_urls": [u for u in (history.urls() or []) if u],
            "errors": [e for e in raw_errors if e],
            "step_log": step_records,
        }

    except asyncio.TimeoutError:
        logger.warning("Agent执行超时 (600s)")
        return {
            "success": False,
            "final_result": "执行超时，Agent 未能在 10 分钟内完成任务。请尝试简化指令。",
            "total_steps": 0,
            "duration_seconds": 600,
            "screenshots": [],
            "visited_urls": [],
            "errors": ["任务执行超时 (600s)"],
            "step_log": [],
        }
    finally:
        if proc is not None:
            with suppress(Exception):
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
        logger.info("Chrome进程已终止")
