import asyncio
import logging
import os
import signal
import socket
from contextlib import suppress
from typing import Any

import aiohttp

from browser_use import Agent, BrowserProfile, Tools
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

# 同一时刻只允许一个 Agent 任务。
#
# 不只是省资源：Chrome 对同一个 --user-data-dir 有单实例锁，两个任务同时启动时
# 第二个进程会把命令行转交给已在跑的实例然后自行退出，于是它那个
# --remote-debugging-port 永远等不到 CDP —— 表现为"启动超时"，报错方向完全错误。
# 与其让用户看到这种莫名其妙的失败，不如明确拒绝第二个请求。
_agent_lock = asyncio.Lock()

AGENT_SYSTEM_CONTEXT = """操控浏览器完成用户任务。

目标系统: {frontend_url}/index.html

★ 登录态 ★ 系统已在浏览器中预置登录凭据，直接导航到 {frontend_url}/index.html
即可进入已登录状态（无需手动登录，也不要在页面里输入任何凭据）。

站点左侧导航栏包含以下页面（中文名 → 用途）：
  地块信息    —— 配置地块位置、面积、作物等基础信息
  单张检测    —— 上传一对双时相影像做变化检测（主要工作页）
  批量检测    —— 一次提交多组影像批量检测
  检测历史    —— 查看/筛选/删除历次检测记录
  数据看板    —— 检测数据统计大屏
  时序分析    —— 把同一地块多期影像组成序列，分析变化速率与趋势
  系统状态    —— 服务运行状态
  结果对比    —— 两条检测记录并排比较
  模型评估    —— 用标注数据评估模型精度
  灾害定损    —— 按变化检测结果估算受灾面积与经济损失
  AI Agent    —— 本功能自身
  检测地图    —— 把带坐标的检测记录打点到地图
  用户管理    —— 管理员功能
  个人中心    —— 账号信息与改密
  关于系统    —— 版本与说明

规则:
1. 页面加载后等待核心内容出现再操作
2. UI 为中文
3. **不确定页面上有什么时，先看左侧导航栏**，不要凭猜测点击
4. 文件上传使用上传按钮
5. 最多滚动3次页面，拿到数据后立即 done 汇报
6. 用中文汇报结果，错误说明原因"""

# 单次任务的总时长上限（秒）。超时文案由它生成，避免两处硬编码各说各的。
AGENT_RUN_TIMEOUT = 600
# 启动 Chrome 后等待 CDP 就绪的上限（秒）
CDP_READY_TIMEOUT = 30

# 不交给 Agent 的工具。
#
# evaluate 能在页面里执行任意 JS，而本服务刚把 24 小时有效的管理员 JWT 写进了
# localStorage —— 只要 Agent 被诱导执行一句 fetch(...+localStorage.auth_token)
# 令牌就出网了。而 Agent 会浏览页面、页面文本会进模型上下文，这条注入路径是通的。
# 文件读写与导出 PDF 对"操作本系统网页"这个任务没有用处，一并去掉，缩小面。
#
# 注意：这是本模块唯一的安全边界，改动前先想清楚新增的工具能不能碰到 localStorage。
AGENT_EXCLUDED_TOOLS = [
    "evaluate",
    "write_file",
    "replace_file",
    "read_file",
    "save_as_pdf",
]


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _newest_playwright_chromium(base: str, marker: str) -> str | None:
    """在 ms-playwright 目录下找构建号最大的 chromium。

    此前把构建号写死成 chromium-1223，而线上实际是 1243 —— 写死的版本号是
    机器状态而非代码保证，playwright 一升级就失效。改为扫描取最新。
    """
    best, best_ver = None, -1
    if not os.path.isdir(base):
        return None
    for entry in os.listdir(base):
        if not entry.startswith("chromium-"):
            continue
        try:
            ver = int(entry.split("-", 1)[1].split("_")[0])
        except (IndexError, ValueError):
            continue
        if ver <= best_ver:
            continue
        for root, _, files in os.walk(os.path.join(base, entry)):
            if marker in files:
                best, best_ver = os.path.join(root, marker), ver
                break
    return best


def _get_chrome_path() -> str:
    import platform
    import shutil

    system = platform.system()

    if system == "Linux":
        for name in ["chromium", "chromium-browser", "google-chrome"]:
            path = shutil.which(name)
            if path:
                return path
        for base in [os.path.expanduser("~/.cache/ms-playwright"), "/root/.cache/ms-playwright"]:
            found = _newest_playwright_chromium(base, "chrome")
            if found:
                return found
        return "chromium"

    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
        base = os.path.join(local_app_data, "ms-playwright")
        found = _newest_playwright_chromium(base, "chrome.exe")
        if found:
            return found
        return "chrome"

    # 其它平台（如 macOS）此前走完两个 if 后隐式返回 None，
    # 随后 create_subprocess_exec(None, ...) 会抛一个与真实原因无关的 TypeError
    logger.warning("未针对平台 %s 适配 Chrome 路径查找，回退到 PATH 中的 chromium", system)
    return shutil.which("chromium") or shutil.which("google-chrome") or "chromium"


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
        # 只绑回环。CDP 本身没有任何鉴权，绑到 0.0.0.0 等于把一个已登录管理员的
        # 浏览器控制权交给同网段任何人。
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={user_data_dir}",
        "--disable-gpu",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-sync",
        # 容器默认 /dev/shm 只有 64MB，本系统有地图/ECharts 大屏/影像画布这类
        # 重页面，渲染进程很容易因共享内存不足而崩溃 —— 而崩溃发生在 CDP 就绪
        # 之后，日志里看不出是 Chrome 的问题。改用 /tmp 落盘。
        "--disable-dev-shm-usage",
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

    # stderr 落盘而不是丢进 DEVNULL：Chrome 拒绝启动、profile 损坏、共享内存不足
    # 等都会写 stderr，丢了就只剩一句"CDP 超时"，完全无从诊断。
    stderr_target = asyncio.subprocess.DEVNULL
    stderr_handle = None
    try:
        log_dir = os.path.join(_project_root(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        stderr_handle = open(os.path.join(log_dir, "chrome.log"), "ab")
        stderr_target = stderr_handle
    except OSError:
        logger.warning("无法写入 Chrome 日志目录，stderr 将被丢弃")

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=stderr_target,
            # POSIX 下让 Chrome 自成进程组，便于连同它的 renderer/gpu 子进程一起
            # 清理；Windows 上该参数被忽略，走 terminate 分支。
            start_new_session=True,
        )
    finally:
        # 子进程已 dup 走这个 fd，父进程这份要关掉，否则每跑一次泄一个句柄
        if stderr_handle is not None:
            with suppress(Exception):
                stderr_handle.close()

    try:
        cdp_url = await _wait_for_cdp(port)
    except Exception:
        # 启动阶段失败时 proc 还握在手里，必须在这里杀掉再抛。
        # 此前异常直接从 _launch_chrome 冒出，调用方那句 `proc, cdp_url = ...`
        # 解包失败、proc 仍是 None，finally 里 `if proc is not None` 不成立，
        # Chrome 就成了没人回收的孤儿进程。
        await _kill_chrome_tree(proc)
        raise
    logger.info("Chrome CDP已就绪: %s", cdp_url)
    return proc, cdp_url


async def _kill_chrome_tree(proc: asyncio.subprocess.Process) -> None:
    """结束 Chrome 及其全部子进程。

    Chrome 会 fork 出 renderer / gpu / zygote 等一堆子进程，只 terminate 主进程
    的话它们在 Linux 上会被 reparent 到 init 继续跑，反复运行就攒成一片孤儿。
    browser-use 自己也不做进程组清理（读过 0.12.7 源码，它同样是裸 terminate），
    而且我们传的是 cdp_url、Chrome 由本进程启动，它根本不持有这个进程 ——
    所以这件事只能由我们负责。
    """
    if proc is None or proc.returncode is not None:
        return

    # Windows 上没有 SIGKILL（signal 模块只提供 SIGTERM/SIGINT/SIGBREAK 等），
    # 所以这里不能按信号名遍历 —— 那样在 Windows 上会直接 AttributeError。
    # 按平台给出「先礼后兵」的两级动作。
    posix = os.name == "posix"
    escalation = (
        [("SIGTERM", signal.SIGTERM), ("SIGKILL", signal.SIGKILL)]
        if posix else [("terminate", None), ("kill", None)]
    )

    for kind, sig in escalation:
        try:
            if posix:
                os.killpg(os.getpgid(proc.pid), sig)
            elif kind == "terminate":
                proc.terminate()
            else:
                proc.kill()
            await asyncio.wait_for(proc.wait(), timeout=5)
            return
        except Exception:
            continue


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class ChromeStartupError(RuntimeError):
    """Chrome 没能在限期内就绪。

    刻意用自定义异常而不是内建 TimeoutError：Python 3.11 起
    `asyncio.TimeoutError is TimeoutError`（内建），所以裸抛 TimeoutError 会被
    外层 `except asyncio.TimeoutError` 当成"任务跑了 10 分钟"接住 ——
    30 秒的启动失败会被报成 10 分钟超时，用户拿到的信息完全是错的。
    """


async def _wait_for_cdp(port: int, timeout: float = CDP_READY_TIMEOUT) -> str:
    loop = asyncio.get_running_loop()
    start = loop.time()
    async with aiohttp.ClientSession() as session:
        while loop.time() - start < timeout:
            with suppress(Exception):
                async with session.get(f"http://127.0.0.1:{port}/json/version") as resp:
                    if resp.status == 200:
                        return f"http://127.0.0.1:{port}/"
            await asyncio.sleep(0.2)
    raise ChromeStartupError(
        f"Chrome 在 {timeout}s 内未就绪（CDP 端口 {port} 无响应）。"
        f"常见原因：浏览器未能启动、用户目录被另一个实例占用、或依赖缺失。"
        f"详见 logs/chrome.log"
    )


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


def _busy_result() -> dict[str, Any]:
    """已有任务在跑时的返回。明确拒绝，而不是排队等十分钟或让两个 Chrome 抢目录。"""
    return {
        "success": False,
        "final_result": "已有 Agent 任务正在执行，请等待它结束后再试。",
        "total_steps": 0,
        "duration_seconds": 0,
        "screenshots": [],
        "visited_urls": [],
        "errors": ["并发受限：同一时刻只允许一个 Agent 任务"],
    }


async def execute_agent(instruction: str, max_steps: int) -> dict[str, Any]:
    # 非阻塞抢锁：抢不到就直接告诉用户，不要排队 —— 排在后面的请求会等满
    # 10 分钟，而 Chrome 的单实例锁会让它们本来也起不来。
    if _agent_lock.locked():
        logger.warning("已有 Agent 任务在运行，拒绝并发请求")
        return _busy_result()

    async with _agent_lock:
        return await _execute_locked(instruction, max_steps)


async def _execute_locked(instruction: str, max_steps: int) -> dict[str, Any]:
    task = AGENT_SYSTEM_CONTEXT.format(frontend_url=AGENT_FRONTEND_URL)
    task += f"\n\n用户任务:\n{instruction}"

    proc = None
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

        agent = Agent(
            task=task,
            llm=llm,
            fallback_llm=fallback_llm,
            browser_profile=browser_profile,
            # 收窄工具集：默认工具里的 evaluate 能执行任意 JS，而 localStorage 里
            # 躺着管理员 JWT，两者相遇就是一条令牌外发的通路。详见
            # AGENT_EXCLUDED_TOOLS 的说明。
            tools=Tools(exclude_actions=AGENT_EXCLUDED_TOOLS),
            use_vision=True,
            flash_mode=False,
            max_failures=3,
            max_actions_per_step=5,
            step_timeout=180,
            # 本服务跑在 uvicorn 里，信号由 uvicorn 管理。browser-use 默认会接管
            # SIGINT/SIGTERM，Windows 上它的处理是 os._exit(0) —— 直接把进程干掉、
            # 不清任何资源，容器里表现为 docker stop 时状态异常。
            enable_signal_handler=False,
        )

        logger.info("Agent开始执行: max_steps=%d", max_steps)

        history = await asyncio.wait_for(
            agent.run(max_steps=max_steps),
            timeout=AGENT_RUN_TIMEOUT,
        )

        # 用 n_last=5 让库只读最后 5 张；不传参会把全部步数的截图都读盘并
        # base64 编码一遍（max_steps 可到 100），然后我们只留 5 张。
        screenshots = history.screenshots(n_last=5) or []
        valid_screenshots = [s for s in screenshots if s is not None]

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
        }

    except ChromeStartupError as exc:
        # 与"任务跑太久"区分开：这是浏览器根本没起来，用户该查环境而不是简化指令
        logger.error("Chrome 启动失败: %s", exc)
        return {
            "success": False,
            "final_result": str(exc),
            "total_steps": 0,
            "duration_seconds": 0,
            "screenshots": [],
            "visited_urls": [],
            "errors": [str(exc)],
        }
    except asyncio.TimeoutError:
        minutes = AGENT_RUN_TIMEOUT // 60
        logger.warning("Agent执行超时 (%ds)", AGENT_RUN_TIMEOUT)
        return {
            "success": False,
            "final_result": f"执行超时，Agent 未能在 {minutes} 分钟内完成任务。请尝试简化指令。",
            "total_steps": 0,
            "duration_seconds": AGENT_RUN_TIMEOUT,
            "screenshots": [],
            "visited_urls": [],
            "errors": [f"任务执行超时 ({AGENT_RUN_TIMEOUT}s)"],
        }
    finally:
        await _kill_chrome_tree(proc)
        logger.info("Chrome进程已终止")
