"""游客免费额度的服务端实现。

额度此前完全由前端 localStorage 维护：清一下缓存就归零，直接打接口更是
一次都拦不住。这里把计数搬到服务端，前端显示的数字改成由接口返回。

两条刻意的选择：

1. **按 IP 按天**，不是按生命周期。一间教室或一个办公室常常共用一个出口
   IP，永久计数会让后来的人一次都试不了。代价是按天重置后同一个人第二天
   还能再试 —— 这本来就是这个额度的定位：让人试试，不是防刷的主要手段
   （防刷靠的是 /detect 上已有的每分钟限流）。
2. **只对游客计数**，登录用户不经过这里。

一个已知的副作用：取的是 `request.client.host`。将来若在 uvicorn 前面加了
反向代理，这里拿到的会是代理的地址，所有人都共享一个额度 —— 那时需要改成
从 X-Forwarded-For 取，并只信任受控代理。
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.core.config import GUEST_DAILY_QUOTA
from backend.app.core.timefmt import CST
from backend.app.models.guest_usage import GuestUsageDB

logger = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(CST).strftime("%Y-%m-%d")


def remaining(db: Session, ip: str) -> int:
    if GUEST_DAILY_QUOTA <= 0:
        return 999
    row = db.query(GuestUsageDB).filter_by(ip=ip, day=_today()).first()
    return max(0, GUEST_DAILY_QUOTA - (row.used if row else 0))


def consume(db: Session, ip: str) -> int | None:
    """扣一次额度，返回扣完还剩几次；额度已用完返回 None。

    计数在**检测成功之后**才调用 —— 请求失败（图片损坏、模型不可用）不该
    消耗用户的免费次数。
    """
    if GUEST_DAILY_QUOTA <= 0:
        return 999  # 0 表示不限制，与 LLM_DAILY_CALL_LIMIT 的约定一致

    day = _today()
    row = db.query(GuestUsageDB).filter_by(ip=ip, day=day).first()
    if row is None:
        row = GuestUsageDB(ip=ip, day=day, used=0)
        db.add(row)

    if row.used >= GUEST_DAILY_QUOTA:
        db.rollback()
        return None

    row.used += 1
    # 顺手清掉两天前的行，避免这张表无限增长。只在「今天这个 IP 的第一次」
    # 触发 —— 每打一次检测扫一次全表不值当，这个清理也不要求精确。
    if row.used == 1:
        cutoff = (datetime.now(CST) - timedelta(days=2)).strftime("%Y-%m-%d")
        db.query(GuestUsageDB).filter(GuestUsageDB.day < cutoff).delete(
            synchronize_session=False
        )
    db.commit()
    logger.info("游客额度: ip=%s day=%s used=%s/%s", ip, day, row.used, GUEST_DAILY_QUOTA)
    return max(0, GUEST_DAILY_QUOTA - row.used)
