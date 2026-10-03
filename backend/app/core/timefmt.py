"""时间的对外表示。

库里存的是 **UTC 的 naive datetime**，而使用者都在国内。直接 strftime 会显示
早 8 小时的时间 —— 不是「换个域名才触发」的潜在风险，而是每次请求都在发生的
用户可见不一致。

此前这段换算只写在 history.py 里（私有函数 `_to_local`），compare / admin /
auth 各自直接 strftime，于是同一个系统里不同页面的时间差 8 小时。此处收成一份，
新端点一律用它，不要再各写一遍。
"""
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))


def to_local(dt: datetime | None, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """UTC → 东八区字符串，默认 "YYYY-MM-DD HH:MM:SS"。

    fmt 可换（个人中心用的是不带秒的 "YYYY-MM-DD HH:MM"）—— 保留调用方既有的
    输出格式，免得把「修时区」顺手变成「改格式」。

    naive datetime 一律**视为 UTC**（库里的写入方都是这么存的）；空值返回 "",
    与结果 URL 的空值约定一致 —— 对外表示里不出现 null。
    """
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CST).strftime(fmt)
