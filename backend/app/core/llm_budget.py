"""LLM 每日调用预算 —— 失控代码的最后一层闸。

## 为什么需要

这个项目的 LLM key 与开发者的 Claude Code **共用同一份额度**。
服务里已经有三重防护，但都是**按请求**的：

    单请求超时       ai_service 90s / tool_agent_service 120s
    循环轮次上限     MAX_TOOL_ROUNDS=8 / browser_use 的 max_steps
    端点限流         AI 5~10 次/分钟、Agent 3 次/分钟

限流是**按分钟**的：3 次/分钟 × 60 × 24 ≈ 一天 4000 次。
一个每 20 秒发一次的循环（比如前端轮询写错、Agent 没收敛）在限流放开后
能安静地跑一整天，而且**不会有任何报错** —— 直到额度见底。

这里加一道按天累计的闸，超了直接拒绝，报错信息明确指向预算，
而不是等下游给出一个看不懂的 401/429。

## 局限（知道就好，别当精确计费）

- 计数器在**进程内存**里：重启归零，多 worker 时每个进程各算一份。
  对单进程部署足够；要做精确计费得落库。
- 统计的是**调用次数**，不是 token 数。够用，而且不需要解析各家
  服务商不同的 usage 字段。
"""

import logging
import threading
from datetime import date

from backend.app.core.config import LLM_DAILY_CALL_LIMIT

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_day: date | None = None
_count = 0
_warned = False

# 用掉多少比例时提醒一次（只在跨过阈值时打一条日志，不重复刷屏）
_WARN_AT = 0.8


class LLMBudgetExceeded(RuntimeError):
    """当日 LLM 调用预算用尽。

    刻意继承 RuntimeError：各调用点已有的 `except Exception` 兜底能接住它，
    不会因为引入这个闸而冒出未处理异常。
    """


def spend(n: int = 1) -> None:
    """记一次 LLM 调用。超出当日预算时抛 LLMBudgetExceeded。

    在**真正发请求之前**调用 —— 超预算的那一次不该被发出去。

    :param n: 本次消耗的次数（一次请求含多轮时传轮数）
    :raises LLMBudgetExceeded: 超出 LLM_DAILY_CALL_LIMIT
    """
    global _day, _count, _warned

    if LLM_DAILY_CALL_LIMIT <= 0:
        return

    with _lock:
        today = date.today()
        if _day != today:
            if _day is not None:
                logger.info("LLM 调用预算：跨天重置（昨日用掉 %d 次）", _count)
            _day = today
            _count = 0
            _warned = False

        if _count + n > LLM_DAILY_CALL_LIMIT:
            raise LLMBudgetExceeded(
                f"已达当日 LLM 调用上限（{LLM_DAILY_CALL_LIMIT} 次）。"
                f"这通常意味着有代码在循环调用 —— 请先排查，"
                f"确需放宽可调大环境变量 LLM_DAILY_CALL_LIMIT，设为 0 则关闭此限制。"
            )

        _count += n
        if not _warned and _count >= LLM_DAILY_CALL_LIMIT * _WARN_AT:
            _warned = True
            logger.warning(
                "LLM 调用已达当日预算的 %d%%（%d/%d）",
                int(_count / LLM_DAILY_CALL_LIMIT * 100), _count, LLM_DAILY_CALL_LIMIT,
            )


def usage() -> dict:
    """当前用量，供系统状态页或排查时查看。"""
    with _lock:
        return {
            "date": str(_day) if _day else None,
            "used": _count,
            "limit": LLM_DAILY_CALL_LIMIT,
            "remaining": max(0, LLM_DAILY_CALL_LIMIT - _count) if LLM_DAILY_CALL_LIMIT > 0 else None,
        }
